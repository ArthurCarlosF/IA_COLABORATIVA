"""Dois hosts lógicos loopback, workers reais, diretórios separados e TLS.

Sem VMs, sem mocks de inferência e sem alterações de firewall ou interfaces.
"""
import argparse
import datetime
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import time

import httpx
import psutil
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT=Path(__file__).resolve().parents[1]


def stop(child):
    if child.poll() is not None:
        return
    try:
        parent=psutil.Process(child.pid)
        descendants=parent.children(recursive=True)
        for process in reversed(descendants):
            try:process.terminate()
            except psutil.NoSuchProcess:pass
        try:parent.terminate()
        except psutil.NoSuchProcess:pass
        _,alive=psutil.wait_procs([*descendants,parent],timeout=5)
        for process in alive:
            try:process.kill()
            except psutil.NoSuchProcess:pass
    except psutil.NoSuchProcess:
        pass
    child.wait(timeout=10)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',default='data/model')
    parser.add_argument('--coding-task',action='store_true')
    parser.add_argument('--reuse-weights',action='store_true',help='Reutilizar arquivos de pesos locais sem copiar GB a cada execução')
    parser.add_argument('--startup-timeout',type=int,default=180)
    parser.add_argument('--p2p',action='store_true')
    parser.add_argument('--sandbox-image',help='ID sha256 de imagem Docker local aprovada')
    parser.add_argument('--serve',action='store_true',help='Manter chat e workers ativos após validar')
    parser.add_argument('--port',type=int,default=8200)
    parser.add_argument('--credits-demo',action='store_true',help='Duas contas e reciprocidade real de créditos')
    args=parser.parse_args()
    model_root=(ROOT/args.root).resolve()
    if not 1024<=args.port<=65533:
        raise SystemExit('Porta base deve estar entre 1024 e 65533')
    addresses=[('127.0.0.1',args.port),('127.0.0.2',args.port+1),('127.0.0.3',args.port+2)]
    probes=[]
    try:
        for host,port in addresses:
            probe=socket.socket()
            probes.append(probe)
            probe.bind((host,port))
    finally:
        for probe in probes:probe.close()
    stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(3)
    directory=ROOT/'runtime/simulation'/stamp
    directory.mkdir(parents=True)
    cert_path=directory/'worker-cert.pem'
    key_path=directory/'worker-key.pem'
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Mesh loopback simulation only')])
    now=datetime.datetime.now(datetime.timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=5))
          .not_valid_after(now+datetime.timedelta(days=7))
          .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(host)) for host,_ in addresses[1:]]),critical=False)
          .add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True).sign(key,hashes.SHA256()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    config=dict(cluster_secret=secrets.token_hex(32),user_token=secrets.token_urlsafe(32),
                coordinator=f'http://127.0.0.1:{args.port}',
                workers={'pc-a':f'https://127.0.0.2:{args.port+1}','pc-b':f'https://127.0.0.3:{args.port+2}'})
    if args.credits_demo:
        config.update(accounts={'peer-user':secrets.token_urlsafe(32)},worker_owners={'pc-a':'local-user','pc-b':'peer-user'},daily_tokens=20000,credit_timezone='America/Sao_Paulo')
    if args.sandbox_image:config['sandbox_image']=args.sandbox_image
    if args.p2p:
        sys.path.insert(0,str(ROOT))
        from mesh.discovery import new_identity
        trusted={}
        identity_files={}
        for label,url in [('coordinator',config['coordinator']),*config['workers'].items()]:
            identity=new_identity()
            identity_path=directory/(label+'-identity.json')
            identity_path.write_text(json.dumps(identity),encoding='utf8')
            identity_files[label]=str(identity_path)
            trusted[identity['peer_id']]=dict(public_key=identity['public_key'],endpoints=[url])
        config['peer_network']=dict(trusted=trusted,identity_files=identity_files,seeds=[config['coordinator'],*config['workers'].values()])
    cfg=directory/'config.json'
    cfg.write_text(json.dumps(config,indent=2),encoding='utf8')
    for i,label in enumerate(config['workers']):
        shard=directory/label/'model'/f'part-{i}'
        if not args.reuse_weights:shutil.copytree(model_root/f'part-{i}',shard)
        else:(directory/label).mkdir(exist_ok=True)
    (directory/'coordinator').mkdir()
    children=[]
    logs=[]
    workers=[]
    def start(role,index=0):
        label='coordinator' if role=='coordinator' else list(config['workers'])[index]
        workdir=directory/label
        log_path=directory/f'{label}-{len(logs)}.log'
        log=open(log_path,'w',encoding='utf8')
        logs.append(log)
        cmd=[sys.executable,'-m','mesh',role,'--config',str(cfg),'--ca',str(cert_path),
             '--root',str(model_root if role=='coordinator' or args.reuse_weights else workdir/'model'),
             '--host',addresses[0 if role=='coordinator' else index+1][0],
             '--port',str(addresses[0 if role=='coordinator' else index+1][1])]
        if role=='worker':
            cmd+=['--id',label,'--part',str(index),'--cert',str(cert_path),'--key',str(key_path)]
        env=dict(os.environ,PYTHONPATH=str(ROOT),HF_HOME=str(ROOT/'data/hf'),MESH_THREADS='1')
        child=subprocess.Popen(cmd,cwd=workdir,env=env,stdout=log,stderr=log,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        children.append(child)
        return child,log_path
    report=dict(kind='logical hosts on one physical computer',directory=str(directory),
                endpoints=dict(coordinator=config['coordinator'],**config['workers']),
                worker_directories={label:str((model_root if args.reuse_weights else directory/label/'model')/f'part-{i}') for i,label in enumerate(config['workers'])},reuse_local_weight_files=args.reuse_weights)
    latest=ROOT/'runtime/simulation/latest.json'
    latest.write_text(json.dumps(dict(directory=str(directory),url=config['coordinator']),indent=2),encoding='utf8')
    auth={'Authorization':'Bearer '+config['user_token']}
    client=httpx.Client(verify=ssl.create_default_context(cafile=str(cert_path)),timeout=30,trust_env=False)
    coordinator=None
    try:
        coordinator=start('coordinator')
        workers=[start('worker',i) for i in range(2)]
        def wait_ready():
            deadline=time.monotonic()+args.startup_timeout
            while time.monotonic()<deadline:
                if any(c.poll() is not None for c,_ in [coordinator,*workers]):
                    raise RuntimeError('Serviço encerrou; consulte os logs em '+str(directory))
                try:
                    state=client.get(config['coordinator']+'/api/status',headers=auth)
                    if state.status_code==200 and len([n for n in state.json()['nodes'] if n['online']])==2:
                        # Uma entrada antiga do heartbeat não prova que o novo processo já iniciou.
                        for label in config['workers']:
                            response=client.post(config['workers'][label]+'/status',content=b'{}',headers=rpc_headers(b'{}'))
                            response.raise_for_status()
                        return state.json()
                except httpx.HTTPError:pass
                time.sleep(.5)
            detail='\n'.join(path.name+': '+path.read_text(encoding='utf8',errors='replace')[-2000:] for path in directory.glob('*.log'))
            raise RuntimeError('Timeout aguardando workers\n'+detail)
        sys.path.insert(0,str(ROOT))
        from mesh.protocol import headers
        def rpc_headers(body):
            from mesh.identity import signed_headers
            identity=json.loads(Path(config['peer_network']['identity_files']['coordinator']).read_text()) if args.p2p else None
            return signed_headers(config['cluster_secret'],body,'/status',identity)
        print('Aguardando os três serviços...',flush=True)
        state=wait_ready()
        print('Workers conectados. Verificando falhas e recuperação...',flush=True)
        service_pids={}
        for label,(_,log_path) in zip(['coordinator',*config['workers']],[coordinator,*workers]):
            match=re.search(r'Started server process \[(\d+)\]',log_path.read_text(encoding='utf8'))
            if not match:raise RuntimeError('PID real não encontrado no log')
            service_pids[label]=int(match.group(1))
        if len(set(service_pids.values()))!=3:raise RuntimeError('Serviços não estão em processos distintos')
        report['service_pids']=service_pids
        report['initial_status']=state
        try:
            with httpx.Client(trust_env=False,timeout=5) as untrusted:
                untrusted.post(config['workers']['pc-a']+'/status',content=b'{}')
        except httpx.ConnectError:
            report['untrusted_certificate_rejected']=True
        else:raise AssertionError('Certificado não confiável foi aceito')
        # Derrubar B: sem sua camada a rede deve falhar, nunca fabricar uma resposta.
        stop(workers[1][0])
        response=client.post(config['coordinator']+'/api/chat',headers=auth,json=dict(prompt='Hello',max_tokens=2))
        assert response.status_code==503 or (response.status_code==200 and '"type": "error"' in response.text)
        report['failure']=dict(status_code=response.status_code,explicit_error=True)
        workers[1]=start('worker',1)
        wait_ready()
        if args.p2p:
            from mesh.identity import signed_headers
            wrong_identity=json.loads(Path(config['peer_network']['identity_files']['pc-b']).read_text())
            denied=client.post(config['workers']['pc-a']+'/status',content=b'{}',headers=signed_headers(config['cluster_secret'],b'{}','/status',wrong_identity))
            assert denied.status_code==401,'Worker conseguiu se passar pelo solicitante'
            report['individual_auth']=dict(cross_worker_impersonation_rejected=True)
            print('Assinatura individual verificada. Desligando o contato inicial para testar gossip...',flush=True)
            stopped_at=int(time.time()*1000)
            stop(coordinator[0])
            deadline=time.monotonic()+25
            survived=False
            while time.monotonic()<deadline:
                learned=[]
                for url in config['workers'].values():
                    response=client.get(url+'/p2p/peers')
                    response.raise_for_status()
                    records=response.json()['records']
                    learned.append({r['payload']['endpoint'] for r in records if r['payload']['issued_ms']>stopped_at})
                if all(set(config['workers'].values())<=contacts for contacts in learned):
                    survived=True
                    break
                time.sleep(.5)
            assert survived,'Gossip parou junto com o contato inicial'
            report['discovery']=dict(coordinator_offline=True,workers_exchanged_fresh_signed_contacts=True,mode='permissioned-gossip')
            coordinator=start('coordinator')
            wait_ready()
        verifier=[sys.executable,str(ROOT/'tools/verify_remote.py'),'--config',str(cfg),
                  '--root',str(model_root),'--ca',str(cert_path),'--output',str(directory/'inference-evidence.json')]
        if args.coding_task:verifier.append('--coding-task')
        print('Comparando logits e gerando código pelo modelo distribuído...',flush=True)
        result=subprocess.run(verifier,cwd=ROOT,env=dict(os.environ,HF_HOME=str(ROOT/'data/hf')),
                              capture_output=True,text=True,timeout=600,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        (directory/'verifier.log').write_text(result.stdout+result.stderr,encoding='utf8')
        if result.returncode:raise RuntimeError('Verificação falhou; veja verifier.log')
        report['inference']=json.loads((directory/'inference-evidence.json').read_text(encoding='utf8'))
        if args.credits_demo:
            peer_auth={'Authorization':'Bearer '+config['accounts']['peer-user']}
            peer_response=client.post(config['coordinator']+'/api/chat',headers=peer_auth,json=dict(prompt='Hello',max_tokens=8))
            peer_response.raise_for_status()
            assert '"type": "done"' in peer_response.text
            report['usage_demo']={}
            for label,identity in [('local-user',auth),('peer-user',peer_auth)]:
                usage_response=client.get(config['coordinator']+'/api/usage',headers=identity)
                usage_response.raise_for_status()
                report['usage_demo'][label]=usage_response.json()
            assert report['usage_demo']['local-user']['earned_total']>0
            assert report['usage_demo']['peer-user']['earned_total']>0
            report['wallet_integrity']=client.get(config['coordinator']+'/api/credits',headers=auth).json()['valid']
            assert report['wallet_integrity']
        report['recovery_verified']=True
        report['passed']=True
        (directory/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
        print('VALIDADO: pc-a e pc-b em IPs loopback distintos, camadas reais e TLS.',flush=True)
        print('Chat:',config['coordinator'],flush=True)
        print('Token de acesso: campo user_token em',cfg,flush=True)
        print('Evidência:',directory/'report.json',flush=True)
        if args.serve:
            print('Serviços ativos. Ctrl+C encerra somente este ambiente.',flush=True)
            while True:
                if any(c.poll() is not None for c,_ in [coordinator,*workers]):raise RuntimeError('Serviço encerrou')
                time.sleep(1)
    finally:
        client.close()
        for child in children:stop(child)
        for log in logs:log.close()

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:print('Ambiente encerrado.')
