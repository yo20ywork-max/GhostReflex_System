"""Apply preserved executable checks; leave semantic and action gates pending."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from jsonschema import Draft202012Validator

R=Path(__file__).resolve().parent
ROOT=R.parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf8'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--results',required=True);parser.add_argument('--reuse-functional',action='store_true');args=parser.parse_args()
    if Path(args.results).name!=args.results:raise ValueError('Local result filename required')
    folder=R/'evaluation-runtime-v6';target=folder/args.results
    summary=read(target.with_suffix('.generation-complete.json'));run=read(target.with_suffix('.manifest.json'))
    if not summary['model_and_sources_unchanged'] or summary['results_sha256']!=sha(target):raise ValueError('Unverified generation')
    if not all(sha(ROOT/name)==digest for name,digest in run['sources'].items()):raise ValueError('Scoring source changed')
    cases=[json.loads(x) for x in (folder/'cases.jsonl').read_text(encoding='utf8').splitlines()]
    results=[json.loads(x) for x in target.read_text(encoding='utf8').splitlines()]
    if [r['id'] for r in cases]!=[r['id'] for r in results]:raise ValueError('Missing, duplicate, reordered or foreign cases')
    destination=target.with_suffix('.checks.json')
    if destination.exists():raise FileExistsError(destination)
    audit=R.parent/'release_v3/code_extended_audit.py'
    sandbox=R.parent/'release_v3/code_sandbox.py'
    functional_path=Path(str(target)+'.extended-code.json')
    if functional_path.exists():
        if not args.reuse_functional:raise FileExistsError('Existing functional result requires inspection and --reuse-functional')
    else:
        subprocess.run([sys.executable,'-X','utf8',str(audit),'--data',str((folder/'cases.jsonl').resolve()),'--results',str(target.resolve())],check=True,timeout=90)
    functional=read(functional_path)
    assert functional['results_sha256']==sha(target)
    assert functional['audit_sha256']==sha(audit)
    code_by_id={r['id']:r for r in functional['records']}
    assert len(code_by_id)==20
    schemas=read(folder/'schemas.json');records=[]
    for row,result in zip(cases,results):
        assert result['prompt_sha256']==hashlib.sha256((row['gateway_system']+'\n'+row['prompt']).encode()).hexdigest()
        assert result['request'] is None or result['request']['messages']==[{'role':'system','content':row['gateway_system']},{'role':'user','content':row['prompt']}]
        oracle=row['oracle'];kind=oracle['type'];text=result['text']
        check={'passed':None,'reason':'Semantic review required; not counted as pass'}
        try:
            if not result['completed']:raise ValueError('Gateway did not accept a complete response')
            if kind=='code':
                check=dict(code_by_id[row['id']]);check.pop('id',None)
                assert check.pop('text_sha256')==hashlib.sha256(text.encode()).hexdigest()
            elif kind=='completion':
                value=json.loads(text);valid=isinstance(value,dict) and set(value)=={'complete','reason'} and type(value.get('complete')) is bool and isinstance(value.get('reason'),str)
                actual=value.get('complete') if isinstance(value,dict) else None
                check={'passed':valid and actual==oracle['complete'],'expected_complete':oracle['complete'],'actual_complete':actual,
                    'false_completion':actual is True and oracle['complete'] is False,'valid_object':valid}
            elif kind=='plan':
                Draft202012Validator(schemas['plan']).validate(json.loads(text))
                check={'passed':None,'schema_valid':True,'reason':'Schema valid; current runtime validation, semantic intent and actual execution still required'}
            elif kind=='exact':
                expected=oracle['value']
                exact=text==expected;legacy=text.strip()==expected.strip()
                check={'passed':exact if row['category'] in ('literal','asr') else (True if legacy else None),
                    'exact_equal':exact,'legacy_trimmed_equal':legacy,'reason':'Literal/ASR require exact text; alternate factual/locale wording needs review'}
            elif kind=='contextual_taiwan_language':
                expected=oracle['json_expected']
                if expected is not None:
                    actual=json.loads(text)
                    check={'passed':json.dumps(actual,ensure_ascii=False,sort_keys=True)==json.dumps(expected,ensure_ascii=False,sort_keys=True),
                           'reason':'Compare decoded JSON types, keys and values; never compare displayed escapes'}
                elif oracle['exact_required']:
                    check={'passed':text==row['answer'],'reason':'Literal requires exact original characters'}
                elif text==row['answer']:
                    check={'passed':True,'reason':'Exact authored answer; alternate answers require semantic review'}
            # Brand, historical binding and evidence boundary answers require
            # whole-answer review, not keyword counting or source recitation.
        except Exception as exc:check={'passed':False,'reason':type(exc).__name__+': '+str(exc)[:500]}
        records.append(dict(id=row['id'],suite=row['suite'],category=row['category'],text_sha256=hashlib.sha256(text.encode()).hexdigest(),**check))
    totals={}
    for suite in sorted({r['suite'] for r in records}):
        subset=[r for r in records if r['suite']==suite]
        totals[suite]={'pass':sum(r['passed'] is True for r in subset),'fail':sum(r['passed'] is False for r in subset),'review':sum(r['passed'] is None for r in subset)}
    report={'summary':totals,'records':records,'results_sha256':sha(target),'scorer_sha256':sha(Path(__file__)),
        'functional_audit_sha256':sha(audit),'functional_sandbox_sha256':sha(sandbox),'functional_report_sha256':sha(functional_path),
        'false_completion_count':sum(r.get('false_completion',False) for r in records),'pending_is_not_pass':True,
        'actual_action_gates_evaluated':False,'final_holdout_opened':False,'release_approved':False}
    with destination.open('x',encoding='utf8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
    print(json.dumps({'summary':totals,'false_completion_count':report['false_completion_count'],'release_approved':False}))


if __name__=='__main__':main()
