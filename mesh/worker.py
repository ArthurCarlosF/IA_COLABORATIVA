import hashlib
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
import httpx
import psutil
import torch
from fastapi import FastAPI, HTTPException, Request
from .model import Shard
from .protocol import authenticated,encode,headers,pack,unpack

def create_worker(directory,worker_id,secret,coordinator,url,verify=True,device='cpu'):
    torch.set_num_threads(int(os.getenv('MESH_THREADS','2')))
    shard=Shard(directory,device)
    gpus=[dict(index=i,name=torch.cuda.get_device_properties(i).name,vram_total=torch.cuda.get_device_properties(i).total_memory) for i in range(torch.cuda.device_count())]
    fingerprint=hashlib.sha256((Path(directory)/'weights.pt').read_bytes()).hexdigest()
    sessions={}
    cache_budget=int(os.getenv('MESH_CACHE_MB','128'))*1048576
    mutex=threading.Lock()
    stop=threading.Event()
    report={'last_error':None}

    def resources():
        with mutex:
            cache_bytes=sum(t.numel()*t.element_size() for s in sessions.values() for kv in s['past'] for t in kv)
        result=dict(gpus=gpus,cpu_count=psutil.cpu_count(),cpu_percent=psutil.cpu_percent(),ram_total=psutil.virtual_memory().total,ram_available=psutil.virtual_memory().available,rss=psutil.Process().memory_info().rss,cache_bytes=cache_bytes,device=str(shard.device),parameters=sum(t.numel() for t in shard.parameters()),sessions=len(sessions))
        if shard.device.type=='cuda':
            free,total=torch.cuda.mem_get_info(shard.device)
            result.update(vram_total=total,vram_free=free,vram_allocated=torch.cuda.memory_allocated(shard.device))
        return result

    def heartbeat():
        with httpx.Client(verify=verify,timeout=5,trust_env=False) as client:
            while not stop.is_set():
                with mutex:
                    for sid in list(sessions):
                        if time.monotonic()-sessions[sid]['updated']>120:
                            del sessions[sid]
                try:
                    body=encode(dict(id=worker_id,url=url,spec=shard.spec,fingerprint=fingerprint,resources=resources()))
                    response=client.post(coordinator+'/internal/register',content=body,headers=headers(secret,body))
                    response.raise_for_status()
                    report['last_error']=None
                except Exception as exc:
                    report['last_error']=str(exc)
                stop.wait(2)

    @asynccontextmanager
    async def lifespan(app):
        thread=threading.Thread(target=heartbeat,daemon=True)
        thread.start()
        yield
        stop.set()
        thread.join(6)

    app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
    app.state.shard=shard
    app.state.sessions=sessions

    @app.post('/step')
    async def step(request:Request):
        message=await authenticated(request,secret)
        try:
            sid=message['session']
            position=message['position']
            if not isinstance(sid,str) or len(sid)!=32 or any(c not in '0123456789abcdef' for c in sid):
                raise ValueError('Invalid session')
            if type(position) is not int or position<0:
                raise ValueError('Invalid position')
            value=unpack(message['tensor'],integer=shard.spec['first'])
            if value.shape[0]!=1 or value.ndim!=(2 if shard.spec['first'] else 3):
                raise ValueError('Invalid batch')
            if not shard.spec['first'] and value.shape[2]!=shard.config.n_embd:
                raise ValueError('Invalid hidden size')
            if shard.spec['first'] and (value.min()<0 or value.max()>=shard.config.vocab_size):
                raise ValueError('Invalid token')
            length=value.shape[1]
            if position+length>min(shard.config.n_positions,512):
                raise ValueError('Context limit exceeded')
            with mutex:
                old=sessions.get(sid)
                if position!=(old['position'] if old else 0):
                    raise HTTPException(409,'KV position mismatch; restart generation')
                if old is None and len(sessions)>=8:
                    raise HTTPException(429,'Session capacity reached')
                projected=2*(shard.spec['end']-shard.spec['start'])*shard.config.n_embd*length*4
                current=sum(t.numel()*t.element_size() for session in sessions.values() for kv in session['past'] for t in kv)
                if current+projected>cache_budget:
                    raise HTTPException(429,'KV memory budget exceeded')
                started=time.perf_counter()
                output,past=shard.step(value,None if old is None else old['past'],position)
                if shard.device.type=='cuda':
                    torch.cuda.synchronize(shard.device)
                elapsed=time.perf_counter()-started
                sessions[sid]=dict(past=past,position=position+length,updated=time.monotonic())
            return dict(tensor=pack(output),seconds=elapsed,units=length*(shard.spec['end']-shard.spec['start']),position=position+length)
        except (KeyError,ValueError,TypeError) as exc:
            raise HTTPException(422,str(exc))

    @app.post('/release')
    async def release(request:Request):
        message=await authenticated(request,secret)
        with mutex:
            sessions.pop(message.get('session'),None)
        return {'ok':True}

    @app.post('/status')
    async def status(request:Request):
        await authenticated(request,secret)
        return dict(id=worker_id,spec=shard.spec,resources=resources(),registration=report)
    return app
