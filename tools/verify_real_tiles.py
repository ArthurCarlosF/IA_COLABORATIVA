"""Compare two real source tiles on two actual small arithmetic worker processes."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
import uuid
import httpx
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from simulate_hosts import stop
from mesh.durable_tiles import tile_bytes
from mesh.slow_inference import run_slow
from mesh.tile_worker import TileClient,TilePool


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--job',default='runtime/slow-480b-proof')
    args=parser.parse_args()
    previous=Path(args.job)
    settings=json.loads((previous/'job.json').read_text(encoding='utf8'))
    program=json.loads((previous/'program.json').read_text(encoding='utf8'))
    with sqlite3.connect(previous/'matrices.sqlite') as local:
        expected=local.execute('SELECT next_column,partial FROM tile_rows WHERE row_start=0').fetchall()
    if len(expected)!=1 or expected[0][0]!=2*settings['tile_columns']:
        raise ValueError('Reference must be paused after exactly two tiles in the first row block')
    directory=ROOT/'runtime'/('real-microtiles-'+uuid.uuid4().hex[:10])
    directory.mkdir(parents=True)
    secret=secrets.token_hex(32)
    config=directory/'worker-config.json'
    config.write_text(json.dumps(dict(tile_secret=secret)))
    children=[];logs=[];urls=[]
    try:
        for index in range(2):
            with socket.socket() as server:
                server.bind(('127.0.0.1',0));port=server.getsockname()[1]
            url=f'http://127.0.0.1:{port}'
            urls.append(url)
            log=(directory/f'worker-{index}.log').open('w')
            logs.append(log)
            children.append(subprocess.Popen([sys.executable,'-m','mesh','tile-worker',
                '--config',str(config),'--port',str(port),'--tile-kib','2'],
                cwd=directory,env=dict(os.environ,PYTHONPATH=str(ROOT)),
                stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0))
        with httpx.Client(timeout=30,trust_env=False) as worker,httpx.Client(
                timeout=60,follow_redirects=True,trust_env=False) as source:
            kernels=[TileClient(url,secret,worker) for url in urls]
            for kernel in kernels:
                deadline=time.monotonic()+45
                while True:
                    try:kernel(np.ones((1,1),np.float32),np.ones((1,1),np.float32),2048);break
                    except httpx.TransportError:
                        if time.monotonic()>=deadline:raise
                        time.sleep(.25)
            counts=[0,0]
            def observed(index):
                def compute(a,w,budget):
                    output=kernels[index](a,w,budget)
                    counts[index]+=1
                    return output
                return compute
            pool=TilePool([observed(0),observed(1)])
            result=asyncio.run(run_slow(program,settings['ids'],directory,
                settings['tokens'],settings['eos'],source,maximum_tiles=2,
                tile_rows=settings['tile_rows'],tile_columns=settings['tile_columns'],
                maximum_bytes=settings['maximum_bytes'],kernel=pool,kernel_id='two-http-fp32-workers-v1'))
        with sqlite3.connect(directory/'matrices.sqlite') as remote:
            actual=remote.execute('SELECT next_column,partial FROM tile_rows WHERE row_start=0').fetchall()
        assert result['status']=='paused' and result['tiles_executed']==2
        assert counts==[1,1] and len(actual)==1 and actual[0][0]==expected[0][0]
        np.testing.assert_allclose(np.frombuffer(actual[0][1],np.float32),
                                   np.frombuffer(expected[0][1],np.float32),atol=1e-6,rtol=1e-6)
        evidence=dict(model=program['model'],revision=program['revision'],
            working_bytes_per_tile=tile_bytes(1,settings['tile_rows'],settings['tile_columns']),
            tiles_per_worker=counts,column=actual[0][0],bit_identical=actual[0][1]==expected[0][1],
            real_checkpoint_tiles=True,full_model_generation=False,**result)
        (directory/'report.json').write_text(json.dumps(evidence,indent=2))
        print(json.dumps(evidence,indent=2))
        print('Report:',directory/'report.json')
    finally:
        for child in children:stop(child)
        for log in logs:log.close()


if __name__=='__main__':main()
