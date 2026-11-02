"""Arquivos privados, revisão otimista e testes Python em container opt-in."""
import ast
import difflib
import hashlib
import os
from pathlib import Path,PurePosixPath
import re
import shutil
import stat
import subprocess
import threading
import time
import uuid

class RevisionConflict(ValueError):pass

class Workspace:
    def __init__(self,root):
        self.root=Path(root).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock()

    def directory(self,user):
        root=self.root/hashlib.sha256(user.encode()).hexdigest()
        root.mkdir(exist_ok=True)
        self._plain(root)
        return root

    @staticmethod
    def _plain(path):
        if path.exists() or path.is_symlink():
            info=path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024):
                raise ValueError('Links e pontos de montagem não são permitidos')

    def path(self,user,name):
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_./-]{1,180}',name):raise ValueError('Nome de arquivo inválido')
        parts=PurePosixPath(name).parts
        if not parts or name.startswith('/') or any(p.startswith('.') or p in ('.','..') or p.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]} for p in parts) or str(PurePosixPath(name))!=name:
            raise ValueError('Caminho inválido')
        root=self.directory(user)
        target=root
        for part in parts:
            target=target/part
            self._plain(target)
        if not target.resolve().is_relative_to(root):raise ValueError('Caminho fora do projeto')
        return target

    def read(self,user,name):
        with self.lock:
            file=self.path(user,name)
            if not file.is_file():raise FileNotFoundError(name)
            if file.stat().st_size>131072:raise ValueError('Arquivo excede 128 KiB')
            data=file.read_bytes()
            return dict(path=name,content=data.decode('utf8'),revision=hashlib.sha256(data).hexdigest())

    def listing(self,user):
        with self.lock:
            root=self.directory(user)
            result=[]
            for path in root.rglob('*'):
                self._plain(path)
                if path.is_file():
                    name=path.relative_to(root).as_posix()
                    self.path(user,name)
                    result.append(dict(path=name,bytes=path.stat().st_size))
            return sorted(result,key=lambda x:x['path'])

    def write(self,user,name,content,base_revision=None):
        if not isinstance(content,str) or len(content.encode('utf8'))>131072:raise ValueError('Conteúdo excede 128 KiB')
        with self.lock:
            file=self.path(user,name)
            if file.exists() and not file.is_file():raise ValueError('O caminho é uma pasta, não um arquivo')
            old=self.read(user,name) if file.exists() else None
            if (old['revision'] if old else None)!=base_revision:raise RevisionConflict('Arquivo mudou; reabra antes de salvar')
            entries=self.listing(user)
            if len(entries)>=200 and old is None:raise ValueError('Limite de 200 arquivos')
            total=sum(e['bytes'] for e in entries)-(len(old['content'].encode()) if old else 0)+len(content.encode())
            if total>2*1024*1024:raise ValueError('Projeto excede 2 MiB')
            file.parent.mkdir(parents=True,exist_ok=True)
            temporary=file.parent/('tmp-'+uuid.uuid4().hex)
            try:
                temporary.write_text(content,encoding='utf8',newline='')
                os.replace(temporary,file)
            finally:
                temporary.unlink(missing_ok=True)
            result=self.read(user,name)
            result['diff']=''.join(difflib.unified_diff((old['content'] if old else '').splitlines(True),content.splitlines(True),fromfile=name+' (antes)',tofile=name+' (depois)'))
            return result

    def check(self,user,name):
        source=self.read(user,name)['content']
        if not name.endswith('.py'):return dict(ok=False,output='Verificação sintática disponível para arquivos Python.')
        try:ast.parse(source,filename=name)
        except SyntaxError as exc:return dict(ok=False,output=f'{name}:{exc.lineno}: {exc.msg}')
        return dict(ok=True,output=f'{name}: sintaxe Python válida. O código não foi executado.')

    def run_tests(self,user,image,timeout=15):
        """Executa somente unittest, sem shell e sem acesso à rede/host externo."""
        if not re.fullmatch(r'sha256:[0-9a-f]{64}',image):raise ValueError('Configure o ID SHA-256 da imagem aprovada')
        docker=shutil.which('docker')
        if not docker:raise RuntimeError('Docker não está disponível')
        root=self.directory(user)
        self.listing(user) # Recusa links antes de montar o projeto.
        if ',' in str(root):raise ValueError('Caminho do projeto incompatível com bind mount')
        name='ia-tests-'+uuid.uuid4().hex
        command=[docker,'run','--rm','--pull=never','--name',name,'--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--user=65534:65534','--cpus=1','--memory=256m','--memory-swap=256m','--pids-limit=64','--ulimit=nofile=128:128','--log-driver=none','--tmpfs=/tmp:rw,noexec,nosuid,size=16m','--mount',f'type=bind,source={root},target=/workspace,readonly','--workdir=/workspace',image,'python','-B','-m','unittest','discover','-s','/workspace','-p','test_*.py','-v']
        child=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        chunks=[]
        truncated=threading.Event()
        def collect():
            size=0
            while True:
                data=child.stdout.read(4096)
                if not data:break
                size+=len(data)
                chunks.append(data[:max(0,65536-(size-len(data)))])
                if size>65536:
                    truncated.set()
                    break
        reader=threading.Thread(target=collect,daemon=True)
        reader.start()
        started=time.monotonic()
        timed_out=False
        try:
            while child.poll() is None:
                if truncated.is_set() or time.monotonic()-started>timeout:
                    timed_out=time.monotonic()-started>timeout
                    subprocess.run([docker,'rm','-f',name],capture_output=True,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                    child.kill()
                    break
                time.sleep(.05)
            child.wait(timeout=10)
            reader.join(2)
            output=b''.join(chunks).decode('utf8',errors='replace')
            if timed_out:output+='\nTempo limite atingido.'
            if truncated.is_set():output+='\nSaída limitada a 64 KiB.'
            return dict(ok=child.returncode==0 and not timed_out and not truncated.is_set(),exit_code=child.returncode,output=output,timeout=timed_out,truncated=truncated.is_set(),seconds=time.monotonic()-started,isolation='docker-network-none-readonly-unprivileged')
        finally:
            if child.poll() is None:child.kill()
            subprocess.run([docker,'rm','-f',name],capture_output=True,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
