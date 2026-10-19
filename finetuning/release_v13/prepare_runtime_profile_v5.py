"""Bind lossless context dedup to unchanged development questions and oracles."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent
ROOT = R.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    withdrawal = json.loads((R / 'PRESERVATION_GUIDANCE_WITHDRAWAL.json').read_text(encoding='utf8'))
    tests = json.loads((R / 'CONTEXT_DEDUP_TESTS.json').read_text(encoding='utf8'))
    assert tests['passed'] and tests['runtime_sha256'] == sha(ROOT / 'run_daemon.py')
    assert tests['module_sha256'] == sha(ROOT / 'model_context.py')
    before = R / 'runtime-v4-sources/runtime_before.py'
    assert sha(before) == withdrawal['after_sha256']
    old = R / 'evaluation-runtime-v4'
    manifest = json.loads((old / 'manifest.json').read_text(encoding='utf8'))
    for name, digest in manifest['source_hashes'].items():
        if name != 'run_daemon.py':
            assert sha(ROOT / name) == digest, name
    lock = json.loads((R / 'DATA_LOCK.json').read_text(encoding='utf8'))
    for name, digest in lock['sha256'].items():
        assert sha(R / name) == digest, name
    destination = R / 'evaluation-runtime-v5'
    destination.mkdir(exist_ok=False)
    names = ('evaluate_gateway', 'score_generation', 'evaluate_identity_independent',
             'run_full_loop', 'evaluate_file_tasks_text', 'check_file_fixture',
             'check_text_fixture', 'audit_full_loop_requirements', 'check_wait_order_audit')
    runners = []
    for name in names:
        source = R / f'{name}_runtime_v4.py'
        target = R / f'{name}_runtime_v5.py'
        raw = source.read_bytes()
        changed = raw.replace(b'evaluation-runtime-v4', b'evaluation-runtime-v5').replace(b'_runtime_v4', b'_runtime_v5')
        assert changed.replace(b'evaluation-runtime-v5', b'evaluation-runtime-v4').replace(b'_runtime_v5', b'_runtime_v4') == raw
        compile(changed, str(target), 'exec')
        with target.open('xb') as f:
            f.write(changed)
        runners.append({'old': source.name, 'old_sha256': sha(source), 'new': target.name, 'new_sha256': sha(target)})
    for name, digest in manifest['outputs'].items():
        assert sha(old / name) == digest
        (destination / name).write_bytes((old / name).read_bytes())
    install = {'installed_utc': datetime.now(timezone.utc).isoformat(),
               'before_sha256': sha(before), 'after_sha256': sha(ROOT / 'run_daemon.py'),
               'module_sha256': sha(ROOT / 'model_context.py'),
               'guidance_withdrawn': True, 'execution_history_unchanged': True,
               'repeated_text_exact_roundtrip': True, 'release_approved': False}
    with (R / 'CONTEXT_DEDUP_INSTALL.json').open('x', encoding='utf8') as f:
        json.dump(install, f, ensure_ascii=False, indent=2)
    snapshot = R / 'runtime-v5-sources'
    snapshot.mkdir(exist_ok=False)
    for name in ('run_daemon.py', 'model_context.py', 'model_json.py'):
        (snapshot / name).write_bytes((ROOT / name).read_bytes())
    manifest['source_hashes']['run_daemon.py'] = sha(ROOT / 'run_daemon.py')
    for p in (ROOT / 'model_context.py', ROOT / 'model_json.py', Path(__file__),
              R / 'CONTEXT_DEDUP_INSTALL.json', R / 'CONTEXT_DEDUP_TESTS.json',
              R / 'PRESERVATION_GUIDANCE_WITHDRAWAL.json'):
        manifest['source_hashes'][str(p.relative_to(ROOT))] = sha(p)
    manifest.update(profile_name='evaluation-runtime-v5',
                    predecessor_manifest_sha256=sha(old / 'manifest.json'),
                    runtime_change='Withdraw item15 guidance; deduplicate identical long text in planner/checker JSON while retaining exact original payload and execution state. Unicode encoder unchanged.')
    with (destination / 'manifest.json').open('x', encoding='utf8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    with (destination / 'PROFILE_PREPARATION.json').open('x', encoding='utf8') as f:
        json.dump({'runners': runners, 'questions_answers_oracles_schemas_byte_identical': True,
                   'runner_changes_only_output_paths_and_control_imports': True,
                   'model_json_and_model_context_dependencies_bound': True,
                   'training_locked_inputs_unchanged': True, 'release_approved': False}, f, indent=2)
    print(json.dumps(install))


if __name__ == '__main__':
    main()
