"""Reuse unchanged baseline generations without mislabelling new model outputs."""
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--baseline',required=True);p.add_argument('--candidate',required=True);p.add_argument('--output',required=True);a=p.parse_args()
base=[r for r in map(json.loads,Path(a.baseline).read_text(encoding='utf8').splitlines()) if r['candidate']=='base']
candidate=list(map(json.loads,Path(a.candidate).read_text(encoding='utf8').splitlines()))
if any(r['candidate']!='adapter' for r in candidate):raise ValueError('Candidate-only file required')
if {r['id']:r['prompt_sha256'] for r in base}!={r['id']:r['prompt_sha256'] for r in candidate}:raise ValueError('Prompt coverage mismatch')
out=Path(a.output)
if out.exists():raise FileExistsError(out)
out.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in base+candidate),encoding='utf8')
print('BASELINE_REUSED_IDENTICAL_PROMPTS')
