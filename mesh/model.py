import json
from pathlib import Path
import torch
from transformers import AutoTokenizer, GPT2LMHeadModel, GPT2Config
from transformers.models.gpt2.modeling_gpt2 import GPT2Block
MODEL = 'sshleifer/tiny-gpt2'
REVISION = '5f91d94bd9cd7190a9f3216ff93cd1dd95f2c7be2'

def prepare(root, model=MODEL, revision=REVISION, parts=2, capacities=None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    full = GPT2LMHeadModel.from_pretrained(model, revision=revision, attn_implementation='eager').eval()
    if not 1 <= parts <= full.config.n_layer:
        raise ValueError('Invalid partition count')
    AutoTokenizer.from_pretrained(model, revision=revision).save_pretrained(root / 'tokenizer')
    full.config.save_pretrained(root)
    state = full.state_dict()
    manifest = dict(model=model, revision=revision, parts=[], layers=full.config.n_layer)
    boundaries=[(i*full.config.n_layer//parts,(i+1)*full.config.n_layer//parts) for i in range(parts)]
    if capacities is not None:
        from .planner import plan
        if len(capacities)!=parts:raise ValueError('One memory budget per worker required')
        size=lambda t:t.numel()*t.element_size()
        layers=[sum(size(t) for n,t in state.items() if n.startswith(f'transformer.h.{i}.')) for i in range(full.config.n_layer)]
        first=sum(size(t) for n,t in state.items() if n.startswith(('transformer.wte.','transformer.wpe.')))
        last=sum(size(t) for n,t in state.items() if n.startswith(('transformer.ln_f.','lm_head.')))
        boundaries=plan(layers,capacities,first,last)
    for i in range(parts):
        start, end = boundaries[i]
        selected = {}
        for name, tensor in state.items():
            if name.startswith('transformer.h.'):
                if start <= int(name.split('.')[2]) < end:
                    selected[name] = tensor
            elif i == 0 and name.startswith(('transformer.wte.', 'transformer.wpe.')):
                selected[name] = tensor
            elif i == parts-1 and name.startswith(('transformer.ln_f.', 'lm_head.')):
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

class Shard(torch.nn.Module):
    def __init__(self, directory, device='cpu'):
        super().__init__()
        directory = Path(directory)
        self.spec = json.loads((directory/'spec.json').read_text())
        self.config = GPT2Config.from_pretrained(directory)
        self.config._attn_implementation = 'eager'
        self.device = torch.device(device)
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
