import asyncio
import anyio
import hashlib
import hmac
import json
import re
import math
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
import httpx
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import HTMLResponse,StreamingResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel,Field,ValidationError,ConfigDict
from transformers import AutoTokenizer
from .ledger import Ledger
from .credits import Wallet,InsufficientCredits
from .scheduler import FairScheduler,CapacityError
from .identity import signed_headers,verify_sender,verify_result,peer_for_endpoint
from .protocol import authenticated,encode,headers,unpack,checkpoint_hash

class Chat(BaseModel):
    model_config=ConfigDict(extra='forbid')
    prompt:str=Field(min_length=1,max_length=32768)
    max_tokens:int=Field(default=32,ge=1,le=1024)
    model:str|None=None
    system:str=Field(default="",max_length=12000)

def create_coordinator(root,secret,user_token,allowed,db_path,verify=True,accounts=None,worker_owners=None,daily_tokens=20000,credit_timezone='America/Sao_Paulo',peer_network=None,coordinator_url=None,workspace_root='runtime/workspaces',sandbox_image=None,allow_host_commands=False):
    catalog=Path(db_path).parent/'model-catalog';catalog.mkdir(parents=True,exist_ok=True)
    selection=catalog/'current.json'
    if selection.exists():
        saved=Path(json.loads(selection.read_text())['root']).resolve()
        if not saved.is_relative_to(catalog.resolve()):raise ValueError('Invalid saved model metadata')
        root=saved
    root=Path(root)
    manifest=json.loads((root/'manifest.json').read_text())
    tokenizer=AutoTokenizer.from_pretrained(root/'tokenizer',local_files_only=True)
    model_config=json.loads((root/'config.json').read_text())
    context_limit=min(4096,model_config.get('max_position_embeddings',4096)) if model_config.get('model_type')=='qwen2' else 512
    output_limit=512 if model_config.get('model_type')=='qwen2' else 128
    if len(allowed)!=len(manifest['parts']):
        raise ValueError('Configure exatamente um worker por partição')
    assignments={worker_id:manifest['parts'][i] for i,worker_id in enumerate(allowed)}
    nodes={}
    scheduler=FairScheduler()
    identities={'local-user':user_token,**(accounts or {})}
    if any(not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',user) or not isinstance(token,str) or len(token)<32 for user,token in identities.items()):
        raise ValueError('Identidades ou tokens inválidos')
    if len(set(identities.values()))!=len(identities):raise ValueError('Cada conta exige token exclusivo')
    token_hashes={user:hashlib.sha256(token.encode()).digest() for user,token in identities.items()}
    owners={worker:'local-user' for worker in allowed}
    if worker_owners:
        if set(worker_owners)-set(allowed):raise ValueError('Proprietário de worker desconhecido')
        owners.update(worker_owners)
    if any(owner not in identities for owner in owners.values()):raise ValueError('Proprietário deve ter identidade configurada')
    ledger=Ledger(db_path)
    wallet=Wallet(ledger,daily_tokens,credit_timezone)
    wallet.recover()
    metrics=dict(requests=0,failures=0,tokens=0,last_seconds=0,tokens_per_second=0,network_retries=0)
    from .partition_store import digest
    fingerprints={s['index']:(digest(manifest['bundles'][s['index']]) if manifest.get('format')=='range-f32-v1' else checkpoint_hash(root/f"part-{s['index']}"/'weights.pt')) for s in manifest['parts']}
    client=httpx.AsyncClient(timeout=20,verify=verify,trust_env=False,limits=httpx.Limits(keepalive_expiry=1))

    identity=json.loads(Path(peer_network['identity_files']['coordinator']).read_text()) if peer_network else None
    gossip=None

    agent=None
    model_control=None
    @asynccontextmanager
    async def lifespan(app):
        if gossip:gossip.start()
        yield
        if model_control:await model_control.close()
        if agent:await agent.close()
        if gossip:gossip.close()
        await client.aclose()
    app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
    if peer_network:
        from .discovery import attach
        gossip=attach(app,peer_network['identity_files']['coordinator'],coordinator_url,peer_network['trusted'],peer_network.get('seeds',[]),dict(role='requester',model=manifest['model'],revision=manifest['revision']),verify,Path(db_path).parent/'peers.json')
    from .workspace import Workspace,RevisionConflict
    workspace=Workspace(workspace_root)
    test_gate=asyncio.Semaphore(1)
    app.state.ledger=ledger
    app.state.wallet=wallet
    app.state.rpc_client=client

    def auth(request):
        value=request.headers.get('authorization','')
        if not value.startswith('Bearer '):raise HTTPException(401,'Autenticação necessária')
        digest=hashlib.sha256(value[7:].encode()).digest()
        matched=None
        for user,expected in token_hashes.items():
            if hmac.compare_digest(digest,expected):matched=user
        if matched is None:raise HTTPException(401,'Autenticação necessária')
        return matched

    async def rpc(node,path,message):
        body=encode(message)
        for attempt in range(2):
            try:
                response=await client.post(node['url']+path,content=body,headers=signed_headers(secret,body,path,identity),timeout=600 if path in ('/model/commit','/model/rollback') else 20)
                response.raise_for_status()
                result=response.json()
                if peer_network and path=='/step':
                    try:verify_result(result,message,peer_for_endpoint(peer_network['trusted'],node['url']))
                    except Exception:raise ValueError('Recibo individual do worker inválido')
                return result
            except (httpx.RemoteProtocolError,httpx.ReadError,httpx.ConnectError,httpx.ReadTimeout):
                if attempt:raise
                metrics['network_retries']+=1
                # O worker aceita somente repetição idêntica do último passo.
                # Nova assinatura temporal, mesmo corpo: sem novo cálculo ou débito.

    class SecurityHeaders:
        def __init__(self,app):
            self.app=app
        async def __call__(self,scope,receive,send):
            async def secure_send(message):
                if message['type']=='http.response.start':
                    message['headers']=list(message.get('headers',[]))+[
                        (b'x-content-type-options',b'nosniff'),
                        (b'content-security-policy',b"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"),
                        (b'cache-control',b'no-store')]
                await send(message)
            await self.app(scope,receive,secure_send)
    app.add_middleware(SecurityHeaders)

    @app.get('/')
    async def home():
        return HTMLResponse((Path(__file__).parent/'web.html').read_text(encoding='utf8'))

    @app.post('/internal/register')
    async def register(request:Request):
        message=await authenticated(request,secret)
        try:
            worker_id=message['id']
            index=message['spec']['index']
            if allowed.get(worker_id)!=message['url']:
                raise HTTPException(403,'Worker ou endereço não permitido')
            if peer_network:
                try:verify_sender(request,message,peer_for_endpoint(peer_network['trusted'],message['url']))
                except Exception:raise HTTPException(401,'Assinatura individual do worker inválida')
            if type(index) is not int or index<0 or index>=len(manifest['parts']):
                raise ValueError('Invalid partition')
            if message['spec']!=assignments[worker_id]:
                raise HTTPException(409,'Partição diferente da atribuída pelo coordenador')
            if message['spec']!=manifest['parts'][index] or message['fingerprint']!=fingerprints[index]:
                raise HTTPException(409,'Checkpoint ou partição incorreta')
            if any(n['spec']['index']==index and key!=worker_id and time.monotonic()-n['seen']<8 for key,n in nodes.items()):
                raise HTTPException(409,'Partição já ocupada')
            nodes[worker_id]=dict(message,seen=time.monotonic())
            return {'ok':True}
        except (KeyError,TypeError,ValueError) as exc:
            raise HTTPException(422,str(exc))

    @app.get('/api/status')
    async def status(request:Request):
        user=auth(request)
        rows=[dict(id=k,url=n['url'],spec=n['spec'],resources=n['resources'],online=time.monotonic()-n['seen']<8) for k,n in nodes.items()]
        return dict(model=manifest['model'],revision=manifest['revision'],nodes=rows,metrics=metrics,busy=bool(scheduler.active),scheduler=scheduler.status(),required_parts=len(manifest['parts']),assignments=assignments,ledger_valid=ledger.verify(),usage=wallet.snapshot(user),context_limit=context_limit,output_limit=output_limit)

    @app.get('/api/usage')
    async def usage(request:Request):
        return wallet.snapshot(auth(request))

    @app.get('/api/credits')
    async def credits(request:Request):
        user=auth(request)
        # Legacy token-layer receipts remain diagnostic; wallet events are authoritative.
        entries=[e for e in ledger.export() if e['event']['user']==user or owners.get(e['event']['worker'])==user]
        audit=wallet.audit(user)
        return dict(valid=ledger.verify() and audit['valid'],entries=entries,unit='token-layer',payments=False,
                    usage=wallet.snapshot(user),wallet=audit)

    @app.get('/api/peers')
    async def peers(request:Request):
        auth(request)
        if not gossip:return dict(mode='disabled',records=[])
        return dict(mode='signed-permissioned-gossip',records=gossip.directory.snapshot(),stats=gossip.directory.stats)

    @app.get('/api/workspace/files')
    async def files(request:Request):
        return dict(files=workspace.listing(auth(request)),container_tests=bool(sandbox_image))

    @app.get('/api/workspace/file')
    async def read_file(request:Request,path:str):
        user=auth(request)
        try:return workspace.read(user,path)
        except FileNotFoundError:raise HTTPException(404,'Arquivo não encontrado')
        except ValueError as exc:raise HTTPException(422,str(exc))

    async def bounded_json(request,limit=800000):
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>limit:raise HTTPException(413,'Mensagem excede limite')
        try:data=json.loads(body)
        except ValueError:raise HTTPException(422,'JSON inválido')
        if not isinstance(data,dict):raise HTTPException(422,'Esperado objeto JSON')
        return data

    @app.post('/api/workspace/file')
    async def save_file(request:Request):
        user=auth(request)
        data=await bounded_json(request)
        if not isinstance(data,dict) or set(data)-{'path','content','base_revision'}:raise HTTPException(422,'Campos inválidos')
        try:return workspace.write(user,data['path'],data['content'],data.get('base_revision'))
        except RevisionConflict as exc:raise HTTPException(409,str(exc))
        except (KeyError,ValueError) as exc:raise HTTPException(422,str(exc))

    @app.post('/api/workspace/check')
    async def check_file(request:Request):
        user=auth(request)
        data=await bounded_json(request,4096)
        try:return workspace.check(user,data['path'])
        except FileNotFoundError:raise HTTPException(404,'Arquivo não encontrado')
        except (KeyError,ValueError,TypeError) as exc:raise HTTPException(422,str(exc))

    @app.post('/api/workspace/tests')
    async def run_tests(request:Request):
        user=auth(request)
        if not sandbox_image:raise HTTPException(503,'Testes em container desativados; configure sandbox_image com imagem local aprovada')
        if test_gate.locked():raise HTTPException(429,'Executor de testes ocupado')
        async with test_gate:
            try:return await asyncio.to_thread(workspace.run_tests,user,sandbox_image)
            except (ValueError,RuntimeError) as exc:raise HTTPException(503,str(exc))

    @app.post('/api/chat')
    async def chat(request:Request):
        user=auth(request)
        if request.headers.get('content-length') and int(request.headers['content-length'])>160000:
            raise HTTPException(413,'Mensagem muito longa')
        size=0
        chunks=[]
        async for chunk in request.stream():
            size+=len(chunk)
            if size>160000:
                raise HTTPException(413,'Mensagem muito longa')
            chunks.append(chunk)
        try:
            query=Chat.model_validate_json(b''.join(chunks))
        except ValidationError:
            raise HTTPException(422,'Prompt ou limite de tokens inválido')
        sid=uuid.uuid4().hex
        if query.model is not None and query.model!=manifest['model']:raise HTTPException(409,'Modelo não está carregado neste cluster')
        if model_control and model_control.busy:raise HTTPException(503,'Troca de modelo em andamento')
        try:scheduler.admit(user,sid)
        except CapacityError as exc:raise HTTPException(429,str(exc))
        pipeline=sorted([dict(n) for n in nodes.values() if time.monotonic()-n['seen']<8],key=lambda n:n['spec']['index'])
        if [n['spec']['index'] for n in pipeline]!=list(range(len(manifest['parts']))):
            scheduler.leave(user,sid)
            raise HTTPException(503,'Conecte todos os workers necessários')
        messages=([dict(role='system',content=query.system)] if query.system else [])+[dict(role='user',content=query.prompt)]
        ids=tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True) if tokenizer.chat_template else tokenizer.encode(query.system+'\n'+query.prompt if query.system else query.prompt)
        if query.max_tokens>output_limit or len(ids)+query.max_tokens>context_limit:
            scheduler.leave(user,sid)
            raise HTTPException(422,f'Contexto máximo: {context_limit} tokens incluindo resposta; saída até {output_limit}')
        try:
            output_budget=wallet.reserve(sid,user,len(ids),query.max_tokens)
        except InsufficientCredits as exc:
            scheduler.leave(user,sid)
            raise HTTPException(402,dict(code='insufficient_tokens',message=str(exc),usage=wallet.snapshot(user)))
        except Exception:
            scheduler.leave(user,sid)
            raise

        cleanup_done=False
        async def finish():
            nonlocal cleanup_done
            if cleanup_done:return
            cleanup_done=True
            try:
                with anyio.CancelScope(shield=True):
                    await asyncio.gather(*(rpc(n,'/release',dict(session=sid)) for n in pipeline),return_exceptions=True)
            finally:
                try:wallet.release(sid)
                finally:scheduler.leave(user,sid)

        async def generate():
            import torch
            from .protocol import pack
            started=time.perf_counter()
            count=0
            metrics['requests']+=1
            position=0
            value=pack(torch.tensor([ids],dtype=torch.long))
            generated=[]
            text=''
            try:
                for iteration in range(output_budget):
                    if await request.is_disconnected():
                        break
                    length=value['shape'][1]
                    # Prefill em fatias limita o tempo exclusivo de uma entrada grande.
                    input_ids=ids if iteration==0 else [generated[-1]]
                    chunks=[input_ids[i:i+32] for i in range(0,len(input_ids),32)]
                    total_units={node['id']:0 for node in pipeline}
                    total_seconds={node['id']:0.0 for node in pipeline}
                    proofs={node['id']:[] for node in pipeline}
                    for chunk in chunks:
                        async with scheduler.turn(user,request.is_disconnected):
                            if await request.is_disconnected():raise asyncio.CancelledError()
                            value=pack(torch.tensor([chunk],dtype=torch.long))
                            for node in pipeline:
                                reply=await rpc(node,'/step',dict(session=sid,position=position,tensor=value,model_fingerprint=fingerprints[node['spec']['index']]))
                                expected=position+len(chunk)
                                if reply['position']!=expected or reply['units']!=len(chunk)*(node['spec']['end']-node['spec']['start']):
                                    raise ValueError('Resposta inconsistente do worker')
                                if not isinstance(reply.get('seconds'),(float,int)) or not math.isfinite(reply['seconds']) or reply['seconds']<0:
                                    raise ValueError('Duração inválida do worker')
                                if reply.get('proof'):proofs[node['id']].append(reply['proof'])
                                total_units[node['id']]+=reply['units']
                                total_seconds[node['id']]+=reply['seconds']
                                value=reply['tensor']
                            position+=len(chunk)
                    completed=[(node,dict(units=total_units[node['id']],seconds=total_seconds[node['id']],proofs=proofs[node['id']])) for node in pipeline]
                    logits=unpack(value)
                    if list(logits.shape)!=[1,1,manifest.get('vocab_size',tokenizer.vocab_size)]:raise ValueError('Logits inválidos')
                    cost=len(ids)+1 if iteration==0 else 1
                    wallet.settle(sid,iteration,cost,[dict(id=node['id'],owner=owners[node['id']],layers=node['spec']['end']-node['spec']['start'],input_tokens=length,receipts=reply['proofs']) for node,reply in completed])
                    for node,reply in completed:
                        ledger.append(f"{sid}:{iteration}:{node['id']}",user,node['id'],reply['units'],reply['seconds'],proof=reply['proofs'])
                    token=int(logits[0,-1].argmax())
                    if token==tokenizer.eos_token_id:
                        break
                    generated.append(token)
                    text=tokenizer.decode(generated,skip_special_tokens=True)
                    count+=1
                    metrics['tokens']+=1
                    yield 'data: '+json.dumps(dict(type='token',text=text,token=token,usage=wallet.snapshot(user)),ensure_ascii=False)+'\n\n'
                    value=pack(torch.tensor([[token]],dtype=torch.long))
                elapsed=time.perf_counter()-started
                metrics.update(last_seconds=elapsed,tokens_per_second=count/max(elapsed,1e-9))
                wallet.release(sid)
                yield 'data: '+json.dumps(dict(type='done',tokens=count,seconds=elapsed,session=sid,input_tokens=len(ids),output_budget=output_budget,usage=wallet.snapshot(user)))+'\n\n'
            except (httpx.HTTPError,ValueError,KeyError,RuntimeError) as exc:
                metrics['failures']+=1
                yield 'data: '+json.dumps(dict(type='error',message='Falha no worker; geração interrompida. '+type(exc).__name__))+'\n\n'
            finally:
                await finish()
        return StreamingResponse(generate(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no'},background=BackgroundTask(finish))
    from .agent import AgentStore,AgentManager,TOOLS
    agent_store=AgentStore(Path(db_path).parent/'agents.sqlite')

    async def agent_infer(authorization,prompt,max_tokens):
        # Same admission, wallet, activation RPC and cancellation as the public chat.
        system=TOOLS if prompt.startswith(TOOLS) else ''
        if system:prompt=prompt[len(TOOLS):]
        def count(text):
            messages=([dict(role='system',content=system)] if system else [])+[dict(role='user',content=text)]
            return len(tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True) if tokenizer.chat_template else tokenizer.encode(system+text))
        if count(prompt)+max_tokens>context_limit:
            raise ValueError('Contexto do agente excede o modelo; reduza tarefa/arquivos. Nenhuma instrução foi descartada.')
        body=encode(dict(prompt=prompt,system=system,max_tokens=min(max_tokens,output_limit),model=manifest['model']))
        consumed=False
        async def receive():
            nonlocal consumed
            if not consumed:
                consumed=True
                return dict(type='http.request',body=body,more_body=False)
            await asyncio.sleep(3600)
            return dict(type='http.disconnect')
        request=Request(dict(type='http',method='POST',path='/api/chat',headers=[(b'authorization',authorization.encode())],query_string=b'',client=('127.0.0.1',0)),receive)
        response=await chat(request)
        text='';done=False
        try:
            async for chunk in response.body_iterator:
                if isinstance(chunk,bytes):chunk=chunk.decode()
                for item in chunk.split('\n\n'):
                    if not item.startswith('data: '):continue
                    data=json.loads(item[6:])
                    if data['type']=='error':raise RuntimeError(data['message'])
                    if data['type']=='token':text=data['text']
                    if data['type']=='done':done=True
        finally:
            await response.body_iterator.aclose()
            if response.background:await response.background()
        if not done:raise RuntimeError('Inferência interrompida')
        return text

    agent=AgentManager(agent_store,workspace,agent_infer,sandbox_image,allow_host_commands)
    app.state.agent=agent
    def local_operator(request):
        return bool(request.client and request.client.host in ('127.0.0.1','::1'))

    @app.get('/api/agent/runs')
    async def agent_runs(request:Request):
        user=auth(request)
        return dict(runs=agent_store.listing(user),host_commands=allow_host_commands and local_operator(request) and user=='local-user',max_steps=agent.max_steps)

    @app.post('/api/agent/runs')
    async def agent_start(request:Request):
        user=auth(request);data=await bounded_json(request,30000)
        if model_control and model_control.busy:raise HTTPException(503,'Troca de modelo em andamento')
        if set(data)-{'task','model'} or not isinstance(data.get('task'),str):raise HTTPException(422,'Informe task e modelo disponível')
        if data.get('model',manifest['model'])!=manifest['model']:raise HTTPException(409,'Modelo não carregado')
        try:
            run=agent.start(user,data['task'],request.headers['authorization'],local_operator(request))
            return agent_store.get(run,user)
        except ValueError as exc:raise HTTPException(409,str(exc))

    @app.get('/api/agent/runs/{run}')
    async def agent_detail(run:str,request:Request,after:int=0):
        user=auth(request)
        try:return dict(run=agent_store.get(run,user),events=agent_store.events(run,user,max(0,after)))
        except KeyError:raise HTTPException(404,'Tarefa não encontrada')

    @app.post('/api/agent/runs/{run}/cancel')
    async def agent_cancel(run:str,request:Request):
        try:agent.cancel(auth(request),run);return dict(ok=True)
        except KeyError:raise HTTPException(404,'Tarefa não encontrada')
        except ValueError as exc:raise HTTPException(409,str(exc))

    @app.post('/api/agent/runs/{run}/approve')
    async def agent_approve(run:str,request:Request):
        user=auth(request);data=await bounded_json(request,4000)
        if set(data)!={'id','approved'} or type(data['approved']) is not bool or not isinstance(data['id'],str):raise HTTPException(422,'Aprovação inválida')
        try:return agent.approve(user,run,data['id'],data['approved'],local_operator(request))
        except KeyError:raise HTTPException(404,'Tarefa não encontrada')
        except PermissionError as exc:raise HTTPException(403,str(exc))
        except ValueError as exc:raise HTTPException(409,str(exc))
    def current_model():return dict(root=root,manifest=manifest,fingerprints=dict(fingerprints))
    def apply_model(new_root):
        nonlocal root,manifest,tokenizer,model_config,context_limit,output_limit,assignments,fingerprints
        new_root=Path(new_root);new_manifest=json.loads((new_root/'manifest.json').read_text())
        if len(new_manifest['parts'])!=len(allowed):raise ValueError('Worker count changed')
        new_tokenizer=AutoTokenizer.from_pretrained(new_root/'tokenizer',local_files_only=True)
        new_config=json.loads((new_root/'config.json').read_text())
        new_fingerprints={part['index']:(digest(new_manifest['bundles'][part['index']]) if new_manifest.get('format')=='range-f32-v1' else checkpoint_hash(new_root/f"part-{part['index']}"/'weights.pt')) for part in new_manifest['parts']}
        root=new_root;manifest=new_manifest;tokenizer=new_tokenizer;model_config=new_config
        if gossip:gossip.directory.capability.update(model=manifest['model'],revision=manifest['revision'])
        fingerprints=new_fingerprints;assignments={key:manifest['parts'][i] for i,key in enumerate(allowed)}
        context_limit=min(4096,model_config.get('max_position_embeddings',4096)) if model_config.get('model_type')=='qwen2' else 512
        output_limit=512 if model_config.get('model_type')=='qwen2' else 128
    from .model_control import ModelControl
    model_control=ModelControl(app,auth,allowed,nodes,rpc,current_model,apply_model,catalog,lambda:not scheduler.active and not agent.active,lambda:(context_limit,output_limit))
    app.state.model_control=model_control
    return app
