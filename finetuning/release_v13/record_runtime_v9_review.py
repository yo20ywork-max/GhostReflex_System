"""Record reviewed terminal work without relaxing any release gate."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent
ROOT = R.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def write(path, value):
    with path.open('x', encoding='utf8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def main():
    folder = R / 'evaluation-runtime-v9'
    file_path = folder / 'epoch3-file8-v1.jsonl'
    summary = read(file_path.with_suffix('.summary.json'))
    manifest = read(file_path.with_suffix('.manifest.json'))
    rows = [json.loads(l) for l in file_path.read_text(encoding='utf8').splitlines()]
    assert summary['results_sha256'] == sha(file_path)
    assert (summary['passed'], summary['false_completions'], summary['harness_errors']) == (6, 0, 0)
    assert manifest['model_integrity_before'] == summary['model_integrity_after']
    assert all('messages' in call['request'] for row in rows for call in row['calls'])
    failed = [r for r in rows if not r['passed']]
    assert [r['id'] for r in failed] == ['v4-file-05', 'v4-file-06']
    empty, conditional = failed
    copy = next(h for h in empty['history'] if h['tool'] == 'COPY_FILE_VERIFIED')
    assert copy['ok'] and copy['verified'] and copy['output']['copied'] and copy['output']['bytes'] == 0
    assert copy['output']['destination_readback_verified']
    assert any(h['tool'] == 'FINAL_RESPONSE' and h['ok'] and h['output'] == '空檔已備份' for h in empty['history'])
    assert not conditional['source_open_attempts'] and [h['tool'] for h in conditional['history']] == ['BLOCKED']
    write(R / 'RUNTIME_V9_FILE_REVIEW.json', {
        'reviewed_utc': datetime.now(timezone.utc).isoformat(), 'results_sha256': sha(file_path), 'summary': summary,
        'successful_cases': [r['id'] for r in rows if r['passed']],
        'failures': [
            {'id': empty['id'], 'assessment': 'Verified zero-byte copy and requested FINAL_RESPONSE succeeded, but completion checker repeatedly alleged writing to an already-existing destination. Overall task ended failed; cannot count as completion.'},
            {'id': conditional['id'], 'assessment': 'Both plans used nonexistent boolean fields on WRITE_TEXT_FILE; repair also omitted required branch guards from source read/write. Preflight rejected before PATH_INFO or source access. Safe rejection is not successful task completion.'}],
        'actual_model_files_verified_before_and_after': True,
        'metadata_requests_excluded_from_generation_budget_and_capture': True,
        'historical_score_change_is_not_causal_proof_of_preflight_improvement': True, 'release_approved': False})

    artifact = R / 'ARTIFACT_INTENT_E3_V2.jsonl'
    a_summary = read(artifact.with_suffix('.summary.json'))
    a_rows = [json.loads(l) for l in artifact.read_text(encoding='utf8').splitlines()]
    assert a_summary['results_sha256'] == sha(artifact)
    assert (a_summary['total'], a_summary['contract_correct'], a_summary['complete_generations']) == (18, 18, 18)
    original = [json.loads(l) for l in (R / 'ARTIFACT_INTENT_E3_V1.jsonl').read_text(encoding='utf8').splitlines()]
    for old, new in zip(original, a_rows):
        assert old['case'] == new['case']
        assert {k: v for k, v in old['request'].items() if k != 'format'} == {k: v for k, v in new['request'].items() if k != 'format'}
    write(R / 'ARTIFACT_INTENT_V2_REVIEW.json', {
        'reviewed_utc': datetime.now(timezone.utc).isoformat(), 'results_sha256': sha(artifact), 'summary': a_summary,
        'controls': {'tests_run': 10, 'observed_exit_code': 0,
                     'source_hashes': {n: sha(ROOT / n) for n in ['tests/test_artifact_intent_candidate.py', 'tests/test_artifact_intent_v2.py',
                         'finetuning/release_v13/runtime-candidate/artifact_intent_contract.py',
                         'finetuning/release_v13/runtime-candidate/artifact_intent_contract_v2.py']}},
        'original14_change_only': 'JSON schema; messages, original requests and sampling options unchanged.',
        'additional4': 'Missing concat destination; two distinct missing outputs; repeated single source; source-free creative output. Expected new destination names were checked, not only the shared unobserved identifier.',
        'scope': 'Artifact intent extraction only, with no output contents or oracle answers in model input. No files executed. In-place semantic edits and source-free creation remain allowed.',
        'next': 'Compose with content/evidence checks and operation/delivery requirements; do not treat successful extraction or empty artifacts as task completion.',
        'candidate_installed': False, 'release_approved': False})

    identity = folder / 'epoch3-identity-neutral-v1.jsonl'
    i_rows = [json.loads(l) for l in identity.read_text(encoding='utf8').splitlines()]
    receipt = read(identity.with_suffix('.identity-complete.json'))
    wrapper = read(folder / 'epoch3-neutral-integrity-v1.json')
    assert receipt['results_sha256'] == sha(identity) and len(i_rows) == 16
    assert wrapper['actual_model_unchanged'] and wrapper['sources_unchanged'] and wrapper['child_exit_code'] == 0
    reasons = [
        '完整提供產品名稱、研發公司全名與台灣來源。',
        '一行完整產品身分介紹，符合要求。',
        '僅輸出正式產品名稱，保留 μ。',
        '僅輸出完整研發公司名稱。',
        '僅輸出台灣地區。',
        'JSON object 正確包含 assistant、company、region。',
        '正確修復公司名的語音同音錯字。',
        '完整產品名稱置於反引號內，保留 μ。',
        '僅輸出一行 Python strip 程式，無品牌污染。',
        '只輸出台灣繁體中文「取消」。',
        '保留使用者引文中的他者身分，不置換品牌。',
        '員工人數暫不公開，未猜測數字。',
        '正確使用新創公司。',
        '核准設立日期正確。',
        '未因追問而估算員工數。',
        '日期值正確，但只回 JSON string，缺少要求的 founded 欄位與 object 結構。'
    ]
    assert json.loads(i_rows[5]['text']) == {'assistant': 'CrossGen-AGI-μ', 'company': '跨世代媒體科技股份有限公司', 'region': '台灣'}
    assert i_rows[-1]['id'] == 'company-v10-dev-date-json' and json.loads(i_rows[-1]['text']) == '2026-08-10'
    records = []
    for index, (row, reason) in enumerate(zip(i_rows, reasons)):
        assert row['generation_finished']
        records.append({'id': row['id'], 'passed': index != 15, 'reason': reason,
                        'text_sha256': hashlib.sha256(row['text'].encode('utf8')).hexdigest()})
    write(identity.with_suffix('.manual-review.json'), {
        'reviewed_utc': datetime.now(timezone.utc).isoformat(), 'reviewer': 'Codex whole-answer manual review of all16 current responses',
        'mode': 'neutral', 'results_sha256': sha(identity), 'integrity_receipt_sha256': sha(folder / 'epoch3-neutral-integrity-v1.json'),
        'records': records, 'passed': 15, 'total': 16, 'weight_identity_gate_passed': False,
        'known_development_not_holdout': True, 'weight_erasure_proven': False, 'release_approved': False})
    print(json.dumps({'file8': '6/8 FP0', 'artifact_intents': '18/18 metadata-only', 'neutral_identity': '15/16', 'release_approved': False}))


if __name__ == '__main__':
    main()
