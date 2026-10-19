"""Compact review view; never produces semantic verdicts automatically."""
import argparse
import json
from pathlib import Path
import re

p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--checks',required=True);p.add_argument('--candidate',default='adapter');p.add_argument('--plans',action='store_true');a=p.parse_args()
rows={r['id']:r for r in map(json.loads,Path(a.data).read_text(encoding='utf8').splitlines())}
checks=json.loads(Path(a.checks).read_text(encoding='utf8'))
for result in checks['results']:
    if result['candidate']!=a.candidate:continue
    row=rows[result['id']]
    if a.plans:
        if row['oracle']['type']!='plan':continue
        text=result['text'].strip()
        match=re.fullmatch(r'```(?:json)?\s*\n(.*?)\n```',text,re.S)
        if match:text=match.group(1)
        try:
            plan=json.loads(text)
            view={'id':row['id'],'objective':plan.get('objective'),'assumptions':plan.get('assumptions'),
                  'steps':[{k:s.get(k) for k in ('tool','goal','success_check')} for s in plan.get('steps',[])],
                  'completion_criteria':plan.get('completion_criteria'),'check':result['check']}
        except (ValueError,TypeError):view={'id':row['id'],'unparsed':result['text']}
    elif result['check']['passed'] is not True:
        view={'id':row['id'],'question':row['prompt'],'answer':result['text'],'reference':row['answer'],'check':result['check']}
    else:continue
    print(json.dumps(view,ensure_ascii=False))
