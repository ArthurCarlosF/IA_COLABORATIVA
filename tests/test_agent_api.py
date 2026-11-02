import json
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from mesh.coordinator import create_coordinator

@pytest.fixture
def api(tmp_path):
    root=Path(__file__).resolve().parents[1]/'data/model'
    app=create_coordinator(root,'s'*64,'u'*64,{'a':'http://127.0.0.1:1','b':'http://127.0.0.1:2'},tmp_path/'bank.db',accounts={'bob':'b'*64},workspace_root=tmp_path/'files')
    with TestClient(app) as client:yield client,app,{'Authorization':'Bearer '+'u'*64}

def test_model_catalog_and_message_validation(api):
    client,app,h=api
    assert client.get('/api/models').status_code==401
    catalog=client.get('/api/models',headers=h).json()
    assert sum(m['available'] for m in catalog['models'])==1 and not catalog['quality_equivalence_verified']
    assert client.post('/api/chat',headers=h,json={'prompt':'hello','model':'absent'}).status_code==409
    assert client.post('/api/agent/runs',headers=h,json={'task':'hello','model':'absent'}).status_code==409
    for body in [[],None,1,'text']:
        assert client.post('/api/agent/runs',headers=h,content=json.dumps(body)).status_code==422
    assert client.post('/api/agent/runs/x/approve',headers=h,json={'id':'x','approved':'true'}).status_code==422

def test_agent_api_private_history_and_host_disabled(api):
    client,app,h=api
    async def infer(*args):return '{"tool":"finish","args":{"summary":"No file changes requested"}}'
    app.state.agent.infer=infer
    response=client.post('/api/agent/runs',headers=h,json={'task':'List no changes'})
    assert response.status_code==200;run=response.json()['id']
    for _ in range(100):
        data=client.get('/api/agent/runs/'+run,headers=h).json()
        if data['run']['status']=='completed':break
        time.sleep(.01)
    assert data['run']['status']=='completed' and data['events']
    assert client.get('/api/agent/runs/'+run,headers={'Authorization':'Bearer '+'b'*64}).status_code==404
    assert client.get('/api/agent/runs',headers=h).json()['host_commands'] is False
    assert client.post('/api/agent/runs/'+run+'/approve',headers=h,json={'id':'absent','approved':True}).status_code==403
