"""Persist bounded observations already obtained by the active task; no polling."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def collect_runtime_evaluations():
    """Summarize only existing receipts, checking their source-result bindings."""
    profile = R / 'evaluation-runtime-v2'
    collected = {}
    for label in ('base', 'epoch1', 'epoch2', 'epoch3'):
        source = profile / (label + '-gateway-v1.jsonl')
        if not source.with_suffix('.generation-complete.json').exists():
            continue
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        receipt = read(source.with_suffix('.generation-complete.json'))
        assert receipt['results_sha256'] == digest and receipt['model_and_sources_unchanged']
        item = {'generation_complete': True, 'results_sha256': digest, 'release_approved': False}
        for suffix, name in (('.checks.json', 'automatic'), ('.manual-review.json', 'whole_answer'),
                             ('.plan-review.json', 'plans')):
            report_path = source.with_suffix(suffix)
            if not report_path.exists():
                continue
            report = read(report_path)
            assert report['results_sha256'] == digest
            item[name] = {'report': str(report_path.relative_to(R)),
                          'report_sha256': hashlib.sha256(report_path.read_bytes()).hexdigest()}
            for key in ('summary', 'false_completion_count', 'parser_accepted', 'planning_passed', 'total'):
                if key in report:
                    item[name][key] = report[key]
        full_loop = source.with_suffix('.full-loop') / 'order-audit-v1.json'
        if full_loop.exists():
            audit = read(full_loop)
            original = full_loop.parent / 'result.json'
            assert audit['original_result_sha256'] == hashlib.sha256(original.read_bytes()).hexdigest()
            item['full_loop'] = {'report': str(full_loop.relative_to(R)), 'total': audit['total'],
                                 'passed': audit['joint_with_order_passed'],
                                 'false_completions': audit['false_completions_with_order']}
        file_path = profile / (label + '-file8-v1.jsonl')
        if file_path.exists():
            rows = []
            for line in file_path.read_text(encoding='utf8').splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    break
            item['file8'] = {'output': str(file_path.relative_to(R)), 'observed_cases': len(rows),
                              'observed_passed': sum(r.get('passed') is True for r in rows),
                              'observed_false_completions': sum(r.get('false_completion') is True for r in rows),
                              'finished': file_path.with_suffix('.summary.json').exists()}
            if item['file8']['finished']:
                summary = read(file_path.with_suffix('.summary.json'))
                assert summary['results_sha256'] == hashlib.sha256(file_path.read_bytes()).hexdigest()
                assert len(rows) == summary['total'] == 8
                item['file8']['summary'] = summary
        collected[label] = item
    return collected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--local-file-session', type=int)
    parser.add_argument('--local-generation-session', type=int)
    parser.add_argument('--epoch-transfer-session', type=int)
    parser.add_argument('--extra-session', type=int, action='append', default=[])
    parser.add_argument('--extra-purpose', default='')
    parser.add_argument('--previous-classification', choices=('progress', 'verified_wait', 'no_progress'), required=True)
    args = parser.parse_args()
    state_path = R.parent / 'release_v4/SESSION_STATE.json'
    state = read(state_path)
    handle = read(R / 'TRAIN_PROCESS.json')
    latest = max((R / 'observations').glob('train-*.json'), key=lambda p: p.name)
    observation = read(latest)
    assert all(handle[key] == observation['handle'][key] for key in ('pid', 'start_ticks', 'pod_id', 'data_lock_sha256'))
    assert handle['data_lock_sha256'] == hashlib.sha256((R / 'DATA_LOCK.json').read_bytes()).hexdigest()
    training = state['release_v13']
    training.update(last_observation=str(latest.relative_to(R)),
                    last_observed_utc=observation['observed_utc'],
                    last_observed_step=max((x['step'] for x in observation['training_tail']), default=0),
                    completed_epochs=[x['epoch'] for x in observation['checkpoints'] if x.get('full_epoch')],
                    last_observed_process_live=observation['process_live'],
                    delivery_readiness='../release_v13/DELIVERY_READINESS.json',
                    delivery_protocol='../release_v13/DELIVERY_PROTOCOL.md')
    manifest = observation.get('report') or {}
    training['terminal_training_verified'] = bool(
        not observation['process_live']
        and (observation.get('runner') or {}).get('status') == 'command_completed'
        and manifest.get('training_completed') is True
        and manifest.get('disk_reload_logits_verified') is True
        and manifest.get('optimizer_steps') == manifest.get('planned_optimizer_steps') == 675
        and len([e for e in manifest.get('epochs', []) if e.get('full_epoch')]) == 3)
    training['native_identity_diagnostics'] = {}
    for epoch in (1, 2, 3):
        native = R / f'artifacts/outputs/identity-backend-e{epoch}/generation-complete.json'
        if native.exists():
            native_summary = read(native)
            native_results = native.parent / 'results.jsonl'
            assert native_summary['results_sha256'] == hashlib.sha256(native_results.read_bytes()).hexdigest()
            training['native_identity_diagnostics'][str(epoch)] = {
                'report': '../release_v13/' + str(native.relative_to(R)),
                'record': native_summary, 'semantic_review_pending': True}
    if (R / 'NATIVE_IDENTITY_REVIEW.json').exists():
        reviewed_native = read(R / 'NATIVE_IDENTITY_REVIEW.json')
        for epoch, item in training['native_identity_diagnostics'].items():
            review = reviewed_native['epochs'][epoch]
            assert review['results_sha256'] == item['record']['results_sha256']
            item.update(semantic_review_pending=False,
                        semantic_review_report='../release_v13/NATIVE_IDENTITY_REVIEW.json',
                        neutral_passed=review['neutral_passed'], branded_passed=review['branded_passed'],
                        cases_per_mode=review['cases_per_mode'], local_backend_pass_inferred=False)
    for filename, field in [('FINAL_TRANSFER_VERIFIED.json', 'final_transfer'), ('CLOUD_CLEANUP.json', 'cloud_cleanup')]:
        if (R / filename).exists():
            receipt = read(R / filename)
            compact_receipt = {k: v for k, v in receipt.items() if k not in ('files', 'checkpoint_entries', 'manifest')}
            if 'files' in receipt:
                compact_receipt['verified_file_count'] = len(receipt['files'])
            training[field] = {'report': '../release_v13/' + filename,
                               'report_sha256': hashlib.sha256((R / filename).read_bytes()).hexdigest(),
                               'record': compact_receipt}
    output = R / 'evaluation-v1/base-file8-current-v1.jsonl'
    summary_path = output.with_suffix('.summary.json')
    # Only complete flushed lines count; a live writer may have a partial tail.
    lines = output.read_text(encoding='utf8').splitlines() if output.exists() else []
    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            break
    local = {'output': str(output.relative_to(R)), 'observed_cases': len(records),
             'finished': summary_path.exists(), 'session': args.local_file_session,
             'observed_passed': sum(x.get('passed') is True for x in records),
             'observed_false_completions': sum(x.get('false_completion') is True for x in records)}
    if summary_path.exists():
        assert args.local_file_session is None, 'Do not record terminal while a session is still outstanding'
        local['summary'] = read(summary_path)
        assert len(records) == local['summary']['total'] == 8
    training['current_runtime_file_baseline'] = local
    if (R / 'FALLBACK_LITERAL_CONTROLS.json').exists():
        candidate = read(R / 'FALLBACK_LITERAL_CONTROLS.json')
        training['fallback_literal_candidate'] = {
            'report': '../release_v13/FALLBACK_LITERAL_CONTROLS.json',
            'candidate_passed': candidate['candidate_passed'],
            'candidate_cases': candidate['candidate_cases'],
            'original_failures_reproduced': candidate['original_reference_failures_reproduced'],
            'installed_in_product': candidate['installed_in_product'],
        }
    if (R / 'FALLBACK_PRODUCTION_VERIFIED.json').exists():
        installed = read(R / 'FALLBACK_LITERAL_INSTALL.json')
        verified = read(R / 'FALLBACK_PRODUCTION_VERIFIED.json')
        assert installed['after_sha256'] == verified['source_sha256']
        training['fallback_literal_candidate'].update(
            installed_in_product=True, production_tests_passed=verified['production_tests_passed'],
            production_test_count=verified['production_test_count'],
            current_verification_report='../release_v13/FALLBACK_PRODUCTION_VERIFIED.json')
        local['runtime_profile'] = 'pre-fallback-fix; historical baseline'
    generation_path = R / 'evaluation-runtime-v2/base-gateway-v1.jsonl'
    generated = []
    if generation_path.exists():
        for line in generation_path.read_text(encoding='utf8').splitlines():
            try:
                generated.append(json.loads(line))
            except json.JSONDecodeError:
                break
    complete_path = generation_path.with_suffix('.generation-complete.json')
    generation = {'profile': 'evaluation-runtime-v2', 'output': str(generation_path.relative_to(R)),
                  'observed_rows': len(generated), 'session': args.local_generation_session,
                  'finished': complete_path.exists(), 'fresh_base_generation': True}
    if complete_path.exists():
        assert args.local_generation_session is None, 'Observe tool-session completion before recording terminal'
        generation['summary'] = read(complete_path)
    training['runtime_v2_generation_baseline'] = generation
    training['neutral_identity_evaluations'] = {}
    for epoch in (1, 2, 3):
        identity = R / f'evaluation-runtime-v2/epoch{epoch}-identity-neutral-v1.manual-review.json'
        if identity.exists():
            reviewed = read(identity)
            source = identity.with_name(f'epoch{epoch}-identity-neutral-v1.jsonl')
            assert reviewed['results_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
            entry = {'report': '../release_v13/' + str(identity.relative_to(R)),
                'report_sha256': hashlib.sha256(identity.read_bytes()).hexdigest(),
                'passed': reviewed['passed'], 'total': reviewed['total'],
                'weight_identity_gate_passed': reviewed['weight_identity_gate_passed'],
                'results_sha256': reviewed['results_sha256']}
            training['neutral_identity_evaluations'][str(epoch)] = entry
            if epoch == 1:
                training['epoch1_neutral_identity'] = entry
    first_generation = R / 'evaluation-runtime-v2/epoch1-gateway-v1.jsonl'
    first_rows = []
    if first_generation.exists():
        for line in first_generation.read_text(encoding='utf8').splitlines():
            try:
                first_rows.append(json.loads(line))
            except json.JSONDecodeError:
                break
        training['epoch1_runtime_v2_generation'] = {
            'output': str(first_generation.relative_to(R)), 'observed_rows': len(first_rows),
            'finished': first_generation.with_suffix('.generation-complete.json').exists(),
            'release_approved': False}
    base_loop = R / 'evaluation-runtime-v2/base-gateway-v1.full-loop/order-audit-v1.json'
    if base_loop.exists():
        audited = read(base_loop)
        training['runtime_v2_base_full_loop'] = {'report': '../release_v13/' + str(base_loop.relative_to(R)),
            'completed': True, 'passed': audited['joint_with_order_passed'], 'total': audited['total'],
            'false_completions': audited['false_completions_with_order']}
    training['epoch1_transfer_session'] = args.epoch_transfer_session
    transfer = R / 'EPOCH-1_TRANSFER_VERIFIED.json'
    training['epoch1_transfer_verified'] = bool(transfer.exists() and read(transfer).get('transfer_verified'))
    for filename, field in [('EPOCH-1_PARAMETER_BINDING.json', 'epoch1_parameter_binding'),
                            ('local-adapters/epoch-1.conversion-provenance.json', 'epoch1_conversion'),
                            ('local-adapters/epoch-1.installed.json', 'epoch1_installation')]:
        if (R / filename).exists():
            training[field] = {'report': '../release_v13/' + filename, 'record': read(R / filename)}
    training['epoch_artifact_stages'] = {}
    for epoch in (1, 2, 3):
        stages = {}
        for filename, field, flag in (
            (f'EPOCH-{epoch}_TRANSFER_VERIFIED.json', 'transfer', 'transfer_verified'),
            (f'EPOCH-{epoch}_PARAMETER_BINDING.json', 'parameter_binding', 'matches_both_rank_agreement'),
            (f'local-adapters/epoch-{epoch}.conversion-provenance.json', 'conversion', 'conversion_verified'),
            (f'local-adapters/epoch-{epoch}.installed.json', 'installation', None),
        ):
            path = R / filename
            if path.exists():
                receipt = read(path)
                stages[field] = {'report': '../release_v13/' + filename,
                                 'report_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                 'verified': receipt.get(flag) is True if flag else bool(receipt.get('model', {}).get('digest'))}
                if field == 'installation':
                    stages[field].update(tag=receipt['tag'], model_digest=receipt['model']['digest'])
        if stages:
            training['epoch_artifact_stages'][str(epoch)] = stages
    if (R / 'CONDITION_DIAGNOSTICS.json').exists():
        training['condition_diagnostics'] = {
            'report': '../release_v13/CONDITION_DIAGNOSTICS.json', 'installed_in_product': True,
            'tests_passed': 18, 'model_repair_success_measured': False}
    if (R / 'CONDITION_RECOVERY_CANDIDATE.json').exists():
        candidate = read(R / 'CONDITION_RECOVERY_CANDIDATE.json')
        training['condition_recovery_candidate'] = {
            'report': '../release_v13/CONDITION_RECOVERY_CANDIDATE.json',
            'candidate_controls_passed': candidate['candidate_controls_passed'],
            'original_unrecovered_failures_reproduced': candidate['original_unrecovered_failures_reproduced'],
            'installed_in_product': False, 'model_repair_success_measured': False}
    if (R / 'CONDITION_RECOVERY_INSTALL.json').exists():
        install_path = R / 'CONDITION_RECOVERY_INSTALL.json'
        installed = read(install_path)
        current_source_sha256 = hashlib.sha256((R.parents[1] / 'run_daemon.py').read_bytes()).hexdigest()
        guidance_path = R / 'PRESERVATION_GUIDANCE_INSTALL.json'
        if (R / 'CONTEXT_DEDUP_INSTALL.json').exists():
            dedup = read(R / 'CONTEXT_DEDUP_INSTALL.json')
            withdrawal = read(R / 'PRESERVATION_GUIDANCE_WITHDRAWAL.json')
            guidance = read(guidance_path)
            assert withdrawal['before_sha256'] == guidance['after_sha256']
            assert withdrawal['after_sha256'] == installed['after_sha256'] == dedup['before_sha256']
            if (R / 'RESULT_CONTRACT_INSTALL.json').exists():
                contracts = read(R / 'RESULT_CONTRACT_INSTALL.json')
                assert contracts['before_sha256'] == dedup['after_sha256']
                if (R / 'GENERATION_CONTEXT_INSTALL.json').exists():
                    context = read(R / 'GENERATION_CONTEXT_INSTALL.json')
                    assert context['before_sha256'] == contracts['after_sha256']
                    if (R / 'FILE_TEXT_SOURCE_INSTALL.json').exists():
                        anchors = read(R / 'FILE_TEXT_SOURCE_INSTALL.json')
                        assert anchors['before_sha256'] == context['after_sha256']
                        if (R / 'MODEL_INTEGRITY_INSTALL.json').exists():
                            integrity = read(R / 'MODEL_INTEGRITY_INSTALL.json')
                            assert anchors['after_sha256'] == integrity['before_sha256']
                            assert integrity['after_sha256'] == current_source_sha256
                            for name, digest in integrity['new_modules'].items():
                                assert digest == hashlib.sha256((R.parents[1] / name).read_bytes()).hexdigest()
                        else:
                            assert anchors['after_sha256'] == current_source_sha256
                        assert anchors['module_after_sha256'] == hashlib.sha256((R.parents[1] / 'argument_references.py').read_bytes()).hexdigest()
                    else:
                        assert context['after_sha256'] == current_source_sha256
                    assert context['module_sha256'] == hashlib.sha256((R.parents[1] / 'generation_context.py').read_bytes()).hexdigest()
                else:
                    assert contracts['after_sha256'] == current_source_sha256
                assert contracts['module_sha256'] == hashlib.sha256((R.parents[1] / 'tool_result_contracts.py').read_bytes()).hexdigest()
            else:
                assert dedup['after_sha256'] == current_source_sha256
            assert dedup['module_sha256'] == hashlib.sha256((R.parents[1] / 'model_context.py').read_bytes()).hexdigest()
        elif guidance_path.exists():
            guidance = read(guidance_path)
            assert guidance['before_sha256'] == installed['after_sha256']
            assert guidance['after_sha256'] == current_source_sha256 and guidance['only_planner_guidance_changed']
        else:
            assert installed['after_sha256'] == current_source_sha256
        training['condition_recovery_candidate']['installed_in_product'] = True
        entry = {'installation_report': '../release_v13/CONDITION_RECOVERY_INSTALL.json',
                 'installation_sha256': hashlib.sha256(install_path.read_bytes()).hexdigest(),
                 'production_source_sha256': installed['after_sha256'], 'tests_passed': False,
                 'model_repair_success_measured': False, 'release_approved': False}
        tests = R / 'CONDITION_RECOVERY_PRODUCTION_TESTS.json'
        if tests.exists():
            checked = read(tests)
            assert checked['source_sha256'] == installed['after_sha256']
            entry.update(tests_passed=checked['passed'], tests_report='../release_v13/' + tests.name,
                         tests_report_sha256=hashlib.sha256(tests.read_bytes()).hexdigest())
        diagnostic = R / 'CONDITION_RECOVERY_MODEL.json'
        if diagnostic.exists():
            observed = read(diagnostic)
            assert observed['sources_and_model_unchanged']
            entry.update(model_diagnostic_report='../release_v13/' + diagnostic.name,
                         model_diagnostic_sha256=hashlib.sha256(diagnostic.read_bytes()).hexdigest(),
                         model_diagnostic_results=[{k: row[k] for k in ('mode', 'status', 'passed', 'append_dispatch_count', 'correct_readback')} for row in observed['records']],
                         model_repair_success_measured=any(row['mode'] == 'after' and row['passed'] for row in observed['records']),
                         autonomous_initial_plan_measured=False)
        training['condition_recovery_production'] = entry
    if (R / 'GREEDY_IDENTITY_REVIEW.json').exists():
        greedy_path = R / 'GREEDY_IDENTITY_REVIEW.json'
        reviewed = read(greedy_path)
        training['greedy_identity_diagnostic'] = {
            'report': '../release_v13/' + greedy_path.name,
            'report_sha256': hashlib.sha256(greedy_path.read_bytes()).hexdigest(),
            'epochs': {e: {k: row[k] for k in ('passed', 'total', 'results_sha256')} for e, row in reviewed['epochs'].items()},
            'conclusion': reviewed['conclusion'], 'original_gate_results_replaced': False}
    training['runtime_v3_prepared'] = (R / 'evaluation-runtime-v3/PROFILE_PREPARATION.json').exists()
    if (R / 'PRESERVATION_GUIDANCE_INSTALL.json').exists():
        guidance = read(R / 'PRESERVATION_GUIDANCE_INSTALL.json')
        training['preservation_guidance'] = {
            'installation_report': '../release_v13/PRESERVATION_GUIDANCE_INSTALL.json',
            'source_sha256': guidance['after_sha256'],
            'installed_in_product': not (R / 'PRESERVATION_GUIDANCE_WITHDRAWAL.json').exists(),
            'training_inputs_changed': False, 'release_approved': False}
        checked = R / 'PRESERVATION_GUIDANCE_TESTS.json'
        if checked.exists():
            test_receipt = read(checked)
            assert test_receipt['source_sha256'] == guidance['after_sha256']
            training['preservation_guidance'].update(tests_passed=test_receipt['passed'],
                tests_report='../release_v13/' + checked.name)
        training['active_runtime_profile'] = 'evaluation-runtime-v4'
        current_evals = {}
        for label, name, suffix in (
            ('file8', 'epoch3-file8-v1.jsonl', '.summary.json'),
            ('generation_contrasts', 'epoch3-generation-contrasts-v1.jsonl', '.summary.json')):
            path = R / 'evaluation-runtime-v4' / name
            if not path.exists():
                continue
            rows = []
            for line in path.read_text(encoding='utf8').splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    break
            entry = {'output': str(path.relative_to(R)), 'observed_cases': len(rows),
                     'observed_passed': sum(r.get('passed') is True for r in rows),
                     'observed_false_completions': sum(r.get('false_completion') is True for r in rows),
                     'finished': path.with_suffix(suffix).exists(), 'release_approved': False}
            if entry['finished']:
                receipt = read(path.with_suffix(suffix))
                assert receipt['results_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
                assert receipt['total'] == len(rows)
                entry['summary'] = receipt
            current_evals[label] = entry
        training['runtime_v4_evaluations'] = current_evals
    if (R / 'CONTEXT_DEDUP_INSTALL.json').exists():
        training['active_runtime_profile'] = 'evaluation-runtime-v5'
        training['context_dedup'] = {
            'installation_report': '../release_v13/CONTEXT_DEDUP_INSTALL.json',
            'tests': read(R / 'CONTEXT_DEDUP_TESTS.json'),
            'captured_controls': '../release_v13/CONTEXT_DEDUP_CAPTURED_CONTROLS.json',
            'unicode_encoder_installed': False,
            'guidance_withdrawal': '../release_v13/PRESERVATION_GUIDANCE_WITHDRAWAL.json',
            'release_approved': False}
        replay_path = R / 'CONTEXT_DEDUP_REPLAY.json'
        if replay_path.exists():
            replay = read(replay_path)
            assert replay['sources_and_model_unchanged']
            training['context_dedup']['captured_replay'] = {
                'report': '../release_v13/CONTEXT_DEDUP_REPLAY.json',
                'sha256': hashlib.sha256(replay_path.read_bytes()).hexdigest(),
                'complete_generations': sum(x.get('complete_generation') is True for x in replay['records']),
                'total': len(replay['records']), 'executed_actions': False,
                'review': '../release_v13/RUNTIME_V5_REVIEW.json'}
        path = R / 'evaluation-runtime-v5/epoch3-file8-v1.jsonl'
        training['runtime_v5_evaluations'] = {}
        if path.exists():
            rows = []
            for line in path.read_text(encoding='utf8').splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    break
            entry = {'output': str(path.relative_to(R)), 'observed_cases': len(rows),
                     'observed_passed': sum(r.get('passed') is True for r in rows),
                     'observed_false_completions': sum(r.get('false_completion') is True for r in rows),
                     'finished': path.with_suffix('.summary.json').exists(), 'release_approved': False}
            if entry['finished']:
                receipt = read(path.with_suffix('.summary.json'))
                assert receipt['results_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
                assert receipt['total'] == len(rows)
                entry['summary'] = receipt
            training['runtime_v5_evaluations']['file8'] = entry
    if (R / 'RESULT_CONTRACT_INSTALL.json').exists():
        training['active_runtime_profile'] = 'evaluation-runtime-v6'
        training['result_contracts'] = {
            'installation_report': '../release_v13/RESULT_CONTRACT_INSTALL.json',
            'tests': read(R / 'RESULT_CONTRACT_TESTS.json'),
            'known_invalid_conditions_rejected_before_dispatch': True,
            'runtime_condition_checks_retained': True, 'release_approved': False}
        path = R / 'evaluation-runtime-v6/epoch3-file8-v1.jsonl'
        training['runtime_v6_evaluations'] = {}
        if path.exists():
            rows = []
            for line in path.read_text(encoding='utf8').splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    break
            entry = {'output': str(path.relative_to(R)), 'observed_cases': len(rows),
                     'observed_passed': sum(r.get('passed') is True for r in rows),
                     'observed_false_completions': sum(r.get('false_completion') is True for r in rows),
                     'finished': path.with_suffix('.summary.json').exists(), 'release_approved': False}
            if entry['finished']:
                receipt = read(path.with_suffix('.summary.json'))
                assert receipt['results_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
                assert receipt['total'] == len(rows)
                entry['summary'] = receipt
            training['runtime_v6_evaluations']['file8'] = entry
        contrast_path = R / 'evaluation-runtime-v6/epoch3-generation-contrasts-v1.summary.json'
        if contrast_path.exists():
            contrast = read(contrast_path)
            result_path = R / 'evaluation-runtime-v6/epoch3-generation-contrasts-v1.jsonl'
            assert contrast['results_sha256'] == hashlib.sha256(result_path.read_bytes()).hexdigest()
            reviewed = read(R / 'GENERATION_CONTRASTS_V6_REVIEW.json')
            assert reviewed['results_sha256'] == contrast['results_sha256']
            training['runtime_v6_evaluations']['generation_contrasts'] = {
                'summary': contrast, 'review': '../release_v13/GENERATION_CONTRASTS_V6_REVIEW.json',
                'semantic_review_pending': False, 'semantic_passed': reviewed['semantic_passed'],
                'full_task_passed': reviewed['full_task_passed'],
                'semantic_false_completions': reviewed['semantic_false_completions']}
        guided = R / 'GUIDED_CONDITION_REPAIR_MODEL.json'
        if guided.exists():
            measured = read(guided)
            assert measured['sources_and_model_unchanged']
            training['result_contracts']['guided_repair_candidate'] = {
                'model_report': '../release_v13/GUIDED_CONDITION_REPAIR_MODEL.json',
                'report_sha256': hashlib.sha256(guided.read_bytes()).hexdigest(),
                'cases': [{k: x[k] for k in ('mode', 'status', 'passed', 'seconds')} for x in measured['records']],
                'installed_in_product': False}
    if (R / 'GENERATION_CONTEXT_INSTALL.json').exists():
        training['active_runtime_profile'] = 'evaluation-runtime-v7'
        training['generation_context'] = {
            'installation_report': '../release_v13/GENERATION_CONTEXT_INSTALL.json',
            'tests': read(R / 'GENERATION_CONTEXT_TESTS.json'),
            'task_local_observations_and_original_request_forwarded': True,
            'new_source_reads_inferred': False, 'release_approved': False}
        current = {}
        for label, filename in (('file8', 'epoch3-file8-v1.jsonl'),
                                ('generation_contrasts', 'epoch3-generation-contrasts-v1.jsonl')):
            path = R / 'evaluation-runtime-v7' / filename
            if not path.exists():
                continue
            rows = []
            for line in path.read_text(encoding='utf8').splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    break
            entry = {'observed_cases': len(rows), 'output': str(path.relative_to(R)),
                     'finished': path.with_suffix('.summary.json').exists(), 'release_approved': False}
            if label == 'file8':
                entry.update(observed_passed=sum(x.get('passed') is True for x in rows),
                             observed_false_completions=sum(x.get('false_completion') is True for x in rows))
            else:
                entry.update(observed_mechanical_passed=sum(x.get('mechanical_passed') is True for x in rows),
                             semantic_review_pending=True)
            if entry['finished']:
                summary = read(path.with_suffix('.summary.json'))
                assert summary['results_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
                assert summary['total'] == len(rows)
                entry['summary'] = summary
            current[label] = entry
        review_path = R / 'GENERATION_CONTRASTS_V7_REVIEW.json'
        if review_path.exists() and 'generation_contrasts' in current:
            review = read(review_path)
            assert review['results_sha256'] == current['generation_contrasts']['summary']['results_sha256']
            current['generation_contrasts'].update(semantic_review_pending=False,
                full_task_passed=review['full_task_passed'], semantic_passed=review['semantic_passed'],
                review='../release_v13/' + review_path.name)
        training['runtime_v7_evaluations'] = current
        for key, filename in [('same_input_model_comparison', 'GENERATION_CONTEXT_MODEL_COMPARISON_REVIEW.json'),
                              ('invalid_plan_echo_ablation', 'UNANCHORED_PLAN_REPLAY_REVIEW.json')]:
            if (R / filename).exists():
                training['generation_context'][key] = {'report': '../release_v13/' + filename,
                    'report_sha256': hashlib.sha256((R / filename).read_bytes()).hexdigest(),
                    'review': read(R / filename), 'release_approved': False}
    if (R / 'FILE_TEXT_SOURCE_INSTALL.json').exists():
        training['active_runtime_profile'] = 'evaluation-runtime-v8'
        training['file_text_source_preflight'] = {'installation': read(R / 'FILE_TEXT_SOURCE_INSTALL.json'),
            'tests': read(R / 'FILE_TEXT_SOURCE_TESTS.json'), 'release_approved': False}
        if (R / 'FILE_TEXT_SOURCE_COMPATIBILITY_TESTS.json').exists():
            training['file_text_source_preflight']['compatibility_tests'] = read(R / 'FILE_TEXT_SOURCE_COMPATIBILITY_TESTS.json')
        path = R / 'evaluation-runtime-v8/epoch3-file8-v1.jsonl'
        current = {}
        if path.exists():
            rows = [json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if line.strip()]
            current = {'observed_cases': len(rows), 'observed_passed': sum(x.get('passed') is True for x in rows),
                       'observed_false_completions': sum(x.get('false_completion') is True for x in rows),
                       'finished': path.with_suffix('.summary.json').exists(), 'release_approved': False}
            if current['finished']:
                summary = read(path.with_suffix('.summary.json'))
                assert summary['total'] == len(rows)
                assert summary['results_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
                current['summary'] = summary
        training['runtime_v8_evaluations'] = {'file8': current}
        if (R / 'RUNTIME_V8_FILE_REVIEW.json').exists():
            reviewed = read(R / 'RUNTIME_V8_FILE_REVIEW.json')
            assert reviewed['results_sha256'] == current['summary']['results_sha256']
            training['runtime_v8_evaluations']['review'] = '../release_v13/RUNTIME_V8_FILE_REVIEW.json'
        diagnostics = R / 'COMPLETION_CHECKER_DIAGNOSTICS_REVIEW.json'
        if diagnostics.exists():
            reviewed = read(diagnostics)
            for label, name in [('adapted', 'COMPLETION_FILE_FACTS_REPLAY.jsonl'), ('base', 'COMPLETION_BASE_COMPARISON.jsonl')]:
                assert reviewed['profiles'][label]['results_sha256'] == hashlib.sha256((R / name).read_bytes()).hexdigest()
            training['completion_diagnostics'] = {
                'review': '../release_v13/' + diagnostics.name,
                'review_sha256': hashlib.sha256(diagnostics.read_bytes()).hexdigest(),
                'profile_summaries': {k: v['summary'] for k, v in reviewed['profiles'].items()},
                'training_audit': read(R / 'COMPLETION_TRAINING_COVERAGE_AUDIT.json'),
                'candidate_controls': read(R / 'COMPLETION_FILE_FACTS_CONTROLS.json'),
                'candidate_installed': False, 'product_default_changed': False, 'release_approved': False}
    experiment_path = R / 'VERIFICATION_CONTRACT_EXPERIMENT_REVIEW.json'
    if experiment_path.exists():
        reviewed = read(experiment_path)
        for name, report in reviewed['reports'].items():
            assert report['results_sha256'] == hashlib.sha256((R / name).read_bytes()).hexdigest()
        training['verification_contract_experiments'] = {
            'review': '../release_v13/' + experiment_path.name,
            'review_sha256': hashlib.sha256(experiment_path.read_bytes()).hexdigest(),
            'reports': reviewed['reports'], 'controls': read(R / 'VERIFICATION_CONTRACT_CONTROLS.json'),
            'gateway_controls': read(R / 'CAPTURED_GATEWAY_TERMINAL_CONTROLS.json'),
            'candidate_installed': False, 'release_approved': False}
    repair_review_path = R / 'BLOB_REPAIR_AND_ARTIFACT_REVIEW.json'
    if repair_review_path.exists():
        reviewed = read(repair_review_path)
        for name, report in reviewed['reports'].items():
            assert report['results_sha256'] == hashlib.sha256((R / name).read_bytes()).hexdigest()
        for name, digest in reviewed['additional_evidence'].items():
            assert digest == hashlib.sha256((R / name).read_bytes()).hexdigest()
        training['model_blob_repair'] = {
            'review': '../release_v13/' + repair_review_path.name,
            'review_sha256': hashlib.sha256(repair_review_path.read_bytes()).hexdigest(),
            'integrity_verification': read(R / 'MODEL_BLOB_INTEGRITY_VERIFIED.json'),
            'artifact_replay': read(R / 'ARTIFACT_INTENT_E3_REPAIRED_V1.summary.json'),
            'historical_checks_only_attested_model_manifest': True,
            'corruption_origin_and_time_unknown': True,
            'gateway_startup_integration_pending': True,
            'candidate_installed': False, 'release_approved': False}
    if (R / 'MODEL_INTEGRITY_INSTALL.json').exists():
        training['active_runtime_profile'] = 'evaluation-runtime-v9'
        training['model_integrity_production'] = {'installation': read(R / 'MODEL_INTEGRITY_INSTALL.json'),
            'task_boundary_disk_check': True, 'loaded_memory_verified': False, 'release_approved': False}
        if 'model_blob_repair' in training:
            training['model_blob_repair']['gateway_startup_integration_pending'] = False
        path = R / 'evaluation-runtime-v9/epoch3-file8-v1.jsonl'
        current = {'observed_cases': 0, 'finished': False, 'release_approved': False}
        if path.exists():
            rows = [json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if line.strip()]
            current.update(observed_cases=len(rows), observed_passed=sum(x.get('passed') is True for x in rows),
                           observed_false_completions=sum(x.get('false_completion') is True for x in rows),
                           finished=path.with_suffix('.summary.json').exists())
            if current['finished']:
                summary = read(path.with_suffix('.summary.json'))
                assert summary['results_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
                assert summary['total'] == len(rows)
                current['summary'] = summary
        training['runtime_v9_evaluations'] = {'file8': current}
        file_review = R / 'RUNTIME_V9_FILE_REVIEW.json'
        if file_review.exists():
            reviewed = read(file_review)
            assert reviewed['results_sha256'] == current['summary']['results_sha256']
            training['runtime_v9_evaluations']['file8']['review'] = '../release_v13/' + file_review.name
        identity = R / 'evaluation-runtime-v9/epoch3-identity-neutral-v1.jsonl'
        if identity.with_suffix('.manual-review.json').exists():
            reviewed = read(identity.with_suffix('.manual-review.json'))
            assert reviewed['results_sha256'] == hashlib.sha256(identity.read_bytes()).hexdigest()
            integrity_path = identity.parent / 'epoch3-neutral-integrity-v1.json'
            assert reviewed['integrity_receipt_sha256'] == hashlib.sha256(integrity_path.read_bytes()).hexdigest()
            training['runtime_v9_evaluations']['neutral_identity'] = {'review': str(identity.with_suffix('.manual-review.json').relative_to(R)),
                'passed': reviewed['passed'], 'total': reviewed['total'], 'results_sha256': reviewed['results_sha256'],
                'weight_identity_gate_passed': reviewed['weight_identity_gate_passed'], 'integrity': read(integrity_path)}
        artifact_path = R / 'ARTIFACT_INTENT_V2_REVIEW.json'
        if artifact_path.exists():
            reviewed = read(artifact_path)
            assert reviewed['results_sha256'] == hashlib.sha256((R / 'ARTIFACT_INTENT_E3_V2.jsonl').read_bytes()).hexdigest()
            for name, digest in reviewed['controls']['source_hashes'].items():
                assert digest == hashlib.sha256((R.parents[1] / name).read_bytes()).hexdigest()
            training['artifact_intent_v2'] = {'review': '../release_v13/' + artifact_path.name, 'summary': reviewed['summary'],
                'controls': reviewed['controls'], 'candidate_installed': False, 'release_approved': False}
    evidence_review = R / 'ARTIFACT_EVIDENCE_REVIEW.json'
    if evidence_review.exists():
        reviewed = read(evidence_review)
        assert reviewed['results_sha256'] == hashlib.sha256((R / 'ARTIFACT_EVIDENCE_REPLAY_V1.jsonl').read_bytes()).hexdigest()
        assert reviewed['raw_sha256'] == hashlib.sha256((R / 'ARTIFACT_EVIDENCE_REPLAY_V1.raw.jsonl').read_bytes()).hexdigest()
        offline = R / reviewed['guard_offline_review']
        assert reviewed['guard_offline_sha256'] == hashlib.sha256(offline.read_bytes()).hexdigest()
        for name, digest in reviewed['controls']['sources'].items():
            assert digest == hashlib.sha256((R.parents[1] / name).read_bytes()).hexdigest()
        training['artifact_evidence_candidate'] = {'review': '../release_v13/' + evidence_review.name,
            'paired_inference': reviewed['summary']['modes'], 'compilation': reviewed['compilation_review'],
            'offline_guard': {k: read(offline)[k] for k in ['total', 'correct', 'false_positives', 'inference_repeated']},
            'controls_passed': reviewed['controls']['tests_run'], 'candidate_installed': False, 'release_approved': False}
    views_review = R / 'FILE_COMPLETION_VIEWS_REVIEW.json'
    if views_review.exists():
        reviewed = read(views_review)
        for name, item in reviewed['reports'].items():
            assert item['summary']['results_sha256'] == hashlib.sha256((R / (name + '.jsonl')).read_bytes()).hexdigest()
            assert item['integrity_receipt_sha256'] == hashlib.sha256((R / (name + '.integrity.json')).read_bytes()).hexdigest()
        for name, digest in reviewed['controls']['sources'].items():
            assert digest == hashlib.sha256((R.parents[1] / name).read_bytes()).hexdigest()
        training['file_completion_views_candidate'] = {'review': '../release_v13/' + views_review.name,
            'historical_replay': reviewed['reports']['FILE_COMPLETION_VIEWS_V1']['summary']['modes'],
            'new_controls': reviewed['reports']['FILE_VIEWS_CONTROLS_V1']['summary'],
            'base_same_input': {k: reviewed['base_same_input_aggregate'][k] for k in ['correct', 'total', 'false_positives']},
            'controls_passed': reviewed['controls']['tests_run'], 'candidate_installed': False, 'release_approved': False}
    operations_review = R / 'OPERATION_OBLIGATIONS_REVIEW.json'
    if operations_review.exists():
        reviewed = read(operations_review)
        for name, item in reviewed['reports'].items():
            assert item['summary']['results_sha256'] == hashlib.sha256((R / (name + '.jsonl')).read_bytes()).hexdigest()
            assert item['integrity_receipt_sha256'] == hashlib.sha256((R / (name + '.integrity.json')).read_bytes()).hexdigest()
        for name, digest in reviewed['controls']['sources'].items():
            assert digest == hashlib.sha256((R.parents[1] / name).read_bytes()).hexdigest()
        component = reviewed['training_component']
        folder = R / component['folder']
        for filename, key in [('PREPARATION.json', 'preparation_sha256'), ('DATA_TOKEN_AUDIT.json', 'token_audit_sha256'), ('LINGUISTIC_REVIEW.json', 'linguistic_review_sha256')]:
            assert component[key] == hashlib.sha256((folder / filename).read_bytes()).hexdigest()
        training['operation_obligations_candidate'] = {'review': '../release_v13/' + operations_review.name,
            'extraction': reviewed['extraction_assessment'], 'clauses': reviewed['clause_assessment'],
            'controls_passed': reviewed['controls']['tests_run'], 'candidate_installed': False, 'release_approved': False}
        training['new_content_training_component'] = component
    if (R / 'UI_COMPOSER_VERIFIED.json').exists():
        ui = read(R / 'UI_COMPOSER_VERIFIED.json')
        assert ui['current_qml_sha256'] == hashlib.sha256((R.parents[1] / 'desktop_ui/Main.qml').read_bytes()).hexdigest()
        assert ui['current_app_sha256'] == hashlib.sha256((R.parents[1] / 'desktop_ui/app.py').read_bytes()).hexdigest()
        training['ui_composer'] = {'report': '../release_v13/UI_COMPOSER_VERIFIED.json',
            'production_ui_updated': True, 'long_input_characters': ui['long_input_characters'],
            'qt_interaction_profiles_passed': ui['qt_interaction_profiles_passed'],
            'target_hardware_verified': False, 'packaged': False}
    training['current_local_runs'] = [s for s in (args.local_file_session, args.local_generation_session, args.epoch_transfer_session, *args.extra_session) if s is not None]
    training['runtime_v2_evaluations'] = collect_runtime_evaluations()
    training['extra_local_work'] = {'sessions': args.extra_session, 'purpose': args.extra_purpose}
    state['active_exec_sessions'] = list(training['current_local_runs'])
    state['active_exec_session'] = next(iter(training['current_local_runs']), None)
    state['previous_goal_turn_classification'] = args.previous_classification
    state['latest_goal_turn_classification'] = 'progress'
    state['updated_utc'] = datetime.now(timezone.utc).isoformat()
    state['release_approved'] = False
    state['next'] = [
        'runtime-v9 installed: per-task local model blob integrity checks precede chat, with52unit/compatibility controls and16file fixture positive controls. Captured inference hooks filter /api/chat so metadata reads do not consume inference budget or overwrite responses. Re-run unchanged file8 with actual pre/post model blob receipts; current sessions in active_exec_sessions are authoritative observations, not inferred from filenames.',
        'Latest: BLOB_REPAIR_AND_ARTIFACT_REVIEW.json establishes an installed E3 adapter blob SHA256 mismatch despite an unchanged model manifest. One tensor contained1024changed float32 values and non-finite data. Bad copy preserved; affected runner unloaded; only damaged blob restored from verified original. Corruption cause/time unknown. Earlier manifest-only stability checks do not attest every historical actual-weight file.',
        'After repair identical14artifact requests all generate completely,13contracts correct; missing-target case still selects source and is rejected. Identical empty-JSON and neutral name probes recover. Actual blobs of all3evaluation models verified;8integrity controls pass. Next require actual-byte checks before/after evaluation, integrate startup/package preflight, fix source/destination schema, and repeat unchanged full gates. No cloud run, default-model switch or release pass.',
        'Training675/675, all3 full checkpoints and last-epoch disk reload are verified terminal; all96 native identity answers are reviewed and full1.04GB backup verified. CLOUD_CLEANUP.json verifies pod deletion; do not restart or SSH this deleted pod.',
        'Base runtime-v2 file8 completed4/8 with0false completions; E1 completed6/8. E1 generation, whole-answer, plan, neutral identity and full12 reviews are recorded.',
        'E2 neutral identity14/16 and full176 review complete; plans11/15, full12withorder6/12 and3false completions, file8completed5/8 and1false completion. Preserve all failure evidence.',
        'E3 original-profile evaluation is complete: neutral15/16, full176 reviewed, plans12/15, full12strict7/12 with3false completions, file8 7/8 with1false completion. File04 loses tab/final newline through MODEL_GENERATE; retain complete raw evidence.',
        'Greedy replay completed and all32 answers reviewed: E2 14/16 and E3 15/16 unchanged. Temperature alone does not fix identity format; backend/quantization/template cause remains unproven. Preserve original gates.',
        'Condition recovery is installed;49 production tests passed and runtime-v3 prepared with unchanged cases/oracles. Injected-fault actual-model diagnostic completed: old runtime stops, fixed runtime recovers exact bytes/readback/reply with one append. It took64.532s and4 model calls, including an intermediate false-negative checker; not autonomous initial planning or file8 acceptance.',
        'runtime-v4 file8 terminal5/8,0false completions. Item15 source-preservation guidance withdrawn after regression; merge bytes correct but checker invented byte-count requirement, replan repeated a write; case06 missed branch guards. Original artifacts retained. Prepared v4 synthesis runner was not executed and cannot run against current source.',
        'Lossless repeated-text context sharing installed,47 relevant tests passed. runtime-v5 binds model_json/model_context and preserves original cases/oracles. E3 file8 terminal5/8 with1false completion; case02 invalid branch then checker hallucination,04 changed merge bytes falsely accepted,05 valid empty copy rejected by checker. Historical v5 file8 and replay are terminal.',
        'Captured v4 overflow/checker replay completed2/2 valid JSONs with exact same decoded payload and original system/options. Replan produced only required FINAL_RESPONSE without truncation; checker now returned false, but its reason inaccurately framed missing reply as format/branch mismatch. No actions executed by replay, no full-release success inferred. See RUNTIME_V5_REVIEW.json.',
        'Compact Unicode encoder remains staged.13737 Unicode controls passed; case01 token-reduction expectation failed (already NFC). Case04 saved40/64 tokens only. Do not describe it as a fix for case01 overflow.',
        'Result boolean contracts installed with66 tests passed; runtime-v6 file8 terminal7/8 with0false completions. Case06 remained blocked after2invalid plans; no path/source action happened. Runtime guard is correct but task failed. Guided-feedback candidate passed7controls, yet current/candidate actual-model diagnostics both blocked; candidate not installed. All3workloads terminal.',
        'v7 generation context installed with28 tests. Synthesis contrasts terminal0/3full,1/3semantic artifact: summary facts correct but completion checker rejected it; creative output is workflow status; code planning invalid before generation. Same-input base/E3 six generations reviewed: E3 code passed8integer cases and raw format, neither model consistently passed all formats. Full file8 terminal4/8,0false completions; failures01,04,06,08. All original records retained.',
        'Invalid-plan echo ablation terminal2responses: conditional still parser-invalid; code parser-valid but merely copied requirements into calculator.py and proposed writing source, semantic0/2. Candidate NOT installed. Do not treat parser acceptance as successful repair.',
        'Full-file reference anchor preflight installed in runtime-v8 with40 tests and34 compatibility tests. File8 terminal3/8 FP0, failures01/04/05 completion false negatives,06 invalid conditional plan,08 repeatedly read nonexistent destination. New anchor guard was not triggered in this particular real-model run;74 tests prove guard behavior but do not imply model task success. Source and all original gates preserved.',
        'Completion fact candidate passed7controls; paired6cases/12responses on E3: baseline3/6 FP1, facts5/6 FP1. Pinned base identical12inputs: both variants4/6 FP2. Reasons often mismatch observed state even when boolean is correct. Both workloads terminal; neither candidate nor base checker installed. Do not fix this by switching model or accepting any true vote.',
        'Requirement/evidence matrix candidate implemented with8controls; E3 six-case replay5/6 FP0, but wrong merge still internally satisfied and only rejected for invented quote. Empty copy rejected similarly. Base4/6 FP1 plus creative JSON parse failure. Candidate not installed; do not equate guarded boolean with semantic correctness.',
        'Outcome-blind exact-text operand compilation now staged separately from calculator: three applicable recorded relations correctly chosen, altered11-vs9character merge detected at index2 (tab vs CR). Expanded8authored variants: v1 E3 6/8; typed v2 E3 6/8 and base5/8. Creative/code misclassified as copy remains; source/destination self-reference prohibited by v2 schema. Not installed and not whole-task proof. Next integrate only after resolving classification and testing the composed content/operation/delivery verifier; do not silently accept empty query as completion.',
        'Empty-query decoder controls: base3/3 exact empty responses; E3 returned empty zero-valued envelopes with done=false in3modes, repeated with explicit neutral system. Cause unproven, not evidence that [] is impossible or a oneOf bug. Base creative raw recapture reached2048token length cutoff. Existing product gateway rejects all9captured incomplete/complete controls correctly; no bypass needed. All nine experiment reports terminal, no sessions remain.',
        'Audit confirms484completion training rows/484unique prompt-answer pairs but158unique reasons,0context-sharing examples; coverage gap is not proof of causal memorization. Frozen training inputs unchanged. Keep short/incomplete-output regression visible when deciding model or adapter changes. Native target hardware, apps, ASR, performance and packaging remain required.',
        'EVALUATION_TEMPLATE_PACKAGING_AUDIT.json shows E3 evaluation tag inherits the same template/default system as base; default metadata lacks product name. Do not mutate pinned evaluation tags or ship them as product default. Create separate branded packaging artifact and verify direct use, retaining neutral-system weight identity gate. This metadata read is not an identity answer probe and does not explain the empty-response cause.',
        'Continue conditional repair, exact text transformations, completion evidence, text/CSS grounding and factual correction without embedding fixture answers. Do not repeat failed feedback-only approach as if successful. Preserve successful recovery and synthesis capabilities; each historical profile only matches its frozen source.',
        'Complete RTX4050/24GB/Windows11 native-app, microphone, long-task recovery, performance, UI and packaging acceptance; target project is not yet open.'
    ]
    if (R / 'MODEL_INTEGRITY_INSTALL.json').exists():
        state['next'] = [
            'Keep full PROJECT_GOALS.md and release gates. Training675/675 and all3checkpoints were backed up; old paid pod was deleted. Do not restart that deleted pod or imply new cloud training.',
            'Installed E3 blob corruption was repaired from verified backup; origin/time unknown. Preserve bad-copy evidence and historical reports. Historical tag checks were not full file verification. Use model_blob_integrity plus run_integrity_checked.py for actual-byte pre/post checks in new evaluations.',
            'runtime-v9 has per-task local model preflight,52unit/compatibility controls and16positive file fixtures. Original file8 terminal6/8 FP0: case05 verified empty copy/final steps falsely rejected by checker; case06 invalid WRITE boolean condition and missing guards blocked all reads. Keep source/conditional protections; do not accept blocked/rejected tasks as successes.',
            'Artifact intent v2 passed18/18metadata-only cases and10controls, including unobserved destinations and mixed outputs. Not installed. Compose extracted artifact requirements with actual content, operation and delivery verification; empty artifacts and unobserved targets are never completion evidence.',
            'Fresh neutral weight-identity16case gate is15/16 with actual model bytes verified around the run. Date JSON returns a string instead of a founded object. Fix without injecting brand/date answers in neutral system or weakening original format gate.',
            'Continue improving conditional planning, completion false negatives/positives, source-based synthesis and code generation using recorded original failures. Existing six-case completion candidates and synthesis failures remain relevant; a parsing or narrow extraction pass does not replace actual semantic task results.',
            'Re-run unchanged full development/full12, synthesis, literal/content-preservation, Taiwan language/ASR and final untouched holdout gates for the final candidate. Do not overwrite frozen data, model evaluation tags or historical failure evidence.',
            'Build a separate branded package/default-system artifact; evaluation tags inherit old default metadata and must not ship as product defaults. Keep independent learned-identity and packaged-identity checks separate; preserve internal license/source sidecars outside model input and routine answers.',
            'Complete Windows11 RTX4050 6GB/24GB target-machine, native-app, microphone, long-task recovery, performance, mature UI and package acceptance. Target project is not yet opened; current RX6700XT results cannot substitute for that hardware.',
        ]
    if evidence_review.exists():
        state['next'].insert(1, 'Artifact evidence candidate:8/8artifact classifications correct; paired checker baseline4/8FP1 vs augmented6/8FP1. Model ignores actual text mismatch and mistakes artifact status prose for operations. Negative-only host guard passes31combined controls and offline saved-response replay7/8FP0, but was NOT installed or tested end-to-end. Current v9 empty-copy false negative remains. Ground semantic content separately from operation/delivery evidence, then re-run original gates. Review ARTIFACT_EVIDENCE_REVIEW.json; terminal session16977 must not be polled/restarted.')
    if views_review.exists():
        state['next'].insert(1, 'Latest separated file checks: original8replay booleans8/8FP0 but wrong reasons remain; NEW positive/negative8controls only3/8FP2 on E3 and5/8FP2 on base with identical22role requests. Both miss required readback/source overwrite and reject legitimate status translation; E3 additionally rejects correct creative/code.43unit/compatibility controls pass but candidate NOT installed. Next bind outcome-blind original operation obligations to mechanical history checks and prepare grounded content/retention training contrasts; do not blacklist status words or switch base by this narrow score. New controls remain development evaluation, not training. FILE_COMPLETION_VIEWS_REVIEW.json binds all3terminal jobs (70193,69375,32982); do not poll/restart them.')
    if operations_review.exists():
        state['next'].insert(1, 'Latest OPERATION_OBLIGATIONS_REVIEW.json: mechanical readback/source/new-file/literal/order checks staged with67combined controls. Actual obligation extraction5/24 (19valid); all-clause coverage24/24structurally present but selected labels only7/24 across18unique requests, including temporal/permission/content-vs-reply errors. Do not install or treat negative-only saved-response improvements as autonomous completion. Terminal jobs40101,20745,93069 must not be polled/restarted. New training-candidate/content-contrasts-v3 contains256rows/128positive-negative pairs; actual pinned tokenizer masks checked, max713tokens, all16translation rows reviewed, old train/dev/lock unchanged. v1/v2 withdrawn before training. Next build family-disjoint validation and retention/identity mix plus operation interpretation contrasts; this component alone is not training-ready, no new weights/cloud run.')
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    record = {'updated_utc': state['updated_utc'], 'training_handle': handle,
              'training_observation': str(latest.relative_to(R)),
              'training_observed_utc': observation['observed_utc'],
              'training_step': training['last_observed_step'],
              'terminal_training_verified': training['terminal_training_verified'],
              'native_identity_diagnostics': training['native_identity_diagnostics'],
              'final_transfer': training.get('final_transfer'),
              'cloud_cleanup': training.get('cloud_cleanup'),
              'training_live_at_observation': observation['process_live'],
              'file_baseline': local, 'generation_baseline': generation, 'delivery_prepared': True,
              'active_local_sessions': training['current_local_runs'],
              'epoch1_transfer_verified': training['epoch1_transfer_verified'],
              'epoch_artifact_stages': training['epoch_artifact_stages'],
              'epoch1_neutral_identity': training.get('epoch1_neutral_identity'),
              'neutral_identity_evaluations': training['neutral_identity_evaluations'],
              'epoch1_generation': training.get('epoch1_runtime_v2_generation'),
              'runtime_v2_evaluations': training['runtime_v2_evaluations'],
              'condition_recovery_candidate': training.get('condition_recovery_candidate'),
              'condition_recovery_production': training.get('condition_recovery_production'),
              'greedy_identity_diagnostic': training.get('greedy_identity_diagnostic'),
              'runtime_v3_prepared': training['runtime_v3_prepared'],
              'active_runtime_profile': training.get('active_runtime_profile', 'evaluation-runtime-v3'),
              'preservation_guidance': training.get('preservation_guidance'),
              'runtime_v4_evaluations': training.get('runtime_v4_evaluations'),
              'context_dedup': training.get('context_dedup'),
              'runtime_v5_evaluations': training.get('runtime_v5_evaluations'),
              'result_contracts': training.get('result_contracts'),
              'runtime_v6_evaluations': training.get('runtime_v6_evaluations'),
              'generation_context': training.get('generation_context'),
              'runtime_v7_evaluations': training.get('runtime_v7_evaluations'),
              'file_text_source_preflight': training.get('file_text_source_preflight'),
              'runtime_v8_evaluations': training.get('runtime_v8_evaluations'),
              'completion_diagnostics': training.get('completion_diagnostics'),
              'verification_contract_experiments': training.get('verification_contract_experiments'),
              'model_blob_repair': training.get('model_blob_repair'),
              'model_integrity_production': training.get('model_integrity_production'),
              'runtime_v9_evaluations': training.get('runtime_v9_evaluations'),
              'artifact_intent_v2': training.get('artifact_intent_v2'),
              'artifact_evidence_candidate': training.get('artifact_evidence_candidate'),
              'file_completion_views_candidate': training.get('file_completion_views_candidate'),
              'operation_obligations_candidate': training.get('operation_obligations_candidate'),
              'new_content_training_component': training.get('new_content_training_component'),
              'ui_composer': training.get('ui_composer'),
              'release_approved': False, 'scope': 'Current v13 only; older top-level master fields may describe historical runs.'}
    (R / 'CURRENT_STATUS.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__':
    main()
