"""Activation-only orchestration. Neural weights remain on assigned workers."""
import math
import torch
from .partition_store import digest
from .protocol import pack, unpack


class GraphExecutor:
    def __init__(self, manifest, pipeline, rpc):
        self.manifest = manifest
        self.nodes = {n['spec']['index']: n for n in pipeline}
        self.pieces = {p['id']: p for p in manifest['pieces']}
        self.fingerprints = {i: digest(manifest['bundles'][i]) for i in self.nodes}
        self.rpc = rpc

    async def step(self, ids, session, position, return_logits=True):
        records = []
        length = ids.shape[1]

        async def execute(op, value):
            owner = self.manifest['owners'][op]
            node = self.nodes[owner]
            request = dict(session=session, position=position, op=op,
                           model_fingerprint=self.fingerprints[owner],
                           tensor=pack(value))
            result = await self.rpc(node, '/step', request)
            if result['position'] != position+length or result['units'] != length:
                raise ValueError('Graph worker returned inconsistent position or work')
            if (not isinstance(result.get('seconds'), (int, float))
                    or not math.isfinite(result['seconds']) or result['seconds'] < 0):
                raise ValueError('Invalid graph timing')
            records.append((node, result))
            return unpack(result['tensor'])

        graph = self.manifest['graph']
        hidden = None
        for op in graph['embeddings']:
            output = await execute(op, ids)
            hidden = output if hidden is None else hidden+output
        for layer in graph['layers']:
            hidden = await execute(layer['attention'], hidden)
            if 'experts' in layer:
                probabilities = (await execute(layer['router'], hidden)).softmax(-1)
                config = self.manifest['config']
                weights, indices = probabilities.topk(config['num_experts_per_tok'], -1)
                if config.get('norm_topk_prob', False):
                    weights = weights/weights.sum(-1, keepdim=True)
                routing = torch.zeros_like(probabilities).scatter(-1, indices, weights)
                expert_input = torch.cat((hidden, routing), -1)
                output = torch.zeros_like(hidden)
                for op in layer['experts']:
                    experts = self.pieces[op]['experts']
                    if not routing[..., experts].any():
                        continue
                    output += await execute(op, expert_input)
            else:
                gates, ups = [], []
                for op in layer['gate']:
                    gates.append(await execute(op, hidden))
                for op in layer['up']:
                    ups.append(await execute(op, hidden))
                product = torch.cat(gates, -1)*torch.cat(ups, -1)
                outputs = []
                for op in layer['down']:
                    outputs.append(await execute(op, product))
                output = torch.cat(outputs, -1)
            hidden = hidden+output
        if not return_logits:
            return None, records
        logits = []
        for op in graph['heads']:
            logits.append(await execute(op, hidden))
        return torch.cat(logits, -1), records
