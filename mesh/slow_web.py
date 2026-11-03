"""Local operator control for durable, isolated inference batches."""
import asyncio
import json
import os
import re
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path
from time import time
from types import SimpleNamespace

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .partition_store import PROFILES, atomic_json


class Batch(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    tiles: int = Field(default=16, ge=1, le=1024)


class Job(Batch):
    profile: str
    prompt: str = Field(min_length=1, max_length=6000)
    tokens: int = Field(default=32, ge=1, le=512)


def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf8'))
    except FileNotFoundError:
        return None


class SlowJobs:
    def __init__(self, app, root, auth, local_operator, bounded_json):
        self.root = Path(root).resolve()
        self.active = None
        self.task = None
        self.process = None
        self.pause_file = None

        def operator(request):
            if auth(request) != 'local-user' or not local_operator(request):
                raise HTTPException(403, 'Modo lento disponível para o operador neste computador')

        async def payload(request, schema):
            try:
                return schema.model_validate(await bounded_json(request, 32000))
            except ValidationError as exc:
                raise HTTPException(422, 'Parâmetros do trabalho inválidos') from exc

        @app.get('/api/slow/jobs')
        async def jobs(request: Request):
            operator(request)
            records = [read_json(p) for p in self.root.glob('*/request.json')]
            records = sorted((r for r in records if r),
                             key=lambda r: (r['id'] == self.active, r['created']), reverse=True)
            return dict(jobs=[self.status(self.root / r['id'], r) for r in records[:30]],
                        profiles=[dict(profile=k, model=v[0]) for k, v in PROFILES.items()])

        @app.post('/api/slow/jobs', status_code=202)
        async def start(request: Request):
            operator(request)
            data = await payload(request, Job)
            if data.profile not in PROFILES or not data.prompt.strip():
                raise HTTPException(422, 'Informe um modelo e uma pergunta válidos')
            self.check_idle()
            record = dict(id=uuid.uuid4().hex, profile=data.profile, prompt=data.prompt,
                          tokens=data.tokens, created=time())
            directory = self.root / record['id']
            directory.mkdir(parents=True)
            atomic_json(directory / 'request.json', record)
            self.launch(directory, data.tiles)
            return self.status(directory, record)

        @app.get('/api/slow/jobs/{job}')
        async def detail(job: str, request: Request):
            operator(request)
            return self.status(*self.find(job))

        @app.post('/api/slow/jobs/{job}/resume', status_code=202)
        async def resume(job: str, request: Request):
            operator(request)
            data = await payload(request, Batch)
            directory, record = self.find(job)
            self.check_idle()
            if self.status(directory, record)['status'] == 'completed':
                raise HTTPException(409, 'Trabalho já concluído')
            self.launch(directory, data.tiles)
            return self.status(directory, record)

        @app.post('/api/slow/jobs/{job}/pause', status_code=202)
        async def pause(job: str, request: Request):
            operator(request)
            directory, record = self.find(job)
            if self.active == job:
                self.pause_file.touch()
            return self.status(directory, record)

    def find(self, job):
        if not re.fullmatch(r'[0-9a-f]{32}', job):
            raise HTTPException(404, 'Trabalho não encontrado')
        directory = self.root / job
        record = read_json(directory / 'request.json')
        if record is None:
            raise HTTPException(404, 'Trabalho não encontrado')
        return directory, record

    def status(self, directory, record):
        result = read_json(directory / 'last-result.json')
        failure = read_json(directory / 'failure.json')
        if self.active == record['id']:
            status = 'pausing' if self.pause_file.exists() else 'running'
        elif failure:
            status = 'failed'
        else:
            status = result['status'] if result else 'paused'
        return dict(**record, status=status, result=result, error=failure)

    def check_idle(self):
        if self.active is not None:
            raise HTTPException(409, 'Já existe um lote em execução neste computador')

    def launch(self, directory, tiles):
        (directory / 'failure.json').unlink(missing_ok=True)
        marker = directory / ('pause-' + uuid.uuid4().hex)
        self.active, self.pause_file = directory.name, marker
        self.task = asyncio.create_task(self.run(directory, tiles, marker))

    async def run(self, directory, tiles, marker):
        try:
            with (directory / 'batch.log').open('wb') as log:
                self.process = subprocess.Popen(
                    [sys.executable, '-m', 'mesh.slow_web', str(directory), str(tiles), marker.name],
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                )
            while self.process.poll() is None:
                await asyncio.sleep(.2)
            if self.process.returncode and not marker.exists():
                atomic_json(directory / 'failure.json',
                            'O lote falhou. Confira batch.log na pasta local e tente retomar.')
        except OSError:
            atomic_json(directory / 'failure.json', 'Não foi possível iniciar o motor local.')
        finally:
            marker.unlink(missing_ok=True)
            self.active = self.process = self.pause_file = None

    async def close(self):
        if self.active is None:
            return
        self.pause_file.touch()
        try:
            await asyncio.wait_for(asyncio.shield(self.task), timeout=5)
        except TimeoutError:
            if self.process and self.process.poll() is None:
                try:
                    self.process.terminate()
                except ProcessLookupError:
                    pass
            await self.task


def run_child(directory, tiles, marker):
    # The lease is held by the process doing the work, including after a
    # coordinator crash. Closing the connection releases it on every exit.
    lock = sqlite3.connect(directory.parent / 'batch-lease.sqlite', timeout=.2)
    try:
        lock.execute('BEGIN EXCLUSIVE')
        if marker.exists():
            return
        from .slow_cli import run_batch
        record = read_json(directory / 'request.json')
        initial = not (directory / 'job.json').exists()
        args = SimpleNamespace(job=directory, max_tiles=tiles, tile_endpoint=None,
                               tile_config=None, ca=None, tile_rows=1,
                               tile_columns=4096, tile_kib=64,
                               prompt=record['prompt'] if initial else None,
                               model_profile=record['profile'] if initial else None,
                               tokens=record['tokens'] if initial else None)
        run_batch(args, SimpleNamespace(is_set=marker.exists))
    finally:
        lock.close()


if __name__ == '__main__':
    job_dir = Path(sys.argv[1])
    run_child(job_dir, int(sys.argv[2]), job_dir / sys.argv[3])
