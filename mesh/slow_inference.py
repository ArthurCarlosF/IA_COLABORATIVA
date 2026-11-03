"""Detached, resumable inference with source weights streamed one tile at a time."""
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace
import numpy as np
import torch
from .durable_tiles import DurableMatmul,matmul_tile
from .graph_executor import GraphExecutor
from .graph_model import GraphShard
from .partition_store import canonical, digest
from .protocol import pack, unpack
from .stream_weights import RemoteWeights


class Paused(Exception):
    pass


class StreamingShard(GraphShard):
    def __init__(self, manifest, source, store, maximum_tiles, cancel):
        # Deliberately do not initialize the resident-weight GraphShard.
        torch.nn.Module.__init__(self)
        self.device = torch.device('cpu')
        self.config = SimpleNamespace(**manifest['config'])
        self.operations = {p['id']: p for p in manifest['pieces']}
        self.entries = {key: value for bundle in manifest['bundles']
                        for key, value in bundle['tensors'].items()}
        self.source, self.store = source, store
        self.remaining = maximum_tiles
        self.executed = 0
        self.cancel = cancel

    def weight(self, operation, name):
        entry = self.entries[operation['weights'][name]]
        if len(entry['shape']) == 1:
            return torch.from_numpy(self.source.vector(entry))
        return self.source.matrix(entry)

    def linear(self, x, weight, bias=None):
        flat = x.reshape(-1, x.shape[-1]).cpu().numpy()
        result = self.store.run(flat, weight.source_id, weight.shape,
                                weight.fetch, max_tiles=self.remaining, cancel=self.cancel)
        self.executed += result['executed']
        if self.remaining is not None:
            self.remaining -= result['executed']
        if result['status'] == 'paused':
            raise Paused(result['id'])
        output = torch.from_numpy(result['output']).reshape(*x.shape[:-1], weight.shape[0])
        return output if bias is None else output+bias

    @torch.inference_mode()
    def step_op(self, op, value, past=None, position=0):
        operation = self.operation(op)
        if operation['kind'] != 'embedding':
            return super().step_op(op, value, past, position)
        start, end = operation['rows']
        output = torch.zeros((*value.shape, self.config.hidden_size), dtype=torch.float32)
        matrix = self.weight(operation, 'model.embed_tokens.weight')
        columns = max(1, self.source.maximum_bytes//4)
        for index, token in enumerate(value.flatten().tolist()):
            if start <= token < end:
                row = output.reshape(-1, self.config.hidden_size)[index]
                for column in range(0, len(row), columns):
                    stop = min(len(row), column+columns)
                    fetched = matrix.fetch(token-start, token-start+1, column, stop)
                    row[column:stop] = torch.from_numpy(fetched[0])
        return output, ()


async def run_slow(manifest, prompt_ids, directory, maximum_tokens, eos_token,
                   client, maximum_tiles=None, tile_rows=16, tile_columns=256,
                   maximum_bytes=65536, cancel=None,kernel=matmul_tile,
                   kernel_id='numpy-local-v1'):
    if (not prompt_ids or any(type(t) is not int or not 0 <= t < manifest['vocab_size']
                              for t in prompt_ids)
            or type(maximum_tokens) is not int or maximum_tokens < 1
            or len(prompt_ids)+maximum_tokens > min(
                4096, manifest['config']['max_position_embeddings'])):
        raise ValueError('Invalid token count or context')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    lease = sqlite3.connect(directory/'lease.sqlite', timeout=.2)
    try:
        lease.execute('BEGIN EXCLUSIVE')
        return await _run(manifest, prompt_ids, directory, maximum_tokens, eos_token,
                          client, maximum_tiles, tile_rows, tile_columns, maximum_bytes,
                          cancel,kernel,kernel_id)
    finally:
        lease.close()


async def _run(manifest, prompt_ids, directory, maximum_tokens, eos_token,
               client, maximum_tiles, tile_rows, tile_columns, maximum_bytes, cancel,
               kernel,kernel_id):
    torch.set_num_threads(1)
    db = sqlite3.connect(directory/'inference.sqlite')
    db.executescript("""
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
CREATE TABLE IF NOT EXISTS generation(id INTEGER PRIMARY KEY, descriptor TEXT NOT NULL,
 position INTEGER NOT NULL, generated TEXT NOT NULL, done INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS attention(op TEXT NOT NULL, position INTEGER NOT NULL,
 input_hash TEXT NOT NULL, output BLOB NOT NULL, k BLOB NOT NULL, v BLOB NOT NULL,
 checksum TEXT NOT NULL, PRIMARY KEY(op,position));
""")
    matrix = DurableMatmul(directory/'matrices.sqlite', tile_rows, tile_columns,
                          maximum_bytes,kernel,kernel_id)
    try:
        description = dict(format='slow-graph-v1', manifest=digest(manifest),
            prompt=prompt_ids, maximum_tokens=maximum_tokens, eos=eos_token,
            tile_rows=tile_rows,tile_columns=tile_columns,maximum_bytes=maximum_bytes,
            torch=str(torch.__version__),numpy=np.__version__)
        if kernel_id!='numpy-local-v1':description['kernel']=kernel_id
        descriptor = canonical(description).decode()
        with db:
            db.execute("INSERT OR IGNORE INTO generation VALUES(1,?,0,'[]',0)",
                       (descriptor,))
        stored, position, generated_json, done = db.execute(
            'SELECT descriptor,position,generated,done FROM generation WHERE id=1').fetchone()
        if stored != descriptor:
            raise ValueError('Resume requires the same model, input and numeric environment')
        generated = json.loads(generated_json)
        h = manifest['config']['hidden_size']
        source = RemoteWeights(manifest['model'], manifest['revision'], client,max(maximum_bytes,h*4))
        shard = StreamingShard(manifest, source, matrix, maximum_tiles, cancel)
        kv_heads = manifest['config']['num_key_value_heads']
        head_dim = manifest['config'].get('head_dim', h//manifest['config']['num_attention_heads'])

        def checksum(input_hash, output, k, v):
            return hashlib.sha256(input_hash.encode()+output+k+v).hexdigest()

        async def local_step(node, path, request):
            start = time.perf_counter()
            op, pos = request['op'], request['position']
            p = shard.operation(op)
            value = unpack(request['tensor'], integer=p['kind']=='embedding')
            if p['kind'] != 'attention':
                output, _ = shard.step_op(op, value, None, pos)
            else:
                input_hash = hashlib.sha256(value.numpy().tobytes()).hexdigest()
                row = db.execute(
                    'SELECT input_hash,output,k,v,checksum FROM attention WHERE op=? AND position=?',
                    (op,pos)).fetchone()
                if row:
                    if row[0] != input_hash or checksum(*row[:4]) != row[4]:
                        raise ValueError('Attention checkpoint differs from this input')
                    output = torch.from_numpy(np.frombuffer(row[1],np.float32).copy()).reshape(1,1,h)
                else:
                    past = None
                    if pos:
                        keys = np.empty((1,kv_heads,pos,head_dim),np.float32)
                        values = np.empty_like(keys)
                        seen = 0
                        for at, ih, result, key, val, sha in db.execute(
                                'SELECT position,input_hash,output,k,v,checksum FROM attention '
                                'WHERE op=? AND position<? ORDER BY position',(op,pos)):
                            if at != seen or checksum(ih,result,key,val) != sha:
                                raise ValueError('Missing or corrupted KV checkpoint')
                            keys[0,:,at,:] = np.frombuffer(key,np.float32).reshape(kv_heads,head_dim)
                            values[0,:,at,:] = np.frombuffer(val,np.float32).reshape(kv_heads,head_dim)
                            seen += 1
                        if seen != pos:
                            raise ValueError('Incomplete KV checkpoint')
                        past = ((torch.from_numpy(keys),torch.from_numpy(values)),)
                    output, cache = shard.step_op(op,value,past,pos)
                    k = cache[0][0][:,:,-1,:].contiguous().numpy().tobytes()
                    v = cache[0][1][:,:,-1,:].contiguous().numpy().tobytes()
                    data = output.contiguous().numpy().tobytes()
                    with db:
                        db.execute('INSERT INTO attention VALUES(?,?,?,?,?,?,?)',
                                   (op,pos,input_hash,data,k,v,checksum(input_hash,data,k,v)))
            return dict(tensor=pack(output),units=1,position=pos+1,
                        seconds=time.perf_counter()-start)

        executor = GraphExecutor(manifest,[dict(id=str(p['index']),spec=p)
                                           for p in manifest['parts']],local_step)
        paused_at = None
        while not done:
            token = (prompt_ids[position] if position < len(prompt_ids)
                     else generated[position-len(prompt_ids)])
            try:
                logits, _ = await executor.step(torch.tensor([[token]],dtype=torch.long),
                    '0'*32, position, return_logits=position>=len(prompt_ids)-1)
            except Paused as paused:
                paused_at = str(paused)
                break
            position += 1
            if logits is not None:
                next_token = int(logits[0,-1].argmax())
                if next_token == eos_token:
                    done = 1
                else:
                    generated.append(next_token)
                    done = int(len(generated)>=maximum_tokens)
            with db:
                db.execute('UPDATE generation SET position=?,generated=?,done=? WHERE id=1',
                           (position,json.dumps(generated),done))
        return dict(status='completed' if done else 'paused',position=position,
                    generated=generated,tiles_executed=shard.executed,
                    source_weight_bytes=source.downloaded_bytes,paused_matrix=paused_at)
    finally:
        matrix.close()
        db.close()
