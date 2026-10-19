"""Verify byte-aware constraints against complete gold plans and invalid JSON."""
import importlib.metadata,json
from pathlib import Path
from transformers import AutoTokenizer
import xgrammar as xgr
R=Path(__file__).resolve().parent
def main():
 tokenizer_path=R/'tokenizer'
 if tokenizer_path.exists():tok=AutoTokenizer.from_pretrained(tokenizer_path,local_files_only=True);vocab=json.loads((tokenizer_path/'config.json').read_text())['vocab_size']
 else:
  cfg=json.loads((R/'config.json').read_text());tok=AutoTokenizer.from_pretrained(cfg['base'],revision=cfg['revision']);vocab=152064
 info=xgr.TokenizerInfo.from_huggingface(tok,vocab_size=vocab,stop_token_ids=tok.eos_token_id);compiler=xgr.GrammarCompiler(info,max_threads=2)
 schema=json.loads((R/'contract.json').read_text(encoding='utf8'))['schema'];compiled=compiler.compile_json_schema(schema,strict_mode=False)
 rows=[]
 def accepts(text,grammar):
  matcher=xgr.GrammarMatcher(grammar)
  for token in tok.encode(text,add_special_tokens=False):
   if not matcher.accept_token(token):return False
  return matcher.accept_token(tok.eos_token_id) and matcher.is_terminated()
 for row in map(json.loads,(R/'dev.jsonl').read_text(encoding='utf8').splitlines()):
  if row['oracle']['type']=='plan':rows.append({'id':row['id'],'passed':accepts(row['answer'],compiled)})
 simple=compiler.compile_json_schema({'type':'object','properties':{'text':{'type':'string'}},'required':['text'],'additionalProperties':False},strict_mode=False)
 cases=[('literal_newline','{"text":"a\nb"}',False),('escaped_newline',json.dumps({'text':'a\nb'}),True),('unicode_path',json.dumps({'text':'C:\\資料夾\\繁體μ𠀀.txt'},ensure_ascii=False),True),('missing_close','{"text":"未完成',False)]
 edge=[{'id':name,'expected':expected,'actual':accepts(text,simple)} for name,text,expected in cases]
 report={'xgrammar':importlib.metadata.version('xgrammar'),'apache_tvm_ffi':importlib.metadata.version('apache-tvm-ffi'),'gold_plans_passed':sum(x['passed'] for x in rows),'gold_plans_total':len(rows),'rows':rows,'edge_cases':edge,'all_passed':all(x['passed'] for x in rows) and all(x['actual']==x['expected'] for x in edge),'scope':'Tokenizer/grammar admission and termination; does not measure model action correctness.'}
 (R/'XGRAMMAR_VERIFIED.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(report))
 if not report['all_passed']:raise RuntimeError('Grammar admission checks failed')
if __name__=='__main__':main()
