"""Evaluate the existing clause reviewer on v4 inputs; preserve scalar scores."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
sys.path.insert(0, str(ROOT))
from completion_requirements import request_clauses, audit_schema, audit_messages, validate_audit
from text_reader import completed_file_contents, uncovered_file_reads
from evaluate_development import inputs, request


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--observed-files', help='Completed eight-case v4 file results file name, instead of the 32 observation cases')
    args = parser.parse_args()
    if Path(args.output).name != args.output: raise ValueError('Output must be a file name')
    target = R/args.output
    if target.exists(): raise FileExistsError(target)
    dev, _, _, locked = inputs()
    paths = [Path(__file__), ROOT/'completion_requirements.py', ROOT/'text_reader.py', R/'evaluate_development.py']
    if args.observed_files:
        if Path(args.observed_files).name != args.observed_files: raise ValueError('Observed file must be a local result name')
        observation_path = R/args.observed_files
        marker = json.loads(observation_path.with_suffix('.summary.json').read_text(encoding='utf8'))
        if marker['cases'] != 8 or marker['evaluation_errors'] or not marker['source_files_unchanged'] or not marker['model_tag_digest_unchanged']:
            raise ValueError('Incomplete or invalid observed run')
        observed = list(map(json.loads, observation_path.read_text(encoding='utf8').splitlines()))
        file_lock = json.loads((R/'FILE_DEV_LOCK_V2.json').read_text(encoding='utf8'))
        data_path = R/file_lock['file']
        if sha(data_path) != file_lock['sha256']: raise ValueError('File development data changed')
        data = {row['id']: row for row in map(json.loads, data_path.read_text(encoding='utf8').splitlines())}
        if len(observed) != 8 or {row['id'] for row in observed} != set(data): raise ValueError('Unexpected observed cases')
        # Only the original request and unmodified observations reach the model.
        # Expected files, artifacts, oracle issues and expected outcome stay out.
        cases = [{'id': row['id'], 'prompt': data[row['id']]['user_request'], 'history': row['history'],
                  'expected': row['evidence_ok'] and row['response_ok']} for row in observed]
        paths += [data_path, observation_path, observation_path.with_suffix('.summary.json')]
    else:
        cases = []
        for row in dev:
            if row['category'] != 'completion': continue
            payload = json.loads(row['prompt'])
            cases.append({'id': row['id'], 'prompt': payload['user_request'], 'history': payload['observed_history'], 'expected': row['oracle']['complete']})
        if len(cases) != 32: raise ValueError('Expected all 32 completion cases')
    model = next(m for m in request('/api/tags')['models'] if m['name']==args.model)
    tools = [row['name'] for row in json.loads((R/'training-contract.json').read_text(encoding='utf8'))['catalog']]
    hashes = {str(path.relative_to(ROOT)): sha(path) for path in paths}
    manifest = {'model': model, 'sources': hashes, 'locked_sources': {k:v['sha256'] for k,v in locked.items()},
                'cases': [c['id'] for c in cases], 'release_approved': False,
                'scope': 'Changed completion inference protocol, existing clause-review code. Saved observation classification only; no new action, repair, or product default change.'}
    with target.with_suffix('.manifest.json').open('x',encoding='utf8') as stream: json.dump(manifest,stream,ensure_ascii=False,indent=2)
    records = []
    with target.open('x',encoding='utf8') as stream:
        for case in cases:
            began = time.monotonic()
            history = [{**row,'sequence_index':i} for i,row in enumerate(case['history'],1)]
            record = {'id':case['id'], 'expected':case['expected'], 'model_digest':model['digest']}
            try:
                if not history or not history[-1].get('ok') or uncovered_file_reads(history):
                    decision, reason = False, 'Existing runtime prerequisite: missing/failed latest step or incomplete file coverage.'
                    record['model_called'] = False
                else:
                    clauses = request_clauses(case['prompt'])
                    payload = {'observed_history':history,'verified_file_contents':completed_file_contents(history)}
                    body = {'model':args.model,'messages':audit_messages(case['prompt'],payload,clauses),
                            'format':audit_schema(clauses,tools,history),'options':{'temperature':0,'num_ctx':12288,'num_predict':3072,'repeat_penalty':1.0},
                            'stream':False,'truncate':False,'shift':False}
                    record.update(request=body,model_called=True)
                    response = request('/api/chat',body);record['response']=response
                    if response.get('done') is not True or response.get('done_reason')!='stop': raise ValueError('Incomplete generation')
                    decision,reason=validate_audit(json.loads(response['message']['content']),clauses,history)
                    if decision and not history[-1].get('verified'): decision,reason=False,'Latest action has no verified outcome.'
                record.update(complete=decision,reason=reason,valid=True,correct=decision==case['expected'])
            except Exception as exc: record.update(error=repr(exc),valid=False,correct=False,complete=False)
            record['seconds']=time.monotonic()-began
            stream.write(json.dumps(record,ensure_ascii=False)+'\n');stream.flush();records.append(record)
            print(json.dumps({key:record.get(key) for key in ['id','complete','expected','correct','valid','seconds']}),flush=True)
    end_model=next(m for m in request('/api/tags')['models'] if m['name']==args.model)
    source_stable=all(sha(ROOT/path)==digest for path,digest in hashes.items()) and all(sha(R/name)==value['sha256'] for name,value in locked.items())
    summary={'rows':len(records),'valid_correct':sum(x['valid'] and x['correct'] for x in records),'invalid':sum(not x['valid'] for x in records),
             'false_completion':sum(x['complete'] and not x['expected'] for x in records),'false_incomplete':sum(not x['complete'] and x['expected'] for x in records),
             'model_calls':sum(x.get('model_called',False) for x in records),'source_files_unchanged':source_stable,'model_digest_unchanged':model['digest']==end_model['digest'],
             'output_sha256':sha(target),'release_approved':False}
    with target.with_suffix('.summary.json').open('x',encoding='utf8') as stream: json.dump(summary,stream,indent=2)
    print(json.dumps(summary),flush=True)
    if not source_stable or model['digest']!=end_model['digest']: raise RuntimeError('Mixed sources or model; invalid comparison')


if __name__=='__main__': main()
