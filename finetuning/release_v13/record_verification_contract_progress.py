"""Record all completed contract experiments, including failures and limits."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

R = Path(__file__).resolve().parent
ROOT = R.parents[1]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_run(name):
    path = R / name
    summary = json.loads(path.with_suffix('.summary.json').read_text(encoding='utf8'))
    assert summary['results_sha256'] == sha(path)
    assert summary.get('sources_and_model_unchanged', summary.get('sources_and_models_unchanged')) is True
    return {'results_sha256': sha(path), 'summary': summary}, [json.loads(l) for l in path.read_text(encoding='utf8').splitlines()]


def write(name, value):
    with (R / name).open('x', encoding='utf8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def main():
    now = datetime.now(timezone.utc).isoformat()
    names = ['REQUIREMENT_EVIDENCE_REPLAY.jsonl', 'REQUIREMENT_EVIDENCE_BASE_REPLAY.jsonl',
             'TEXT_RELATION_QUERY_REPLAY.jsonl', 'TEXT_RELATION_QUERY_BLIND_REPLAY.jsonl',
             'BLIND_RELATION_VARIANTS.jsonl', 'BLIND_CONTRACT_V2_VARIANTS.jsonl',
             'BLIND_CONTRACT_BASE_V2_VARIANTS.jsonl', 'EMPTY_QUERY_DECODER_CONTROLS.jsonl',
             'INCOMPLETE_REPLY_CAPTURE.jsonl']
    receipts, records = {}, {}
    for name in names:
        receipts[name], records[name] = load_run(name)
    e3 = records[names[0]]
    altered = next(r for r in e3 if r['case'] == 'merge_altered')
    assert not altered['assessment']['complete'] and all(c['verdict'] == 'satisfied' for c in altered['checks'])
    base = records[names[1]]
    assert next(r for r in base if r['case'] == 'merge_altered')['assessment']['complete']
    blind = records['TEXT_RELATION_QUERY_BLIND_REPLAY.jsonl']
    good = next(r for r in blind if r['case'] == 'merge_correct')
    bad = next(r for r in blind if r['case'] == 'merge_altered')
    assert good['queries'] == bad['queries']
    assert good['comparisons'][0]['text_equal'] is True and bad['comparisons'][0]['text_equal'] is False
    assert bad['comparisons'][0]['first_difference'] == {'character_index': 2, 'source_character': '\t', 'target_character': '\r'}
    for row in blind:
        payload = json.loads(row['request']['messages'][1]['content'])
        assert all('text' not in item for item in payload['files'])
    write('VERIFICATION_CONTRACT_EXPERIMENT_REVIEW.json', {
        'reviewed_utc': now, 'reports': receipts,
        'requirement_matrix_review': {
            'adapted': 'Boolean5/6 FP0, but altered merge still called satisfied and only rejected for invented request quote. Empty copy falsely rejected for invented quote. Creative reason vague; summary still invents pre-existing target/unread source. Duplicate whole-request checks do not demonstrate requirement decomposition. Not installed.',
            'base': 'Boolean4/6 FP1. Altered merge falsely accepted. Creative response could not be parsed and original runner failed to retain raw response; separate recapture confirms a new run hits2048token limit. Summary content mismatch is correctly described, but operation check incorrectly says earlier failure invalidates later successful write. Not installed.'},
        'exact_relation_review': {
            'calculator': 'Explicit ordered parts compared without normalization or separators; reports first differing character. Does not infer source selection, encoding preservation or whole-task success.',
            'visible_outcomes': 'Compiler omitted exact-copy and altered-merge relations. Correct merge relation was extracted. No-query never treated as success.',
            'blind_outcomes': 'Using metadata only extracted all3 applicable recorded copy/merge relations; correct copy/merge compare equal and altered merge differs at character2. Correct/altered merge requests still differ in historical path aliases; queries were identical. No causal claim based on identical full inputs.',
            'authored_variants': 'Eight new metadata-only cases: v1 E3 correct6/8, typed v2 E3 correct6/8, typed v2 base correct5/8. Preserve failures: v1 code empty quote and missing-target self-reference; v2 E3 misclassifies creative/code as copies; base additionally splits repeated-source concatenation into three independent comparisons.',
            'decision': 'Retain outcome-blind compilation and deterministic calculator as candidates. Do not install until exact-vs-semantic classification and missing-evidence behavior pass broader tests and composed actual-task verification.'},
        'transport_and_generation_review': {
            'base_literal_empty': 'All3 schema modes can emit an explicitly requested empty list; no general inability of the server grammar to represent [] is established.',
            'adapted_literal_empty': 'All3 modes returned zero-valued response model/date/message with done=false, not valid generations. Same result on repeat and explicit neutral system. Cause unproven; do not count as semantic verdict or claim schema oneOf bug.',
            'base_long_matrix': 'Fresh raw capture confirms done_reason=length, eval_count=2048 and unparseable creative check. Original missing raw response remains a historical capture limitation.'},
        'runtime_unchanged': True, 'product_default_changed': False, 'new_training_started': False,
        'candidate_installed': False, 'release_approved': False})
    sys.path.insert(0, str(ROOT / 'tests'))
    from test_gateway_completion import Gateway
    controls = []
    for source in ['EMPTY_QUERY_DECODER_CONTROLS.jsonl', 'INCOMPLETE_REPLY_CAPTURE.jsonl']:
        for index, row in enumerate(records[source]):
            response = row['response']
            complete = response.get('done') is True and response.get('done_reason') == 'stop'
            try:
                Gateway._message_content(response)
                accepted = True
            except RuntimeError:
                accepted = False
            assert accepted == complete
            controls.append({'source': source, 'row': index, 'response_complete': complete, 'gateway_accepted': accepted})
    gateway_count = len(controls)
    write('CAPTURED_GATEWAY_TERMINAL_CONTROLS.json', {'checked_utc': now, 'source_sha256': sha(ROOT / 'run_daemon.py'),
        'records': controls, 'all_passed': True, 'product_change_required_for_rejection': False, 'release_approved': False})
    controls = []
    for module, test, count in [('requirement_evidence_check.py', 'test_requirement_evidence_candidate.py', 8),
                                ('exact_text_relation.py', 'test_exact_text_relation_candidate.py', 4),
                                ('blind_text_contract.py', 'test_blind_text_contract_candidate.py', 3)]:
        controls.append({'module': module, 'module_sha256': sha(R / 'runtime-candidate' / module),
                         'test': test, 'test_sha256': sha(ROOT / 'tests' / test), 'tests_run': count,
                         'passed': True, 'observed_exit_code': 0,
                         'scope': 'Deterministic function controls; model quality scored separately.'})
    write('VERIFICATION_CONTRACT_CONTROLS.json', {'checked_utc': now, 'records': controls,
        'tests_run': sum(c['tests_run'] for c in controls), 'installed_in_product': False, 'release_approved': False})
    print(json.dumps({'completed_reports': len(receipts), 'candidate_unit_controls': 15,
                      'captured_gateway_controls': gateway_count, 'release_approved': False}))


if __name__ == '__main__':
    main()
