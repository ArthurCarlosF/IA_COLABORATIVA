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
from pydantic import BaseModel,Field,ValidationError,ConfigDict
from transformers import AutoTokenizer
from .ledger import Ledger
from .credits import Wallet,InsufficientCredits
from .protocol import authenticated,encode,headers,unpack

class Chat(BaseModel):
    model_config=ConfigDict(extra='forbid')
    prompt:str=Field(min_length=1,max_length=4096)
    max_tokens:int=Field(default=32,ge=1,le=128)

def create_coordinator(root,secret,user_token,allowed,db_path,verify=True,accounts=None,worker_owners=None,daily_tokens=20000,credit_timezone='America/Sao_Paulo'):
    root=Path(root)
    manifest=json.loads((root/'manifest.json').read_text())
    tokenizer=AutoTokenizer.from_pretrained(root/'tokenizer',local_files_only=True)
    if len(allowed)!=len(manifest['parts']):
        raise ValueError('Configure exatamente um worker por partição')
    assignments={worker_id:manifest['parts'][i] for i,worker_id in enumerate(allowed)}
    nodes={}
    gate=asyncio.Lock()
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
    metrics=dict(requests=0,failures=0,tokens=0,last_seconds=0,tokens_per_second=0)
    fingerprints={s['index']:hashlib.sha256((root/f"part-{s['index']}"/'weights.pt').read_bytes()).hexdigest() for s in manifest['parts']}
    client=httpx.AsyncClient(timeout=20,verify=verify,trust_env=False)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await client.aclose()
    app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
    app.state.ledger=ledger
    app.state.wallet=wallet

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
        response=await client.post(node['url']+path,content=body,headers=headers(secret,body))
        response.raise_for_status()
        return response.json()

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
        return dict(model=manifest['model'],revision=manifest['revision'],nodes=rows,metrics=metrics,busy=gate.locked(),required_parts=len(manifest['parts']),assignments=assignments,ledger_valid=ledger.verify(),usage=wallet.snapshot(user))

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

    @app.post('/api/chat')
    async def chat(request:Request):
        user=auth(request)
        if request.headers.get('content-length') and int(request.headers['content-length'])>20000:
            raise HTTPException(413,'Mensagem muito longa')
        size=0
        chunks=[]
        async for chunk in request.stream():
            size+=len(chunk)
            if size>20000:
                raise HTTPException(413,'Mensagem muito longa')
            chunks.append(chunk)
        try:
            query=Chat.model_validate_json(b''.join(chunks))
        except ValidationError:
            raise HTTPException(422,'Prompt ou limite de tokens inválido')
        if gate.locked():
            raise HTTPException(429,'Inferência ocupada; aguarde')
        await gate.acquire()
        pipeline=sorted([dict(n) for n in nodes.values() if time.monotonic()-n['seen']<8],key=lambda n:n['spec']['index'])
        if [n['spec']['index'] for n in pipeline]!=list(range(len(manifest['parts']))):
            gate.release()
            raise HTTPException(503,'Conecte todos os workers necessários')
        ids=tokenizer.encode(query.prompt)
        if len(ids)+query.max_tokens>512:
            gate.release()
            raise HTTPException(422,'Contexto máximo: 512 tokens incluindo resposta')
        sid=uuid.uuid4().hex
        try:
            output_budget=wallet.reserve(sid,user,len(ids),query.max_tokens)
        except InsufficientCredits as exc:
            gate.release()
            raise HTTPException(402,dict(code='insufficient_tokens',message=str(exc),usage=wallet.snapshot(user)))
        except Exception:
            gate.release()
            raise

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
                    completed=[]
                    for node in pipeline:
                        reply=await rpc(node,'/step',dict(session=sid,position=position,tensor=value))
                        expected=position+length
                        if reply['position']!=expected or reply['units']!=length*(node['spec']['end']-node['spec']['start']):
                            raise ValueError('Resposta inconsistente do worker')
                        if not isinstance(reply.get('seconds'),(float,int)) or not math.isfinite(reply['seconds']) or reply['seconds']<0:
                            raise ValueError('Duração inválida do worker')
                        completed.append((node,reply))
                        value=reply['tensor']
                    logits=unpack(value)
                    if list(logits.shape)!=[1,1,tokenizer.vocab_size]:raise ValueError('Logits inválidos')
                    cost=len(ids)+1 if iteration==0 else 1
                    wallet.settle(sid,iteration,cost,[dict(id=node['id'],owner=owners[node['id']],layers=node['spec']['end']-node['spec']['start'],input_tokens=length) for node,_ in completed])
                    for node,reply in completed:
                        ledger.append(f"{sid}:{iteration}:{node['id']}",user,node['id'],reply['units'],reply['seconds'])
                    token=int(logits[0,-1].argmax())
                    if token==tokenizer.eos_token_id:
                        break
                    generated.append(token)
                    text=tokenizer.decode(generated,skip_special_tokens=True)
                    count+=1
                    metrics['tokens']+=1
                    yield 'data: '+json.dumps(dict(type='token',text=text,token=token,usage=wallet.snapshot(user)),ensure_ascii=False)+'\n\n'
                    position+=length
                    value=pack(torch.tensor([[token]],dtype=torch.long))
                elapsed=time.perf_counter()-started
                metrics.update(last_seconds=elapsed,tokens_per_second=count/max(elapsed,1e-9))
                wallet.release(sid)
                yield 'data: '+json.dumps(dict(type='done',tokens=count,seconds=elapsed,session=sid,input_tokens=len(ids),output_budget=output_budget,usage=wallet.snapshot(user)))+'\n\n'
            except (httpx.HTTPError,ValueError,KeyError,RuntimeError) as exc:
                metrics['failures']+=1
                yield 'data: '+json.dumps(dict(type='error',message='Falha no worker; geração interrompida. '+type(exc).__name__))+'\n\n'
            finally:
                try:
                    with anyio.CancelScope(shield=True):
                        await asyncio.gather(*(rpc(n,'/release',dict(session=sid)) for n in pipeline),return_exceptions=True)
                finally:
                    try:
                        wallet.release(sid)
                    finally:
                        gate.release()
        return StreamingResponse(generate(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no'})
    return app
