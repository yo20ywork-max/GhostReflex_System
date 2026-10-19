"""Persist full-plan semantic review, separately from parser acceptance."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    path = R / 'UNANCHORED_PLAN_REPLAY.json'
    data = json.loads(path.read_text(encoding='utf8'))
    assert data['sources_and_model_unchanged']
    assert [(r['case'], r['plan_valid']) for r in data['records']] == [('conditional', False), ('code', True)]
    plans = [json.loads(row['response']['message']['content']) for row in data['records']]
    assert plans[0]['steps'][-1]['args']['message'] == '{{step:4.content_verified}}：新副本完成'
    assert not any(s['tool'] == 'MODEL_GENERATE' for s in plans[1]['steps'])
    assert plans[1]['steps'][1]['args'] == {'path': 'calculator.py', 'content': '{{step:1.file_text}}', 'overwrite': True}
    assert plans[1]['steps'][2]['args']['path'] == '函式需求.txt'
    review = {'reviewed_utc': datetime.now(timezone.utc).isoformat(), 'report_sha256': sha(path),
        'complete_generations': 2, 'parser_valid': 1, 'semantic_repair_passed': 0,
        'cases': [
            {'id': 'conditional', 'passed': False,
             'finding': 'Correct PATH_INFO branch predicates now appear, but final reply still uses unsupported WRITE content_verified placeholder; invalid plan, no dispatch.'},
            {'id': 'code', 'passed': False,
             'finding': 'Valid JSON/tool schema but no program synthesis. Copies requirement prose into calculator.py with overwrite true and proposes writing preserved source. No actual actions executed.'}],
        'decision': 'Do not install unanchored repair candidate; parser improvement alone does not satisfy original tasks.',
        'candidate_installed': False, 'actions_executed': False, 'release_approved': False}
    with (R / 'UNANCHORED_PLAN_REPLAY_REVIEW.json').open('x', encoding='utf8') as f:
        json.dump(review, f, ensure_ascii=False, indent=2)
    path = R / 'evaluation-runtime-v7/epoch3-file8-v1.jsonl'
    rows = [json.loads(l) for l in path.read_text(encoding='utf8').splitlines()]
    summary = json.loads(path.with_suffix('.summary.json').read_text(encoding='utf8'))
    assert summary['results_sha256'] == sha(path)
    assert [r['id'] for r in rows if not r['passed']] == ['v4-file-01', 'v4-file-04', 'v4-file-06', 'v4-file-08']
    findings = {
        'v4-file-01': 'Copy bytes correct, but MODEL_GENERATE referenced WRITE.file_text; later generation reproduced source instead of final delivery and replanning exhausted context.',
        'v4-file-04': 'Exact merge written/read back, completion checker rejected result and replan proposed duplicate write; no MODEL_GENERATE call in this case.',
        'v4-file-06': 'Invalid WRITE boolean condition rejected in preflight; no source read or path action, task not completed.',
        'v4-file-08': 'Seed read covered137/550 characters; replanner repeatedly read nonexistent destination instead of completing source and publishing copy.'}
    review = {'reviewed_utc': datetime.now(timezone.utc).isoformat(), 'results_sha256': sha(path), 'summary': summary,
              'failures': findings, 'single_run_not_causal_attribution': True, 'release_approved': False}
    with (R / 'RUNTIME_V7_FILE_REVIEW.json').open('x', encoding='utf8') as f:
        json.dump(review, f, ensure_ascii=False, indent=2)
    print(json.dumps({'replay_semantic_passed': 0, 'file8_passed': summary['passed'], 'release_approved': False}))


if __name__ == '__main__':
    main()
