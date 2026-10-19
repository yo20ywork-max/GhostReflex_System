"""Check every Qwen LoRA tensor survives the pinned GGUF conversion exactly."""
import argparse,hashlib,json,re,sys
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R.parent/'release_v2/llama.cpp/gguf-py'))
import gguf
from safetensors import safe_open
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser();group=p.add_mutually_exclusive_group(required=True);group.add_argument('--epoch',choices=['1','2','3']);group.add_argument('--prior-fusion',action='store_true');a=p.parse_args()
 name='epoch-'+str(a.epoch)
 if a.prior_fusion:raise ValueError('V13 only verifies its own checkpoints')
 source=R/'artifacts'/'outputs'/name/'adapter_model.safetensors'
 dest=R/'local-adapters'/(name+'.gguf');alpha=64
 reader=gguf.GGUFReader(dest);assert reader.fields['general.architecture'].contents()=='qwen2';assert reader.fields['adapter.type'].contents()=='lora';assert reader.fields['adapter.lora.alpha'].contents()==alpha
 tensors={t.name:t.data for t in reader.tensors};seen=set()
 mapping={'mlp.down_proj':'ffn_down','mlp.up_proj':'ffn_up','mlp.gate_proj':'ffn_gate','self_attn.q_proj':'attn_q','self_attn.k_proj':'attn_k','self_attn.v_proj':'attn_v','self_attn.o_proj':'attn_output'}
 with safe_open(str(source),framework='np') as f:
  for name in f.keys():
   match=re.fullmatch(r'base_model.model.model.layers\.(\d+)\.(.+)\.lora_([AB])\.weight',name)
   if not match:raise ValueError('Unexpected tensor name')
   layer,module,side=match.groups();key=f'blk.{layer}.{mapping[module]}.weight.lora_{side.lower()}'
   array=f.get_tensor(name)
   if not np.isfinite(array).all() or not np.array_equal(array,tensors[key]):raise ValueError('Conversion changed tensor: '+name)
   seen.add(key)
 if seen!=set(tensors) or len(seen)!=392:raise ValueError('Incomplete tensor mapping')
 report={'verified':True,'epoch':a.epoch,'source_sha256':sha(source),'gguf_sha256':sha(dest),'gguf_bytes':dest.stat().st_size,'tensor_count':len(seen),'all_tensors_bitwise_equal':True,'lora_alpha':alpha,'converter_commit':'6a1a922d269908a29cbd4b49c27e6a8e7fd10fae','scope':'Format conversion integrity, not model quality or base-quantization equivalence.'}
 dest.with_suffix('.verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
if __name__=='__main__':main()
