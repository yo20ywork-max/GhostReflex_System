"""Freeze one candidate and unopened evaluation hashes before final generation."""
import argparse,hashlib,json,datetime
from pathlib import Path
R=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',choices=['epoch1','epoch2','repair'],required=True);p.add_argument('--diagnostic-only',action='store_true');a=p.parse_args()
 if (R/'FINAL_SELECTION.json').exists():raise RuntimeError('Candidate selection already frozen')
 if any((R/n).exists() for n in ['local-final-test.jsonl','local-final-provenance.jsonl']):raise RuntimeError('Final outputs already exist')
 gate_path=R/('DEV_GATE-'+a.candidate+'.json');gate=json.loads(gate_path.read_text())
 if not gate['development_passed'] and not a.diagnostic_only:raise RuntimeError('Candidate fails development criteria; diagnostic-only assessment must be explicit')
 adapter_name={'epoch1':'epoch-1','epoch2':'epoch-2','repair':'repair'}[a.candidate]
 adapter=R/'local-adapters'/(adapter_name+'.gguf');verified=json.loads(adapter.with_suffix('.verified.json').read_text())
 if not verified['verified'] or not verified['all_tensors_bitwise_equal'] or sha(adapter)!=verified['gguf_sha256']:raise ValueError('Unverified selected weight')
 selection={'selected_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'candidate':a.candidate,'model':gate['model'],'model_digest':gate['model_digest'],'development_passed':gate['development_passed'],'diagnostic_only':a.diagnostic_only,'known_failed_checks':gate['failed_checks'],'development_gate_sha256':sha(gate_path),'gguf_sha256':verified['gguf_sha256'],'safetensors_sha256':verified['source_sha256'],'heldout_sha256':{n:sha(R/n) for n in ['test.jsonl','provenance-audit.jsonl']},'criteria_sha256':sha(R/'RELEASE_CRITERIA.md'),'rubric_sha256':sha(R/'AUDIT_RUBRIC.md'),'scoring_policy_sha256':sha(R/'SCORING_POLICY.json'),'extended_code_audit_sha256':sha(R/'code_extended_audit.py'),'product_release_approved':False,'scope':'One candidate frozen before new test/provenance outputs. No further training based on these final answers in this run.'}
 with (R/'FINAL_SELECTION.json').open('x',encoding='utf8') as f:json.dump(selection,f,indent=2)
 print(json.dumps(selection))
if __name__=='__main__':main()
