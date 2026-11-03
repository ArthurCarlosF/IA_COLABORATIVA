"""A small, stateless FP32 arithmetic service. No checkpoint or Torch required."""
import base64
import hashlib
import hmac
import json
import math
import time
from urllib.parse import urlsplit
import httpx
import numpy as np
from fastapi import FastAPI, HTTPException, Request, Response
from .durable_tiles import matmul_tile, tile_bytes

MAX_MESSAGE = 131072


def wire(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def mac(secret, value):
    return hmac.new(secret.encode(),value,hashlib.sha256).hexdigest()


def matrix(value):
    a=np.asarray(value,dtype='<f4')
    return dict(shape=list(a.shape),data=base64.b64encode(a.tobytes()).decode())


def unmatrix(message):
    if not isinstance(message,dict) or set(message)!={'shape','data'}:
        raise ValueError('Invalid matrix object')
    shape=message['shape']
    if (not isinstance(shape,list) or len(shape)!=2
            or any(type(n) is not int or not 1<=n<=65535 for n in shape)
            or math.prod(shape)*4>MAX_MESSAGE):
        raise ValueError('Invalid matrix shape')
    raw=base64.b64decode(message['data'],validate=True)
    if len(raw)!=math.prod(shape)*4:raise ValueError('Invalid matrix bytes')
    return np.frombuffer(raw,dtype='<f4').reshape(shape)


def create_tile_worker(secret, maximum_bytes=65536):
    if not isinstance(secret,str) or len(secret)<32 or not 1024<=maximum_bytes<=65536:
        raise ValueError('Invalid tile service configuration')
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)

    @app.post('/tile/matmul')
    async def execute(request:Request):
        body=bytearray()
        wire_limit=min(MAX_MESSAGE,maximum_bytes*3//2+1024)
        async for block in request.stream():
            if len(body)+len(block)>wire_limit:raise HTTPException(413,'Tile message too large')
            body.extend(block)
        stamp=request.headers.get('x-time','')
        try:fresh=abs(time.time()-float(stamp))<30
        except ValueError:fresh=False
        if not fresh or not hmac.compare_digest(mac(secret,stamp.encode()+b'.'+body),
                                                  request.headers.get('x-signature','')):
            raise HTTPException(401,'Invalid tile signature')
        try:
            data=json.loads(body)
            if (set(data)!={'version','inputs','weights','maximum_bytes'}
                    or type(data['version']) is not int or data['version']!=1):
                raise ValueError('Invalid tile protocol')
            budget=data['maximum_bytes']
            if type(budget) is not int or not 1024<=budget<=65536:
                raise ValueError('Invalid tile budget')
            a,w=unmatrix(data['inputs']),unmatrix(data['weights'])
            output=matmul_tile(a,w,min(budget,maximum_bytes))
            result=wire(dict(version=1,tensor=matrix(output),
                working_bytes=tile_bytes(a.shape[0],w.shape[0],a.shape[1])))
        except (KeyError,TypeError,ValueError) as exc:raise HTTPException(422,str(exc))
        request_hash=hashlib.sha256(body).hexdigest()
        return Response(result,media_type='application/json',headers={
            'X-Tile-Receipt':mac(secret,request_hash.encode()+b'.'+result)})
    return app


class TileClient:
    def __init__(self, endpoint, secret, client):
        url=urlsplit(endpoint)
        if (url.scheme not in ('http','https') or not url.hostname or url.username
                or url.password or url.query or url.fragment or url.path not in ('','/')):
            raise ValueError('Invalid tile worker endpoint')
        if url.scheme!='https' and url.hostname not in ('127.0.0.1','localhost','::1'):
            raise ValueError('Remote tile workers require HTTPS')
        if not isinstance(secret,str) or len(secret)<32:raise ValueError('Invalid tile secret')
        self.endpoint,self.secret,self.client=endpoint.rstrip('/'),secret,client

    def __call__(self, inputs, weights, maximum_bytes):
        body=wire(dict(version=1,inputs=matrix(inputs),weights=matrix(weights),
                       maximum_bytes=maximum_bytes))
        if len(body)>MAX_MESSAGE:raise ValueError('Tile exceeds wire limit')
        stamp=str(time.time())
        with self.client.stream('POST',self.endpoint+'/tile/matmul',content=body,
                headers={'X-Time':stamp,'X-Signature':mac(self.secret,stamp.encode()+b'.'+body),
                         'Content-Type':'application/json'}) as response:
            response.raise_for_status()
            data=bytearray()
            for chunk in response.iter_bytes(chunk_size=65536):
                data.extend(chunk)
                if len(data)>MAX_MESSAGE:raise ValueError('Tile reply too large')
            expected=mac(self.secret,hashlib.sha256(body).hexdigest().encode()+b'.'+data)
            if not hmac.compare_digest(expected,response.headers.get('x-tile-receipt','')):
                raise ValueError('Invalid tile receipt')
        result=json.loads(data)
        if result['version']!=1 or result['working_bytes']!=tile_bytes(
                inputs.shape[0],weights.shape[0],inputs.shape[1]):
            raise ValueError('Invalid tile result descriptor')
        output=unmatrix(result['tensor'])
        if output.shape!=(inputs.shape[0],weights.shape[0]) or not np.isfinite(output).all():
            raise ValueError('Invalid arithmetic reply')
        return output


class TilePool:
    """Round-robin, retrying only before a durable arithmetic commit."""
    def __init__(self, kernels):
        if not kernels:raise ValueError('At least one tile worker is required')
        self.kernels=list(kernels)
        self.cursor=0

    def __call__(self, inputs, weights, maximum_bytes):
        errors=[]
        for _ in self.kernels:
            kernel=self.kernels[self.cursor]
            self.cursor=(self.cursor+1)%len(self.kernels)
            try:return kernel(inputs,weights,maximum_bytes)
            except (httpx.HTTPError,ValueError) as exc:errors.append(type(exc).__name__)
        raise RuntimeError('No tile worker accepted the operation: '+', '.join(errors))
