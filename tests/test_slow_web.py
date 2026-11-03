import time

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from mesh.slow_web import SlowJobs


def make_app(path):
    app = FastAPI()

    def auth(request):
        user = request.headers.get('authorization')
        if not user:
            raise HTTPException(401)
        return user

    async def body(request):
        return await request.json()

    jobs = SlowJobs(app, path, auth, lambda r: r.client.host == '127.0.0.1',
                    lambda r, _: body(r))
    return app, jobs


def test_slow_jobs_local_and_bounded(tmp_path):
    app, _ = make_app(tmp_path)
    h = {'authorization': 'local-user'}
    path = '/api/slow/jobs'
    with TestClient(app) as remote:
        assert remote.get(path).status_code == 401
        assert remote.get(path, headers=h).status_code == 403
    with TestClient(app, client=('127.0.0.1', 1234)) as client:
        assert client.get(path, headers={'authorization': 'guest'}).status_code == 403
        assert client.get(path + '/secret.json', headers=h).status_code == 404
        for data in ({'tiles': 1025}, {'tiles': True}, {'profile': 'elsewhere'},
                     {'tile_endpoint': 'http://127.0.0.1:1234'}, {'prompt': ' '}):
            body = {'profile': 'coder-480b', 'prompt': 'hello', **data}
            assert client.post(path, headers=h, json=body).status_code == 422
        assert client.get(path, headers=h).json()['jobs'] == []


def test_pause_and_restart_keep_same_job(tmp_path):
    app, jobs = make_app(tmp_path)
    h = {'authorization': 'local-user'}
    path = '/api/slow/jobs'
    with TestClient(app, client=('127.0.0.1', 1234)) as client:
        response = client.post(path, headers=h, json={
            'profile': 'coder-480b', 'prompt': 'Preserve this prompt', 'tiles': 1})
        assert response.status_code == 202
        job = response.json()['id']
        assert client.post(path + '/' + job + '/resume', headers=h,
                           json={'tiles': 1}).status_code == 409
        assert client.post(path + '/' + job + '/pause', headers=h).status_code == 202
        deadline = time.monotonic() + 45
        while jobs.active is not None and time.monotonic() < deadline:
            time.sleep(.1)
        assert jobs.active is None
    app, _ = make_app(tmp_path)
    with TestClient(app, client=('127.0.0.1', 1234)) as client:
        saved = client.get(path + '/' + job, headers=h).json()
        assert saved['status'] == 'paused'
        assert saved['prompt'] == 'Preserve this prompt'
