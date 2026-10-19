"""Filter public examples using literal test extraction and restricted evaluation."""
import ast,collections,hashlib,json,re,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent
def main():
 source=R/'sources/code-source.jsonl';out=[];counts=collections.Counter();seen=set()
 for row in map(json.loads,source.read_text(encoding='utf8').splitlines()):
  if float(row['average_test_score'])!=1:counts['upstream_failed']+=1;continue
  match=re.fullmatch(r'\s*```python\s*\n(.*?)\n```\s*',row['output'],re.S)
  if not match:counts['not_single_python_block']+=1;continue
  code=match.group(1)
  try:
   tests=[];function=None
   for text in json.loads(row['unit_tests']):
    body=ast.parse(text).body
    if len(body)!=1 or not isinstance(body[0],ast.Assert):raise ValueError()
    c=body[0].test
    if not isinstance(c,ast.Compare) or len(c.ops)!=1 or not isinstance(c.ops[0],ast.Eq) or not isinstance(c.left,ast.Call) or not isinstance(c.left.func,ast.Name) or c.left.keywords:raise ValueError()
    name=c.left.func.id
    if function is not None and function!=name:raise ValueError()
    function=name;tests.append({'args':[ast.literal_eval(x) for x in c.left.args],'expected':ast.literal_eval(c.comparators[0])})
   if len(tests)<5:raise ValueError()
   payload={'code':code,'function':function,'tests':tests}
   wire=json.dumps(payload)
   if len(wire)>40000:raise ValueError()
  except (ValueError,SyntaxError,TypeError):counts['unsupported_test_structure']+=1;continue
  # Keep one example per function name as a conservative near-duplicate filter.
  if function in seen:counts['duplicate_function']+=1;continue
  try:
   p=subprocess.run([sys.executable,'-I',str(R/'code_sandbox.py')],input=wire,capture_output=True,text=True,encoding='utf8',timeout=3)
   result=json.loads(p.stdout)
  except (ValueError,subprocess.TimeoutExpired):counts['evaluation_error']+=1;continue
  if not result.get('passed'):counts['restricted_test_failed']+=1;continue
  seen.add(function);out.append({'id':'oci-'+row['id'],'function':function,'prompt':row['input']+'\nReturn only the Python implementation, including required imports.','answer':code,'tests':tests,'source_id':row['id'],'upstream_score':row['average_test_score'],'verification':result})
  counts['accepted']+=1
 (R/'sources/code-verified.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in out),encoding='utf8')
 receipt={'counts':dict(counts),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'execution':'Allowlisted pure functions in isolated Python subprocesses, 3-second timeout; no desktop/network/filesystem access exposed. Not a full OS sandbox.','limitation':'Passing the supplied assertions does not prove all cases or exclude pretraining overlap.'}
 (R/'sources/CODE_FILTER.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
if __name__=='__main__':main()
