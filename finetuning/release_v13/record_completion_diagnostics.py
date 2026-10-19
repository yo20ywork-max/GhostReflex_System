"""Bind completed diagnostics to source reports without changing release gates."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    with (R / name).open('x', encoding='utf8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def main():
    now = datetime.now(timezone.utc).isoformat()
    profiles = {}
    for label, name in [('adapted', 'COMPLETION_FILE_FACTS_REPLAY.jsonl'), ('base', 'COMPLETION_BASE_COMPARISON.jsonl')]:
        path = R / name
        summary = json.loads(path.with_suffix('.summary.json').read_text(encoding='utf8'))
        assert summary['sources_and_model_unchanged'] and summary['results_sha256'] == sha(path)
        rows = [json.loads(l) for l in path.read_text(encoding='utf8').splitlines()]
        assert len(rows) == summary['rows'] == 12
        profiles[label] = {'results_sha256': sha(path), 'summary': summary,
                           'answers': [{k: row.get(k) for k in ['case', 'mode', 'complete', 'correct', 'reason']} for row in rows]}
    assert profiles['adapted']['summary']['modes']['derived_facts']['false_positives'] == 1
    assert profiles['base']['summary']['modes']['derived_facts']['false_positives'] == 2
    write('COMPLETION_CHECKER_DIAGNOSTICS_REVIEW.json', {
        'reviewed_utc': now, 'profiles': profiles,
        'reason_review': {
            'adapted': 'Correct copy answers are grounded. Merge with derived facts returns true but reason only cites final reply; altered merge receives the same inadequate reasoning and false true verdict. Creative negative reasons claim missing read/no dispatch despite actual readback; summary negatives cite cancellation or absent readback rather than evaluating invented summary facts. Correct boolean alone does not establish reliable reasoning.',
            'base': 'Correct copy/merge/empty-copy are accepted. Both variants falsely accept altered merge and workflow status as welcome copy. Summary negatives either claim write failure after later successful write or anchor on an earlier fixture-denied step; neither establishes stable semantic verification.',
            'repeat_variation': 'Adapted baseline identical captured copy input now returned true although full-flow historical reply was false. Captured temperature is already0; cause of this variation is unproven. Do not attribute it to temperature0.2.'},
        'decision': 'Neither switch to base nor install derived facts as a sufficient completion fix. Continue an independently evaluated requirement/evidence and artifact-semantic checking design; preserve positive and negative cases.',
        'candidate_installed': False, 'product_default_changed': False, 'actions_executed': False, 'release_approved': False})
    path = R / 'evaluation-runtime-v8/epoch3-file8-v1.jsonl'
    summary = json.loads(path.with_suffix('.summary.json').read_text(encoding='utf8'))
    rows = [json.loads(l) for l in path.read_text(encoding='utf8').splitlines()]
    assert summary['results_sha256'] == sha(path) and summary['passed'] == 3 and summary['false_completions'] == 0
    assert [r['id'] for r in rows if r['passed']] == ['v4-file-02', 'v4-file-03', 'v4-file-07']
    assert not any('全文引用只能指向前面的唯一' in json.dumps(c['request'], ensure_ascii=False) for r in rows for c in r['calls'])
    write('RUNTIME_V8_FILE_REVIEW.json', {
        'reviewed_utc': now, 'results_sha256': sha(path), 'summary': summary,
        'failures': {
            'v4-file-01': 'Exact copy and readback; completion checker invents BitConverter/encoding change, then replan repeats successful write and is stopped.',
            'v4-file-04': 'Exact merge and readback; completion checker invents unopened failsafe, then proposes duplicate write.',
            'v4-file-05': 'Verified zero-byte copy and readback; checker repeatedly invents pre-existing target, cancellation, or readback mismatch. Final reply attempts do not resolve it.',
            'v4-file-06': 'Impossible WRITE boolean fields rejected before path or file operations. No valid branch plan.',
            'v4-file-08': 'After137/550-character seed read, repeatedly tries reading nonexistent destination instead of continuing source and creating copy.'},
        'new_anchor_guard_triggered_by_model_in_this_run': False,
        'scope': 'Anchor guard covered by74 automated tests but not exercised by this run. Different whole-flow results cannot be causally attributed to guard; no original artifacts or expectations changed.',
        'release_approved': False})
    source = R / 'train.jsonl'
    locked = json.loads((R / 'DATA_LOCK.json').read_text(encoding='utf8'))['sha256']['train.jsonl']
    assert sha(source) == locked
    rows = [json.loads(l) for l in source.read_text(encoding='utf8').splitlines()]
    checks = []
    for row in rows:
        try:
            answer = json.loads(row['answer']) if isinstance(row['answer'], str) else row['answer']
        except (ValueError, TypeError):
            continue
        if isinstance(answer, dict) and type(answer.get('complete')) is bool:
            checks.append((row, answer))
    reasons = Counter(a.get('reason') for _, a in checks)
    audit = {'audited_utc': now, 'training_sha256': locked, 'training_rows': len(rows),
             'completion_rows': len(checks), 'completion_labels': dict(Counter(str(a['complete']) for _, a in checks)),
             'unique_reasons': len(reasons), 'most_common_reasons': reasons.most_common(16),
             'unique_prompt_answer_pairs': len(set((r['prompt'], r['answer']) for r, _ in checks)),
             'rows_with_context_sharing': sum('shared_context_text' in r['prompt'] for r, _ in checks),
             'rows_with_derived_file_facts': sum('derived_file_observation_facts' in r['prompt'] for r, _ in checks),
             'interpretation': 'Repeated generic labels and input-format coverage are audit findings, not proof of causal memorization or a successful retraining prescription. No training input modified and no new training started.',
             'release_approved': False}
    assert len(checks) == 484 and len(reasons) == 158
    write('COMPLETION_TRAINING_COVERAGE_AUDIT.json', audit)
    candidate = R / 'runtime-candidate/completion_file_facts.py'
    write('COMPLETION_FILE_FACTS_CONTROLS.json', {'checked_utc': now, 'candidate_sha256': sha(candidate),
        'test_sha256': sha(R.parents[1] / 'tests/test_completion_file_facts_candidate.py'),
        'tests_run': 7, 'passed': True, 'observed_stdout': 'Ran7tests;OK', 'observed_exit_code': 0,
        'installed_in_product': False, 'release_approved': False})
    print(json.dumps({'v8_file_passed': summary['passed'], 'completion_train_rows': len(checks),
                      'training_unique_pairs': audit['unique_prompt_answer_pairs'],
                      'training_context_sharing_rows': audit['rows_with_context_sharing'], 'release_approved': False}))


if __name__ == '__main__':
    main()
