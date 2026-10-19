"""Record failed extraction, mechanical checks and the new untrained data component."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

R = Path(__file__).resolve().parent
ROOT = R.parents[1]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    return json.loads(p.read_text(encoding='utf8'))


def rows(p):
    return [json.loads(l) for l in p.read_text(encoding='utf8').splitlines()]


def main():
    target = R / 'OPERATION_OBLIGATIONS_REVIEW.json'
    assert not target.exists()
    reports = {}
    for name in ['OPERATION_OBLIGATIONS_V1', 'REQUEST_CLAUSE_COVERAGE_V1']:
        path = R / (name + '.jsonl')
        summary, run, integrity = [read(R / (name + suffix)) for suffix in ['.summary.json', '.run.json', '.integrity.json']]
        assert summary['results_sha256'] == sha(path) and summary['sources_and_tag_unchanged']
        assert all(sha(Path(p)) == h for p, h in run['sources'].items())
        assert integrity['actual_model_unchanged'] and integrity['sources_unchanged'] and integrity['child_exit_code'] == 0
        reports[name] = {'summary': summary, 'integrity_receipt_sha256': sha(R / (name + '.integrity.json'))}
    obligation_rows = rows(R / 'OPERATION_OBLIGATIONS_V1.jsonl')
    for label, kind, status in [('source_overwritten_before_copy', 'preserve_sources', 'unmet'),
                                 ('summary_without_readback', 'destination_readback', 'uncertain')]:
        row = next(r for r in obligation_rows if r['case'] == label)
        assert row['previous_complete'] is True and row['guarded_complete'] is False
        assert any(c['kind'] == kind and c['status'] == status for c in row['operation_check']['checks'])
    clause_rows = rows(R / 'REQUEST_CLAUSE_COVERAGE_V1.jsonl')
    unique_requests = {json.loads(r['request']['messages'][1]['content'])['user_request'] for r in clause_rows}
    assert len(unique_requests) == 18 and all(r['valid'] for r in clause_rows)
    data = R / 'training-candidate/content-contrasts-v3'
    prep, audit = read(data / 'PREPARATION.json'), read(data / 'DATA_TOKEN_AUDIT.json')
    for name, digest in audit['files'].items(): assert sha(data / name) == digest
    assert sha(R / 'build_content_training_contrasts.py') == prep['script_sha256']
    assert sha(R / 'audit_content_training_contrasts.py') == audit['audit_script_sha256']
    for name, digest in prep['frozen_v13_inputs_unchanged'].items(): assert sha(R / name) == digest
    examples = rows(data / 'rows.jsonl')
    translations = [r for r in examples if r['category'] == 'content-literal-status']
    assert len(translations) == 16
    assert 'Proofreading of the document has not been completed yet.' in json.loads(translations[0]['prompt'])['semantic_artifacts'][0]['output']['text']
    linguistic = {'reviewed_utc': datetime.now(timezone.utc).isoformat(), 'rows_sha256': sha(data / 'rows.jsonl'),
        'reviewed_ids': [r['id'] for r in translations], 'reviewed': 16, 'accepted': 16,
        'notes': 'Reviewed all8Chinese/English positive-negative pairs. Preserve incomplete vs completed proofreading, unsaved/saved, generating/generated, closed/open, unsent/sent, ended/not-ended, unopened/opened and waiting/finished distinctions. These are quoted translation content, not actual tool states.',
        'corrected_before_training': ['v1 filename parity and fixed factual perturbation shortcuts removed in v2',
                                     'v2 unfinished proofreading wording and negative generation sentence tightened in v3'],
        'training_ready': False, 'training_started': False, 'release_approved': False}
    (data / 'LINGUISTIC_REVIEW.json').write_text(json.dumps(linguistic, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    test_modules = ['tests.test_file_operation_obligations_candidate', 'tests.test_request_clause_coverage_candidate',
        'tests.test_file_completion_views_candidate', 'tests.test_artifact_completion_guard_candidate',
        'tests.test_artifact_evidence_candidate', 'tests.test_artifact_intent_v2', 'tests.test_artifact_intent_candidate']
    result = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'unittest', *test_modules], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0 and 'Ran 67 tests' in result.stderr
    record = {'reviewed_utc': datetime.now(timezone.utc).isoformat(), 'reports': reports,
        'extraction_assessment': {
            'complete_contracts_correct': 5, 'total': 24, 'protocol_valid': 19,
            'failures': ['Preserve-source/read-before-write omitted despite explicit requests.',
                         'Required quotes sometimes invented; no-reply requests sometimes invent an exact reply.',
                         'Conditional existing-target skip collapsed to unconditional exact reply; reply-before-readback extra requirement omitted.'],
            'two_prior_false_positives_blocked': ['source_overwritten_before_copy', 'summary_without_readback'],
            'scope': 'Guard applied to saved completion responses after fresh requirement extraction. No autonomous task rerun; extraction failures remain failures.'},
        'clause_assessment': {'responses': 24, 'unique_original_requests': 18, 'all_units_structurally_present': 24,
            'selected_global_labels_correct': 7, 'selected_global_labels_total': 24,
            'whole_clause_review': ['Source-preservation units now usually receive an explicit label, but permissions can be mislabeled prohibitions.',
                'Readback-before-reply omitted or reversed; no-reply unit can acquire a false temporal requirement.',
                'Some artifact creative/summary requirements mislabeled semantic_reply; exact-copy/content preservation can be mislabeled source preservation.',
                'Global label-presence score does not prove per-clause accuracy or target binding. New browser/conditional units retained as unresolved in some cases.'],
            'scope': 'Lossless coverage and no invented quotes; not semantic interpretation or whole-task completion.'},
        'controls': {'tests_run': 67, 'exit_code': result.returncode, 'output': result.stderr,
            'sources': {str(p.relative_to(ROOT)): sha(p) for p in [
                R / 'runtime-candidate/file_operation_obligations.py', R / 'runtime-candidate/request_clause_coverage.py',
                ROOT / 'tests/test_file_operation_obligations_candidate.py', ROOT / 'tests/test_request_clause_coverage_candidate.py']}},
        'training_component': {'folder': str(data.relative_to(R)), 'preparation_sha256': sha(data / 'PREPARATION.json'),
            'token_audit_sha256': sha(data / 'DATA_TOKEN_AUDIT.json'), 'linguistic_review_sha256': sha(data / 'LINGUISTIC_REVIEW.json'),
            'rows': 256, 'pairs': 128, 'positive': 128, 'negative': 128,
            'factual_rows': 192, 'code_rows': 48, 'translation_rows': 16,
            'max_tokens': audit['max_tokens'], 'answer_only_masks_verified': 256,
            'data_tokens': ['system', 'prompt', 'answer'], 'metadata_sidecar_excluded': True,
            'frozen_v13_inputs_unchanged': True, 'training_ready': False, 'training_started': False,
            'pending': ['Independent template/family-disjoint development data and unchanged holdout isolation',
                        'Retention/identity mixture and complete training configuration', 'Formal training and unchanged release gates']},
        'next': ['Improve operation extraction coverage, negation and temporal relations without hiding unsupported requirements.',
                 'Continue preparing the new paired content/operation training mix and independent validation; current256rows are only one component and cannot replace the full original training objective.',
                 'Do not install current parser/role candidates based on narrow guard results. Preserve old failures, neutral identity gate, native-app/ASR/UI/hardware/full-task requirements.'],
        'all_inference_and_tokenizer_jobs_terminal': True, 'production_runtime_unchanged': True,
        'candidate_installed': False, 'model_default_changed': False, 'cloud_resources_created': False, 'release_approved': False}
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'obligation_contracts': '5/24', 'clause_presence': '7/24;18unique requests', 'controls': 67,
                      'new_training_component': '256rows;128pairs;not trained', 'release_approved': False}))


if __name__ == '__main__':
    main()
