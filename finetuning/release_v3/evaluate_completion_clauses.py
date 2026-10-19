"""Compare the clause audit on the locked 32 known development observations.

This changes the inference contract, not data, weights or original scores. It
does not access final test/provenance-audit questions or execute any action.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

R=Path(__file__).resolve().parent;ROOT=R.parents[1]
sys.path.insert(0,str(ROOT))
from completion_requirements import request_clauses,audit_schema,audit_messages,validate_audit
from text_reader import completed_file_contents
from evaluate_local import request


def main():
    p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    output=R/a.output
    if output.exists():raise FileExistsError(output)
    data_path=R/'dev.jsonl';rows=[x for x in map(json.loads,data_path.read_text(encoding='utf8').splitlines()) if x['category']=='completion']
    if len(rows)!=32:raise ValueError('Expected locked32 known development cases')
    tools=[x['name'] for x in json.loads((R/'training-contract.json').read_text(encoding='utf8'))['catalog']]
    model=next(x for x in request('/api/tags')['models'] if x['name']==a.model)
    sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'completion_requirements.py',ROOT/'text_reader.py',R/'evaluate_local.py',Path(__file__)]}
    manifest={'data_sha256':hashlib.sha256(data_path.read_bytes()).hexdigest(),'model':model,'source_sha256':sources,'rows':32,'release_approved':False,'scope':'Locked known development observations, changed clause inference contract; not held-out or actual model action execution.'}
    with output.with_suffix('.manifest.json').open('x',encoding='utf8') as f:json.dump(manifest,f,ensure_ascii=False,indent=2)
    results=[]
    with output.open('x',encoding='utf8') as f:
        for i,row in enumerate(rows,1):
            payload=json.loads(row['prompt']);prompt=payload['user_request'];history=payload['observed_history'];clauses=request_clauses(prompt)
            payload['verified_file_contents']=completed_file_contents(history)
            body={'model':a.model,'messages':audit_messages(prompt,payload,clauses),'format':audit_schema(clauses,tools,history),'options':{'temperature':0,'num_ctx':12288,'num_predict':3072,'repeat_penalty':1.0},'stream':False,'truncate':False,'shift':False}
            result={'id':row['id'],'expected':row['oracle']['complete'],'request':body,'model_digest':model['digest']};started=time.monotonic()
            try:
                response=request('/api/chat',body);result['response']=response
                if response.get('done_reason')!='stop':raise ValueError('Incomplete generation')
                decision,reason=validate_audit(json.loads(response['message']['content']),clauses,history)
                result.update(complete=decision,reason=reason,valid=True,correct=decision==result['expected'])
            except Exception as exc:result.update(error=repr(exc),complete=False,valid=False,correct=False)
            result.update(seconds=time.monotonic()-started,operational_decision_correct=result['complete']==result['expected'])
            results.append(result);f.write(json.dumps(result,ensure_ascii=False)+'\n');f.flush()
            print(json.dumps({k:result.get(k) for k in ['id','expected','complete','valid','correct','seconds']}),flush=True)
    summary={'rows':len(results),'valid_correct':sum(x['valid'] and x['correct'] for x in results),'invalid':sum(not x['valid'] for x in results),'false_completion':sum(x['complete'] and not x['expected'] for x in results),'false_incomplete':sum(not x['complete'] and x['expected'] for x in results),'source_files_unchanged':all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==v for p,v in sources.items()),'output_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'release_approved':False}
    output.with_suffix('.summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
