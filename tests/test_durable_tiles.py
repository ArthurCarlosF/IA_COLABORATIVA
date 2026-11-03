import os
from pathlib import Path
import subprocess
import sys
import numpy as np
import pytest
from mesh.durable_tiles import DurableMatmul, matmul_tile, tile_bytes


def test_forced_process_exit_resumes_after_last_committed_tile(tmp_path):
    rng=np.random.default_rng(53)
    a=rng.normal(size=(2,11)).astype('float32')
    w=rng.normal(size=(7,11)).astype('float32')
    np.save(tmp_path/'a.npy',a)
    np.save(tmp_path/'w.npy',w)
    root=Path(__file__).resolve().parents[1]
    child=subprocess.run([sys.executable,'-c',
        "import os,numpy as np;from mesh.durable_tiles import DurableMatmul;"
        "a=np.load('a.npy');w=np.load('w.npy');s=DurableMatmul('jobs.db',3,4);"
        "s.run(a,'immutable',w.shape,lambda r,z,c,d:w[r:z,c:d],"
        "after_commit=lambda _:os._exit(17))"],
        cwd=tmp_path,env=dict(os.environ,PYTHONPATH=str(root)),timeout=60)
    assert child.returncode==17
    store=DurableMatmul(tmp_path/'jobs.db',3,4)
    reads=[]
    def fetch(r,z,c,d):
        reads.append((r,z,c,d))
        return w[r:z,c:d]
    try:
        result=store.run(a,'immutable',w.shape,fetch)
        assert result['status']=='completed' and result['executed']==8
        assert reads[0]==(0,3,4,8) and (0,3,0,4) not in reads
        np.testing.assert_allclose(result['output'],a@w.T,rtol=1e-6,atol=1e-6)
        again=store.run(a,'immutable',w.shape,lambda *args:pytest.fail('Read completed weights'))
        assert again['executed']==0
        np.testing.assert_array_equal(again['output'],result['output'])
    finally:store.close()


def test_tile_budget_refuses_before_fetch_and_detects_corruption(tmp_path):
    a=np.ones((1,16),np.float32)
    w=np.ones((4,16),np.float32)
    with pytest.raises(ValueError,match='working memory'):
        matmul_tile(a,w,maximum_bytes=32)
    store=DurableMatmul(tmp_path/'tiny.db',2,4,maximum_bytes=32)
    try:
        with pytest.raises(ValueError,match='before fetching'):
            store.run(a,'tiny',w.shape,lambda *args:pytest.fail('Fetch out of budget'))
    finally:store.close()
    store=DurableMatmul(tmp_path/'valid.db',2,4)
    try:
        result=store.run(a,'tiny',w.shape,lambda r,z,c,d:w[r:z,c:d],max_tiles=1)
        assert result['status']=='paused'
        with store.db:store.db.execute("UPDATE tile_rows SET partial=x'00'")
        with pytest.raises(ValueError,match='Corrupted'):
            store.run(a,'tiny',w.shape,lambda *args:pytest.fail('Fetch on corrupt state'))
    finally:store.close()
