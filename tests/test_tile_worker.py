import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import httpx
import numpy as np
import psutil
import pytest
from mesh.tile_worker import TileClient


def test_small_tile_on_another_process_with_auth_and_budget(tmp_path):
    root=Path(__file__).resolve().parents[1]
    secret='test-only-microtile-secret-'*3
    cfg=tmp_path/'config.json'
    cfg.write_text(json.dumps(dict(tile_secret=secret)))
    with socket.socket() as server:
        server.bind(('127.0.0.1',0))
        port=server.getsockname()[1]
    with (tmp_path/'worker.log').open('w') as log:
        worker=subprocess.Popen([sys.executable,'-m','mesh','tile-worker',
            '--config',str(cfg),'--port',str(port),'--tile-kib','2'],
            cwd=tmp_path,env=dict(os.environ,PYTHONPATH=str(root)),
            stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            url=f'http://127.0.0.1:{port}'
            a=np.arange(64,dtype=np.float32).reshape(1,64)/64
            w=np.arange(256,dtype=np.float32).reshape(4,64)/256
            with httpx.Client(timeout=4,trust_env=False) as client:
                kernel=TileClient(url,secret,client)
                deadline=time.monotonic()+60
                while time.monotonic()<deadline:
                    try:result=kernel(a,w,2048);break
                    except httpx.TransportError:
                        if worker.poll() is not None:pytest.fail('Tile worker stopped')
                        time.sleep(.2)
                else:pytest.fail('Tile worker startup timeout')
                np.testing.assert_allclose(result,a@w.T,rtol=1e-6,atol=1e-6)
                with pytest.raises(httpx.HTTPStatusError) as denied:
                    TileClient(url,'wrong-token-'*4,client)(a,w,2048)
                assert denied.value.response.status_code==401
                with pytest.raises(httpx.HTTPStatusError) as rejected:
                    kernel(np.ones((8,1),np.float32),np.ones((16,1),np.float32),65536)
                assert rejected.value.response.status_code==422
        finally:
            try:
                process=psutil.Process(worker.pid)
                for child in reversed(process.children(recursive=True)):
                    try:child.terminate()
                    except psutil.NoSuchProcess:pass
                process.terminate()
            except psutil.NoSuchProcess:pass
            worker.wait(timeout=15)
