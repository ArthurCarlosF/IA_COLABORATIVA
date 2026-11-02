"""Descoberta por gossip assinado entre identidades previamente autorizadas.

Não implementa consenso de créditos, prova de inferência ou identidade pública anti-Sybil.
"""
import base64
import hashlib
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit
import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey,Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from .protocol import encode


def new_identity():
    key=Ed25519PrivateKey.generate()
    private=key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption()).hex()
    public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw).hex()
    return dict(peer_id=hashlib.sha256(bytes.fromhex(public)).hexdigest()[:40],public_key=public,private_key=private)


def safe_endpoint(value):
    if not isinstance(value,str) or len(value)>256:raise ValueError('Endpoint inválido')
    url=urlsplit(value)
    if url.scheme not in ('http','https') or not url.hostname or url.username or url.password or url.path not in ('','/') or url.query or url.fragment:
        raise ValueError('Endpoint inválido')
    if url.scheme!='https' and url.hostname not in ('localhost','127.0.0.1','::1'):raise ValueError('Endpoint remoto exige HTTPS')
    return value.rstrip('/')

class PeerDirectory:
    def __init__(self,identity,endpoint,trusted,capability,state_path=None,now=None):
        self.identity=identity
        self.endpoint=safe_endpoint(endpoint)
        self.trusted=trusted
        if not 1<=len(trusted)<=64:raise ValueError('Limite de 64 identidades autorizadas')
        self.clock=now or time.time
        self.capability=capability
        self.key=Ed25519PrivateKey.from_private_bytes(bytes.fromhex(identity['private_key']))
        public=self.key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw).hex()
        if public!=identity['public_key'] or hashlib.sha256(bytes.fromhex(public)).hexdigest()[:40]!=identity['peer_id']:
            raise ValueError('Identidade inconsistente')
        for peer_id,entry in trusted.items():
            if hashlib.sha256(bytes.fromhex(entry['public_key'])).hexdigest()[:40]!=peer_id:raise ValueError('Identidade autorizada inválida')
            for url in entry['endpoints']:safe_endpoint(url)
        if identity['peer_id'] not in trusted or self.endpoint not in trusted[identity['peer_id']]['endpoints']:
            raise ValueError('Identidade/endpoint próprio não autorizado')
        self.state_path=Path(state_path) if state_path else None
        self.lock=threading.RLock()
        self.records={}
        self.last_issued=0
        self.stats=dict(accepted=0,rejected=0,exchanges=0,last_error=None)
        if self.state_path and self.state_path.exists():
            if self.state_path.stat().st_size>1024*1024:raise ValueError('Arquivo de contatos excede limite')
            cached=json.loads(self.state_path.read_text(encoding='utf8'))
            for record in cached[:64]:
                try:self.accept(record,persist=False)
                except (ValueError,KeyError,TypeError):pass

    def _save(self):
        if self.state_path:
            self.state_path.parent.mkdir(parents=True,exist_ok=True)
            temporary=self.state_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(list(self.records.values())),encoding='utf8')
            temporary.replace(self.state_path)

    def own_record(self):
        with self.lock:
            issued=max(int(self.clock()*1000),self.last_issued+1)
            self.last_issued=issued
            payload=dict(version=1,peer_id=self.identity['peer_id'],public_key=self.identity['public_key'],endpoint=self.endpoint,issued_ms=issued,expires_ms=issued+30000,capability=self.capability)
            envelope=dict(payload=payload,signature=base64.b64encode(self.key.sign(encode(payload))).decode())
            self.accept(envelope)
            return envelope

    def accept(self,envelope,persist=True):
        try:
            if not isinstance(envelope,dict) or set(envelope)!={'payload','signature'} or len(encode(envelope))>16384:raise ValueError('Anúncio inválido')
            p=envelope['payload']
            if set(p)!={'version','peer_id','public_key','endpoint','issued_ms','expires_ms','capability'} or p['version']!=1:raise ValueError('Formato inválido')
            entry=self.trusted.get(p['peer_id'])
            if not entry or p['public_key']!=entry['public_key'] or p['endpoint'] not in entry['endpoints']:raise ValueError('Identidade/endereço não autorizado')
            now=int(self.clock()*1000)
            if type(p['issued_ms']) is not int or type(p['expires_ms']) is not int or p['issued_ms']>now+5000 or not p['issued_ms']<p['expires_ms']<=p['issued_ms']+30000 or p['expires_ms']<=now:
                raise ValueError('Anúncio vencido ou relógio inválido')
            if not isinstance(p['capability'],dict) or len(encode(p['capability']))>4096:raise ValueError('Capacidade inválida')
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(p['public_key'])).verify(base64.b64decode(envelope['signature'],validate=True),encode(p))
            with self.lock:
                old=self.records.get(p['peer_id'])
                if old:
                    if old==envelope:return False
                    if old['payload']['issued_ms']>=p['issued_ms']:raise ValueError('Replay ou versão conflitante')
                self.records[p['peer_id']]=json.loads(encode(envelope))
                self.stats['accepted']+=1
                if persist:self._save()
            return True
        except Exception as exc:
            self.stats['rejected']+=1
            raise ValueError('Anúncio de participante recusado') from exc

    def snapshot(self):
        with self.lock:
            now=int(self.clock()*1000)
            return [record for record in self.records.values() if record['payload']['expires_ms']>now]

