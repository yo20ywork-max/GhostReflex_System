"""Completion checker with explicit candidate reply and omitted planned goals.

Known development only; no execution, repair, default-model change or release.
"""
import argparse
import hashlib
import json
import time
from types import SimpleNamespace
from pathlib import Path
from file_flow import runtime,cases as file_cases,ROOT,R
from evaluate_development import request,inputs
from completion_delivery import project_delivery_messages


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if Path(args.output).name!=args.output:raise ValueError('Output must be a file name')
    target=R/args.output
    if target.exists():raise FileExistsError(target)
    dev,_,_,locked=inputs();cases=[]
    for row in dev:
        if row['category']=='completion':
            payload=json.loads(row['prompt'])
            cases.append({'group':'completion32','id':row['id'],'prompt':payload['user_request'],
                          'history':payload['observed_history'],'expected':row['oracle']['complete']})
    paths=[Path(__file__),ROOT/'completion_delivery.py',ROOT/'tests/test_completion_delivery.py',ROOT/'run_daemon.py',ROOT/'text_reader.py',R/'file_flow.py',R/'evaluate_development.py']
    for stem,group in [('epoch3-file-development-v1','file8'),('epoch2-copy-extension-v1','copy2'),('epoch3-file-reply-guard-v1','file8_guard')]:
        source=R/(stem+'.jsonl');summary=source.with_suffix('.summary.json');manifest=source.with_suffix('.manifest.json')
        marker=json.loads(summary.read_text(encoding='utf8'))
        count=8 if group.startswith('file8') else 2
        if marker['cases']!=count or marker['evaluation_errors']:raise ValueError('Unfinished observation run')
        if not marker.get('source_files_unchanged',marker.get('sources_unchanged')):raise ValueError('Mixed observation sources')
        if not marker.get('model_tag_digest_unchanged',marker.get('model_digest_unchanged')):raise ValueError('Mixed observation model')
        # Summary identifies exact immutable observation bytes.
        if marker.get('output_sha256') and sha(source)!=marker['output_sha256']:raise ValueError('Changed observation output')
        if group.startswith('file8'):data={row['id']:row for row in file_cases()}
        else:data={row['id']:row for row in json.loads(manifest.read_text(encoding='utf8'))['cases']}
        observed=[json.loads(x) for x in source.read_text(encoding='utf8').splitlines()]
        if len(observed)!=count or {r['id'] for r in observed}!=set(data):raise ValueError('Incomplete observations')
        for row in observed:
            cases.append({'group':group,'id':row['id'],'prompt':data[row['id']]['user_request'],
                          'history':row['history'],'expected':row['evidence_ok'] and row['response_ok']})
        paths += [source,summary,manifest]
    if len(cases)!=50:raise ValueError('Expected 50 development observations')
    model=next(m for m in request('/api/tags')['models'] if m['name']==args.model)
    scope,_,_=runtime();hashes={str(p.relative_to(ROOT)):sha(p) for p in paths}
    with target.with_suffix('.manifest.json').open('x',encoding='utf8') as f:
        json.dump({'model':model,'sources':hashes,'cases':[{'group':c['group'],'id':c['id']} for c in cases],
                   'scope':'Known saved observations: computed candidate reply and planned-goal removal. Not a release, blind test or actual mixed-model repair.',
                   'settings':{'think':False,'temperature':0,'num_ctx':12288,'num_predict':1024,'repeat_penalty':1.0,'presence_penalty':0},
                   'release_approved':False},f,ensure_ascii=False,indent=2)
    records=[]
    with target.open('x',encoding='utf8') as output:
        for case in cases:
            calls=[];start=time.monotonic()
            class Gateway:
                def chat_json(self,*,messages,schema,models=None):
                    revised,removed=project_delivery_messages(messages)
                    body={'model':args.model,'messages':revised,'format':schema,
                          'options':{'temperature':0,'num_ctx':12288,'num_predict':1024,'repeat_penalty':1.0,'presence_penalty':0},
                          'stream':False,'truncate':False,'shift':False,'think':False}
                    record={'request':body,'removed_planned_goals':removed};calls.append(record)
                    response=request('/api/chat',body);record['response']=response
                    if response.get('done') is not True or response.get('done_reason')!='stop':raise ValueError('Incomplete generation')
                    return json.loads(response['message']['content']),args.model
            checker=scope['Planner'].__new__(scope['Planner']);checker.settings=SimpleNamespace(planner_num_ctx=12288);checker.gateway=Gateway()
            # Only original prompt and real history enter the actual checker.
            decision,reason=checker.assess_completion(case['prompt'],case['history'])
            errors=[c for c in calls if 'response' not in c or c['response'].get('done_reason')!='stop']
            valid=not errors and not reason.startswith(('完成核對未成功','完成核對回應格式不正確'))
            row={'group':case['group'],'id':case['id'],'expected':case['expected'],'complete':decision,
                 'reason':reason,'valid':valid,'correct':valid and decision==case['expected'],'calls':calls,'seconds':time.monotonic()-start}
            output.write(json.dumps(row,ensure_ascii=False)+'\n');output.flush();records.append(row)
            print(json.dumps({k:row[k] for k in ['group','id','complete','expected','valid','correct','seconds']}),flush=True)
    end=next(m for m in request('/api/tags')['models'] if m['name']==args.model)
    stable=all(sha(ROOT/p)==h for p,h in hashes.items()) and all(sha(R/p)==v['sha256'] for p,v in locked.items())
    def stats(rows):return {'rows':len(rows),'valid_correct':sum(r['correct'] for r in rows),'invalid':sum(not r['valid'] for r in rows),
                            'false_completion':sum(r['complete'] and not r['expected'] for r in rows),
                            'false_incomplete':sum(not r['complete'] and r['expected'] for r in rows)}
    summary={**stats(records),'groups':{g:stats([r for r in records if r['group']==g]) for g in ['completion32','file8','copy2','file8_guard']},
             'source_files_unchanged':stable,'model_digest_unchanged':model['digest']==end['digest'],
             'output_sha256':sha(target),'release_approved':False}
    with target.with_suffix('.summary.json').open('x',encoding='utf8') as f:json.dump(summary,f,indent=2)
    print(json.dumps(summary),flush=True)
    if not stable or model['digest']!=end['digest']:raise RuntimeError('Mixed sources/model')


if __name__=='__main__':main()
