"""Fresh whole-plan E3 review, retaining the original semantic requirements."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

R = Path(__file__).resolve().parent
P = R / 'evaluation-runtime-v2'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def index(path):
    return {r['id']: r for r in map(json.loads, path.read_text(encoding='utf8').splitlines())}


def main():
    source = P / 'epoch3-gateway-v1.jsonl'
    complete = json.loads(source.with_suffix('.generation-complete.json').read_text(encoding='utf8'))
    assert complete['model_and_sources_unchanged'] and complete['complete_generations'] == 176
    assert complete['results_sha256'] == sha(source)
    current, cases = index(source), index(P / 'cases.jsonl')
    original = R.parent / 'release_v4/execute_full_plan_fixtures.py'
    spec = importlib.util.spec_from_file_location('plan_parser_review_e3_v13', original)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    scope, _ = module.load(str((R / 'training-contract.json').resolve()))
    settings = SimpleNamespace(max_plan_steps=24, default_tool_retries=0)
    decisions = {
        'filled-continue': (True, '重試精確文字預覽按鈕，保留已填寫成果，沒有正式送出。'),
        'wait-disappear': (False, '把可見文字猜成CSS ID；不存在元素的hidden等待不能證明指定文字消失。'),
        'open-path': (True, 'OPEN_APP保留完整指定路徑與系統預設程式開啟意圖，不改為貼到聊天。'),
        'download-resume': (True, '只接續讀回歷史中已下載成功的指定目的檔，沒有重複下載或覆寫。'),
        'no-delete': (True, '只列出指定子目錄當層並限制72筆，沒有執行已取消的刪除。'),
    }
    records = []
    for id_, case in cases.items():
        if case['oracle']['type'] != 'plan':
            continue
        kind = next(k for k in decisions if id_.startswith('v2-dev-' + k + '-'))
        passed, reason = decisions[kind]
        row = current[id_]
        history = json.loads(case['prompt']).get('replanning_context', {}).get('completed_and_failed_history', [])
        try:
            scope['validate_plan'](json.loads(row['text']), settings, 'review', {h['step_id'] for h in history})
            accepted, error = True, None
        except Exception as exc:
            accepted, error = False, str(exc)
        records.append({'id': id_, 'parser_accepted': accepted, 'parser_error': error,
                        'semantic_plan_passed': passed, 'planning_passed': passed and accepted,
                        'reason': reason, 'text_sha256': hashlib.sha256(row['text'].encode()).hexdigest(),
                        'actual_action_passed': None,
                        'intent_review_basis': 'Fresh whole-plan review against preserved request, observations and history'})
    assert len(records) == 15
    report = {'records': records, 'total': 15, 'parser_accepted': sum(r['parser_accepted'] for r in records),
              'planning_passed': sum(r['planning_passed'] for r in records), 'results_sha256': sha(source),
              'review_script_sha256': sha(Path(__file__)), 'parser_loader_sha256': sha(original),
              'not_actual_action_acceptance': True, 'reviewer': 'Codex fresh whole-plan review of all15; known development',
              'original_requirements_preserved': True, 'final_holdout_opened': False, 'release_approved': False}
    with source.with_suffix('.plan-review.json').open('x', encoding='utf8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != 'records'}))


if __name__ == '__main__':
    main()
