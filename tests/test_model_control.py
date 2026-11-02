import asyncio
import json
from pathlib import Path
import pytest
from fastapi import FastAPI
from starlette.requests import Request
from mesh.model_control import ModelControl
from mesh.partition_store import PROFILES,digest

@pytest.mark.parametrize('rollback_breaks',[False,True])
def test_activation_failure_restores_all_or_blocks_for_explicit_recovery(tmp_path,monkeypatch,rollback_breaks):
    async def scenario():
        model,revision=PROFILES['coder-0.5b'];config=dict(model_type='qwen2',num_hidden_layers=2,use_sliding_window=False)
        bundles=[]
        for i in range(2):bundles.append(dict(model=model,revision=revision,format='range-f32-v1',config=config,spec=dict(index=i,start=i,end=i+1,first=i==0,last=i==1),tensors={f'model.layers.{i}.weight':dict(shape=[2,2],dtype='F32',start=100,size=16,file='model.safetensors')}))
        plan=dict(model=model,revision=revision,parts=[b['spec'] for b in bundles],bundles=bundles,config=config)
        monkeypatch.setattr('mesh.model_control.plan_remote',lambda *args:plan)
        class Tokenizer:
            def save_pretrained(self,path):Path(path).mkdir(exist_ok=True)
        monkeypatch.setattr('mesh.model_control.AutoTokenizer.from_pretrained',lambda *args,**kwargs:Tokenizer())
        old=tmp_path/'old';old.mkdir();current={'root':old,'manifest':dict(model='old'),'fingerprints':{0:'old-a',1:'old-b'}};active={'a':'old-a','b':'old-b'};fail_recovery=[rollback_breaks]
        def apply(root):current['root']=Path(root)
        async def rpc(node,path,body):
            key=node['id'];i=0 if key=='a' else 1
            if path=='/status':return dict(resources=dict(host_id=key,ram_available=4*2**30,weight_bytes=100,rss=100,device='cpu',sessions=0))
            if path=='/model/stage':return dict(id=digest(bundles[i]))
            if path=='/model/status':return dict(id=digest(bundles[i]),state='ready')
            if path=='/model/commit':
                if key=='b':raise RuntimeError('Injected second-worker activation failure')
                active[key]=digest(bundles[i]);return dict(fingerprint=active[key],spec=bundles[i]['spec'])
            if path=='/model/rollback':
                if fail_recovery[0]:raise RuntimeError('Injected lost worker during rollback')
                active[key]=['old-a','old-b'][i];return dict(fingerprint=active[key])
            if path=='/model/abort':return dict(ok=True)
            raise AssertionError(path)
        catalog=tmp_path/'catalog';catalog.mkdir()
        ctl=ModelControl(FastAPI(),lambda request:'local-user',{'a':'http://a','b':'http://b'},{},rpc,lambda:dict(current),apply,catalog,lambda:True,lambda:(4096,512))
        ctl.busy=True;ctl.job=dict(state='planning');await ctl.execute('coder-0.5b')
        if rollback_breaks:
            assert ctl.busy and ctl.job['state']=='recovery_required' and ctl.journal.exists()
            fail_recovery[0]=False
            request=Request(dict(type='http',client=('127.0.0.1',1),headers=[]))
            await ctl.recover(request)
        else:assert ctl.job['state']=='failed'
        assert not ctl.busy and active=={'a':'old-a','b':'old-b'} and current['root']==old and not ctl.journal.exists()
        assert not ctl.selection.exists()
    asyncio.run(scenario())


def test_shared_gpu_and_shared_cpu_memory_are_not_counted_once_per_process():
    controller=ModelControl.__new__(ModelControl)
    common=dict(host_id='same-host',weight_bytes=2**30,rss=2**30,ram_available=4*2**30,device='cpu')
    cpu=controller.budgets({'a':dict(common),'b':dict(common)})
    assert sum(cpu.values())<=5*2**30
    gpu=dict(common,device='cuda:0',device_id='one-physical-gpu',vram_free=4*2**30)
    result=controller.budgets({'a':dict(gpu),'b':dict(gpu)})
    assert sum(result.values())<=5*2**30
    separate=controller.budgets({'a':dict(gpu),'b':dict(gpu,device_id='another-physical-gpu')})
    assert sum(separate.values())>sum(result.values())