class Gossip:
    def __init__(self,directory,seeds,verify=True):
        self.directory=directory
        allowed={url for value in directory.trusted.values() for url in value['endpoints']}
        if any(url not in allowed for url in seeds):raise ValueError('Contato inicial fora da lista autorizada')
        self.seeds=seeds
        self.verify=verify
        self.stop=threading.Event()
        self.thread=None

    def start(self):
        self.thread=threading.Thread(target=self.run,daemon=True)
        self.thread.start()

    def run(self):
        with httpx.Client(verify=self.verify,timeout=1,trust_env=False) as client:
            while not self.stop.is_set():
                try:own=self.directory.own_record()
                except Exception as exc:
                    self.directory.stats['last_error']=type(exc).__name__
                    self.stop.wait(2)
                    continue
                contacts=list(dict.fromkeys([*self.seeds,*[r['payload']['endpoint'] for r in self.directory.snapshot()]]))
                for url in contacts[:8]:
                    if self.stop.is_set():break
                    if url==self.directory.endpoint:continue
                    try:
                        with client.stream('POST',url+'/p2p/announce',content=encode(own),headers={'Content-Type':'application/json'}) as result:
                            result.raise_for_status()
                        data=bytearray()
                        with client.stream('GET',url+'/p2p/peers') as result:
                            result.raise_for_status()
                            for chunk in result.iter_bytes():
                                data.extend(chunk)
                                if len(data)>1024*1024:raise ValueError('Lista de contatos excede limite')
                        records=json.loads(data)['records']
                        if not isinstance(records,list) or len(records)>64:raise ValueError('Lista inválida')
                        for record in records:
                            try:self.directory.accept(record)
                            except ValueError:pass
                        self.directory.stats['exchanges']+=1
                        self.directory.stats['last_error']=None
                    except Exception as exc:self.directory.stats['last_error']=type(exc).__name__
                self.stop.wait(2)

    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(5)


def attach(app,identity_file,endpoint,trusted,seeds,capability,verify=True,state_path=None):
    from fastapi import Request,HTTPException
    identity=json.loads(Path(identity_file).read_text(encoding='utf8'))
    directory=PeerDirectory(identity,endpoint,trusted,capability,state_path)
    gossip=Gossip(directory,seeds,verify)
    app.state.peers=directory
    @app.get('/p2p/peers')
    async def peers():
        return dict(records=directory.snapshot(),mode='signed-permissioned-gossip')
    @app.post('/p2p/announce')
    async def announce(request:Request):
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>16384:raise HTTPException(413,'Anúncio excede limite')
        try:accepted=directory.accept(json.loads(body))
        except (ValueError,TypeError):raise HTTPException(403,'Anúncio inválido ou identidade não autorizada')
        return dict(accepted=accepted)
    return gossip
