"""Run only in the isolated Transformers 4.51.3 reference environment.

Synthetic tiny matrices validate architecture math, never 480B model quality.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from safetensors.torch import save_file
from transformers import Qwen3MoeConfig, Qwen3MoeForCausalLM


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--directory',default='runtime/moe-reference')
    args=parser.parse_args()
    root=Path(args.directory)
    root.mkdir(parents=True,exist_ok=True)
    torch.set_num_threads(1)
    torch.manual_seed(37)
    config=Qwen3MoeConfig(vocab_size=64,hidden_size=16,intermediate_size=32,
        moe_intermediate_size=12,num_hidden_layers=2,num_attention_heads=4,
        num_key_value_heads=2,head_dim=4,num_experts=4,num_experts_per_tok=2,
        norm_topk_prob=True,max_position_embeddings=128)
    config._attn_implementation='eager'
    model=Qwen3MoeForCausalLM(config).eval()
    config.save_pretrained(root)
    save_file({name:value.contiguous() for name,value in model.state_dict().items()},
              root/'model.safetensors')
    ids=torch.tensor([[1,5,7]])
    past=None
    results={}
    with torch.inference_mode():
        for step in range(4):
            result=model(ids,past_key_values=past,use_cache=True)
            past=result.past_key_values
            results['ids_'+str(step)]=ids.numpy()
            results['logits_'+str(step)]=result.logits[:,-1:,:].numpy()
            ids=result.logits[:,-1,:].argmax(-1).reshape(1,1)
    np.savez(root/'reference.npz',**results)
    (root/'provenance.json').write_text(json.dumps(dict(
        synthetic=True,quality_benchmark=False,torch=torch.__version__,
        transformers=__import__('transformers').__version__,steps=4)),encoding='utf8')
    print('Synthetic MoE reference saved:',root)


if __name__=='__main__':
    main()
