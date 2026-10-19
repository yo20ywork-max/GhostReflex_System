"""Exercise the export code on a small synthetic architecture, never a quality benchmark."""
import hashlib,json,os
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parent
if os.name!='posix' or ROOT.as_posix()!='/workspace/crossgen-release-v1':raise RuntimeError('Cloud workspace only')
os.environ['HF_HOME']=str(ROOT/'hf-cache')
import torch
from transformers import AutoTokenizer,Qwen2Config,Qwen2ForCausalLM
from export_gguf import write_merged_gguf,LLAMA_COMMIT
torch.set_num_threads(2)
cfg=json.loads((ROOT/'config.json').read_text())
source=ROOT/'llama.cpp'
if subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()!=LLAMA_COMMIT:raise ValueError('Converter version mismatch')
temporary=ROOT/'converter-verification';temporary.mkdir(exist_ok=True)
metadata=temporary/'metadata';metadata.mkdir(exist_ok=True)
tokenizer=AutoTokenizer.from_pretrained(cfg['base'],revision=cfg['revision'],local_files_only=True)
tokenizer.save_pretrained(metadata)
config=Qwen2Config(vocab_size=151936,hidden_size=64,intermediate_size=128,num_hidden_layers=1,num_attention_heads=4,num_key_value_heads=2,max_position_embeddings=2048,bos_token_id=151643,eos_token_id=151645,tie_word_embeddings=False)
model=Qwen2ForCausalLM(config).to(dtype=torch.bfloat16).eval()
model.config.architectures=['Qwen2ForCausalLM'];model.config.save_pretrained(metadata)
out=temporary/'synthetic-f16.gguf'
if out.exists():raise FileExistsError(out)
write_merged_gguf(model,metadata,source,out)
import gguf
reader=gguf.GGUFReader(out)
names={t.name for t in reader.tensors}
assert 'token_embd.weight' in names and 'output.weight' in names
assert out.stat().st_size<100_000_000
receipt={'synthetic_export_verified':True,'converter_commit':LLAMA_COMMIT,'tensor_count':len(names),'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'scope':'Engineering verification of the conversion path only; random tiny weights do not measure trained-model quality.'}
(ROOT/'CONVERTER_VERIFIED.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt),flush=True)
