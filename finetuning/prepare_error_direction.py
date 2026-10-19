"""Use observed baseline mistakes for the isolated error-direction experiment."""
import copy
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parent
baseline=root/'results/baseline-20260905T151429Z.jsonl'
observed={r['id']:r for r in (json.loads(line) for line in baseline.read_text(encoding='utf-8').splitlines())}
data=json.loads((root/'political_pilot_data.json').read_text(encoding='utf-8'))
rows=[]
for row in data['records']:
    if row['split']!='train':
        continue
    record=observed[row['id']]
    row=copy.deepcopy(row)
    row['rejected']=record['response']['message']['content']
    row['rejected_origin']='observed local qwen2.5-coder:7b baseline; stored source file hash below'
    row['baseline_sha256']=hashlib.sha256(baseline.read_bytes()).hexdigest()
    row['baseline_model_digest']=record['model']['digest']
    rows.append(row)
data['records']=rows
data['status']='Isolated error-direction pilot only. Never serve this adapter to product users.'
output=root/'error_direction_data.json'
output.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Prepared {len(rows)} observed baseline error targets; no evaluation rows used.')
