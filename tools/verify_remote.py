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
from transformers import AutoTokenizer,GPT2LMHeadModel
from mesh.protocol import encode,headers,pack,unpack

parser=argparse.ArgumentParser()
parser.add_argument('--config',default='runtime/config.json')
parser.add_argument('--root',default='data/model')
parser.add_argument('--ca')
parser.add_argument('--output',default='runtime/remote-evidence.json')
args=parser.parse_args()
config=json.loads(Path(args.config).read_text(encoding='utf8'))
root=Path(args.root)
manifest=json.loads((root/'manifest.json').read_text())
tokenizer=AutoTokenizer.from_pretrained(root/'tokenizer',local_files_only=True)
full=GPT2LMHeadModel.from_pretrained(manifest['model'],revision=manifest['revision'],local_files_only=True,attn_implementation='eager').eval()
torch.set_num_threads(1)
auth={'Authorization':'Bearer '+config['user_token']}
report={}
with httpx.Client(verify=ssl.create_default_context(cafile=args.ca) if args.ca else True,timeout=40,trust_env=False) as client:
    status=client.get(config['coordinator']+'/api/status',headers=auth)
    status.raise_for_status()
    report['status']=status.json()
    pipeline=sorted([n for n in report['status']['nodes'] if n['online']],key=lambda n:n['spec']['index'])
    if len(pipeline)!=len(manifest['parts']):raise SystemExit('Workers incompletos')
    def rpc(node,path,message):
        body=encode(message)
        response=client.post(node['url']+path,content=body,headers=headers(config['cluster_secret'],body))
        response.raise_for_status()
        return response.json()
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
    start=time.perf_counter()
    response=client.post(config['coordinator']+'/api/chat',headers=auth,json=dict(prompt='What is a computer?',max_tokens=12))
    response.raise_for_status()
    events=[json.loads(s[6:]) for s in response.text.split('\n\n') if s.startswith('data: ')]
    assert events and events[-1]['type']=='done',events
    report['chat']=dict(events=events,seconds=time.perf_counter()-start)
    response=client.get(config['coordinator']+'/api/credits',headers=auth)
    response.raise_for_status()
    credits=response.json()
    assert credits['valid']
    report['credits']=dict(valid=credits['valid'],entries=len(credits['entries']))
output=Path(args.output)
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
print('Verificado: 8 passos numericamente equivalentes, chat e créditos. Evidência:',output)
