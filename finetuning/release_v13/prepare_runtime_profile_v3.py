"""Separate post-recovery runtime evidence; preserve all questions and oracles."""
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


def main():
    installed = read(R / 'CONDITION_RECOVERY_INSTALL.json')
    assert installed['installed_in_product'] and installed['candidate_ast_matches_product']
    assert sha(ROOT / 'run_daemon.py') == installed['after_sha256']
    verified = read(R / 'CONDITION_RECOVERY_PRODUCTION_TESTS.json')
    assert verified['passed'] and verified['source_sha256'] == installed['after_sha256']
    old_folder = R / 'evaluation-runtime-v2'
    original = read(old_folder / 'manifest.json')
    for name, digest in original['source_hashes'].items():
        if name == 'run_daemon.py':
            assert digest == installed['before_sha256']
        else:
            assert sha(ROOT / name) == digest, name
    for name, digest in read(R / 'DATA_LOCK.json')['sha256'].items():
        assert sha(R / name) == digest, name
    names = ('evaluate_gateway', 'score_generation', 'evaluate_identity_independent',
             'run_full_loop', 'evaluate_file_tasks_text', 'check_file_fixture',
             'check_text_fixture', 'audit_full_loop_requirements', 'check_wait_order_audit')
    planned = []
    for name in names:
        source = R / f'{name}_runtime_v2.py'
        target = R / f'{name}_runtime_v3.py'
        assert not target.exists()
        raw = source.read_bytes()
        changed = raw.replace(b'evaluation-runtime-v2', b'evaluation-runtime-v3').replace(b'_runtime_v2', b'_runtime_v3')
        assert changed.replace(b'evaluation-runtime-v3', b'evaluation-runtime-v2').replace(b'_runtime_v3', b'_runtime_v2') == raw
        compile(changed, str(target), 'exec')
        planned.append((source, target, changed))
    destination = R / 'evaluation-runtime-v3'
    destination.mkdir(exist_ok=False)
    for name, digest in original['outputs'].items():
        assert sha(old_folder / name) == digest
        (destination / name).write_bytes((old_folder / name).read_bytes())
    for _, target, raw in planned:
        with target.open('xb') as f:
            f.write(raw)
    manifest = dict(original)
    manifest['source_hashes'] = dict(original['source_hashes'])
    manifest['source_hashes']['run_daemon.py'] = installed['after_sha256']
    for p in (Path(__file__), R / 'CONDITION_RECOVERY_INSTALL.json', R / 'CONDITION_RECOVERY_PRODUCTION_TESTS.json'):
        manifest['source_hashes'][str(p.relative_to(ROOT))] = sha(p)
    manifest.update(profile_name='evaluation-runtime-v3', profile_created_utc=datetime.now(timezone.utc).isoformat(),
                    predecessor_manifest_sha256=sha(old_folder / 'manifest.json'),
                    runtime_change='Only invalid-condition terminal policy permits explicit bounded retry/replan; actions stay blocked until valid.')
    assert {name: sha(destination / name) for name in original['outputs']} == original['outputs']
    with (destination / 'manifest.json').open('x', encoding='utf8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    record = {'runners': [{'old': s.name, 'old_sha256': sha(s), 'new': t.name, 'new_sha256': sha(t)} for s, t, _ in planned],
              'questions_answers_oracles_schemas_byte_identical': True,
              'runner_changes_only_output_paths_and_control_imports': True,
              'training_locked_inputs_unchanged': True, 'model_inference_started': False,
              'historical_outputs_rewritten': False, 'release_approved': False}
    with (destination / 'PROFILE_PREPARATION.json').open('x', encoding='utf8') as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in record.items() if k != 'runners'}))


if __name__ == '__main__':
    main()
