"""Verify tokenizer IDs and architectural metadata without copying model weights."""
import hashlib,json,re,sys
from pathlib import Path
from evaluate_local import request
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R.parent/'release_v2/llama.cpp/gguf-py'))
import gguf
from transformers import AutoTokenizer

def main():
    model=request('/api/show',{'model':'qwen2.5-coder:7b'})
    match=re.search(r'^FROM\s+(.+)$',model['modelfile'],re.M)
    if not match:raise ValueError('No observed local base path')
    path=Path(match[1].strip().strip('"'))
    if not path.is_file():raise ValueError('Observed base file is unavailable')
    reader=gguf.GGUFReader(path);tokens=reader.fields['tokenizer.ggml.tokens'].contents()
    tokenizer=AutoTokenizer.from_pretrained(str(R.parent/'release_v2/tokenizer'),local_files_only=True,trust_remote_code=False)
    mismatch=[{'token':token,'id':index} for token,index in tokenizer.get_vocab().items() if index>=len(tokens) or tokens[index]!=token]
    config=json.loads((R.parent/'release_v2/tokenizer/config.json').read_text());mapping={'qwen2.embedding_length':'hidden_size','qwen2.block_count':'num_hidden_layers','qwen2.attention.head_count':'num_attention_heads','qwen2.attention.head_count_kv':'num_key_value_heads'}
    architecture={key:{'gguf':reader.fields[key].contents(),'hf':config[field]} for key,field in mapping.items()}
    report={'base_path':str(path),'base_file_bytes':path.stat().st_size,'hf_token_count':len(tokenizer.get_vocab()),'gguf_token_count':len(tokens),'token_id_mismatches':len(mismatch),'first_mismatches':mismatch[:5],'architecture':architecture,'metadata_compatible':not mismatch and all(x['gguf']==x['hf'] for x in architecture.values()),'scope':'Token strings/IDs and architecture only. Does not establish equivalence or provenance of quantized base tensors. No model copied or downloaded.'}
    (R/'DEPLOYMENT_METADATA.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ('base_path','architecture')},ensure_ascii=False))

if __name__=='__main__':main()
