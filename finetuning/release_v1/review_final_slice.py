import json,argparse
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('stem');p.add_argument('--candidate',default='adapter');p.add_argument('--start',type=int,default=0);p.add_argument('--count',type=int,default=20);p.add_argument('--pending',action='store_true');a=p.parse_args()
root=Path(__file__).resolve().parent
c=json.loads((root/(a.stem+'.jsonl.checks.json')).read_text(encoding='utf8'))
rows=[r for r in c['results'] if r['candidate']==a.candidate and (r['check']['passed'] is None if a.pending else r['category'] in ['tools','recovery','negation'])]
for r in rows[a.start:a.start+a.count]:print(json.dumps({'id':r['id'],'text':r['text'],'check':r['check']},ensure_ascii=False))
print('TOTAL',len(rows))
