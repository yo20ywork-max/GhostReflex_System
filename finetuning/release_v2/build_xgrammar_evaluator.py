"""Create a separately versioned evaluator; never rewrite the frozen original."""
import ast,hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent
def main():
 dest=R/'evaluate_xgrammar.py'
 if dest.exists():raise FileExistsError(dest)
 lock=json.loads((R/'DATA_LOCK.json').read_text());source=R/'evaluate.py'
 if hashlib.sha256(source.read_bytes()).hexdigest()!=lock['sha256']['evaluate.py']:raise ValueError('Original evaluator changed')
 text=source.read_text(encoding='utf8')
 replacements=[
  ('verify_lock();cfg=',"verify_lock();verify_lock('GRAMMAR_EVAL_LOCK.json');cfg="),
  ('from lmformatenforcer import JsonSchemaParser\n    from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn', 'import xgrammar as xgr\n    import xgrammar.contrib.hf\n    from importlib.metadata import version'),
  ("schema=json.loads((ROOT/'contract.json').read_text(encoding='utf8'))['schema']", "schema=json.loads((ROOT/'contract.json').read_text(encoding='utf8'))['schema']\n    info=xgr.TokenizerInfo.from_huggingface(tokenizer,vocab_size=model.config.vocab_size,stop_token_ids=eos_ids)\n    compiler=xgr.GrammarCompiler(info,max_threads=2)\n    compiled=compiler.compile_json_schema(schema,strict_mode=False)\n    receipt.update(grammar_engine='xgrammar',xgrammar_version=version('xgrammar'),strict_mode=False)"),
  ("if plan:grammar['prefix_allowed_tokens_fn']=build_transformers_prefix_allowed_tokens_fn(tokenizer,JsonSchemaParser(schema))", "if plan:grammar['logits_processor']=[xgr.contrib.hf.LogitsProcessor(compiled)]"),
  ("result['schema_constrained']=plan", "result['schema_constrained']=plan\n                    result['grammar_engine']='xgrammar' if plan else None\n                    if plan:\n                        try:json.loads(answer);result['json_parseable']=True\n                        except ValueError:result['json_parseable']=False;result['completed']=False"),
 ]
 for old,new in replacements:
  if text.count(old)!=1:raise ValueError('Unexpected source shape: '+old[:80])
  text=text.replace(old,new)
 ast.parse(text);dest.write_text(text,encoding='utf8')
 names=['evaluate_xgrammar.py','verify_xgrammar.py','build_xgrammar_evaluator.py']
 out={'sha256':{**lock['sha256'],**{n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in names}},'reason':'Original LMFE0.11.3 rejects every known-good development gold token path and admits premature EOS/invalid strings. Separate byte-aware XGrammar comparison.','dependencies':{'xgrammar':'0.2.5.post1','apache-tvm-ffi':'0.1.13.post3'},'original_evaluator_unchanged':True,'strict_mode':False,'test_outputs_seen':False}
 (R/'GRAMMAR_EVAL_LOCK.json').write_text(json.dumps(out,indent=2));print(json.dumps({k:v for k,v in out.items() if k!='sha256'}))
if __name__=='__main__':main()
