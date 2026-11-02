"""Smoke real da aplicação, sem carregar um modelo de referência inteiro."""
import argparse
import ast
import base64
import json
from pathlib import Path
import re
import sys
import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mesh.protocol import encode,headers

parser=argparse.ArgumentParser()
parser.add_argument('--directory',default='runtime/network')
args=parser.parse_args()
directory=(ROOT/args.directory).resolve()
config=json.loads((directory/'active-config.json').read_text(encoding='utf8'))
url=config['coordinator']
auth={'Authorization':'Bearer '+config['user_token']}
report=dict(full_reference_comparison=False)
def checkpoint(stage):
    report['stage']=stage
    (directory/'smoke-evidence.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    print(stage,flush=True)
with httpx.Client(timeout=60,trust_env=False) as client:
    def get(path,identity=auth):
        response=client.get(url+path,headers=identity);response.raise_for_status();return response.json()
    def post(path,value,identity=auth):
        response=client.post(url+path,headers=identity,json=value);response.raise_for_status();return response.json()
    def chat(prompt,max_tokens=128,identity=auth):
        response=client.post(url+'/api/chat',headers=identity,json=dict(prompt=prompt,max_tokens=max_tokens));response.raise_for_status()
        events=[json.loads(part[6:]) for part in response.text.split('\n\n') if part.startswith('data: ')]
        assert events and events[-1]['type']=='done',events
        text=[e['text'] for e in events if e['type']=='token']
        return text[-1] if text else ''
    def save(name,content):
        response=client.get(url+'/api/workspace/file',headers=auth,params={'path':name})
        previous=response.json()['revision'] if response.status_code==200 else None
        return post('/api/workspace/file',dict(path=name,content=content,base_revision=previous))
    state=get('/api/status')
    assert len([n for n in state['nodes'] if n['online']])==2
    report['model']=state['model'];report['scheduler']=state['scheduler'];checkpoint('workers_ready')
    code=chat('Write a Python function named add that takes a and b and returns their sum. Return only the Python code.')
    fenced=re.search(r'```(?:python)?\s*\n(.*?)```',code,re.S)
    if fenced:code=fenced.group(1)
    tree=ast.parse(code.strip())
    allowed=(ast.Module,ast.FunctionDef,ast.arguments,ast.arg,ast.Return,ast.BinOp,ast.Add,ast.Name,ast.Load,ast.Constant,ast.Expr)
    assert len(list(ast.walk(tree)))<100 and all(isinstance(node,allowed) for node in ast.walk(tree))
    assert len(tree.body)==1 and tree.body[0].name=='add' and not tree.body[0].decorator_list and not tree.body[0].args.defaults
    scope={'__builtins__':{'int':int,'float':float}}
    exec(compile(tree,'<checked-generated-add>','exec'),scope)
    for a,b,c in [(2,3,5),(-4,1,-3),(0,0,0)]:assert scope['add'](a,b)==c
    report['python']=dict(code=code.strip(),three_cases_passed=True);checkpoint('python_generated_and_checked')
    save('add.py',code.strip()+'\n')
    report['syntax']=post('/api/workspace/check',dict(path='add.py'))
    assert report['syntax']['ok']
    save('test_add.py','import unittest\nfrom add import add\nclass TestAdd(unittest.TestCase):\n    def test_sum(self): self.assertEqual(add(2,3),5)\n')
    peer={'Authorization':'Bearer '+config['accounts']['peer-user']}
    assert client.get(url+'/api/workspace/file',headers=peer,params={'path':'add.py'}).status_code==404
    checkpoint('private_files_saved')
    # Uma contribuição real na direção oposta deve criar extra para a conta principal.
    before=get('/api/usage')
    chat('Hello',2,peer)
    after=get('/api/usage')
    assert after['earned_total']>before['earned_total']
    report['usage']=after
    audit=get('/api/credits')
    assert audit['valid']
    proofs=[p for row in audit['entries'] for p in (row['event'].get('proof') or [])]
    assert proofs
    for proof in proofs:
        public=config['peer_network']['trusted'][proof['peer_id']]['public_key']
        signed={key:value for key,value in proof.items() if key!='signature'}
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public)).verify(base64.b64decode(proof['signature']),encode(signed))
    report['verified_receipts']=len(proofs)
    report['peers']=get('/api/peers')
    report['container_tests']=dict(skipped=True,reason='Docker não habilitado neste perfil') if not config.get('sandbox_image') else post('/api/workspace/tests',{})
    if config.get('sandbox_image'):assert report['container_tests']['ok']
    report['passed']=True
    checkpoint('application_smoke_passed')
