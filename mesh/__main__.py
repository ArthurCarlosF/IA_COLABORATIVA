import argparse
import json
import os
import secrets
import ssl
from pathlib import Path
import uvicorn

def main():
    parser=argparse.ArgumentParser(description='Inferência GPT-2 por camadas distribuídas')
    parser.add_argument('command',choices=['prepare','init','coordinator','worker','peer-key','plan-model'])
    parser.add_argument('--root',default='data/model')
    parser.add_argument('--config',default='runtime/config.json')
    parser.add_argument('--model',default='sshleifer/tiny-gpt2')
    parser.add_argument('--revision',default='5f91d94bd9cd7190a9f3216ff93cd1dd95f2c7be2')
    parser.add_argument('--parts',type=int,default=2)
    parser.add_argument('--model-profile',default='coder-32b')
    parser.add_argument('--assignment',help='Metadata assignment file; download only this worker partition')
    parser.add_argument('--memory-mb',help='Orçamento de pesos por worker, separado por vírgulas')
    parser.add_argument('--id',default='worker-0')
    parser.add_argument('--part',type=int,default=0)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int)
    parser.add_argument('--device',default='cpu')
    parser.add_argument('--cert')
    parser.add_argument('--key')
    parser.add_argument('--ca')
    parser.add_argument('--identity',default='runtime/identity.json')
    args=parser.parse_args()
    os.environ.setdefault("HF_HOME",str(Path("data/hf").resolve()))
    if args.command=='peer-key':
        from .discovery import new_identity
        path=Path(args.identity)
        if path.exists():raise SystemExit('Identidade já existe; não sobrescrita')
        path.parent.mkdir(parents=True,exist_ok=True)
        identity=new_identity()
        path.write_text(json.dumps(identity,indent=2),encoding='utf8')
        print('Identidade criada:',identity['peer_id'],'em',path)
        return
    if args.command=='plan-model':
        from .partition_store import plan_remote,atomic_json,PROFILES
        from transformers import AutoTokenizer
        if args.model_profile not in PROFILES:raise SystemExit('Perfil desconhecido')
        root=Path(args.root)
        if (root/'manifest.json').exists():raise SystemExit('Plano já existe; use outra pasta')
        capacities=[int(float(x)*1048576) for x in args.memory_mb.split(',')] if args.memory_mb else None
        result=plan_remote(args.model_profile,args.parts,capacities)
        root.mkdir(parents=True,exist_ok=True)
        atomic_json(root/'manifest.json',result);atomic_json(root/'config.json',result['config'])
        AutoTokenizer.from_pretrained(result['model'],revision=result['revision'],trust_remote_code=False).save_pretrained(root/'tokenizer')
        for bundle in result['bundles']:atomic_json(root/f"assignment-{bundle['spec']['index']}.json",bundle)
        print('Somente metadados preparados em',root,'; cada worker usa seu assignment-N.json')
        return
    if args.command=='prepare':
        from .model import prepare
        capacities=[int(float(x)*1048576) for x in args.memory_mb.split(',')] if args.memory_mb else None
        prepare(args.root,args.model,args.revision,args.parts,capacities)
        print('Checkpoint particionado em',args.root)
        return
    config_path=Path(args.config)
    if args.command=='init':
        if config_path.exists():
            raise SystemExit('Configuração já existe; não sobrescrita')
        config_path.parent.mkdir(parents=True,exist_ok=True)
        value=dict(cluster_secret=secrets.token_hex(32),user_token=secrets.token_urlsafe(32),coordinator='http://127.0.0.1:8000',workers={f'worker-{i}':f'http://127.0.0.1:{8100+i}' for i in range(args.parts)},daily_tokens=20000,credit_timezone='America/Sao_Paulo',worker_owners={f'worker-{i}':'local-user' for i in range(args.parts)})
        config_path.write_text(json.dumps(value,indent=2),encoding='utf8')
        print('Segredos criados em',config_path,'- restrinja acesso ao arquivo')
        return
    config=json.loads(config_path.read_text(encoding='utf8'))
    remote=args.host not in ('127.0.0.1','localhost','::1')
    urls=[config['coordinator'],*config['workers'].values()]
    from urllib.parse import urlsplit
    for url in urls:
        parsed=urlsplit(url)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
            raise SystemExit('URL de serviço inválida')
        if parsed.hostname not in ('127.0.0.1','localhost','::1') and parsed.scheme!='https':
            raise SystemExit('Comunicação remota exige HTTPS')
    if remote and not (args.cert and args.key):
        raise SystemExit('Escuta remota exige --cert e --key; use VPN/LAN privada')
    if len(config['cluster_secret'])<32 or (args.command=='coordinator' and len(config.get('user_token',''))<32):
        raise SystemExit('Segredos devem ter pelo menos 32 caracteres')
    verify=ssl.create_default_context(cafile=args.ca) if args.ca else True
    Path('runtime').mkdir(exist_ok=True)
    if args.command=='coordinator':
        from .coordinator import create_coordinator
        app=create_coordinator(args.root,config['cluster_secret'],config['user_token'],config['workers'],'runtime/credits.sqlite',verify,accounts=config.get('accounts'),worker_owners=config.get('worker_owners'),daily_tokens=config.get('daily_tokens',20000),credit_timezone=config.get('credit_timezone','America/Sao_Paulo'),peer_network=config.get('peer_network'),coordinator_url=config['coordinator'],sandbox_image=config.get('sandbox_image'),allow_host_commands=config.get('allow_host_commands',False))
        port=args.port or 8000
    else:
        from .worker import create_worker
        directory=Path(args.root)/f'part-{args.part}'
        if args.assignment:
            from .partition_store import provision
            assignment=json.loads(Path(args.assignment).read_text())
            if assignment['spec']['index']!=args.part:raise SystemExit('Assignment diferente do índice do worker')
            if Path('runtime/model-active.json').exists():
                from .partition_store import digest
                directory=Path('runtime/model-parts')/digest(assignment)
            else:directory=provision(assignment,'runtime/model-parts')
        app=create_worker(directory,args.id,config['cluster_secret'],config['coordinator'],config['workers'][args.id],verify,args.device,config.get('peer_network'))
        port=args.port or 8100+args.part
    uvicorn.run(app,host=args.host,port=port,ssl_certfile=args.cert,ssl_keyfile=args.key,access_log=False)

if __name__=='__main__':
    main()
