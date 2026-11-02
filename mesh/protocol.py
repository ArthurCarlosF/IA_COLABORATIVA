import base64
import hashlib
import hmac
import json
import math
import time
import numpy as np
import torch
from fastapi import HTTPException, Request
MAX_BODY = 4*1024*1024

def pack(value):
    arr=value.detach().cpu().contiguous().numpy()
    return dict(shape=list(arr.shape), dtype=str(arr.dtype), data=base64.b64encode(arr.tobytes()).decode())

def unpack(value, integer=False):
    if not isinstance(value, dict) or set(value)!={'shape','dtype','data'}:
        raise ValueError('Invalid tensor')
    shape=value['shape']
    if not isinstance(shape,list) or not 2<=len(shape)<=3 or any(type(n) is not int or n<1 for n in shape):
        raise ValueError('Invalid shape')
    dtype='int64' if integer else 'float32'
    if value['dtype']!=dtype or math.prod(shape)>1000000:
        raise ValueError('Invalid tensor type or size')
    data=base64.b64decode(value['data'],validate=True)
    if len(data)!=math.prod(shape)*np.dtype(dtype).itemsize:
        raise ValueError('Invalid tensor length')
    arr=np.frombuffer(data,dtype=dtype).reshape(shape).copy()
    if not np.isfinite(arr).all():
        raise ValueError('Non finite tensor')
    return torch.from_numpy(arr)

def encode(value):
    return json.dumps(value,separators=(',',':'),allow_nan=False).encode()

def headers(secret,body):
    stamp=str(time.time())
    signature=hmac.new(secret.encode(),stamp.encode()+b'.'+body,hashlib.sha256).hexdigest()
    return {'Content-Type':'application/json','X-Time':stamp,'X-Signature':signature}

async def authenticated(request:Request,secret):
    chunks=[]
    size=0
    async for chunk in request.stream():
        size+=len(chunk)
        if size>MAX_BODY:
            raise HTTPException(413,'Message too large')
        chunks.append(chunk)
    body=b''.join(chunks)
    stamp=request.headers.get('x-time','')
    signature=request.headers.get('x-signature','')
    try:
        fresh=abs(time.time()-float(stamp))<30
    except ValueError:
        fresh=False
    expected=hmac.new(secret.encode(),stamp.encode()+b'.'+body,hashlib.sha256).hexdigest()
    if not fresh or not hmac.compare_digest(expected.encode(),signature.encode()):
        raise HTTPException(401,'Invalid signature')
    try:
        return json.loads(body)
    except (ValueError,UnicodeError):
        raise HTTPException(422,'Invalid JSON')


def checkpoint_hash(path):
    with open(path,'rb') as handle:
        return hashlib.file_digest(handle,'sha256').hexdigest()
