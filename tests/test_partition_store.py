"""Synthetic matrices test selective transport and numeric preservation, not model quality."""
import hashlib
import json
import math
import re
import struct
import httpx
import pytest
import torch
from safetensors.torch import save
from transformers import Qwen2Config,Qwen2ForCausalLM
from mesh.partition_store import PROFILES,tensor_header,read_range,owner,provision,load_mapped,digest
from mesh.model import Shard

def fixture_source():
    torch.manual_seed(23);cfg=Qwen2Config(vocab_size=1024,hidden_size=16,intermediate_size=32,num_hidden_layers=4,num_attention_heads=4,num_key_value_heads=2,max_position_embeddings=128)
    cfg._attn_implementation='eager';model=Qwen2ForCausalLM(cfg).eval();data=save({k:v.contiguous() for k,v in model.state_dict().items()});reads=[]
    def handle(request):
        match=re.fullmatch(r'bytes=(\d+)-(\d+)',request.headers.get('range',''));assert match
        a,b=map(int,match.groups());reads.append((a,b+1))
        return httpx.Response(206,headers={'Content-Range':f'bytes {a}-{b}/{len(data)}'},content=data[a:b+1])
    return model,cfg,httpx.Client(transport=httpx.MockTransport(handle)),reads

def test_partial_fetch_never_reads_foreign_weights_and_logits_match(tmp_path,monkeypatch):
    torch.set_num_threads(1)
    full,cfg,client,reads=fixture_source();header=tensor_header(client,'https://source.test/model');header_end=8+struct.unpack('<Q',save({k:v.contiguous() for k,v in full.state_dict().items()})[:8])[0]
    shards=[]
    for index in range(2):
        selected={k:dict(v,file='model.safetensors') for k,v in header.items() if owner(k,[(0,2),(2,4)])==index}
        model,revision=PROFILES['coder-0.5b'];bundle=dict(model=model,revision=revision,config=cfg.to_dict(),spec=dict(index=index,start=index*2,end=index*2+2,first=index==0,last=index==1),tensors=selected,format='range-f32-v1')
        reads.clear();path=provision(bundle,tmp_path/str(index),client=client)
        assert (path/'weights.json').exists() and not (path/'weights.pt').exists()
        expected=sum(e['size'] for e in selected.values());assert sum(b-a for a,b in reads)==expected
        for a,b in reads:assert any(e['start']<=a<b<=e['start']+e['size'] for e in selected.values())
        actual=load_mapped(path)
        for key,tensor in actual.items():torch.testing.assert_close(tensor,full.state_dict()[key],rtol=0,atol=0)
        shards.append(Shard(path))
    ids=torch.tensor([[1,3,5]]);past=[None,None];value=ids
    with torch.inference_mode():
        reference=full(ids).logits[:,-1:,:]
        for i,shard in enumerate(shards):value,past[i]=shard.step(value,None,0)
    torch.testing.assert_close(value,reference,atol=1e-6,rtol=1e-5)
    # Local corruption is rejected before a mapped shard can be activated.
    index=json.loads((path/'weights.json').read_text());file=path/next(iter(index['tensors'].values()))['file']
    with file.open('r+b') as f:f.write(b'BAD!')
    with pytest.raises(ValueError,match='Corrupted'):load_mapped(path)

def test_full_download_refused_before_body_consumption():
    consumed=[]
    class Body(httpx.SyncByteStream):
        def __iter__(self):consumed.append(True);yield b'x'*1000
    client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,stream=Body())))
    with pytest.raises(ValueError,match='full download prohibited'):read_range(client,'https://source.test/a',0,8)
    assert not consumed

def test_invalid_range_and_short_reply_rejected():
    for header,data in [('bytes 2-9/20',b'12345678'),('bytes 0-7/20',b'123')]:
        client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(206,headers={'Content-Range':header},content=data)))
        with pytest.raises(ValueError):read_range(client,'https://source.test/a',0,8)
