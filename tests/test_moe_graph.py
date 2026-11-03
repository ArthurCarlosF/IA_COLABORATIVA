"""Independent Transformers oracle and actual worker RPCs for the MoE graph."""
import asyncio
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import httpx
import numpy as np
import psutil
import pytest
import torch
from mesh.graph_executor import GraphExecutor
from mesh.graph_plan import build_graph, provision_graph
from mesh.partition_store import PROFILES
from mesh.protocol import encode, headers
from mesh.slow_inference import run_slow

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def oracle():
    path=ROOT/'runtime/moe-reference'
    if not (path/'reference.npz').exists():
        pytest.skip('Build synthetic oracle with tools/make_moe_reference.py (Transformers 4.51.3)')
    c=json.loads((path/'config.json').read_text())
    data=(path/'model.safetensors').read_bytes()
    model,revision=PROFILES['coder-480b']
    graph=build_graph(model,revision,c,None,2,max_parameters=6000,piece_parameters=900)
    results=np.load(path/'reference.npz')
    yield graph,data,results
    results.close()


def source(data, reads):
    def response(request):
        start,end=map(int,re.fullmatch(r'bytes=(\d+)-(\d+)',request.headers['range']).groups())
        reads.append((start,end+1))
        return httpx.Response(206,content=data[start:end+1],
            headers={'Content-Range':f'bytes {start}-{end}/{len(data)}'})
    return httpx.Client(transport=httpx.MockTransport(response))


def port():
    with socket.socket() as server:
        server.bind(('127.0.0.1',0))
        return server.getsockname()[1]


def stop(child):
    try:
        process=psutil.Process(child.pid)
        for p in reversed(process.children(recursive=True)):
            try:p.terminate()
            except psutil.NoSuchProcess:pass
        process.terminate()
    except psutil.NoSuchProcess:pass
    child.wait(timeout=15)


def test_moe_four_steps_match_oracle_through_two_real_workers(oracle,tmp_path):
    graph,data,reference=oracle
    assert len(graph['pieces'])>graph['layers']
    assert any(len(layer['experts'])>1 for layer in graph['graph']['layers'])
    secret='synthetic-test-only-secret-'*3
    ports=[port(),port()]
    nodes=[dict(id=f'worker-{i}',spec=spec,url=f'http://127.0.0.1:{ports[i]}')
           for i,spec in enumerate(graph['parts'])]
    cfg=tmp_path/'config.json'
    cfg.write_text(json.dumps(dict(cluster_secret=secret,coordinator='http://127.0.0.1:9',
                                   workers={n['id']:n['url'] for n in nodes})))
    children=[]
    logs=[]
    try:
        for i,node in enumerate(nodes):
            with source(data,[]) as client:
                prepared=provision_graph(graph['bundles'][i],tmp_path/'cache',client=client)
            root=tmp_path/f'worker-{i}'
            root.mkdir()
            shutil.copytree(prepared,root/f'part-{i}')
            log=(root/'worker.log').open('w')
            logs.append(log)
            children.append(subprocess.Popen(
                [sys.executable,'-m','mesh','worker','--config',str(cfg),'--root',str(root),
                 '--part',str(i),'--id',node['id'],'--port',str(ports[i])],
                cwd=root,env=dict(os.environ,PYTHONPATH=str(ROOT),MESH_THREADS='1'),
                stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0))
        with httpx.Client(timeout=3,trust_env=False) as client:
            deadline=time.monotonic()+150
            while time.monotonic()<deadline:
                try:
                    body=encode({})
                    if all(client.post(n['url']+'/status',content=body,
                                headers=headers(secret,body)).status_code==200 for n in nodes):
                        break
                except httpx.HTTPError:pass
                if any(c.poll() is not None for c in children):break
                time.sleep(.25)
            else:pytest.fail('Graph workers timed out')
            assert all(c.poll() is None for c in children), [
                (tmp_path/f'worker-{i}'/'worker.log').read_text(errors='replace') for i in range(2)]
        async def run():
            async with httpx.AsyncClient(timeout=15,trust_env=False) as client:
                async def rpc(node,path,message):
                    body=encode(message)
                    r=await client.post(node['url']+path,content=body,headers=headers(secret,body))
                    r.raise_for_status()
                    return r.json()
                executor=GraphExecutor(graph,nodes,rpc)
                position=0
                used=set()
                errors=[]
                for step in range(4):
                    ids=torch.from_numpy(reference[f'ids_{step}'])
                    output,records=await executor.step(ids,'a'*32,position)
                    expected=torch.from_numpy(reference[f'logits_{step}'])
                    torch.testing.assert_close(output,expected,rtol=1e-5,atol=1e-6)
                    assert output.argmax().item()==expected.argmax().item()
                    used.update(n['id'] for n,_ in records)
                    errors.append(float((output-expected).abs().max()))
                    position+=ids.shape[1]
                assert used=={'worker-0','worker-1'}
                for node in nodes:await rpc(node,'/release',dict(session='a'*32))
                return errors
        errors=asyncio.run(run())
        (ROOT/'runtime/moe-rpc-evidence.json').write_text(json.dumps(dict(
            synthetic=True,actual_http_workers=2,steps=4,errors=errors,
            max_logit_error=max(errors)),indent=2))
    finally:
        for child in children:stop(child)
        for log in logs:log.close()


def test_streamed_generation_resumes_attention_and_matrices(oracle,tmp_path):
    graph,data,reference=oracle
    reads=[]
    prompt=reference['ids_0'].tolist()[0]
    with source(data,reads) as client:
        first=asyncio.run(run_slow(graph,prompt,tmp_path,4,None,client,
                                  maximum_tiles=17,tile_rows=16,tile_columns=16))
        assert first['status']=='paused' and first['tiles_executed']==17
        second=asyncio.run(run_slow(graph,prompt,tmp_path,4,None,client,
                                   maximum_tiles=25,tile_rows=16,tile_columns=16))
        assert second['status']=='paused'
        final=asyncio.run(run_slow(graph,prompt,tmp_path,4,None,client,
                                  tile_rows=16,tile_columns=16))
        expected=[int(reference[f'logits_{i}'].argmax()) for i in range(4)]
        assert final['status']=='completed' and final['generated']==expected
        again=asyncio.run(run_slow(graph,prompt,tmp_path,4,None,client,
                                  tile_rows=16,tile_columns=16))
        assert again['tiles_executed']==again['source_weight_bytes']==0
    assert not list(tmp_path.rglob('*.safetensors')) and not list(tmp_path.rglob('*.bin'))
    (ROOT/'runtime/moe-slow-evidence.json').write_text(json.dumps(dict(
        synthetic=True,checkpoints=[first,second,final],oracle_tokens=expected),indent=2))


def test_thousand_participants_do_not_require_whole_transformer_layers():
    cfg=dict(model_type='qwen3_moe',hidden_size=6144,head_dim=128,
             vocab_size=151936,num_attention_heads=96,num_key_value_heads=8,
             num_hidden_layers=62,moe_intermediate_size=2560,
             intermediate_size=8192,num_experts=160,num_experts_per_tok=8,
             tie_word_embeddings=False)
    model,revision=PROFILES['coder-480b']
    result=build_graph(model,revision,cfg,None,1024)
    assert len(result['parts'])==1024 and len(result['pieces'])>10000
    assert result['source_parameters']==480154875392
    assert max(sum(p['parameters'] for p in b['pieces'])
               for b in result['bundles'])<=1_000_000_000
    assert len(result['owners'])==len(result['pieces'])
