"""Perfil local persistente: aplicação separada da simulação/benchmark."""
import argparse
import datetime
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import sys
import time

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from simulate_hosts import stop

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mesh.discovery import new_identity


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8400)
    parser.add_argument('--root',default='data/qwen-coder')
    parser.add_argument('--directory',default='runtime/network')
    parser.add_argument('--sandbox-image')
    parser.add_argument('--allow-host-commands',action='store_true',help='Enable explicit per-command operator approval; commands run on this host')
    args=parser.parse_args()
    if not 1024<=args.port<=65533:raise SystemExit('Porta inválida')
    model_root=(ROOT/args.root).resolve()
    directory=(ROOT/args.directory).resolve()
    addresses=[('127.0.0.1',args.port),('127.0.0.2',args.port+1),('127.0.0.3',args.port+2)]
    probes=[]
    try:
        for host,port in addresses:
            probe=socket.socket();probes.append(probe);probe.bind((host,port))
    finally:
        for probe in probes:probe.close()
    directory.mkdir(parents=True,exist_ok=True)
    cfg=directory/'config.json'
    endpoints={'coordinator':f'http://127.0.0.1:{args.port}','pc-a':f'https://127.0.0.2:{args.port+1}','pc-b':f'https://127.0.0.3:{args.port+2}'}
    if not cfg.exists():
        trusted={};identity_files={}
        for label,url in endpoints.items():
            identity=new_identity()
            path=directory/(label+'-identity.json')
            path.write_text(json.dumps(identity),encoding='utf8')
            identity_files[label]=str(path)
            trusted[identity['peer_id']]=dict(public_key=identity['public_key'],endpoints=[url])
        config=dict(cluster_secret=secrets.token_hex(32),user_token=secrets.token_urlsafe(32),accounts={'peer-user':secrets.token_urlsafe(32)},coordinator=endpoints['coordinator'],workers={k:v for k,v in endpoints.items() if k!='coordinator'},worker_owners={'pc-a':'local-user','pc-b':'peer-user'},daily_tokens=20000,credit_timezone='America/Sao_Paulo',peer_network=dict(trusted=trusted,identity_files=identity_files,seeds=list(endpoints.values())))
        cfg.write_text(json.dumps(config,indent=2),encoding='utf8')
    config=json.loads(cfg.read_text(encoding='utf8'))
    if config['coordinator']!=endpoints['coordinator'] or config['workers']!={k:v for k,v in endpoints.items() if k!='coordinator'}:
        raise SystemExit('As portas diferem do perfil salvo; escolha outra pasta --directory ou a porta original')
    cert_path=directory/'worker-cert.pem';key_path=directory/'worker-key.pem'
    regenerate=not cert_path.exists() or not key_path.exists()
    if not regenerate:
        cert=x509.load_pem_x509_certificate(cert_path.read_bytes())
        regenerate=cert.not_valid_after_utc<=datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=1)
    if regenerate:
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'IA Colaborativa local profile')])
        now=datetime.datetime.now(datetime.timezone.utc)
        cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=5)).not_valid_after(now+datetime.timedelta(days=7)).add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(h)) for h,_ in addresses[1:]]),critical=False).add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True).sign(key,hashes.SHA256()))
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    active=dict(config)
    active['allow_host_commands']=args.allow_host_commands
    if args.sandbox_image:active['sandbox_image']=args.sandbox_image
    else:active.pop('sandbox_image',None)
    active_cfg=directory/'active-config.json'
    active_cfg.write_text(json.dumps(active,indent=2),encoding='utf8')
    children=[];logs=[]
    try:
        for index,label in enumerate(endpoints):
            workdir=directory/label;workdir.mkdir(exist_ok=True)
            log=open(directory/(label+'.log'),'a',encoding='utf8');logs.append(log)
            role='coordinator' if index==0 else 'worker'
            cmd=[sys.executable,'-m','mesh',role,'--root',str(model_root),'--config',str(active_cfg),'--host',addresses[index][0],'--port',str(addresses[index][1]),'--ca',str(cert_path)]
            if index:
                cmd+=['--id',label,'--part',str(index-1),'--cert',str(cert_path),'--key',str(key_path)]
                assignment=model_root/f'assignment-{index-1}.json'
                if assignment.exists():cmd+=['--assignment',str(assignment)]
            env=dict(os.environ,PYTHONPATH=str(ROOT),HF_HOME=str(ROOT/'data/hf'),MESH_THREADS='1',PYTHONUTF8='1')
            children.append(subprocess.Popen(cmd,cwd=workdir,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0))
        print('Iniciando perfil persistente; sem cópia de pesos ou modelo de referência...',flush=True)
        auth={'Authorization':'Bearer '+config['user_token']}
        deadline=time.monotonic()+600
        with httpx.Client(verify=ssl.create_default_context(cafile=str(cert_path)),timeout=5,trust_env=False) as client:
            while time.monotonic()<deadline:
                if any(c.poll() is not None for c in children):raise RuntimeError('Serviço encerrou; veja logs em '+str(directory))
                try:
                    response=client.get(config['coordinator']+'/api/status',headers=auth)
                    if response.status_code==200 and len([n for n in response.json()['nodes'] if n['online']])==2:
                        ready=dict(url=config['coordinator'],config=str(cfg),active_config=str(active_cfg),model_root=str(model_root),mode='persistent-authorized-network',full_reference_validation=False)
                        (directory/'ready.json').write_text(json.dumps(ready,indent=2),encoding='utf8')
                        print('PRONTO:',config['coordinator'],flush=True)
                        print('Contas e tokens:',cfg,flush=True)
                        print('Créditos e arquivos serão mantidos nesta pasta. Ctrl+C encerra os serviços.',flush=True)
                        break
                except httpx.HTTPError:pass
                time.sleep(.5)
            else:raise RuntimeError('Timeout de inicialização; veja logs em '+str(directory))
        while True:
            if any(c.poll() is not None for c in children):raise RuntimeError('Serviço encerrou')
            time.sleep(1)
    finally:
        for child in children:stop(child)
        for log in logs:log.close()

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:print('Rede encerrada; dados preservados.')
