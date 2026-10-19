"""Record the completed condition-diagnostic checks and generation boundary."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent
ROOT = R.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nodes(path):
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    return {n.name: ast.dump(n) for n in tree.body
            if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in ('OllamaGateway', 'extract_json_object')}


def main():
    run_path = R / 'evaluation-runtime-v2/base-gateway-v1.manifest.json'
    run = json.loads(run_path.read_text(encoding='utf8'))
    assert all(sha(ROOT / name) == digest for name, digest in run['sources'].items())
    assert all('step_conditions.py' not in name for name in run['sources'])
    assert nodes(ROOT / 'run_daemon.py') == nodes(R / 'runtime_source.py')
    lock = json.loads((R / 'DATA_LOCK.json').read_text(encoding='utf8'))
    assert all(sha(R / name) == digest for name, digest in lock['sha256'].items())
    record = {'recorded_utc': datetime.now(timezone.utc).isoformat(),
              'before_sha256': sha(R / 'runtime-v2-sources/step_conditions_before.py'),
              'after_sha256': sha(ROOT / 'step_conditions.py'),
              'test_command': 'PYTHONPATH=tests C:/Python312/python.exe -X utf8 -m unittest tests.test_step_conditions tests.test_argument_references',
              'observed_exit_code': 0, 'observed_tests': 18, 'observed_seconds': 1.330,
              'test_sources': {name: sha(ROOT / 'tests' / name) for name in
                               ('test_step_conditions.py', 'test_argument_references.py')},
              'change': 'Explain actual condition source type, requested-field type and existing boolean field names without copying document values.',
              'missing_or_non_boolean_fields_still_rejected': True,
              'active_generation_sources_unchanged': True,
              'gateway_and_json_extractor_ast_unchanged': True,
              'training_locked_inputs_unchanged': True,
              'actual_model_repair_success_measured': False,
              'future_full_loop_sources_include_condition_module': True,
              'installed_in_product': True, 'release_approved': False}
    with (R / 'CONDITION_DIAGNOSTICS.json').open('x', encoding='utf8') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
    print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__':
    main()
