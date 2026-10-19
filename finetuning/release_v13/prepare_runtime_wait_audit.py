"""Route the existing strict wait-order audit to runtime-v2 results."""
import ast
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    original = R / 'audit_full_loop_requirements.py'
    target = R / 'audit_full_loop_requirements_runtime_v2.py'
    raw = original.read_bytes()
    assert raw.count(b'evaluation-v1') == 1
    changed = raw.replace(b'evaluation-v1', b'evaluation-runtime-v2')
    with target.open('xb') as stream:
        stream.write(changed)
    before = next(n for n in ast.parse(raw).body if getattr(n, 'name', None) == 'wait_order')
    after = next(n for n in ast.parse(changed).body if getattr(n, 'name', None) == 'wait_order')
    assert ast.dump(before) == ast.dump(after)
    original_test = R / 'check_wait_order_audit.py'
    test = R / 'check_wait_order_audit_runtime_v2.py'
    test_source = original_test.read_bytes()
    assert test_source.count(b'from audit_full_loop_requirements import wait_order') == 1
    with test.open('xb') as stream:
        stream.write(test_source.replace(b'from audit_full_loop_requirements import wait_order',
                                        b'from audit_full_loop_requirements_runtime_v2 import wait_order'))
    report = {'original_audit_sha256': sha(original), 'runtime_v2_audit_sha256': sha(target),
              'original_controls_sha256': sha(original_test), 'runtime_v2_controls_sha256': sha(test),
              'wait_order_function_ast_identical': True, 'only_results_folder_and_test_import_changed': True,
              'model_results_audited': False, 'release_approved': False}
    with (R / 'evaluation-runtime-v2/WAIT_AUDIT_PREPARATION.json').open('x', encoding='utf8') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(report))


if __name__ == '__main__':
    main()
