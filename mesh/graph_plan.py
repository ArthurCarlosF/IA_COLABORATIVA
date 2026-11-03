"""Parameter-budget planning below whole-layer granularity.

This module plans work; it does not advertise an unimplemented executor.
"""
import math
import json
from pathlib import Path
from .partition_store import PROFILES

LARGE_PROFILE = ('Qwen/Qwen3-Coder-480B-A35B-Instruct',
                 '9d90cf8fca1bf7b7acca42d3fc9ae694a2194069')


def split_rows(shape, maximum_parameters):
    """Contiguous source rows, without downloading any foreign matrix columns."""
    if not shape or any(type(n) is not int or n < 1 for n in shape):
        raise ValueError('Invalid tensor shape')
    if type(maximum_parameters) is not int or maximum_parameters < 1:
        raise ValueError('Invalid parameter budget')
    width = math.prod(shape[1:])
    rows = maximum_parameters // width
    if not rows:
        raise ValueError('Budget cannot hold one row; column tensor parallelism required')
    return [(start, min(start + rows, shape[0]))
            for start in range(0, shape[0], rows)]


def pack_experts(experts, hidden_size, intermediate_size, maximum_parameters):
    """An expert owns its three FFN matrices; a pack also owns the norm."""
    if any(type(v) is not int or v < 1 for v in
           (experts, hidden_size, intermediate_size, maximum_parameters)):
        raise ValueError('Invalid expert budget')
    per_expert = 3 * hidden_size * intermediate_size
    count = (maximum_parameters - hidden_size) // per_expert
    if not count:
        raise ValueError('One expert exceeds the budget; split its matrices')
    return [list(range(start, min(start + count, experts)))
            for start in range(0, experts, count)]


def source_metadata(profile):
    from huggingface_hub import hf_hub_download
    model, revision = PROFILES[profile]
    config = json.loads(Path(hf_hub_download(
        model, 'config.json', revision=revision)).read_text())
    try:
        files = json.loads(Path(hf_hub_download(
            model, 'model.safetensors.index.json', revision=revision)).read_text())['weight_map']
    except Exception as exc:
        from huggingface_hub.errors import EntryNotFoundError
        if not isinstance(exc, EntryNotFoundError):
            raise
        files = None
    return model, revision, config, files


