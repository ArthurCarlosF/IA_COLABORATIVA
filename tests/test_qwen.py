"""Regressão da arquitetura com pesos sintéticos; o teste do checkpoint real é separado."""
import json
import torch
from transformers import Qwen2Config,Qwen2ForCausalLM
from mesh.model import Shard

def test_qwen_partition_cache_matches_complete_tensor_model(tmp_path):
    torch.manual_seed(17)
    torch.set_num_threads(1)
    cfg=Qwen2Config(vocab_size=64,hidden_size=16,intermediate_size=32,num_hidden_layers=4,num_attention_heads=4,num_key_value_heads=2,max_position_embeddings=128)
    cfg._attn_implementation='eager'
    full=Qwen2ForCausalLM(cfg).eval()
    shards=[]
    for index in range(2):
        path=tmp_path/str(index);path.mkdir()
        cfg.save_pretrained(path)
        spec=dict(index=index,start=index*2,end=(index+1)*2,first=index==0,last=index==1)
        (path/'spec.json').write_text(json.dumps(spec))
        selected={}
        for name,value in full.state_dict().items():
            if name.startswith('model.layers.'):
                if spec['start']<=int(name.split('.')[2])<spec['end']:selected[name]=value
            elif (index==0 and name.startswith('model.embed_tokens.')) or (index==1 and name.startswith(('model.norm.','lm_head.'))):selected[name]=value
        torch.save(selected,path/'weights.pt')
        shards.append(Shard(path))
    ids=torch.tensor([[i%64 for i in range(70)]])
    reference_past=None
    caches=[None,None]
    position=0
    with torch.inference_mode():
        for _ in range(6):
            ref=full(ids,past_key_values=reference_past,use_cache=True)
            reference_past=ref.past_key_values
            for offset in range(0,ids.shape[1],32):
                value=ids[:,offset:offset+32]
                length=value.shape[1]
                for i,shard in enumerate(shards):value,caches[i]=shard.step(value,caches[i],position)
                position+=length
            torch.testing.assert_close(value,ref.logits[:,-1:,:],atol=1e-6,rtol=1e-5)
            ids=value[0,-1].argmax().reshape(1,1)
