"""Validate authored waits against real local DOM transitions and wrong targets."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from playwright.sync_api import sync_playwright

R = Path(__file__).resolve().parent
ROOT = R.parents[1]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    folder = R / 'action-additions-v1'
    output = folder / 'BROWSER_EXECUTION_CONTROLS.json'
    if output.exists():
        raise FileExistsError(output)
    data = folder / 'additions.jsonl'
    assert sha(data) == json.loads((folder / 'PREPARATION.json').read_text(encoding='utf8'))['data_sha256']
    parser_path = R.parent / 'release_v4/execute_full_plan_fixtures.py'
    spec = importlib.util.spec_from_file_location('actual_browser_handlers', parser_path)
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)
    scope, source_hash = parser.load(str((R.parent / 'release_v12/training-contract.json').resolve()))
    rows = [r for r in map(json.loads, data.read_text(encoding='utf8').splitlines()) if '-wait-' in r['id']]
    records = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            for row in rows:
                payload, plan = json.loads(row['prompt']), json.loads(row['answer'])
                waiting, read = [s['args'] for s in plan['steps']]
                for wrong_target in (False, True):
                    page = browser.new_page()
                    try:
                        adapter = scope['BrowserSession'].__new__(scope['BrowserSession'])
                        adapter.ensure = lambda: page
                        ctx = SimpleNamespace(runtime=SimpleNamespace(browser=adapter))
                        page.set_content('<meta charset="utf-8"><div id="busy-control"></div><div id="result-control"></div>')
                        page.evaluate('''cfg => {
                          const busy = document.querySelector('#busy-control');
                          const result = document.querySelector('#result-control');
                          busy.id = cfg.busyId; busy.textContent = cfg.text;
                          result.id = cfg.resultId; window.transitionDone = false;
                          setTimeout(() => { busy.remove(); result.textContent = cfg.expected;
                            window.transitionDone = true; }, 800);
                        }''', {'busyId': waiting['target'][1:] if waiting['by'] == 'css' else 'busy-control',
                               'text': payload['runtime_context']['observed_texts'][0],
                               'resultId': read['target'][1:], 'expected': row['id'] + '成功'})
                        args = dict(waiting)
                        if wrong_target:
                            args.update(by='css', target='#nonexistent-control')
                        wait_result = scope['tool_browser_wait_for'](ctx, **args)
                        transition_seen = page.evaluate('window.transitionDone')
                        result = scope['tool_browser_get_text'](ctx, **read)
                        assert wait_result.ok and wait_result.verified
                        if wrong_target:
                            assert transition_seen is False and result.output == '', row['id']
                        else:
                            assert transition_seen is True and result.ok and result.verified
                            assert result.output == row['id'] + '成功', row['id']
                        records.append({'id': row['id'], 'wrong_target_control': wrong_target,
                                        'passed': True, 'wait_returned_success': wait_result.ok,
                                        'actual_transition_seen_before_read': transition_seen,
                                        'read_output': result.output})
                    finally:
                        page.close()
        finally:
            browser.close()
    assert len(records) == 16
    report = {'positive_controls': 8, 'wrong_target_controls': 8, 'all_passed': True,
              'records': records, 'data_sha256': sha(data), 'checker_sha256': sha(Path(__file__)),
              'production_source_sha256': source_hash, 'loader_sha256': sha(parser_path),
              'model_generated': False, 'uses_local_dom_only': True,
              'scope': 'Actual wait/read handlers; does not prove a generated agent plan or total task latency.',
              'training_ready': False, 'release_approved': False}
    with output.open('x', encoding='utf8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != 'records'}))


if __name__ == '__main__':
    main()
