import asyncio
import anyio
import hashlib
import hmac
import json
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
from .protocol import authenticated,encode,headers,unpack

class Chat(BaseModel):
    model_config=ConfigDict(extra='forbid')
    prompt:str=Field(min_length=1,max_length=4096)
    max_tokens:int=Field(default=32,ge=1,le=128)

def create_coordinator(root,secret,user_token,allowed,db_path,verify=True):
    root=Path(root)
    manifest=json.loads((root/'manifest.json').read_text())
    tokenizer=AutoTokenizer.from_pretrained(root/'tokenizer',local_files_only=True)
    if len(allowed)!=len(manifest['parts']):
        raise ValueError('Configure exatamente um worker por partição')
    assignments={worker_id:manifest['parts'][i] for i,worker_id in enumerate(allowed)}
    nodes={}
    gate=asyncio.Lock()
    ledger=Ledger(db_path)
    metrics=dict(requests=0,failures=0,tokens=0,last_seconds=0,tokens_per_second=0)
    fingerprints={s['index']:hashlib.sha256((root/f"part-{s['index']}"/'weights.pt').read_bytes()).hexdigest() for s in manifest['parts']}
    client=httpx.AsyncClient(timeout=20,verify=verify,trust_env=False)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await client.aclose()
    app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
    app.state.ledger=ledger

    def auth(request):
        token=request.headers.get('authorization','').removeprefix('Bearer ')
        if not hmac.compare_digest(token.encode(),user_token.encode()):
            raise HTTPException(401,'Autenticação necessária')

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
        auth(request)
        rows=[dict(id=k,url=n['url'],spec=n['spec'],resources=n['resources'],online=time.monotonic()-n['seen']<8) for k,n in nodes.items()]
        return dict(model=manifest['model'],revision=manifest['revision'],nodes=rows,metrics=metrics,busy=gate.locked(),required_parts=len(manifest['parts']),assignments=assignments,ledger_valid=ledger.verify())

    @app.get('/api/credits')
    async def credits(request:Request):
        auth(request)
        return dict(valid=ledger.verify(),entries=ledger.export(),unit='token-layer',payments=False)

    @app.post('/api/chat')
    async def chat(request:Request):
        auth(request)
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
                for iteration in range(query.max_tokens):
                    if await request.is_disconnected():
                        break
                    length=value['shape'][1]
                    for node in pipeline:
                        reply=await rpc(node,'/step',dict(session=sid,position=position,tensor=value))
                        expected=position+length
                        if reply['position']!=expected or reply['units']!=length*(node['spec']['end']-node['spec']['start']):
                            raise ValueError('Resposta inconsistente do worker')
                        ledger.append(f"{sid}:{iteration}:{node['id']}",'local-user',node['id'],reply['units'],reply['seconds'])
                        value=reply['tensor']
                    logits=unpack(value)
                    token=int(logits[0,-1].argmax())
                    if token==tokenizer.eos_token_id:
                        break
                    generated.append(token)
                    text=tokenizer.decode(generated,skip_special_tokens=True)
                    count+=1
                    metrics['tokens']+=1
                    yield 'data: '+json.dumps(dict(type='token',text=text,token=token),ensure_ascii=False)+'\n\n'
                    position+=length
                    value=pack(torch.tensor([[token]],dtype=torch.long))
                elapsed=time.perf_counter()-started
                metrics.update(last_seconds=elapsed,tokens_per_second=count/max(elapsed,1e-9))
                yield 'data: '+json.dumps(dict(type='done',tokens=count,seconds=elapsed,session=sid))+'\n\n'
            except (httpx.HTTPError,ValueError,KeyError,RuntimeError) as exc:
                metrics['failures']+=1
                yield 'data: '+json.dumps(dict(type='error',message='Falha no worker; geração interrompida. '+type(exc).__name__))+'\n\n'
            finally:
                try:
                    with anyio.CancelScope(shield=True):
                        await asyncio.gather(*(rpc(n,'/release',dict(session=sid)) for n in pipeline),return_exceptions=True)
                finally:
                    gate.release()
        return StreamingResponse(generate(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no'})
    return app
