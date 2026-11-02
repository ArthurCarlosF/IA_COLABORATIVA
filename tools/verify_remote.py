"""Compara logits por RPC, executa chat e salva evidência; não simula workers."""
import argparse
import json
import os
from pathlib import Path
import sys
import ssl
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
import torch
from transformers import AutoTokenizer,AutoModelForCausalLM
from mesh.protocol import encode,headers,pack,unpack
from mesh.identity import signed_headers,verify_result,peer_for_endpoint

parser=argparse.ArgumentParser()
parser.add_argument('--config',default='runtime/config.json')
parser.add_argument('--root',default='data/model')
parser.add_argument('--ca')
parser.add_argument('--coding-task',action='store_true')
parser.add_argument('--output',default='runtime/remote-evidence.json')
args=parser.parse_args()
config=json.loads(Path(args.config).read_text(encoding='utf8'))
root=Path(args.root)
manifest=json.loads((root/'manifest.json').read_text())
tokenizer=AutoTokenizer.from_pretrained(root/'tokenizer',local_files_only=True)
torch.set_num_threads(1)
full=AutoModelForCausalLM.from_pretrained(manifest['model'],revision=manifest['revision'],local_files_only=True,attn_implementation='eager',torch_dtype=torch.float32).eval()
torch.set_num_threads(1)
auth={'Authorization':'Bearer '+config['user_token']}
identity=json.loads(Path(config['peer_network']['identity_files']['coordinator']).read_text()) if config.get('peer_network') else None
report={}
with httpx.Client(verify=ssl.create_default_context(cafile=args.ca) if args.ca else True,timeout=40,trust_env=False) as client:
    status=client.get(config['coordinator']+'/api/status',headers=auth)
    status.raise_for_status()
    report['status']=status.json()
    pipeline=sorted([n for n in report['status']['nodes'] if n['online']],key=lambda n:n['spec']['index'])
    if len(pipeline)!=len(manifest['parts']):raise SystemExit('Workers incompletos')
    def rpc(node,path,message):
        body=encode(message)
        response=client.post(node['url']+path,content=body,headers=signed_headers(config['cluster_secret'],body,path,identity))
        response.raise_for_status()
        result=response.json()
        if identity and path=='/step':verify_result(result,message,peer_for_endpoint(config['peer_network']['trusted'],node['url']))
        return result
    sid=uuid.uuid4().hex
    ids=tokenizer.encode('What is artificial intelligence?',return_tensors='pt')
    position=0
    past=None
    errors=[]
    start=time.perf_counter()
    try:
        with torch.inference_mode():
            for step in range(8):
                ref=full(ids,past_key_values=past,use_cache=True)
                past=ref.past_key_values
                value=pack(ids)
                for node in pipeline:value=rpc(node,'/step',dict(session=sid,position=position,tensor=value))['tensor']
                distributed=unpack(value)
                errors.append((distributed-ref.logits[:,-1:,:]).abs().max().item())
                torch.testing.assert_close(distributed,ref.logits[:,-1:,:],rtol=1e-5,atol=1e-6)
                token=int(distributed[0,-1].argmax())
                assert token==int(ref.logits[0,-1].argmax())
                position+=ids.shape[1]
                ids=torch.tensor([[token]])
    finally:
        for node in pipeline:
            try:rpc(node,'/release',dict(session=sid))
            except httpx.HTTPError:pass
    report['numerical']=dict(steps=8,max_abs_error=max(errors),seconds=time.perf_counter()-start)
    # A referência só serve à comparação; não deve ocupar RAM durante geração/testes.
    del full,ref,past
    import gc
    gc.collect()
    start=time.perf_counter()
    response=client.post(config['coordinator']+'/api/chat',headers=auth,json=dict(prompt='What is a computer?',max_tokens=12))
    response.raise_for_status()
    events=[json.loads(s[6:]) for s in response.text.split('\n\n') if s.startswith('data: ')]
    assert events and events[-1]['type']=='done',events
    report['chat']=dict(events=events,seconds=time.perf_counter()-start)
    if args.coding_task:
        import ast
        import re
        response=client.post(config['coordinator']+'/api/chat',headers=auth,json=dict(prompt='Write a Python function named add that takes a and b and returns their sum. Return only the Python code.',max_tokens=128))
        response.raise_for_status()
        coding_events=[json.loads(s[6:]) for s in response.text.split('\n\n') if s.startswith('data: ')]
        assert coding_events and coding_events[-1]['type']=='done',coding_events
        emitted=[e['text'] for e in coding_events if e['type']=='token']
        code=emitted[-1].strip() if emitted else ''
        fenced=re.search(r'```(?:python)?\s*\n(.*?)```',code,re.S)
        if fenced:code=fenced.group(1).strip()
        tree=ast.parse(code)
        allowed=(ast.Module,ast.FunctionDef,ast.arguments,ast.arg,ast.Return,ast.BinOp,ast.Add,ast.Name,ast.Load,ast.Constant,ast.Expr)
        assert len(list(ast.walk(tree)))<=100 and all(isinstance(n,allowed) for n in ast.walk(tree)),'Código fora do teste aritmético seguro'
        assert len(tree.body)==1 and isinstance(tree.body[0],ast.FunctionDef) and tree.body[0].name=='add'
        assert not tree.body[0].decorator_list and not tree.body[0].args.defaults
        namespace={'__builtins__':{'int':int,'float':float}}
        exec(compile(tree,'<generated-add>','exec'),namespace)
        cases=[(2,3,5),(-4,1,-3),(0,0,0)]
        for a,b,expected in cases:assert namespace['add'](a,b)==expected
        report['coding_task']=dict(code=code,cases=cases,passed=True,model=manifest['model'])
    if args.coding_task:
        files={'add.py':report['coding_task']['code']+'\n','test_add.py':'import unittest\nfrom add import add\nclass TestAdd(unittest.TestCase):\n    def test_positive(self): self.assertEqual(add(2,3),5)\n    def test_negative(self): self.assertEqual(add(-4,1),-3)\n    def test_zero(self): self.assertEqual(add(0,0),0)\n'}
        for name,content in files.items():
            old=client.get(config['coordinator']+'/api/workspace/file',headers=auth,params={'path':name})
            base=old.json()['revision'] if old.status_code==200 else None
            saved=client.post(config['coordinator']+'/api/workspace/file',headers=auth,json=dict(path=name,content=content,base_revision=base))
            saved.raise_for_status()
        checked=client.post(config['coordinator']+'/api/workspace/check',headers=auth,json=dict(path='add.py'))
        checked.raise_for_status()
        report['workspace_syntax']=checked.json()
        assert report['workspace_syntax']['ok']
        if config.get('sandbox_image'):
            tested=client.post(config['coordinator']+'/api/workspace/tests',headers=auth,json={})
            tested.raise_for_status()
            report['workspace_tests']=tested.json()
            assert report['workspace_tests']['ok'],report['workspace_tests']
        else:report['workspace_tests']=dict(skipped=True,reason='Imagem/executor Docker não habilitado; arquivos e sintaxe validados')
    response=client.get(config['coordinator']+'/api/credits',headers=auth)
    response.raise_for_status()
    credits=response.json()
    assert credits['valid']
    report['credits']=dict(valid=credits['valid'],entries=len(credits['entries']))
    if identity:
        import base64
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        proofs=[proof for entry in credits['entries'] for proof in (entry['event'].get('proof') or [])]
        assert proofs,'Recibos assinados ausentes no extrato'
        for proof in proofs:
            public=config['peer_network']['trusted'][proof['peer_id']]['public_key']
            signed={key:value for key,value in proof.items() if key!='signature'}
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(public)).verify(base64.b64decode(proof['signature']),encode(signed))
        report['credits']['verified_individual_receipts']=len(proofs)
output=Path(args.output)
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
print('Verificado: 8 passos numericamente equivalentes, chat e créditos. Evidência:',output)
