"""Record terminal paired inference and a separately labelled offline guard replay."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from model_context import unpack

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
P = R / 'runtime-candidate/artifact_completion_guard.py'
spec = importlib.util.spec_from_file_location('artifact_guard_review', P)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    return json.loads(p.read_text(encoding='utf8'))


def main():
    target = R / 'ARTIFACT_EVIDENCE_REVIEW.json'
    offline = R / 'ARTIFACT_GUARD_OFFLINE_V1.json'
    assert not target.exists() and not offline.exists()
    source = R / 'ARTIFACT_EVIDENCE_REPLAY_V1.jsonl'
    summary = read(source.with_suffix('.summary.json'))
    receipt = read(source.with_suffix('.integrity.json'))
    run = read(source.with_suffix('.run.json'))
    raw = source.with_suffix('.raw.jsonl')
    assert summary['results_sha256'] == sha(source) and summary['raw_sha256'] == sha(raw)
    assert receipt['actual_model_unchanged'] and receipt['sources_unchanged'] and receipt['child_exit_code'] == 0
    assert all(sha(Path(p)) == h for p, h in run['sources'].items())
    rows = [json.loads(l) for l in source.read_text(encoding='utf8').splitlines()]
    inputs = {(r['case'], r['mode']): r for r in map(json.loads, raw.read_text(encoding='utf8').splitlines())}
    results = []
    for row in rows:
        if row['mode'] != 'artifact_evidence':
            continue
        raw_row = inputs[(row['case'], row['mode'])]
        context = json.loads(raw_row['request']['messages'][1]['content'])
        if 'shared_context_text' in context:
            context = unpack(context)
        verdict = json.loads(raw_row['response']['message']['content'])
        result = guard.assess(row['compilation']['value'], context['user_request'], context['observed_history'], verdict)
        results.append({'case': row['case'], 'expected_complete': row['expected_complete'],
                        'result': result, 'correct': result['complete'] is row['expected_complete']})
    assert len(results) == 8
    changed = [r['case'] for r in results if r['result']['complete'] != r['result']['model_verdict']['complete']]
    assert changed == ['merge_altered']
    controls = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'unittest',
        'tests.test_artifact_completion_guard_candidate', 'tests.test_artifact_evidence_candidate',
        'tests.test_artifact_intent_v2', 'tests.test_artifact_intent_candidate'], cwd=ROOT, capture_output=True, text=True)
    assert controls.returncode == 0 and 'Ran 31 tests' in controls.stderr
    offline_record = {'reviewed_utc': datetime.now(timezone.utc).isoformat(), 'source_results_sha256': sha(source),
        'source_raw_sha256': sha(raw), 'guard_source_sha256': sha(P), 'records': results,
        'total': len(results), 'correct': sum(r['correct'] for r in results),
        'false_positives': sum(r['result']['complete'] and not r['expected_complete'] for r in results),
        'inference_repeated': False, 'mode': 'Offline postprocessing of unchanged saved actual-model responses',
        'only_changed_case': 'merge_altered: host catches missing TAB at character2 (11 source chars vs9 target chars).',
        'positive_verdicts_created_by_guard': False, 'candidate_installed': False, 'release_approved': False}
    offline.write_text(json.dumps(offline_record, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    notes = {
        'copy_correct': 'Artifact operands and exact text evidence correct. Candidate reason also claims byte equality; original trusted source/target digests must support that claim, not decoded text equality alone.',
        'merge_correct': 'Correct operands/order and identical11characters. Candidate boolean correct but reason mentions only final reply, omitting file requirements.',
        'empty_copy_correct': 'Actual zero-byte exclusive copy and reply evidenced; candidate positive reason is consistent.',
        'merge_altered': 'Correctly compiled concat and host computed first difference at2 (TAB vs CR); model nevertheless declared success based only on final reply. Negative-only guard now blocks this saved false positive.',
        'creative_status_instead_of_welcome': 'Correctly classified semantic generation. Candidate false boolean correct, but repeats content status as operational truth; verified source read and destination readback exist. Real defect is status text instead of two welcome sentences.',
        'summary_invented_facts': 'Correctly classified semantic generation. False boolean is correct but explanation invents existing destination/overwrite. Must assess actual summary factual errors and observed delivery/readback independently.',
        'v9_empty_copy_correct': 'Correct exclusive zero-byte copy facts and requested reply; candidate still invents pre-existing destination and source/readback mismatch. This failure remains.',
        'v9_empty_copy_without_reply': 'Counterfactual removes only FINAL_RESPONSE. Negative boolean correct, but reason invents existing destination/readback problems rather than identifying missing reply.'}
    record = {'reviewed_utc': datetime.now(timezone.utc).isoformat(),
        'results_sha256': sha(source), 'raw_sha256': sha(raw), 'summary': summary,
        'integrity_receipt_sha256': sha(source.with_suffix('.integrity.json')),
        'actual_model_files_verified_before_and_after': True,
        'compilation_review': {'total': 8, 'correct': 8, 'scope': 'Artifact types, ordered source IDs and destination IDs/names only; no proof of arbitrary requirement coverage.'},
        'case_reviews': notes, 'guard_offline_review': offline.name, 'guard_offline_sha256': sha(offline),
        'controls': {'tests_run': 31, 'exit_code': controls.returncode, 'output': controls.stderr,
            'sources': {str(p.relative_to(ROOT)): sha(p) for p in [P, P.with_name('artifact_evidence.py'),
                ROOT / 'tests/test_artifact_completion_guard_candidate.py', ROOT / 'tests/test_artifact_evidence_candidate.py']}},
        'conclusion': 'Added evidence improves paired boolean accuracy4/8to6/8 but retains1false positive and multiple ungrounded reasons. Offline negative-only guard removes that false positive (7/8), not fresh autonomous task acceptance. Neither component is installed.',
        'next': 'Separate checking generated content from workflow status quoted inside that content; ground operation and exact delivery requirements in trusted history. Resolve current empty-copy false negative, then repeat original end-to-end gates with the composed runtime. Preserve model identity, conditional planning, hardware/UI/native-app/ASR and full release requirements.',
        'production_runtime_unchanged': True, 'candidate_installed': False, 'cloud_resources_created': False,
        'release_approved': False}
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'paired': summary['modes'], 'offline_guard': {'correct': offline_record['correct'], 'total': 8, 'false_positives': offline_record['false_positives']}, 'controls': 31, 'release_approved': False}))


if __name__ == '__main__':
    main()
