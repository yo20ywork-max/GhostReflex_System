"""Run final model-only evaluation once using the frozen candidate and data hashes."""
import hashlib,json,subprocess,sys
from pathlib import Path
from evaluate_local import request
R=Path(__file__).resolve().parent
def main():
 s=json.loads((R/'FINAL_SELECTION.json').read_text())
 model=next(m for m in request('/api/tags')['models'] if m['name']==s['model'])
 if model['digest']!=s['model_digest']:raise ValueError('Selected model was replaced')
 for name,digest in s['heldout_sha256'].items():
  if hashlib.sha256((R/name).read_bytes()).hexdigest()!=digest:raise ValueError('Held-out input changed')
 for name,output in [('test.jsonl','local-final-test.jsonl'),('provenance-audit.jsonl','local-final-provenance.jsonl')]:
  if (R/output).exists():raise FileExistsError(output)
 for name,output in [('test.jsonl','local-final-test.jsonl'),('provenance-audit.jsonl','local-final-provenance.jsonl')]:
  subprocess.run([sys.executable,'-X','utf8',str(R/'evaluate_local.py'),'--data',name,'--output',output,'--model',s['model'],'--candidate','adapter'],check=True)
 subprocess.run([sys.executable,'-X','utf8',str(R/'score_runtime.py'),'--data',str(R/'test.jsonl'),'--results',str(R/'local-final-test.jsonl')],check=True)
 subprocess.run([sys.executable,'-X','utf8',str(R/'code_extended_audit.py'),'--data','test.jsonl','--results','local-final-test.jsonl'],check=True)
 print('FINAL_LOCAL_GENERATION_AND_AUTOMATIC_CHECKS_DONE')
if __name__=='__main__':main()
