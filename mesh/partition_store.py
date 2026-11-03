"""Metadata planning and HTTP byte-range provisioning: never download a complete checkpoint."""
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import shutil
import httpx

CHUNK=8*1024*1024
DTYPES={'F32':4,'F16':2,'BF16':2}
PROFILES={
 'coder-480b':('Qwen/Qwen3-Coder-480B-A35B-Instruct','9d90cf8fca1bf7b7acca42d3fc9ae694a2194069'),
 'general-0.5b':('Qwen/Qwen2.5-0.5B-Instruct','7ae557604adf67be50417f59c2c2f167def9a775'),
 'coder-0.5b':('Qwen/Qwen2.5-Coder-0.5B-Instruct','ea3f2471cf1b1f0db85067f1ef93848e38e88c25'),
 'coder-1.5b':('Qwen/Qwen2.5-Coder-1.5B-Instruct','2e1fd397ee46e1388853d2af2c993145b0f1098a'),
 'coder-32b':('Qwen/Qwen2.5-Coder-32B-Instruct','381fc969f78efac66bc87ff7ddeadb7e73c218a7'),
 'general-72b':('Qwen/Qwen2.5-72B-Instruct','495f39366efef23836d0cfae4fbe635880d2be31')}

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def atomic_json(path,value):
    path=Path(path);temp=path.with_suffix(path.suffix+'.tmp');temp.write_bytes(canonical(value));temp.replace(path)

def read_range(client,url,start,size):
    if type(start) is not int or start<0 or type(size) is not int or not 0<size<=CHUNK:raise ValueError('Invalid byte range')
    end=start+size-1
    separator='&' if '?' in url else '?'
    with client.stream('GET',url+separator+f'mesh_range={start}-{end}',headers={'Range':f'bytes={start}-{end}','Accept-Encoding':'identity'}) as response:
        if response.status_code!=206:raise ValueError('Source refused partial download; full download prohibited')
        match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',response.headers.get('content-range',''))
        if not match or (int(match[1]),int(match[2]))!=(start,end) or int(match[3])<=end:raise ValueError('Invalid Content-Range')
        result=bytearray()
        for block in response.iter_bytes(chunk_size=65536):
            result.extend(block)
            if len(result)>size:raise ValueError('Range exceeded requested size')
        if len(result)!=size:raise ValueError('Truncated range')
        return result

def tensor_header(client,url):
    length=struct.unpack('<Q',read_range(client,url,0,8))[0]
    if not 2<=length<=CHUNK:raise ValueError('Safetensors header too large')
    header=json.loads(read_range(client,url,8,length));result={}
    for name,entry in header.items():
        if name=='__metadata__':continue
        shape=entry['shape'];dtype=entry['dtype'];a,b=entry['data_offsets']
        if dtype not in DTYPES or not isinstance(shape,list) or not shape or any(type(n) is not int or n<=0 for n in shape):raise ValueError('Unsupported tensor')
        if type(a) is not int or type(b) is not int or a<0 or b-a!=math.prod(shape)*DTYPES[dtype]:raise ValueError('Invalid tensor offsets')
        result[name]=dict(shape=shape,dtype=dtype,start=8+length+a,size=b-a)
    return result

def owner(name,boundaries):
    if name.startswith('model.layers.'):
        layer=int(name.split('.')[2])
        for i,(start,end) in enumerate(boundaries):
            if start<=layer<end:return i
        raise ValueError('Layer outside model')
    if name.startswith('model.embed_tokens.'):return 0
    if name.startswith(('model.norm.','lm_head.')):return len(boundaries)-1
    raise ValueError('Unexpected tensor '+name)

