import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time
import uuid
import httpx
import psutil
import pytest
import torch
from transformers import AutoTokenizer,GPT2LMHeadModel
from mesh.model import MODEL,REVISION
from mesh.protocol import pack,unpack,encode,headers

ROOT=Path(__file__).resolve().parents[1]
MODEL_ROOT=ROOT/'data/model'
REPORT={}

def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0))
        return s.getsockname()[1]

@pytest.fixture(scope='module',params=['http','https'])
def cluster(tmp_path_factory,request):
    if not (MODEL_ROOT/'manifest.json').exists():
        pytest.fail('Checkpoint missing: run python -m mesh prepare')
    directory=tmp_path_factory.mktemp('cluster')
    ports=[free_port() for _ in range(3)]
    scheme=request.param
    cert_path=None
    if scheme=='https':
        import datetime
        import ipaddress
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes,serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Mesh test only')])
        now=datetime.datetime.now(datetime.timezone.utc)
        cert=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=5)).not_valid_after(now+datetime.timedelta(days=1)).add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False).add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True).sign(key,hashes.SHA256())
        cert_path=directory/'test-cert.pem'
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (directory/'test-key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    config=dict(cluster_secret='c'*64,user_token='u'*64,coordinator=f'{scheme}://127.0.0.1:{ports[0]}',workers={f'worker-{i}':f'{scheme}://127.0.0.1:{ports[i+1]}' for i in range(2)})
    cfg=directory/'config.json'
    cfg.write_text(json.dumps(config))
    children=[]
    logs=[]
    def start(role,index=0):
        log=open(directory/f'{role}-{index}-{len(logs)}.log','w')
        logs.append(log)
        cmd=[sys.executable,'-m','mesh',role,'--root',str(MODEL_ROOT),'--config',str(cfg),'--port',str(ports[0] if role=='coordinator' else ports[index+1])]
        if cert_path:cmd+=['--cert',str(cert_path),'--key',str(directory/'test-key.pem'),'--ca',str(cert_path)]
        if role=='worker':cmd+=['--id',f'worker-{index}','--part',str(index)]
        env=dict(os.environ,PYTHONPATH=str(ROOT),MESH_THREADS='1')
        child=subprocess.Popen(cmd,cwd=directory,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        children.append(child)
        return child
    coordinator=start('coordinator')
    workers=[start('worker',i) for i in range(2)]
    client=httpx.Client(timeout=40,trust_env=False,verify=ssl.create_default_context(cafile=str(cert_path)) if cert_path else True)
    auth={'Authorization':'Bearer '+config['user_token']}
    def wait_ready():
        deadline=time.monotonic()+100
        while time.monotonic()<deadline:
            try:
                response=client.get(config['coordinator']+'/api/status',headers=auth)
                if response.status_code==200 and len([n for n in response.json()['nodes'] if n['online']])==2:
                    return
            except httpx.HTTPError:pass
            if any(c.poll() is not None for c in [coordinator,*workers]):
                break
            time.sleep(.5)
        for log in logs:log.flush()
        pytest.fail('Cluster startup failed: '+str(directory)+'\n'+'\n'.join(f.read_text(errors='replace') for f in directory.glob('*.log')))
    try:
        wait_ready()
        REPORT['process_ids']=[c.pid for c in children]
        REPORT.setdefault('transports',[]).append(scheme)
        REPORT['last_transport']=scheme
        yield dict(config=config,client=client,auth=auth,workers=workers,start=start,wait=wait_ready,directory=directory,scheme=scheme)
    finally:
        client.close()
        for child in children:
            if child.poll() is None:child.terminate()
        for child in children:
            try:child.wait(10)
            except subprocess.TimeoutExpired:child.kill()
        for log in logs:log.close()
        (ROOT/'runtime').mkdir(exist_ok=True)
        (ROOT/'runtime/test-evidence.json').write_text(json.dumps(REPORT,indent=2),encoding='utf8')

def rpc(c,index,path,message):
    body=encode(message)
    response=c['client'].post(c['config']['workers'][f'worker-{index}']+path,content=body,headers=headers(c['config']['cluster_secret'],body))
    response.raise_for_status()
    return response.json()

def test_01_real_logits_and_cache(cluster):
    torch.set_num_threads(1)
    full=GPT2LMHeadModel.from_pretrained(MODEL,revision=REVISION,local_files_only=True,attn_implementation='eager').eval()
    tokenizer=AutoTokenizer.from_pretrained(MODEL_ROOT/'tokenizer',local_files_only=True)
    ids=tokenizer.encode('What is artificial intelligence?',return_tensors='pt')
    sid=uuid.uuid4().hex
    past=None
    position=0
    errors=[]
    generated=[]
    with torch.inference_mode():
        for _ in range(8):
            output=full(ids,past_key_values=past,use_cache=True)
            past=output.past_key_values
            value=pack(ids)
            for index in range(2):
                value=rpc(cluster,index,'/step',dict(session=sid,position=position,tensor=value))['tensor']
            distributed=unpack(value)
            error=(output.logits[:,-1:,:]-distributed).abs().max().item()
            errors.append(error)
            torch.testing.assert_close(distributed,output.logits[:,-1:,:],rtol=1e-5,atol=1e-6)
            token=int(distributed[0,-1].argmax())
            assert token==int(output.logits[0,-1].argmax())
            generated.append(token)
            position+=ids.shape[1]
            ids=torch.tensor([[token]])
    for i in range(2):rpc(cluster,i,'/release',dict(session=sid))
    REPORT['numerical']=dict(steps=8,max_abs_error=max(errors),atol=1e-6,rtol=1e-5,generated_tokens=generated)

def test_02_chat_stream_and_credits(cluster):
    c=cluster
    start=time.perf_counter()
    response=c['client'].post(c['config']['coordinator']+'/api/chat',headers=c['auth'],json=dict(prompt='What is a computer?',max_tokens=12))
    assert response.status_code==200
    events=[json.loads(s[6:]) for s in response.text.split('\n\n') if s.startswith('data: ')]
    assert events[-1]['type']=='done'
    tokens=[e for e in events if e['type']=='token']
    assert len(tokens)>0 and not any(e['type']=='error' for e in events)
    elapsed=time.perf_counter()-start
    credits=c['client'].get(c['config']['coordinator']+'/api/credits',headers=c['auth']).json()
    assert credits['valid'] and len(credits['entries'])==2*len(tokens)
    assert {e['event']['worker'] for e in credits['entries']}=={'worker-0','worker-1'}
    assert all(e['event']['credit']+e['event']['debit']==0 for e in credits['entries'])
    page=c['client'].get(c['config']['coordinator']+'/')
    assert page.status_code==200 and 'Chat distribu' in page.text
    REPORT['chat']=dict(tokens=len(tokens),seconds=elapsed,tokens_per_second=len(tokens)/elapsed,response=tokens[-1]['text'],ledger_entries=len(credits['entries']))

def test_03_security_and_validation(cluster):
    c=cluster
    url=c['config']['coordinator']
    assert c['client'].get(url+'/api/status').status_code==401
    if c['scheme']=='https':
        with httpx.Client(trust_env=False,timeout=5) as untrusted:
            with pytest.raises(httpx.ConnectError):
                untrusted.get(url+'/api/status')
    assert c['client'].post(url+'/api/chat',headers=c['auth'],json=dict(prompt='',max_tokens=10000)).status_code==422
    assert c['client'].post(c['config']['workers']['worker-0']+'/step',json={}).status_code==401
    body=encode(dict(id='evil',url='http://169.254.169.254',spec={'index':0}))
    assert c['client'].post(url+'/internal/register',content=body,headers=headers(c['config']['cluster_secret'],body)).status_code==403
    bad=encode(dict(session=uuid.uuid4().hex,position=0,tensor=pack(torch.tensor([[-1]]))))
    assert c['client'].post(c['config']['workers']['worker-0']+'/step',content=bad,headers=headers(c['config']['cluster_secret'],bad)).status_code==422
    assigned=c['client'].get(url+'/api/status',headers=c['auth']).json()['assignments']
    wrong=encode(dict(id='worker-0',url=c['config']['workers']['worker-0'],spec=assigned['worker-1'],fingerprint='0'*64))
    assert c['client'].post(url+'/internal/register',content=wrong,headers=headers(c['config']['cluster_secret'],wrong)).status_code==409
    sid=uuid.uuid4().hex
    msg=dict(session=sid,position=1,tensor=pack(torch.tensor([[1]])))
    body=encode(msg)
    assert c['client'].post(c['config']['workers']['worker-0']+'/step',content=body,headers=headers(c['config']['cluster_secret'],body)).status_code==409

def test_04_cache_release_and_memory(cluster):
    c=cluster
    baseline=[rpc(c,i,'/status',{})['resources'] for i in range(2)]
    sid=uuid.uuid4().hex
    value=pack(torch.tensor([[1,2,3,4]]))
    for i in range(2):value=rpc(c,i,'/step',dict(session=sid,position=0,tensor=value))['tensor']
    active=[rpc(c,i,'/status',{})['resources'] for i in range(2)]
    assert all(r['cache_bytes']>0 and r['sessions']==1 for r in active)
    for i in range(2):rpc(c,i,'/release',dict(session=sid))
    final=[rpc(c,i,'/status',{})['resources'] for i in range(2)]
    assert all(r['cache_bytes']==0 and r['sessions']==0 for r in final)
    assert all(final[i]['rss']-baseline[i]['rss']<64*1024*1024 for i in range(2))
    REPORT['memory']=dict(baseline=baseline,active=active,after_release=final)

def test_05_worker_failure_and_recovery(cluster):
    c=cluster
    worker=c['workers'][1]
    worker.terminate()
    worker.wait(10)
    response=c['client'].post(c['config']['coordinator']+'/api/chat',headers=c['auth'],json=dict(prompt='Hello',max_tokens=2))
    assert response.status_code==503 or (response.status_code==200 and '"type": "error"' in response.text)
    status=rpc(c,0,'/status',{})
    assert status['resources']['sessions']==0
    c['workers'][1]=c['start']('worker',1)
    # Registration from the previous process can remain visible briefly; ensure new process responds.
    deadline=time.monotonic()+80
    while time.monotonic()<deadline:
        try:
            rpc(c,1,'/status',{})
            break
        except httpx.HTTPError:time.sleep(.5)
    c['wait']()
    response=c['client'].post(c['config']['coordinator']+'/api/chat',headers=c['auth'],json=dict(prompt='Hello',max_tokens=2))
    assert response.status_code==200 and '"type": "done"' in response.text
    REPORT['failure_recovery']='worker terminated; generation failed explicitly; cache released; worker restarted; generation succeeded'


def test_06_concurrency_and_cancel(cluster):
    c=cluster
    url=c['config']['coordinator']
    with c['client'].stream('POST',url+'/api/chat',headers=c['auth'],json=dict(prompt='Hello',max_tokens=64)) as response:
        assert response.status_code==200
        for line in response.iter_lines():
            if line.startswith('data: '):
                assert json.loads(line[6:])['type']=='token'
                break
        busy=c['client'].post(url+'/api/chat',headers=c['auth'],json=dict(prompt='Hello',max_tokens=2))
        assert busy.status_code==429
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        state=c['client'].get(url+'/api/status',headers=c['auth']).json()
        if not state['busy']:break
        time.sleep(.1)
    assert not state['busy']
    assert all(rpc(c,i,'/status',{})['resources']['sessions']==0 for i in range(2))
    REPORT['cancel_and_concurrency']='second generation rejected with 429; client disconnected; gate and both KV caches released'
