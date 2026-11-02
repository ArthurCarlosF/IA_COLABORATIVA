import json
from pathlib import Path
import torch
from transformers import AutoTokenizer, AutoConfig, AutoModelForCausalLM, GPT2Config
from transformers.models.gpt2.modeling_gpt2 import GPT2Block
MODEL = 'sshleifer/tiny-gpt2'
REVISION = '5f91d94bd9cd7190a9f3216ff93cd1dd95f2c7be2'

def prepare(root, model=MODEL, revision=REVISION, parts=2, capacities=None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    config=AutoConfig.from_pretrained(model,revision=revision)
    if config.model_type not in ('gpt2','qwen2'):raise ValueError('Arquitetura não suportada')
    if getattr(config,'use_sliding_window',False):raise ValueError('Sliding window não suportada')
    full = AutoModelForCausalLM.from_pretrained(model, revision=revision, attn_implementation='eager',torch_dtype=torch.float32).eval()
    qwen=config.model_type=='qwen2'
    layer_count=config.num_hidden_layers
    prefix='model.layers.' if qwen else 'transformer.h.'
    first_prefix=('model.embed_tokens.',) if qwen else ('transformer.wte.','transformer.wpe.')
    last_prefix=('model.norm.','lm_head.') if qwen else ('transformer.ln_f.','lm_head.')
    if not 1 <= parts <= layer_count:
        raise ValueError('Invalid partition count')
    AutoTokenizer.from_pretrained(model, revision=revision).save_pretrained(root / 'tokenizer')
    full.config.save_pretrained(root)
    state = full.state_dict()
    manifest = dict(model=model, revision=revision, parts=[], layers=layer_count,architecture=config.model_type,vocab_size=config.vocab_size)
    boundaries=[(i*layer_count//parts,(i+1)*layer_count//parts) for i in range(parts)]
    if capacities is not None:
        from .planner import plan
        if len(capacities)!=parts:raise ValueError('One memory budget per worker required')
        size=lambda t:t.numel()*t.element_size()
        layers=[sum(size(t) for n,t in state.items() if n.startswith(f'{prefix}{i}.')) for i in range(layer_count)]
        first=sum(size(t) for n,t in state.items() if n.startswith(first_prefix))
        last=sum(size(t) for n,t in state.items() if n.startswith(last_prefix))
        boundaries=plan(layers,capacities,first,last)
    for i in range(parts):
        start, end = boundaries[i]
        selected = {}
        for name, tensor in state.items():
            if name.startswith(prefix):
                if start <= int(name.split('.')[2]) < end:
                    selected[name] = tensor
            elif i == 0 and name.startswith(first_prefix):
                selected[name] = tensor
            elif i == parts-1 and name.startswith(last_prefix):
                selected[name] = tensor
        directory = root / f'part-{i}'
        directory.mkdir(exist_ok=True)
        full.config.save_pretrained(directory)
        torch.save(selected, directory / 'weights.pt')
        spec = dict(index=i, start=start, end=end, first=i==0, last=i==parts-1)
        (directory / 'spec.json').write_text(json.dumps(spec), encoding='utf8')
        manifest['parts'].append(spec)
    (root / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf8')
    return full

class GPT2Shard(torch.nn.Module):
    def __init__(self, directory, device='cpu'):
        super().__init__()
        directory = Path(directory)
        self.spec = json.loads((directory/'spec.json').read_text())
        self.config = GPT2Config.from_pretrained(directory)
        self.config._attn_implementation = 'eager'
        self.device = torch.device(device)
        self.kv_bytes_per_token=2*(self.spec['end']-self.spec['start'])*self.config.n_embd*4
        self.blocks = torch.nn.ModuleList([GPT2Block(self.config, layer_idx=i) for i in range(self.spec['start'], self.spec['end'])])
        if self.spec['first']:
            self.wte = torch.nn.Embedding(self.config.vocab_size, self.config.n_embd)
            self.wpe = torch.nn.Embedding(self.config.n_positions, self.config.n_embd)
        if self.spec['last']:
            self.ln_f = torch.nn.LayerNorm(self.config.n_embd, eps=self.config.layer_norm_epsilon)
            self.head = torch.nn.Linear(self.config.n_embd, self.config.vocab_size, bias=False)
        original = torch.load(directory/'weights.pt', map_location='cpu', weights_only=True)
        renamed = {}
        for name, value in original.items():
            if name.startswith('transformer.h.'):
                fields = name.split('.')
                key = 'blocks.'+str(int(fields[2])-self.spec['start'])+'.'+'.'.join(fields[3:])
            else:
                key = name.replace('transformer.', '').replace('lm_head.', 'head.')
            renamed[key] = value
        self.load_state_dict(renamed, strict=True)
        self.to(self.device).eval()

    @torch.inference_mode()
    def step(self, value, past=None, position=0):
        value = value.to(self.device)
        if self.spec['first']:
            positions = torch.arange(position, position+value.shape[1], device=self.device)
            value = self.wte(value)+self.wpe(positions)
        presents = []
        for i, block in enumerate(self.blocks):
            out = block(value, layer_past=None if past is None else past[i], use_cache=True)
            value = out[0]
            presents.append(out[1])
        if self.spec['last']:
            value = self.head(self.ln_f(value))[:, -1:, :]
        return value, tuple(presents)


class QwenShard(torch.nn.Module):
    def __init__(self,directory,device='cpu'):
        super().__init__()
        from transformers.models.qwen2.modeling_qwen2 import Qwen2DecoderLayer,Qwen2RMSNorm
        directory=Path(directory)
        self.spec=json.loads((directory/'spec.json').read_text())
        self.config=AutoConfig.from_pretrained(directory)
        self.config._attn_implementation='eager'
        if self.config.use_sliding_window:raise ValueError('Sliding window não suportada')
        self.config.n_embd=self.config.hidden_size
        self.config.n_positions=self.config.max_position_embeddings
        self.device=torch.device(device)
        count=self.spec['end']-self.spec['start']
        self.kv_bytes_per_token=2*count*self.config.num_key_value_heads*(self.config.hidden_size//self.config.num_attention_heads)*4
        # Cache local usa índices contíguos; posições RoPE continuam globais à sequência.
        with torch.device('meta'):
            self.blocks=torch.nn.ModuleList([Qwen2DecoderLayer(self.config,layer_idx=i) for i in range(count)])
            if self.spec['first']:
                self.embed=torch.nn.Embedding(self.config.vocab_size,self.config.hidden_size)
            if self.spec['last']:
                self.norm=Qwen2RMSNorm(self.config.hidden_size,eps=self.config.rms_norm_eps)
                self.head=torch.nn.Linear(self.config.hidden_size,self.config.vocab_size,bias=False)
        if (directory/'weights.json').exists():
            from .partition_store import load_mapped
            original=load_mapped(directory)
        else:original=torch.load(directory/'weights.pt',map_location='cpu',weights_only=True,mmap=True)
        renamed={}
        for name,value in original.items():
            if name.startswith('model.layers.'):
                fields=name.split('.')
                key='blocks.'+str(int(fields[2])-self.spec['start'])+'.'+'.'.join(fields[3:])
            else:
                key=name.replace('model.embed_tokens.','embed.').replace('model.norm.','norm.').replace('lm_head.','head.')
            renamed[key]=value
        self.load_state_dict(renamed,strict=True,assign=True)
        from transformers.models.qwen2.modeling_qwen2 import Qwen2RotaryEmbedding
        for block in self.blocks:block.self_attn.rotary_emb=Qwen2RotaryEmbedding(self.config.hidden_size//self.config.num_attention_heads,max_position_embeddings=self.config.max_position_embeddings,base=self.config.rope_theta,device=self.device)
        self.to(self.device).eval()

    @torch.inference_mode()
    def step(self,value,past=None,position=0):
        from transformers.cache_utils import DynamicCache
        from transformers.models.qwen2.modeling_qwen2 import _prepare_4d_causal_attention_mask_with_cache_position
        value=value.to(self.device)
        if self.spec['first']:value=self.embed(value)
        cache=DynamicCache.from_legacy_cache(past)
        if cache.get_seq_length()!=position:raise ValueError('Posição de cache inválida')
        cache_position=torch.arange(position,position+value.shape[1],device=self.device)
        mask=_prepare_4d_causal_attention_mask_with_cache_position(None,sequence_length=value.shape[1],target_length=position+value.shape[1]+1,dtype=value.dtype,device=self.device,min_dtype=torch.finfo(value.dtype).min,cache_position=cache_position,batch_size=value.shape[0])
        for block in self.blocks:
            value=block(value,attention_mask=mask,position_ids=cache_position.unsqueeze(0),past_key_value=cache,use_cache=True,cache_position=cache_position)[0]
        if self.spec['last']:value=self.head(self.norm(value)).float()[:,-1:,:]
        return value,cache.to_legacy_cache()


def Shard(directory,device='cpu'):
    config=AutoConfig.from_pretrained(directory)
    cls={'gpt2':GPT2Shard,'qwen2':QwenShard}.get(config.model_type)
    if cls is None:raise ValueError('Arquitetura não suportada')
    return cls(directory,device)
