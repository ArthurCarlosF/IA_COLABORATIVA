"""CLI for persistent, local-only streaming jobs."""
import asyncio
import json
from pathlib import Path
import signal
import ssl
import threading
from contextlib import ExitStack
import httpx
from transformers import Qwen2TokenizerFast
from .graph_plan import source_metadata, build_graph
from .partition_store import PROFILES, atomic_json
from .slow_inference import run_slow


def run_batch(args, stop):
    directory=Path(args.job)
    job_file=directory/'job.json'
    plan_file=directory/'program.json'
    if job_file.exists():
        settings=json.loads(job_file.read_text(encoding='utf8'))
        if args.prompt is not None and args.prompt!=settings['prompt']:
            raise SystemExit('Use outro diretório para uma pergunta diferente')
        if args.model_profile is not None and args.model_profile!=settings['profile']:
            raise SystemExit('O checkpoint não pode mudar na retomada')
        if args.tokens is not None and args.tokens!=settings['tokens']:
            raise SystemExit('A quantidade de tokens já está fixada neste trabalho')
        if args.tile_endpoint is not None and args.tile_endpoint!=settings.get('tile_endpoints',[]):
            raise SystemExit('O executor de blocos já está fixado neste trabalho')
        program=json.loads(plan_file.read_text(encoding='utf8'))
        tokenizer=Qwen2TokenizerFast.from_pretrained(directory/'tokenizer',local_files_only=True)
    else:
        if not args.prompt or not args.prompt.strip():
            raise SystemExit('Informe --prompt para iniciar um trabalho novo')
        profile=args.model_profile or 'coder-480b'
        if profile not in PROFILES:raise SystemExit('Perfil desconhecido')
        model,revision,config,files=source_metadata(profile)
        # A logical program, not a resident assignment. This format cannot be
        # passed to the ordinary worker provisioning endpoint.
        program=build_graph(model,revision,config,files,1,max_parameters=10**12,
                            piece_parameters=1_000_000_000)
        program['format']='graph-stream-v1'
        for bundle in program['bundles']:bundle['format']='graph-stream-v1'
        tokenizer=Qwen2TokenizerFast.from_pretrained(model,revision=revision)
        ids=(tokenizer.apply_chat_template([dict(role='user',content=args.prompt)],
              tokenize=True,add_generation_prompt=True)
             if tokenizer.chat_template else tokenizer.encode(args.prompt))
        settings=dict(profile=profile,prompt=args.prompt,ids=ids,
                      tokens=args.tokens if args.tokens is not None else 16,
                      eos=tokenizer.eos_token_id,tile_rows=args.tile_rows,
                      tile_columns=args.tile_columns,maximum_bytes=args.tile_kib*1024,
                      tile_endpoints=args.tile_endpoint or [])
        directory.mkdir(parents=True,exist_ok=True)
        tokenizer.save_pretrained(directory/'tokenizer')
        atomic_json(plan_file,program)
        atomic_json(job_file,settings)
    with ExitStack() as stack:
        client=stack.enter_context(httpx.Client(follow_redirects=True,timeout=60,trust_env=False))
        execution={}
        if settings.get('tile_endpoints'):
            from .tile_worker import TileClient,TilePool
            if not args.tile_config:raise SystemExit('Informe --tile-config com o segredo do executor')
            secret=json.loads(Path(args.tile_config).read_text(encoding='utf8'))['tile_secret']
            verify=ssl.create_default_context(cafile=args.ca) if args.ca else True
            worker=stack.enter_context(httpx.Client(timeout=30,verify=verify,trust_env=False))
            endpoints=settings['tile_endpoints']
            execution=dict(kernel=TilePool([TileClient(url,secret,worker) for url in endpoints]),
                           kernel_id='tile-rpc-v1:'+','.join(endpoints))
        result=asyncio.run(run_slow(program,settings['ids'],directory,
             settings['tokens'],settings['eos'],client,maximum_tiles=args.max_tiles,
             tile_rows=settings['tile_rows'],tile_columns=settings['tile_columns'],
             maximum_bytes=settings['maximum_bytes'],cancel=stop,**execution))
    result['text']=tokenizer.decode(result['generated'],skip_special_tokens=True)
    result['model']=program['model']
    atomic_json(directory/'last-result.json',result)
    return result


def run(args):
    stop=threading.Event()
    previous=signal.signal(signal.SIGINT,lambda *_:stop.set())
    try:
        result=run_batch(args,stop)
    finally:
        signal.signal(signal.SIGINT,previous)
    print(json.dumps(result,ensure_ascii=False,indent=2))
