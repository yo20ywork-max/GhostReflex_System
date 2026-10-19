"""Cross-runtime token ID parity using the GGUF tokenizer and fixed HF tokenizer."""
import ast,hashlib,json,os,subprocess,unicodedata
from pathlib import Path
ROOT=Path(__file__).resolve().parent
os.environ['HF_HOME']=str(ROOT/'hf-cache')
from transformers import AutoTokenizer
cfg=json.loads((ROOT/'config.json').read_text())
tokenizer=AutoTokenizer.from_pretrained(cfg['base'],revision=cfg['revision'],local_files_only=True)
texts=['CrossGen-AGI-μ，來自台灣的跨世代媒體科技股份有限公司。','不要山除檔案；展開目路。','你好\n\n  hello\tworld 1234567890 3.14159','def f(xs):\n    return [x * 2 for x in xs]\n','C:\\Users\\小明\\My Files\\a.txt','é é ＡＢＣ 😀 台灣🇹🇼','1987年7月15日；1992年11月7日。',tokenizer.apply_chat_template([{'role':'system','content':'請以台灣繁體中文回答。'},{'role':'user','content':'你是誰？'}],tokenize=False,add_generation_prompt=True)]
binary=ROOT/'quantizer/llama-b10819/llama-tokenize';model=ROOT/'converter-verification/synthetic-f16.gguf'
checks=[]
normalizer=json.loads(tokenizer.backend_tokenizer.to_str()).get('normalizer')
if normalizer!={'type':'NFC'}:raise ValueError('Unexpected upstream normalizer')
for text in texts:
    expected=tokenizer(text,add_special_tokens=False)['input_ids']
    result=subprocess.run([str(binary),'-m',str(model),'--stdin','--ids','--no-bos','--offline'],input=text,capture_output=True,text=True,encoding='utf8',timeout=30,check=True)
    actual=ast.literal_eval(result.stdout.strip())
    canonical=unicodedata.normalize('NFC',text)
    result=subprocess.run([str(binary),'-m',str(model),'--stdin','--ids','--no-bos','--offline'],input=canonical,capture_output=True,text=True,encoding='utf8',timeout=30,check=True)
    canonical_ids=ast.literal_eval(result.stdout.strip())
    checks.append({'text_sha256':hashlib.sha256(text.encode()).hexdigest(),'tokens':len(expected),'raw_equal':actual==expected,'nfc_equal':canonical_ids==expected})
    if canonical_ids!=expected:raise ValueError({'expected':expected,'actual':canonical_ids,'case':len(checks)})
receipt={'tokenizer_parity_verified_with_nfc':True,'raw_tokenizer_parity':all(c['raw_equal'] for c in checks),'cases':checks,'source_revision':cfg['revision'],'upstream_normalizer':normalizer,'note':'Original HF tokenizer applies NFC. GGUF caller must apply NFC to model-input text to reproduce it; raw decomposition can differ. Preserve original user text separately for byte-exact file operations. No Mistral-specific regex change applied.'}
(ROOT/'TOKENIZER_VERIFIED.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt),flush=True)