def plan_remote(profile,parts,capacities=None,client=None):
    from huggingface_hub import hf_hub_download
    from transformers import AutoConfig
    model,revision=PROFILES[profile]
    config=AutoConfig.from_pretrained(model,revision=revision,trust_remote_code=False).to_dict()
    if config['model_type']!='qwen2' or config.get('use_sliding_window'):raise ValueError('Unsupported architecture')
    if not 1<=parts<=config['num_hidden_layers']:raise ValueError('Invalid partition count')
    try:
        index=json.loads(Path(hf_hub_download(model,'model.safetensors.index.json',revision=revision)).read_text());weight_map=index['weight_map']
        files=sorted(set(weight_map.values()))
    except Exception as exc:
        from huggingface_hub.errors import EntryNotFoundError
        if not isinstance(exc,EntryNotFoundError):raise
        files=['model.safetensors'];weight_map=None
    entries={}
    owned=client is None
    if owned:client=httpx.Client(follow_redirects=True,timeout=60,trust_env=False)
    try:
        for file in files:
            if not re.fullmatch(r'model(?:-\d+-of-\d+)?\.safetensors',file):raise ValueError('Invalid shard filename')
            url=f'https://huggingface.co/{model}/resolve/{revision}/{file}'
            for name,entry in tensor_header(client,url).items():
                if weight_map and weight_map.get(name)!=file:raise ValueError('Inconsistent safetensors index')
                if name in entries:raise ValueError('Duplicate tensor')
                entries[name]=dict(entry,file=file)
    finally:
        if owned:client.close()
    if config.get('tie_word_embeddings') and 'lm_head.weight' not in entries:entries['lm_head.weight']=dict(entries['model.embed_tokens.weight'])
    if weight_map and set(weight_map)-set(entries):raise ValueError('Missing tensors')
    count=config['num_hidden_layers'];boundaries=[(i*count//parts,(i+1)*count//parts) for i in range(parts)]
    if capacities:
        from .planner import plan
        layer_bytes=[0]*count;first=last=0
        for name,entry in entries.items():
            size=math.prod(entry['shape'])*4
            if name.startswith('model.layers.'):layer_bytes[int(name.split('.')[2])]+=size
            elif name.startswith('model.embed_tokens.'):first+=size
            else:last+=size
        boundaries=plan(layer_bytes,capacities,first,last)
    result=dict(model=model,revision=revision,architecture='qwen2',layers=count,vocab_size=config['vocab_size'],format='range-f32-v1',config=config,parts=[],bundles=[])
    for i,(start,end) in enumerate(boundaries):
        spec=dict(index=i,start=start,end=end,first=i==0,last=i==parts-1)
        selected={name:entry for name,entry in entries.items() if owner(name,boundaries)==i}
        bundle=dict(model=model,revision=revision,config=config,spec=spec,tensors=selected,format='range-f32-v1')
        result['parts'].append(spec);result['bundles'].append(bundle)
    return result

def validate_bundle(bundle):
    if isinstance(bundle,dict) and bundle.get('format')=='graph-f32-v1':
        from .graph_plan import validate_graph_bundle
        return validate_graph_bundle(bundle)
    if bundle.get('format')!='range-f32-v1' or (bundle.get('model'),bundle.get('revision')) not in PROFILES.values():raise ValueError('Unapproved checkpoint')
    cfg=bundle['config'];spec=bundle['spec']
    if cfg.get('model_type')!='qwen2' or cfg.get('use_sliding_window') or not 0<=spec['start']<spec['end']<=cfg['num_hidden_layers']:raise ValueError('Invalid partition')
    for name,entry in bundle['tensors'].items():
        if name.startswith('model.layers.'):
            if not spec['start']<=int(name.split('.')[2])<spec['end']:raise ValueError('Foreign layer in partition')
        elif name.startswith('model.embed_tokens.'):
            if not spec['first']:raise ValueError('Foreign embeddings')
        elif name.startswith(('model.norm.','lm_head.')):
            if not spec['last']:raise ValueError('Foreign output weights')
        else:raise ValueError('Unexpected tensor')
        if entry['dtype'] not in DTYPES or not re.fullmatch(r'model(?:-\d+-of-\d+)?\.safetensors',entry['file']):raise ValueError('Invalid source')
        if not entry['shape'] or any(type(n) is not int or n<=0 for n in entry['shape']) or type(entry['start']) is not int or entry['start']<8 or entry['size']!=math.prod(entry['shape'])*DTYPES[entry['dtype']]:raise ValueError('Invalid tensor range')
    return sum(math.prod(e['shape'])*4 for e in bundle['tensors'].values())

def provision(bundle,cache,progress=None,client=None):
    if bundle.get('format')=='graph-f32-v1':
        from .graph_plan import provision_graph
        return provision_graph(bundle,cache,progress,client)
    import torch
    from transformers import Qwen2Config
    validate_bundle(bundle)
    path=Path(cache)/digest(bundle);path.mkdir(parents=True,exist_ok=True)
    if path.is_symlink() or not path.resolve().is_relative_to(Path(cache).resolve()):raise ValueError('Invalid partition cache path')
    complete=path/'weights.json'
    if complete.exists():
        load_mapped(path,verify=True);return path
    if shutil.disk_usage(path).free<validate_bundle(bundle)+2*CHUNK:raise ValueError('Insufficient disk for assigned partition')
    atomic_json(path/'blueprint.json',bundle);Qwen2Config.from_dict(json.loads(canonical(bundle['config']))).save_pretrained(path);atomic_json(path/'spec.json',bundle['spec'])
    owned=client is None
    if owned:client=httpx.Client(follow_redirects=True,timeout=60,trust_env=False)
    tensors={};downloaded=0
    try:
        for name,entry in sorted(bundle['tensors'].items()):
            filename=hashlib.sha256(name.encode()).hexdigest()+'.bin';target=path/filename;temporary=path/(filename+'.download');sha=hashlib.sha256()
            url=f"https://huggingface.co/{bundle['model']}/resolve/{bundle['revision']}/{entry['file']}"
            element_size=DTYPES[entry['dtype']];dtype={'F32':torch.float32,'F16':torch.float16,'BF16':torch.bfloat16}[entry['dtype']]
            if temporary.is_symlink():raise ValueError('Invalid partial tensor path')
            with temporary.open('wb') as handle:
                for offset in range(0,entry['size'],CHUNK):
                    size=min(CHUNK,entry['size']-offset);raw=read_range(client,url,entry['start']+offset,size)
                    block=torch.frombuffer(raw,dtype=dtype).float().numpy().tobytes();handle.write(block);sha.update(block);downloaded+=size
                    if progress:progress(dict(bytes_downloaded=downloaded,tensor=name,partition=bundle['spec']['index']))
            temporary.replace(target);tensors[name]=dict(file=filename,shape=entry['shape'],sha256=sha.hexdigest())
        atomic_json(complete,dict(blueprint=digest(bundle),tensors=tensors,bytes_downloaded=downloaded,download_scope='assigned-tensors-only',maximum_range_bytes=CHUNK))
        return path
    finally:
        if owned:client.close()

def load_mapped(path,verify=True):
    import torch
    path=Path(path);index=json.loads((path/'weights.json').read_text());blueprint=json.loads((path/'blueprint.json').read_text());validate_bundle(blueprint)
    if index['blueprint']!=digest(blueprint) or set(index['tensors'])!=set(blueprint['tensors']):raise ValueError('Partition index mismatch')
    result={}
    for name,entry in index['tensors'].items():
        expected=hashlib.sha256(name.encode()).hexdigest()+'.bin'
        if entry['file']!=expected or entry['shape']!=blueprint['tensors'][name]['shape']:raise ValueError('Invalid partition file')
        file=path/expected;size=math.prod(entry['shape'])
        if file.is_symlink() or file.stat().st_size!=size*4:raise ValueError('Invalid tensor file')
        if verify:
            with file.open('rb') as handle:
                if hashlib.file_digest(handle,'sha256').hexdigest()!=entry['sha256']:raise ValueError('Corrupted tensor file')
        result[name]=torch.from_file(str(file),shared=False,size=size,dtype=torch.float32).reshape(entry['shape'])
    return result

def partition_fingerprint(directory):
    directory=Path(directory)
    if (directory/'blueprint.json').exists():
        from .partition_store import digest
        return digest(json.loads((directory/'blueprint.json').read_text()))
    from .protocol import checkpoint_hash
    return checkpoint_hash(directory/'weights.pt')
