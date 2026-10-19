"""Report real requirements and fixture limitations without altering raw scores."""
import argparse
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',required=True);args=parser.parse_args()
    if Path(args.input).name!=args.input:raise ValueError('Filename only')
    path=HERE/args.input
    summary=json.loads(path.with_suffix('.summary.json').read_text(encoding='utf8'))
    if summary.get('self_check'):raise ValueError('Use actual model outputs')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if summary['output_sha256']!=digest:raise ValueError('Output hash changed')
    result=[]
    for line in path.read_text(encoding='utf8').splitlines():
        row=json.loads(line)
        restrictions=[{'step_id':h['step_id'],'tool':h['tool'],'error':h.get('error')} for h in row['history']
                      if 'fixture' in (h.get('error') or '').lower() or 'disposable' in (h.get('error') or '').lower()]
        operation_issues=[x for x in row['issues'] if x!='Required final reply not delivered']
        plans=[]
        for call in row['calls']:
            try:answer=json.loads(call.get('response',{}).get('message',{}).get('content',''))
            except ValueError:continue
            if isinstance(answer,dict) and isinstance(answer.get('steps'),list):
                plans.append([{'id':s.get('id'),'tool':s.get('tool'),'when':s.get('when')} for s in answer['steps']])
        result.append(dict(id=row['id'],status=row['status'],raw_passed=row['passed'],false_completion=row['false_completion'],
                           artifact_and_operation_requirements_passed=not operation_issues,operation_issues=operation_issues,
                           required_reply_delivered='Required final reply not delivered' not in row['issues'],
                           fixture_restrictions=restrictions,source_open_attempts=row['source_open_attempts'],
                           call_count=len(row['calls']),generated_plan_tools=plans,seconds=row['seconds']))
    report=dict(input=args.input,input_sha256=digest,raw_summary=summary,cases=result,
                artifact_and_operation_passed=sum(x['artifact_and_operation_requirements_passed'] for x in result),
                required_reply_delivered=sum(x['required_reply_delivered'] for x in result),
                cases_with_fixture_restrictions=sum(bool(x['fixture_restrictions']) for x in result),
                limitation='Restricted file fixture does not execute native/other tools advertised in the full desktop catalog. A fixture restriction is not proof that the real product would fail that continuation. Independently observed forbidden reads, wrong bytes, missing copies and invalid condition evidence remain actual findings. Raw case scores are preserved; do not present them as general desktop success rates.',
                target_hardware_validated=False,release_approved=False)
    with path.with_suffix('.review.json').open('x',encoding='utf8') as out:json.dump(report,out,ensure_ascii=False,indent=2)
    print(json.dumps({k:report[k] for k in ('input','artifact_and_operation_passed','required_reply_delivered','cases_with_fixture_restrictions','release_approved')}))


if __name__=='__main__':main()
