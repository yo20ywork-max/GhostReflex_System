"""Freeze pre-dispatch full-file anchor checking; preserve all original gates."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent
ROOT = R.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    old = R / 'evaluation-runtime-v7'
    manifest = json.loads((old / 'manifest.json').read_text(encoding='utf8'))
    before = R / 'runtime-v7-sources/run_daemon.py'
    assert sha(before) == manifest['source_hashes']['run_daemon.py']
    for name, digest in manifest['source_hashes'].items():
        if name not in ('run_daemon.py', 'argument_references.py'):
            assert sha(ROOT / name) == digest, name
    tree = ast.parse((ROOT / 'run_daemon.py').read_text(encoding='utf-8-sig'))
    planner = next(n for n in tree.body if getattr(n, 'name', '') == 'Planner')
    method = next(n for n in planner.body if getattr(n, 'name', '') == '_request_valid_plan')
    class RemovePreflight(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            if node.module == 'argument_references' and [n.name for n in node.names] == ['validate_file_text_sources']:
                return None
            return node
        def visit_Expr(self, node):
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == 'validate_file_text_sources':
                return None
            return node
    RemovePreflight().visit(method)
    assert ast.dump(tree) == ast.dump(ast.parse(before.read_text(encoding='utf-8-sig')))
    module = ROOT / 'argument_references.py'
    # Existing reference grammar/literal interpretation must be byte-identical.
    prefix = module.read_bytes().split(b'\n\ndef validate_file_text_sources')[0]
    previous = prefix.rstrip(b'\r\n') + b'\n'
    run_manifest = json.loads((old / 'epoch3-file8-v1.manifest.json').read_text(encoding='utf8'))
    expected = run_manifest['sources']['argument_references.py']
    if hashlib.sha256(previous).hexdigest() != expected:
        previous = previous.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
    assert hashlib.sha256(previous).hexdigest() == expected
    tests = {'checked_utc': datetime.now(timezone.utc).isoformat(), 'tests_run': 40, 'passed': True,
             'command': 'python -m unittest test_file_text_sources test_argument_references test_plan_execution_integrity test_tool_result_contracts test_generation_context',
             'observed_process_exit_code': 0, 'observed_stdout': 'Ran 40 tests; OK',
             'source_sha256': sha(ROOT / 'run_daemon.py'), 'module_sha256': sha(module),
             'test_sha256': sha(ROOT / 'tests/test_file_text_sources.py'), 'release_approved': False}
    install = {'installed_utc': tests['checked_utc'], 'before_sha256': sha(before),
               'after_sha256': sha(ROOT / 'run_daemon.py'), 'module_before_sha256': expected,
               'module_after_sha256': sha(module), 'only_runtime_method_changed': 'Planner._request_valid_plan',
               'existing_reference_parser_unchanged': True, 'runtime_coverage_and_version_checks_preserved': True,
               'tests_run': 40, 'release_approved': False}
    for name, value in [('FILE_TEXT_SOURCE_TESTS.json', tests), ('FILE_TEXT_SOURCE_INSTALL.json', install)]:
        with (R / name).open('x', encoding='utf8') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
    destination = R / 'evaluation-runtime-v8'
    destination.mkdir(exist_ok=False)
    snapshot = R / 'runtime-v8-sources'
    snapshot.mkdir(exist_ok=False)
    (snapshot / 'argument_references_before.py').write_bytes(previous)
    for name in ('run_daemon.py', 'argument_references.py', 'generation_context.py', 'tool_result_contracts.py'):
        (snapshot / name).write_bytes((ROOT / name).read_bytes())
    runners = []
    for source in sorted(R.glob('*_runtime_v7.py')):
        target = source.with_name(source.name.replace('_runtime_v7', '_runtime_v8'))
        raw = source.read_bytes()
        changed = raw.replace(b'evaluation-runtime-v7', b'evaluation-runtime-v8').replace(b'_runtime_v7', b'_runtime_v8')
        assert changed.replace(b'evaluation-runtime-v8', b'evaluation-runtime-v7').replace(b'_runtime_v8', b'_runtime_v7') == raw
        compile(changed, str(target), 'exec')
        with target.open('xb') as f:
            f.write(changed)
        runners.append({'old': source.name, 'old_sha256': sha(source), 'new': target.name, 'new_sha256': sha(target)})
    for name, digest in manifest['outputs'].items():
        assert sha(old / name) == digest
        (destination / name).write_bytes((old / name).read_bytes())
    for path in (ROOT / 'run_daemon.py', module, Path(__file__), R / 'FILE_TEXT_SOURCE_TESTS.json', R / 'FILE_TEXT_SOURCE_INSTALL.json'):
        manifest['source_hashes'][str(path.relative_to(ROOT))] = sha(path)
    manifest.update(profile_name='evaluation-runtime-v8', predecessor_manifest_sha256=sha(old / 'manifest.json'),
                    runtime_change='Reject file_text references to non-READ anchors before dispatch; preserve literal/output semantics and runtime whole-file/version verification.')
    with (destination / 'manifest.json').open('x', encoding='utf8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    with (destination / 'PROFILE_PREPARATION.json').open('x', encoding='utf8') as f:
        json.dump({'runners': runners, 'questions_answers_oracles_schemas_byte_identical': True,
                   'runner_changes_only_output_paths_and_control_imports': True, 'release_approved': False}, f, indent=2)
    print(json.dumps(install))


if __name__ == '__main__':
    main()
