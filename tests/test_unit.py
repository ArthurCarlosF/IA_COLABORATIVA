import json
import time
import pytest
import torch
from fastapi import FastAPI,Request
from fastapi.testclient import TestClient
from mesh.protocol import pack,unpack,encode,headers,authenticated
from mesh.ledger import Ledger

@pytest.mark.parametrize('value',[torch.tensor([[1,2]],dtype=torch.long),torch.randn(1,3,2)])
def test_tensor_roundtrip(value):
    assert torch.equal(value,unpack(pack(value),integer=value.dtype==torch.long))

@pytest.mark.parametrize('value',[
    {'shape':[1,-1],'dtype':'float32','data':''},
    {'shape':[1,1000001],'dtype':'float32','data':''},
    {'shape':[1,2],'dtype':'pickle','data':''},
    {'shape':[1,2],'dtype':'float32','data':'@@@@'},
    {'shape':[1,2],'dtype':'float32','data':'AAAA'},
    {},
])
def test_invalid_tensors(value):
    with pytest.raises((ValueError,TypeError)):
        unpack(value)

def test_nonfinite():
    with pytest.raises(ValueError):
        unpack(pack(torch.tensor([[float('nan')]])))

def test_authentication():
    app=FastAPI()
    @app.post('/')
    async def endpoint(request:Request):
        return await authenticated(request,'secret')
    with TestClient(app) as client:
        body=encode({'ok':1})
        assert client.post('/',content=body,headers=headers('secret',body)).status_code==200
        assert client.post('/',content=body,headers=headers('wrong',body)).status_code==401
        signed=headers('secret',body)
        signed['X-Time']='0'
        assert client.post('/',content=body,headers=signed).status_code==401
        assert client.post('/',content=b'x'*(4*1024*1024+1)).status_code==413

def test_audit_and_deduplication(tmp_path):
    ledger=Ledger(tmp_path/'ledger.db')
    ledger.append('r','u','w',3,.2)
    ledger.append('r','u','w',3,.2)
    ledger.append('s','u','w',1,.1)
    assert len(ledger.export())==2 and ledger.verify()
    assert sum(e['event']['debit']+e['event']['credit'] for e in ledger.export())==0
    ledger.db.execute("UPDATE entries SET event='{}' WHERE seq=1")
    ledger.db.commit()
    assert not ledger.verify()


def test_memory_planner():
    from mesh.planner import plan
    assert plan([10,10,10,10],[15,40])==[(0,1),(1,4)]
    assert plan([10,10],[30,30],10,10)==[(0,1),(1,2)]
    with pytest.raises(ValueError):plan([10,10],[5,30])
    with pytest.raises(ValueError):plan([10],[10,10])
    with pytest.raises(ValueError):plan([-1],[10])


def test_worker_kv_budget(monkeypatch):
    from pathlib import Path
    from mesh.worker import create_worker
    monkeypatch.setenv('MESH_CACHE_MB','0')
    root=Path(__file__).resolve().parents[1]/'data/model/part-0'
    if not root.exists():pytest.fail('Run mesh prepare first')
    app=create_worker(root,'test','secret','http://127.0.0.1:1','http://127.0.0.1:2')
    client=TestClient(app)
    body=encode(dict(session='a'*32,position=0,tensor=pack(torch.tensor([[1]]))))
    response=client.post('/step',content=body,headers=headers('secret',body))
    assert response.status_code==429
    assert not app.state.sessions


def test_remote_http_refused(tmp_path,monkeypatch):
    from mesh.__main__ import main
    config=tmp_path/'config.json'
    config.write_text(json.dumps(dict(cluster_secret='s'*64,user_token='u'*64,coordinator='http://192.0.2.1:8000',workers={})))
    monkeypatch.setattr('sys.argv',['mesh','coordinator','--config',str(config)])
    with pytest.raises(SystemExit,match='HTTPS'):main()