def expected_shapes(c):
    h = c['hidden_size']
    hd = c.get('head_dim', h // c['num_attention_heads'])
    q = c['num_attention_heads'] * hd
    k = c['num_key_value_heads'] * hd
    moe = c['model_type'] == 'qwen3_moe'
    shapes = {'model.embed_tokens.weight': [c['vocab_size'], h],
              'model.norm.weight': [h]}
    if not c.get('tie_word_embeddings'):
        shapes['lm_head.weight'] = [c['vocab_size'], h]
    for layer in range(c['num_hidden_layers']):
        p = f'model.layers.{layer}.'
        shapes[p + 'input_layernorm.weight'] = [h]
        shapes[p + 'post_attention_layernorm.weight'] = [h]
        for name, out, inp in [('q_proj', q, h), ('k_proj', k, h),
                               ('v_proj', k, h), ('o_proj', h, q)]:
            shapes[p + 'self_attn.' + name + '.weight'] = [out, inp]
        if moe:
            shapes[p + 'self_attn.q_norm.weight'] = [hd]
            shapes[p + 'self_attn.k_norm.weight'] = [hd]
        else:
            for name, out in [('q_proj', q), ('k_proj', k), ('v_proj', k)]:
                shapes[p + 'self_attn.' + name + '.bias'] = [out]
        prefixes = ([p + f'mlp.experts.{i}.' for i in range(c['num_experts'])]
                    if moe else [p + 'mlp.'])
        intermediate = c['moe_intermediate_size'] if moe else c['intermediate_size']
        for prefix in prefixes:
            for name, shape in [('gate_proj', [intermediate, h]),
                                ('up_proj', [intermediate, h]),
                                ('down_proj', [h, intermediate])]:
                shapes[prefix + name + '.weight'] = shape
        if moe:
            shapes[p + 'mlp.gate.weight'] = [c['num_experts'], h]
    return shapes


def build_graph(model, revision, c, files, workers, capacities=None,
                max_parameters=1_000_000_000, piece_parameters=None):
    if (c.get('model_type') not in ('qwen2', 'qwen3_moe')
            or c.get('use_sliding_window')
            or c.get('rope_scaling')
            or c.get('hidden_act', 'silu') != 'silu'):
        raise ValueError('Unsupported graph architecture')
    if type(workers) is not int or not 1 <= workers <= 8191:
        raise ValueError('Invalid worker count')
    if type(max_parameters) is not int or max_parameters < 1:
        raise ValueError('Invalid parameter budget')
    shapes = expected_shapes(c)
    if files and set(files) != set(shapes):
        raise ValueError('Source tensor names differ from the supported architecture')
    files = files or {key: 'model.safetensors' for key in shapes}
    source_total = sum(math.prod(shape) for shape in shapes.values())
    budgets = list(capacities) if capacities else [max_parameters*4] * workers
    if len(budgets) != workers or any(type(v) is not int or v <= 0 for v in budgets):
        raise ValueError('Invalid memory budgets')
    budgets = [min(v, max_parameters*4) for v in budgets]
    if sum(budgets) < source_total*4:
        raise ValueError('Insufficient aggregate memory for graph checkpoint')
    h = c['hidden_size']
    moe = c['model_type'] == 'qwen3_moe'
    cap = (min(max(1, max_parameters//16),
               max(1, math.ceil(source_total / workers * .9)))
           if workers > c['num_hidden_layers'] * 4 else max_parameters)
    if piece_parameters is not None:
        if type(piece_parameters) is not int or piece_parameters < 1:
            raise ValueError('Invalid piece budget')
        cap = min(cap, piece_parameters)
    pieces = []
    graph = dict(embeddings=[], layers=[], heads=[])

    def piece(kind, names, rows=None, experts=None, layer=None):
        index = str(len(pieces))
        tensors, weights = {}, {}
        for name in names:
            shape = shapes[name]
            sliced = rows and name.endswith(('embed_tokens.weight', 'lm_head.weight',
                                             'gate_proj.weight', 'up_proj.weight',
                                             'down_proj.weight'))
            start, end = rows if sliced else (0, shape[0])
            alias = index + ':' + name
            tensors[alias] = dict(source=name, source_shape=shape,
                                  rows=[start, end], shape=[end-start, *shape[1:]],
                                  file=files[name])
            weights[name] = alias
        parameters = sum(math.prod(t['shape']) for t in tensors.values())
        limit = max_parameters if kind == 'attention' else cap
        if parameters > limit:
            raise ValueError(f'Atomic {kind} requires {parameters} parameters; '
                             f'budget {limit}. Finer tensor parallelism required.')
        pieces.append(dict(id=index, kind=kind, weights=weights, tensors=tensors,
                           parameters=parameters, rows=rows, experts=experts,
                           layer=layer))
        return index

    def split(kind, name, norm=None, layer=None):
        reserve = math.prod(shapes[norm]) if norm else 0
        if reserve >= cap:
            raise ValueError('Budget cannot hold normalization and a matrix row')
        return [piece(kind, [name, *([norm] if norm else [])], rows=[a, b], layer=layer)
                for a, b in split_rows(shapes[name], cap-reserve)]

    graph['embeddings'] = split('embedding', 'model.embed_tokens.weight')
    for layer in range(c['num_hidden_layers']):
        p = f'model.layers.{layer}.'
        norm = p + 'post_attention_layernorm.weight'
        names = [name for name in shapes if name.startswith(p+'self_attn.')]
        entry = dict(attention=piece('attention', names + [p+'input_layernorm.weight'],
                                     layer=layer))
        if moe:
            entry['router'] = piece('router', [p+'mlp.gate.weight', norm], layer=layer)
            entry['experts'] = []
            for experts in pack_experts(c['num_experts'], h,
                                        c['moe_intermediate_size'], cap):
                names = [p + f'mlp.experts.{expert}.{proj}.weight'
                         for expert in experts
                         for proj in ('gate_proj', 'up_proj', 'down_proj')]
                entry['experts'].append(piece('experts', names + [norm],
                                              experts=experts, layer=layer))
        else:
            entry['gate'] = split('gate', p+'mlp.gate_proj.weight', norm, layer)
            entry['up'] = split('up', p+'mlp.up_proj.weight', norm, layer)
            entry['down'] = split('down', p+'mlp.down_proj.weight', layer=layer)
        graph['layers'].append(entry)
    head = 'model.embed_tokens.weight' if c.get('tie_word_embeddings') else 'lm_head.weight'
    graph['heads'] = split('head', head, 'model.norm.weight')
    if len(pieces) < workers:
        raise ValueError('More workers than executable pieces; lower the piece budget')
    used, owners = [0] * workers, {}
    initial = sorted(range(workers), key=lambda i: budgets[i], reverse=True)
    for rank, block in enumerate(sorted(pieces, key=lambda p: p['parameters'], reverse=True)):
        choices = ([initial[rank]] if rank < workers else
                   sorted(range(workers), key=lambda i: used[i]/budgets[i]))
        node = next((i for i in choices
                     if used[i] + block['parameters']*4 <= budgets[i]), None)
        if node is None:
            raise ValueError('Insufficient memory for graph assignment')
        owners[block['id']] = node
        used[node] += block['parameters'] * 4
    parts, bundles = [], []
    for node in range(workers):
        assigned = [p for p in pieces if owners[p['id']] == node]
        tensors = {key: value for p in assigned for key, value in p['tensors'].items()}
        operations = [{k: v for k, v in p.items() if k != 'tensors'} for p in assigned]
        spec = dict(index=node, start=node, end=node+1,
                    first=node == 0, last=node == workers-1)
        parts.append(spec)
        bundles.append(dict(model=model, revision=revision, config=c,
                            format='graph-f32-v1', spec=spec, pieces=operations,
                            tensors=tensors, max_parameters=max_parameters))
    return dict(model=model, revision=revision, config=c, architecture=c['model_type'],
                format='graph-f32-v1', layers=c['num_hidden_layers'],
                vocab_size=c['vocab_size'], parts=parts, bundles=bundles, graph=graph,
                pieces=[{k: v for k, v in p.items() if k != 'tensors'} for p in pieces],
                owners=owners, source_parameters=source_total,
                assigned_parameters=sum(used)//4,
                max_parameters_per_worker=max_parameters)


def plan_graph_remote(profile, parts, capacities=None, max_parameters=1_000_000_000):
    model, revision, config, files = source_metadata(profile)
    return build_graph(model, revision, config, files, parts, capacities, max_parameters)


def validate_graph_bundle(bundle):
    import re
    if (bundle.get('format') != 'graph-f32-v1'
            or (bundle.get('model'), bundle.get('revision')) not in PROFILES.values()):
        raise ValueError('Unapproved graph checkpoint')
    if bundle['config'].get('model_type') not in ('qwen2', 'qwen3_moe'):
        raise ValueError('Unsupported graph model')
    if not bundle['pieces'] or len({p['id'] for p in bundle['pieces']}) != len(bundle['pieces']):
        raise ValueError('Invalid graph operations')
    required = {alias for p in bundle['pieces'] for alias in p['weights'].values()}
    if required != set(bundle['tensors']):
        raise ValueError('Operation weights differ from assigned tensors')
    count = 0
    for alias, entry in bundle['tensors'].items():
        shape = entry['source_shape']
        start, end = entry['rows']
        if (not shape or any(type(n) is not int or n < 1 for n in shape)
                or not 0 <= start < end <= shape[0]
                or entry['shape'] != [end-start, *shape[1:]]):
            raise ValueError('Invalid source row slice')
        if not re.fullmatch(r'model(?:-\d+-of-\d+)?\.safetensors', entry['file']):
            raise ValueError('Invalid source filename')
        count += math.prod(entry['shape'])
    if count > bundle['max_parameters']:
        raise ValueError('Worker exceeds its parameter budget')
    return count*4


def provision_graph(bundle, cache, progress=None, client=None):
    import hashlib
    import shutil
    import httpx
    import torch
    from .partition_store import (digest, atomic_json, load_mapped, CHUNK,
                                  tensor_header, read_range, DTYPES)
    validate_graph_bundle(bundle)
    path = Path(cache)/digest(bundle)
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or not path.resolve().is_relative_to(Path(cache).resolve()):
        raise ValueError('Invalid graph cache')
    if (path/'weights.json').exists():
        load_mapped(path)
        return path
    if shutil.disk_usage(path).free < validate_graph_bundle(bundle)+2*CHUNK:
        raise ValueError('Insufficient disk for assigned graph operations')
    atomic_json(path/'blueprint.json', bundle)
    atomic_json(path/'config.json', bundle['config'])
    atomic_json(path/'spec.json', bundle['spec'])
    owned = client is None
    if owned:
        client = httpx.Client(follow_redirects=True, timeout=60, trust_env=False)
    headers, index, downloaded = {}, {}, 0
    try:
        for alias, entry in bundle['tensors'].items():
            url = (f"https://huggingface.co/{bundle['model']}/resolve/"
                   f"{bundle['revision']}/{entry['file']}")
            if entry['file'] not in headers:
                headers[entry['file']] = tensor_header(client, url)
            source = headers[entry['file']][entry['source']]
            if source['shape'] != entry['source_shape']:
                raise ValueError('Source shape differs from assignment')
            width = math.prod(entry['source_shape'][1:])
            element = DTYPES[source['dtype']]
            start = source['start'] + entry['rows'][0]*width*element
            size = math.prod(entry['shape'])*element
            filename = hashlib.sha256(alias.encode()).hexdigest()+'.bin'
            temporary = path/(filename+'.download')
            if temporary.is_symlink():
                raise ValueError('Invalid partial tensor file')
            sha = hashlib.sha256()
            with temporary.open('wb') as handle:
                for offset in range(0, size, CHUNK):
                    raw = read_range(client, url, start+offset, min(CHUNK, size-offset))
                    dtype = {'F32': torch.float32, 'F16': torch.float16,
                             'BF16': torch.bfloat16}[source['dtype']]
                    block = torch.frombuffer(raw, dtype=dtype).float().numpy().tobytes()
                    handle.write(block)
                    sha.update(block)
                    downloaded += len(raw)
                    if progress:
                        progress(dict(bytes_downloaded=downloaded, tensor=alias,
                                      partition=bundle['spec']['index']))
            temporary.replace(path/filename)
            index[alias] = dict(file=filename, shape=entry['shape'], sha256=sha.hexdigest())
        atomic_json(path/'weights.json',
                    dict(blueprint=digest(bundle), tensors=index,
                         bytes_downloaded=downloaded,
                         download_scope='assigned-matrix-rows-and-experts-only',
                         maximum_range_bytes=CHUNK))
        return path
    finally:
        if owned:
            client.close()
