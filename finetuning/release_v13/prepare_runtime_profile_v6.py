"""Freeze result-contract preflight with all existing questions/oracles retained."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent
ROOT = R.parents[1]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    old = R / 'evaluation-runtime-v5'
    manifest = json.loads((old / 'manifest.json').read_text(encoding='utf8'))
    tests = json.loads((R / 'RESULT_CONTRACT_TESTS.json').read_text(encoding='utf8'))
    assert tests['passed'] and tests['source_sha256'] == sha(ROOT / 'run_daemon.py')
    assert tests['module_sha256'] == sha(ROOT / 'tool_result_contracts.py')
    before = R / 'runtime-v5-sources/run_daemon.py'
    assert sha(before) == manifest['source_hashes']['run_daemon.py']
    for name, digest in manifest['source_hashes'].items():
        if name != 'run_daemon.py':
            assert sha(ROOT / name) == digest, name
    lock = json.loads((R / 'DATA_LOCK.json').read_text(encoding='utf8'))
    for name, digest in lock['sha256'].items():
        assert sha(R / name) == digest, name
    def strip(source):
        tree = ast.parse(source.read_text(encoding='utf-8-sig'))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == 'Planner':
                node.body = [n for n in node.body if getattr(n, 'name', '') not in ('_system_prompt', '_request_valid_plan')]
        return ast.dump(tree, include_attributes=False)
    assert strip(before) == strip(ROOT / 'run_daemon.py')
    install = {'installed_utc': datetime.now(timezone.utc).isoformat(),
               'before_sha256': sha(before), 'after_sha256': sha(ROOT / 'run_daemon.py'),
               'module_sha256': sha(ROOT / 'tool_result_contracts.py'),
               'only_runtime_methods_changed': ['Planner._system_prompt', 'Planner._request_valid_plan'],
               'executor_handlers_and_context_dedup_unchanged': True,
               'tests_run': tests['tests_run'], 'release_approved': False}
    with (R / 'RESULT_CONTRACT_INSTALL.json').open('x', encoding='utf8') as f:
        json.dump(install, f, ensure_ascii=False, indent=2)
    destination = R / 'evaluation-runtime-v6'
    destination.mkdir(exist_ok=False)
    snapshot = R / 'runtime-v6-sources'
    snapshot.mkdir(exist_ok=False)
    for name in ('run_daemon.py', 'tool_result_contracts.py', 'step_conditions.py', 'model_context.py', 'model_json.py'):
        (snapshot / name).write_bytes((ROOT / name).read_bytes())
    names = ('evaluate_gateway', 'score_generation', 'evaluate_identity_independent',
             'run_full_loop', 'evaluate_file_tasks_text', 'check_file_fixture',
             'check_text_fixture', 'audit_full_loop_requirements', 'check_wait_order_audit')
    runners = []
    for name in names:
        source, target = R / f'{name}_runtime_v5.py', R / f'{name}_runtime_v6.py'
        raw = source.read_bytes()
        changed = raw.replace(b'evaluation-runtime-v5', b'evaluation-runtime-v6').replace(b'_runtime_v5', b'_runtime_v6')
        assert changed.replace(b'evaluation-runtime-v6', b'evaluation-runtime-v5').replace(b'_runtime_v6', b'_runtime_v5') == raw
        compile(changed, str(target), 'exec')
        with target.open('xb') as f:
            f.write(changed)
        runners.append({'old': source.name, 'old_sha256': sha(source), 'new': target.name, 'new_sha256': sha(target)})
    for name, digest in manifest['outputs'].items():
        assert sha(old / name) == digest
        (destination / name).write_bytes((old / name).read_bytes())
    manifest['source_hashes']['run_daemon.py'] = sha(ROOT / 'run_daemon.py')
    for p in (ROOT / 'tool_result_contracts.py', Path(__file__), R / 'RESULT_CONTRACT_INSTALL.json', R / 'RESULT_CONTRACT_TESTS.json'):
        manifest['source_hashes'][str(p.relative_to(ROOT))] = sha(p)
    manifest.update(profile_name='evaluation-runtime-v6', predecessor_manifest_sha256=sha(old / 'manifest.json'),
                    runtime_change='Advertise possible boolean result fields; reject impossible/untrusted conditions before dispatch without rewriting predicates. Unknown tool results remain checked at runtime.')
    with (destination / 'manifest.json').open('x', encoding='utf8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    with (destination / 'PROFILE_PREPARATION.json').open('x', encoding='utf8') as f:
        json.dump({'runners': runners, 'questions_answers_oracles_schemas_byte_identical': True,
                   'runner_changes_only_output_paths_and_control_imports': True,
                   'training_locked_inputs_unchanged': True, 'release_approved': False}, f, indent=2)
    print(json.dumps(install))


if __name__ == '__main__':
    main()
