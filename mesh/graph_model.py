"""Weight-local operators for Qwen2 dense and Qwen3 MoE execution graphs."""
import json
import math
from pathlib import Path
from types import SimpleNamespace
import hashlib
import torch
from torch.nn import functional as F
from .partition_store import load_mapped


class GraphShard(torch.nn.Module):
    is_graph = True
    linear = staticmethod(F.linear)

    def __init__(self, directory, device='cpu'):
        super().__init__()
        directory = Path(directory)
        blueprint = json.loads((directory/'blueprint.json').read_text())
        self.spec = blueprint['spec']
        self.config = SimpleNamespace(**blueprint['config'])
        self.config.n_embd = self.config.hidden_size
        self.config.n_positions = self.config.max_position_embeddings
        self.device = torch.device(device)
        self.operations = {p['id']: p for p in blueprint['pieces']}
        tensors = load_mapped(directory)
        self.keys = {key: hashlib.sha256(key.encode()).hexdigest() for key in tensors}
        self.weights = torch.nn.ParameterDict({
            self.keys[key]: torch.nn.Parameter(value, requires_grad=False)
            for key, value in tensors.items()})
        self.kv_bytes_per_token = 0
        self.to(self.device).eval()

    def operation(self, op):
        if not isinstance(op, str) or op not in self.operations:
            raise ValueError('Operation not assigned to this worker')
        return self.operations[op]

    def input_width(self, op):
        kind = self.operation(op)['kind']
        if kind == 'down':
            return self.config.intermediate_size
        if kind == 'experts':
            return self.config.hidden_size + self.config.num_experts
        return self.config.hidden_size

    def cache_rate(self, op):
        if self.operation(op)['kind'] != 'attention':
            return 0
        c = self.config
        return 2*c.num_key_value_heads*getattr(
            c, 'head_dim', c.hidden_size//c.num_attention_heads)*4

    def weight(self, operation, name):
        return self.weights[self.keys[operation['weights'][name]]]

    def norm(self, x, weight):
        return x * torch.rsqrt(x.float().square().mean(-1, keepdim=True)
                               + self.config.rms_norm_eps) * weight

    @torch.inference_mode()
    def step_op(self, op, value, past=None, position=0):
        p = self.operation(op)
        kind = p['kind']
        c = self.config
        value = value.to(self.device)
        prefix = f"model.layers.{p['layer']}." if p['layer'] is not None else ''
        w = lambda name: self.weight(p, name)
        if kind == 'embedding':
            start, end = p['rows']
            mask = (value >= start) & (value < end)
            output = F.embedding((value-start).clamp(0, end-start-1),
                                 w('model.embed_tokens.weight'))
            return output*mask.unsqueeze(-1), ()
        if kind == 'head':
            source = ('model.embed_tokens.weight' if c.tie_word_embeddings
                      else 'lm_head.weight')
            x = self.norm(value[:, -1:, :], w('model.norm.weight'))
            return self.linear(x, w(source)), ()
        if kind in ('gate', 'up', 'router'):
            x = self.norm(value, w(prefix+'post_attention_layernorm.weight'))
            projection = 'gate' if kind == 'router' else kind+'_proj'
            output = self.linear(x, w(prefix+'mlp.'+projection+'.weight'))
            return (F.silu(output) if kind == 'gate' else output), ()
        if kind == 'down':
            return self.linear(value, w(prefix+'mlp.down_proj.weight')), ()
        if kind == 'experts':
            hidden = value[..., :c.hidden_size]
            routing = value[..., c.hidden_size:]
            x = self.norm(hidden, w(prefix+'post_attention_layernorm.weight'))
            flat = x.reshape(-1, c.hidden_size)
            route = routing.reshape(-1, c.num_experts)
            out = torch.zeros_like(flat)
            for expert in p['experts']:
                indices = torch.nonzero(route[:, expert] != 0).flatten()
                if not len(indices):
                    continue
                local = flat[indices]
                base = prefix+f'mlp.experts.{expert}.'
                output = self.linear(
                    F.silu(self.linear(local, w(base+'gate_proj.weight'))) *
                    self.linear(local, w(base+'up_proj.weight')),
                    w(base+'down_proj.weight'))
                out.index_add_(0, indices, output*route[indices, expert, None])
            return out.reshape_as(hidden), ()
        if kind != 'attention':
            raise ValueError('Unsupported graph operation')
        residual = value
        x = self.norm(value, w(prefix+'input_layernorm.weight'))
        batch, length, _ = x.shape
        hd = getattr(c, 'head_dim', c.hidden_size//c.num_attention_heads)
        projected = []
        for name, heads in [('q', c.num_attention_heads),
                            ('k', c.num_key_value_heads),
                            ('v', c.num_key_value_heads)]:
            base = prefix+'self_attn.'+name+'_proj.'
            bias = w(base+'bias') if base+'bias' in p['weights'] else None
            state = self.linear(x, w(base+'weight'), bias).view(batch, length, heads, hd)
            norm = prefix+'self_attn.'+name+'_norm.weight'
            if norm in p['weights']:
                state = self.norm(state, w(norm))
            projected.append(state.transpose(1, 2))
        q, k, v = projected
        positions = torch.arange(position, position+length, device=self.device)
        inverse = 1/(c.rope_theta**(torch.arange(
            0, hd, 2, device=self.device, dtype=torch.float32)/hd))
        angles = torch.outer(positions.float(), inverse)
        angles = torch.cat((angles, angles), -1)[None, None, :, :]

        def rotate(t):
            rotated = torch.cat((-t[..., hd//2:], t[..., :hd//2]), -1)
            return t*angles.cos() + rotated*angles.sin()

        q, k = rotate(q), rotate(k)
        if past:
            if past[0][0].shape[-2] != position:
                raise ValueError('Attention cache position mismatch')
            k = torch.cat((past[0][0], k), -2)
            v = torch.cat((past[0][1], v), -2)
        elif position:
            raise ValueError('Missing attention cache')
        cache = ((k, v),)
        groups = c.num_attention_heads//c.num_key_value_heads
        allowed = torch.arange(k.shape[-2], device=self.device)[None, :] <= positions[:, None]
        attended = []
        for head in range(c.num_key_value_heads):
            query = q[:, head*groups:(head+1)*groups]
            scores = torch.matmul(query, k[:, head:head+1].transpose(-1, -2))/math.sqrt(hd)
            scores = scores.masked_fill(~allowed[None, None], torch.finfo(scores.dtype).min)
            attended.append(torch.matmul(scores.softmax(-1, dtype=torch.float32),
                                          v[:, head:head+1]))
        attention = torch.cat(attended, 1)
        attention = attention.transpose(1, 2).reshape(batch, length, -1)
        return residual+self.linear(attention, w(prefix+'self_attn.o_proj.weight')), cache
