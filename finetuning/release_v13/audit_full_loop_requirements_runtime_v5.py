"""Audit original waiting-before-reading requirements omitted by the old oracle.

This preserves the original recorded score and adds a stricter trace check. It
does not call the model, execute tools, or claim native/target-hardware coverage.
"""
import argparse
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wait_order(trace, *, text, selector, timeout_ms, fixture_selector='#busy'):
    """The original DOM fixture maps its visible loading text to #busy.

Every attempted result read must follow a successful wait for that exact
loading object. A failed/irrelevant wait or a later correct retry cannot repair
an earlier premature read. Matching the final result alone is insufficient.
"""
    observed_wait = False
    premature = []
    reads = []
    invalid_waits = []
    for index, entry in enumerate(trace, 1):
        args = entry.get('args') or {}
        if entry.get('tool') == 'BROWSER_WAIT_FOR':
            by, target = args.get('by'), args.get('target')
            target_matches = (by == 'text' and target == text) or (by == 'css' and target == fixture_selector)
            requested_timeout = args.get('timeout_ms', 30000)
            within_limit = type(requested_timeout) is int and 0 < requested_timeout <= timeout_ms
            correct = target_matches and args.get('state') in ('hidden', 'detached') and within_limit
            if not correct:
                invalid_waits.append(index)
            elif entry.get('ok') is True and entry.get('verified') is True:
                observed_wait = True
        if entry.get('tool') == 'BROWSER_GET_TEXT' and args.get('by') == 'css' and args.get('target') == selector:
            reads.append(index)
            if not observed_wait:
                premature.append(index)
    # An irrelevant or failed attempt may be repaired before reading the
    # result. It cannot serve as evidence, but is not itself a user-forbidden
    # action. Do not invent a no-retries requirement.
    passed = observed_wait and bool(reads) and not premature
    return {'passed': passed, 'successful_wait_for_original_object': observed_wait,
            'result_read_indices': reads, 'premature_read_indices': premature,
            'wrong_target_state_or_timeout_indices': invalid_waits,
            'scope': 'Actual trace ordering and timeout argument; not total elapsed-time or native-app validation'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--results', required=True)
    args = parser.parse_args()
    if Path(args.results).name != args.results:
        raise ValueError('Local generation filename required')
    folder = R / 'evaluation-runtime-v5' / (Path(args.results).stem + '.full-loop')
    original = json.loads((folder / 'result.json').read_text(encoding='utf8'))
    joint = json.loads((folder / 'joint-review.json').read_text(encoding='utf8'))
    assert sha(folder / 'result.json') == joint['result_sha256']
    assert joint['extra_sources_unchanged'] and original['source_files_unchanged'] and original['model_digest_unchanged']
    cases = {r['id']: r for r in map(json.loads, (folder / 'cases.jsonl').read_text(encoding='utf8').splitlines())}
    fixture = R.parent / 'release_v4/execute_full_plan_fixtures.py'
    assert sha(fixture) == original['fixture_script_sha256'] == 'd2295652630c758c0971b742b2236620908abf316f6870ca98e0bd99e56919fd'
    records = []
    for row in original['records']:
        case = cases[row['id']]
        audit = None
        if case['group'] == 'v2-dev-wait-disappear':
            slot = row['id'].rsplit('-', 1)[-1]
            user_request = json.loads(case['prompt'])['user_request']
            assert user_request == f'等網頁「正在產生{slot}」消失後，讀取 #result，最多等 23 秒。'
            audit = wait_order(row['trace'], text='正在產生' + slot, selector='#result', timeout_ms=23000)
        completed = row.get('agent_status') == 'completed'
        passed = bool(row['passed'] and completed and (audit is None or audit['passed']))
        records.append({'id': row['id'], 'original_oracle_passed': row['passed'],
                        'agent_completed': completed, 'wait_order_audit': audit,
                        'joint_with_order_passed': passed,
                        'false_completion_with_order': completed and not passed})
    assert len(records) == 12
    report = {'records': records, 'total': len(records),
              'original_joint_passed': joint['joint_oracle_and_completed'],
              'joint_with_order_passed': sum(r['joint_with_order_passed'] for r in records),
              'false_completions_with_order': sum(r['false_completion_with_order'] for r in records),
              'original_result_sha256': sha(folder / 'result.json'),
              'original_cases_sha256': sha(folder / 'cases.jsonl'), 'fixture_sha256': sha(fixture),
              'auditor_sha256': sha(Path(__file__)), 'original_oracle_unchanged': True,
              'all_release_requirements_proven': False, 'release_approved': False}
    with (folder / 'order-audit-v1.json').open('x', encoding='utf8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != 'records'}))


if __name__ == '__main__':
    main()
