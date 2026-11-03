"""Exercise the new chat graph with already provisioned real Qwen weights.

Reuses files via hard links in the workspace. It does not download weights or
modify the live network profile.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
import httpx
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mesh.graph_plan import build_graph
from mesh.partition_store import atomic_json,digest
from simulate_hosts import stop


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',default='runtime/network')
    parser.add_argument('--port',type=int,default=8680)
    args=parser.parse_args()
    source=(ROOT/args.source).resolve()
    catalog=source/'coordinator/runtime/model-catalog'
    selected=json.loads((catalog/'current.json').read_text())['root']
    model=(source/'coordinator'/selected).resolve()
    manifest=json.loads((model/'manifest.json').read_text())
    if manifest['architecture']!='qwen2' or manifest['format']!='range-f32-v1':
        raise ValueError('Use an existing real Qwen2 range profile')
    directory=ROOT/'runtime'/('graph-chat-'+uuid.uuid4().hex[:10])
    root=directory/'model'
    root.mkdir(parents=True)
    graph=build_graph(manifest['model'],manifest['revision'],manifest['config'],None,2)
    weights={}
    for worker in ('pc-a','pc-b'):
        state=json.loads((source/worker/'runtime/model-active.json').read_text())
        part=Path(state['directory']).resolve()
        if not part.is_relative_to((source/worker/'runtime/model-parts').resolve()):
            raise ValueError('Expected the worker cache of the selected profile')
        index=json.loads((part/'weights.json').read_text())
        weights.update({name:(part/entry['file'],entry)
                        for name,entry in index['tensors'].items()})
    for i,bundle in enumerate(graph['bundles']):
        target=root/f'part-{i}'
        target.mkdir()
        index={}
        for alias,entry in bundle['tensors'].items():
            old,metadata=weights[entry['source']]
            if metadata['shape']!=entry['shape'] or entry['rows']!=[0,entry['shape'][0]]:
                raise ValueError('This verification reuses complete matrices from existing parts')
            file=hashlib.sha256(alias.encode()).hexdigest()+'.bin'
            os.link(old,target/file)
            index[alias]=dict(metadata,file=file)
        atomic_json(target/'blueprint.json',bundle)
        atomic_json(target/'spec.json',bundle['spec'])
        atomic_json(target/'config.json',bundle['config'])
        atomic_json(target/'weights.json',dict(blueprint=digest(bundle),tensors=index))
    atomic_json(root/'manifest.json',graph)
    atomic_json(root/'config.json',graph['config'])
    shutil.copytree(model/'tokenizer',root/'tokenizer')
    runtime=directory/'network'
    with (directory/'launcher.log').open('w') as log:
        child=subprocess.Popen([sys.executable,str(ROOT/'tools/run_network.py'),
            '--root',str(root),'--directory',str(runtime),'--port',str(args.port)],
            cwd=ROOT,stdout=log,stderr=log,env=dict(os.environ,PYTHONUTF8='1'))
        try:
            print('Waiting for graph chat profile:',directory,flush=True)
            deadline=time.monotonic()+300
            while time.monotonic()<deadline:
                if child.poll() is not None:raise RuntimeError('Launcher stopped; inspect logs')
                if (runtime/'ready.json').exists():break
                time.sleep(.5)
            else:raise RuntimeError('Graph chat startup timed out')
            cfg=json.loads((runtime/'config.json').read_text())
            headers={'Authorization':'Bearer '+cfg['user_token']}
            url=cfg['coordinator']
            with httpx.Client(timeout=180,trust_env=False) as client:
                response=client.post(url+'/api/chat',headers=headers,json=dict(
                    model=graph['model'],prompt='What is 2+2? Answer briefly.',max_tokens=16))
                response.raise_for_status()
                events=[json.loads(line[6:]) for line in response.text.splitlines()
                        if line.startswith('data: ')]
                assert any(e['type']=='done' for e in events),events[-3:]
                assert not any(e['type']=='error' for e in events)
                text=next(e['text'] for e in reversed(events) if e['type']=='token')
                assert '4' in text,text
                status=client.get(url+'/api/status',headers=headers).json()
                audit=client.get(url+'/api/credits',headers=headers).json()
                assert status['logical_pieces']>2 and audit['valid']
                assert not status['busy'] and status['usage']['daily_reserved']==0
                report=dict(model=graph['model'],pieces=status['logical_pieces'],
                            workers=2,tls=True,actual_weights=True,answer=text,
                            audit_valid=audit['valid'],events=events,weights_downloaded=0)
                (directory/'report.json').write_text(json.dumps(report,indent=2))
                print('Verified:',text,'•',status['logical_pieces'],'operations',flush=True)
        finally:stop(child)


if __name__=='__main__':main()
