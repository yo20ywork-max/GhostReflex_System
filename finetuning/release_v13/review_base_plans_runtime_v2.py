"""Reparse fresh base plans; reuse intent review only for byte-identical plans."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

R = Path(__file__).resolve().parent
P = R / 'evaluation-runtime-v2'
OLD = R.parent / 'release_v12/evaluation-v1'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def index(path):
    return {r['id']: r for r in map(json.loads, path.read_text(encoding='utf8').splitlines())}


def main():
    source = P / 'base-gateway-v1.jsonl'
    completed = read(source.with_suffix('.generation-complete.json'))
    assert completed['results_sha256'] == sha(source) and completed['model_and_sources_unchanged']
    current, previous, cases = index(source), index(OLD / 'base-gateway-v1.jsonl'), index(P / 'cases.jsonl')
    old = read(OLD / 'base-gateway-v1.plan-review.json')
    assert old['results_sha256'] == sha(OLD / 'base-gateway-v1.jsonl')
    assert (P / 'cases.jsonl').read_bytes() == (OLD / 'cases.jsonl').read_bytes()
    original = R.parent / 'release_v4/execute_full_plan_fixtures.py'
    spec = importlib.util.spec_from_file_location('plan_parser_review_v13', original)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    scope, _ = module.load(str((R / 'training-contract.json').resolve()))
    settings = SimpleNamespace(max_plan_steps=24, default_tool_retries=0)
    records = []
    for decision in old['records']:
        id_ = decision['id']
        row, old_row, case = current[id_], previous[id_], cases[id_]
        assert row['text'] == old_row['text'] and row['prompt_sha256'] == old_row['prompt_sha256']
        assert decision['text_sha256'] == hashlib.sha256(row['text'].encode()).hexdigest()
        history = json.loads(case['prompt']).get('replanning_context', {}).get('completed_and_failed_history', [])
        try:
            scope['validate_plan'](json.loads(row['text']), settings, 'review', {h['step_id'] for h in history})
            accepted, error = True, None
        except Exception as exc:
            accepted, error = False, str(exc)
        records.append({**decision, 'parser_accepted': accepted, 'parser_error': error,
                        'planning_passed': accepted and decision['semantic_plan_passed'],
                        'intent_review_basis': 'Identical current prompt/system and plan text to preserved whole-plan review',
                        'actual_action_passed': None})
    assert len(records) == 15
    report = {'records': records, 'total': 15, 'parser_accepted': sum(r['parser_accepted'] for r in records),
              'planning_passed': sum(r['planning_passed'] for r in records), 'results_sha256': sha(source),
              'previous_plan_review_sha256': sha(OLD / 'base-gateway-v1.plan-review.json'),
              'review_script_sha256': sha(Path(__file__)), 'not_actual_action_acceptance': True,
              'reviewer': 'Codex whole-plan review reuse with fresh current parser; known development',
              'release_approved': False}
    with (P / 'base-gateway-v1.plan-review.json').open('x', encoding='utf8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != 'records'}))


if __name__ == '__main__':
    main()
