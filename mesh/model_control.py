"""Permissioned model switch transaction; coordinator stores metadata, workers store their partitions."""
import asyncio
import json
from pathlib import Path
import time
import uuid
from fastapi import HTTPException,Request
from transformers import AutoTokenizer
from .partition_store import PROFILES,plan_remote,digest,validate_bundle,atomic_json

class ModelControl:
    def __init__(self,app,auth,allowed,nodes,rpc,current,apply,catalog,idle,context_limits):
        self.auth=auth;self.allowed=allowed;self.nodes=nodes;self.rpc=rpc;self.current=current;self.apply=apply;self.catalog=Path(catalog);self.idle=idle;self.limits=context_limits
        self.journal=self.catalog/'transaction.json';self.selection=self.catalog/'current.json';self.busy=False;self.task=None;self.job=dict(state='idle')
        if self.journal.exists():
            journal=json.loads(self.journal.read_text())
            selected=json.loads(self.selection.read_text())['root'] if self.selection.exists() else str(current()['root'])
            if selected==journal['new_root']:self.journal.unlink()
            else:self.busy=True;self.job=dict(state='recovery_required',message='Previous model switch interrupted; operator recovery required')
        app.get('/api/models')(self.models)
        app.post('/api/models/switch')(self.switch)
        app.get('/api/models/job')(self.job_status)
        app.post('/api/models/recover')(self.recover)
    def operator(self,request):
        if self.auth(request)!='local-user' or not request.client or request.client.host not in ('127.0.0.1','::1'):raise HTTPException(403,'Somente o operador local pode trocar o modelo da rede')
    async def models(self,request:Request):
        self.auth(request);active=self.current();manifest=active['manifest'];context,output=self.limits();rows=[]
        for key,(model,revision) in PROFILES.items():
            loaded=manifest['model']==model and manifest['revision']==revision
            rows.append(dict(id=model,profile=key,revision=revision,available=loaded,selectable=True,parts=len(self.allowed),context=context if loaded else 4096,max_output=output if loaded else 512,agent_supported=True,state='active' if loaded else 'requires_preparation',storage='assigned-partition-only'))
        if not any(r['available'] for r in rows):rows.insert(0,dict(id=manifest['model'],profile=None,revision=manifest['revision'],available=True,selectable=False,parts=len(self.allowed),context=context,max_output=output,agent_supported=context>=2048,state='active'))
        return dict(active=manifest['model'],models=rows,switching=self.busy,job=self.job,can_switch=self.auth(request)=='local-user' and request.client and request.client.host in ('127.0.0.1','::1'),quality_equivalence_verified=False)
    async def job_status(self,request:Request):self.auth(request);return self.job
    async def switch(self,request:Request):
        self.operator(request)
        body=await request.body()
        if len(body)>1000:raise HTTPException(413,'Pedido muito grande')
        try:
            data=json.loads(body)
            if not isinstance(data,dict) or set(data)!={'profile'} or data['profile'] not in PROFILES:raise ValueError()
        except (ValueError,TypeError):raise HTTPException(422,'Perfil de modelo inválido')
        if self.busy:raise HTTPException(409,'Outra troca ou recuperação está em andamento')
        active=self.current()['manifest']
        if PROFILES[data['profile']]==(active['model'],active['revision']):raise HTTPException(409,'Este modelo já está ativo')
        if not self.idle():raise HTTPException(409,'Aguarde terminar ou cancele as tarefas antes de trocar')
        self.busy=True;self.job=dict(id=uuid.uuid4().hex,state='planning',profile=data['profile'])
        self.task=asyncio.create_task(self.execute(data['profile']))
        return self.job
    async def call(self,node,path,body,timeout=660):
        # The control plane can legitimately take longer than one inference RPC.
        return await asyncio.wait_for(self.rpc(node,path,body),timeout)
    def budgets(self,reports):
        groups={}
        for key,r in reports.items():
            device=r['device']
            resource=(r['host_id'],'gpu',r.get('device_id',device)) if device.startswith('cuda') else (r['host_id'],'cpu')
            groups.setdefault(resource,[]).append((key,r))
        budgets={}
        for resource,group in groups.items():
            if resource[1]=='gpu':
                available=min(r['vram_free'] for _,r in group)
                reclaim=sum(r['weight_bytes'] for _,r in group)
                usable=max(0,available+reclaim-512*1048576*len(group))
            else:
                available=min(r['ram_available'] for _,r in group)
                reclaim=sum(min(r['weight_bytes'],r['rss']) for _,r in group)
                usable=max(0,available+reclaim-1024*1048576)
            share=usable//len(group)
            for key,r in group:budgets[key]=int(share)
        if any(v<=0 for v in budgets.values()):raise ValueError('Memória disponível insuficiente após reserva de execução')
        return budgets
    async def execute(self,profile):
        old=self.current();participants=[dict(id=k,url=v) for k,v in self.allowed.items()];journal=None;new_root=None
        try:
            reports={}
            for node in participants:
                response=await self.call(node,'/status',{})
                if response['resources']['sessions']:raise ValueError('Worker com KV ativo')
                reports[node['id']]=response['resources']
            budgets=self.budgets(reports);self.job['budgets']=budgets
            if profile in ('general-72b','coder-480b'):
                from .graph_plan import plan_graph_remote
                planner=plan_graph_remote
            else:planner=plan_remote
            plan=await asyncio.to_thread(planner,profile,len(participants),[budgets[n['id']] for n in participants])
            self.job.update(state='preparing',assignments=[dict(worker=n['id'],spec=b['spec'],weight_bytes=validate_bundle(b)) for n,b in zip(participants,plan['bundles'])])
            new_root=self.catalog/digest(dict(model=plan['model'],revision=plan['revision'],parts=plan['parts']));new_root.mkdir(exist_ok=True)
            atomic_json(new_root/'manifest.json',plan);atomic_json(new_root/'config.json',plan['config'])
            tokenizer_class=AutoTokenizer
            if plan.get('architecture')=='qwen3_moe':
                from transformers import Qwen2TokenizerFast
                tokenizer_class=Qwen2TokenizerFast
            tokenizer=await asyncio.to_thread(tokenizer_class.from_pretrained,plan['model'],revision=plan['revision'],trust_remote_code=False)
            tokenizer.save_pretrained(new_root/'tokenizer')
            for node,bundle in zip(participants,plan['bundles']):await self.call(node,'/model/stage',dict(bundle=bundle))
            deadline=time.monotonic()+1800
            while time.monotonic()<deadline:
                states={}
                for node,bundle in zip(participants,plan['bundles']):
                    state=await self.call(node,'/model/status',{})
                    if state.get('id')!=digest(bundle):raise ValueError('Worker staged a different assignment')
                    if state['state']=='failed':raise ValueError(node['id']+': '+state.get('error','Preparation failed'))
                    states[node['id']]=state
                self.job['workers']={k:{x:v for x,v in s.items() if x!='directory'} for k,s in states.items()}
                if all(s['state']=='ready' for s in states.values()):break
                await asyncio.sleep(1)
            else:raise ValueError('Tempo limite de preparação; modelo anterior preservado')
            journal=dict(old_root=str(old['root']),new_root=str(new_root),ids={n['id']:digest(b) for n,b in zip(participants,plan['bundles'])},old_fingerprints={str(k):v for k,v in old['fingerprints'].items()})
            atomic_json(self.journal,journal);self.job['state']='activating'
            self.apply(new_root)
            for node,bundle in zip(participants,plan['bundles']):
                result=await self.call(node,'/model/commit',dict(id=digest(bundle)))
                if result['fingerprint']!=digest(bundle) or result['spec']!=bundle['spec']:raise ValueError('Worker activated wrong partition')
            self.nodes.clear()
            atomic_json(self.selection,dict(root=str(new_root)));self.journal.unlink();self.job['state']='completed'
        except Exception as exc:
            self.job.update(state='failed',error=str(exc)[:1500])
            await asyncio.gather(*(self.call(n,'/model/abort',{}) for n in participants),return_exceptions=True)
            if journal:
                self.apply(old['root'])
                try:await self.rollback(journal)
                except Exception as rollback_error:
                    self.job.update(state='recovery_required',rollback_error=str(rollback_error)[:1000]);return
        finally:
            self.busy=self.job['state']=='recovery_required'
    async def rollback(self,journal):
        for index,(key,url) in enumerate(self.allowed.items()):
            reply=await self.call(dict(id=key,url=url),'/model/rollback',dict(id=journal['ids'][key]))
            if reply['fingerprint']!=journal['old_fingerprints'][str(index)]:raise ValueError('Rollback fingerprint mismatch: '+key)
        self.nodes.clear()
        if self.journal.exists():self.journal.unlink()
    async def recover(self,request:Request):
        self.operator(request)
        if self.job['state']!='recovery_required':raise HTTPException(409,'Nenhuma recuperação pendente')
        journal=json.loads(self.journal.read_text())
        try:
            self.apply(journal['old_root']);await self.rollback(journal);self.busy=False;self.job=dict(state='recovered')
            return self.job
        except Exception as exc:raise HTTPException(503,str(exc)[:500])
    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
