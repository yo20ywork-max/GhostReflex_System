"""Score completed locked development generation, keeping semantic review explicit."""
import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from jsonschema import Draft202012Validator

R = Path(__file__).resolve().parent
V3 = R.parent / 'release_v3'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--results', required=True)
    args = parser.parse_args()
    if Path(args.results).name != args.results:
        raise ValueError('Results must be a file name')
    result_path = R / args.results
    marker = json.loads(result_path.with_suffix('.generation-complete.json').read_text(encoding='utf8'))
    if not marker['model_and_sources_unchanged'] or marker['results_sha256'] != sha(result_path):
        raise ValueError('Unverified or changed generation results')
    lock = json.loads((R / 'DATA_LOCK.json').read_text(encoding='utf8'))
    for name in ('dev.jsonl', 'training-contract.json', 'runtime_source.py'):
        if sha(R / name) != lock['sha256'][name]:
            raise ValueError('Locked input changed')
    if sha(R.parents[1] / 'run_daemon.py') != sha(R / 'runtime_source.py'):
        raise ValueError('Runtime changed; preserve a separate comparison protocol')
    spec = importlib.util.spec_from_file_location('crossgen_v4_actual_validator', V3 / 'execute_plan_fixtures.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    scope, runtime_hash = module.load(str(R / 'training-contract.json'))
    contract = json.loads((R / 'training-contract.json').read_text(encoding='utf8'))
    validator = Draft202012Validator(contract['schema'])
    data = {r['id']: r for r in map(json.loads, (R / 'dev.jsonl').read_text(encoding='utf8').splitlines())}
    results = list(map(json.loads, result_path.read_text(encoding='utf8').splitlines()))
    if len(results) != len(data) or {r['id'] for r in results} != set(data):
        raise ValueError('Incomplete or duplicate results')
    records = []
    for result in results:
        row = data[result['id']]
        if result['prompt_sha256'] != hashlib.sha256((row['system'] + '\n' + row['prompt']).encode()).hexdigest():
            raise ValueError('Wrong prompt result')
        kind = row['oracle']['type']
        check = {'passed': None, 'reason': 'Requires semantic review'}
        try:
            if not result['completed']:
                raise ValueError('Generation incomplete')
            if kind == 'plan':
                value = json.loads(result['text'])
                validator.validate(value)
                history = json.loads(row['prompt']).get('replanning_context', {}).get('completed_and_failed_history', [])
                scope['validate_plan'](value, SimpleNamespace(max_plan_steps=contract['profile']['max_plan_steps'], default_tool_retries=0), 'candidate', {x['step_id'] for x in history})
                check = {'passed': None, 'schema_and_runtime_valid': True, 'reason': 'Needs semantic review and actual execution'}
            elif kind == 'completion':
                value = json.loads(result['text'])
                expected = row['oracle']['complete']
                valid = type(value.get('complete')) is bool and isinstance(value.get('reason'), str) and set(value) == {'reason', 'complete'}
                check = {'passed': valid and value['complete'] == expected, 'expected_complete': expected, 'assessed_complete': value.get('complete'),
                         'false_completion': valid and value['complete'] and not expected, 'false_incomplete': valid and not value['complete'] and expected}
            elif kind == 'code':
                code = result['text'].strip()
                match = re.fullmatch(r'```(?:python)?\s*\n(.*?)\n```', code, re.S)
                if match:
                    code = match.group(1)
                payload = {'code': code, 'function': row['oracle']['function'], 'tests': row['oracle']['tests']}
                process = subprocess.run([sys.executable, '-I', str(V3 / 'code_sandbox.py')], input=json.dumps(payload), text=True, encoding='utf8', capture_output=True, timeout=3)
                check = json.loads(process.stdout)
            elif kind == 'exact':
                check = {'passed': result['text'].strip() == row['oracle']['value'].strip(), 'reason': 'Exact diagnostic; equivalent wording requires separate semantic review'}
        except Exception as exc:
            check = {'passed': False, 'reason': str(exc)[:500]}
        records.append({'id': result['id'], 'category': result['category'], 'text_sha256': hashlib.sha256(result['text'].encode()).hexdigest(), **check})
    summary = {cat: {label: sum(x['category'] == cat and x['passed'] is val for x in records) for label, val in [('passed', True), ('failed', False), ('review', None)]} for cat in sorted({x['category'] for x in records})}
    report = {'release_approved': False, 'summary': summary, 'records': records, 'scorer_sha256': sha(Path(__file__)),
              'runtime_source_sha256': runtime_hash, 'results_sha256': sha(result_path), 'strict_code_sandbox_sha256': sha(V3 / 'code_sandbox.py'),
              'plan_loader_sha256': sha(V3 / 'execute_plan_fixtures.py'), 'scope': 'Original strict code evaluator; separate functional audit and semantic review remain required.'}
    with (R / (args.results + '.checks.json')).open('x', encoding='utf8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
