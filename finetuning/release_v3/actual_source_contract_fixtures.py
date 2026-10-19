"""Check frozen extracted contracts against real, bounded file/DOM observations.

Actions below are manually authored fixtures, NOT model-generated plans. No
native input, clipboard, network, shell, or non-fixture files are accessed.
"""
import argparse
import ast
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from playwright.sync_api import sync_playwright

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
sys.path.insert(0, str(ROOT))
from evidence_contract import check_contract
from source_contract import compile_source_contract
from execute_plan_fixtures import load


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--extractions', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    output = R / a.output
    if output.exists():
        raise FileExistsError(output)
    extraction_path = R / a.extractions
    generated = {x['id']: x for x in map(json.loads, extraction_path.read_text(encoding='utf8').splitlines())}
    cases = {x['id']: x for x in map(json.loads, (R / 'source-contract-new-dev.jsonl').read_text(encoding='utf8').splitlines())}
    catalog = json.loads((R / 'training-contract.json').read_text(encoding='utf8'))['catalog']
    scope, runtime_hash = load('training-contract.json')
    tree = ast.parse((ROOT / 'run_daemon.py').read_text(encoding='utf-8-sig'))
    append = next(x for x in tree.body if getattr(x, 'name', None) == 'tool_append_text_file')
    append.decorator_list = []
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), append], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), '<actual append fixture>', 'exec'), scope)
    supported = ('three_reads', 'actual_count', 'read_no_append', 'click_once', 'empty_directory')
    records = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            for case_id in supported:
                original = cases[case_id]['user_request']
                entry = generated[case_id]
                if entry['request'] != original:
                    raise ValueError('Extraction request mismatch')
                try:
                    compiled = compile_source_contract(original, entry['extracted'], catalog)
                except ValueError as exc:
                    records.append({'id': case_id, 'error': str(exc), 'correct': False, 'not_executed': True})
                    continue
                for positive in (True, False):
                    with tempfile.TemporaryDirectory(dir=R, prefix='source-actual-') as temporary:
                        work = Path(temporary).resolve()
                        if not work.is_relative_to(R.resolve()):
                            raise ValueError('Fixture escaped workspace')
                        page = browser.new_page()
                        page.set_default_timeout(2000)
                        adapter = scope['BrowserSession'].__new__(scope['BrowserSession'])
                        adapter.ensure = lambda: page
                        ctx = SimpleNamespace(settings=SimpleNamespace(workspace=work, allow_outside_workspace=False), runtime=SimpleNamespace(browser=adapter))
                        history = []

                        def call(tool, args):
                            handler = scope['tool_' + tool.lower()]
                            result = handler(ctx, **args)
                            history.append({'tool': tool, 'args': args, 'ok': result.ok, 'verified': result.verified,
                                            'output': result.output, 'error': result.error, 'evidence': result.evidence, 'terminal': result.terminal})
                            if not result.ok:
                                raise RuntimeError(result.error)

                        try:
                            if case_id == 'three_reads':
                                names = ['早班.txt', '午班.txt', '晚班.txt']
                                for name in names:
                                    (work / name).write_text(name + '內容', encoding='utf8')
                                for name in names if positive else [names[0], names[2], names[1]]:
                                    call('READ_TEXT_FILE', {'path': name})
                            elif case_id == 'actual_count':
                                folder = work / '製作/音軌'
                                folder.mkdir(parents=True)
                                for index in range(81):
                                    (folder / f'{index:03}.txt').write_text(str(index), encoding='utf8')
                                call('LIST_DIRECTORY', {'path': '製作/音軌', 'max_items': 72 if positive else 300})
                                if len(history[-1]['output']) != (72 if positive else 81):
                                    raise ValueError('Actual list fixture count mismatch')
                            elif case_id == 'read_no_append':
                                path = work / '企劃/開場白.txt'
                                path.parent.mkdir(parents=True)
                                path.write_text('開場原稿', encoding='utf8')
                                call('READ_TEXT_FILE', {'path': '企劃/開場白.txt'})
                                if not positive:
                                    call('APPEND_TEXT_FILE', {'path': '企劃/開場白.txt', 'content': '！'})
                                if path.read_text(encoding='utf8') != ('開場原稿' if positive else '開場原稿！'):
                                    raise ValueError('Actual file fixture content mismatch')
                            elif case_id == 'click_once':
                                page.set_content('<meta charset="utf-8"><button onclick="window.n=(window.n||0)+1">產生預檢</button>')
                                for _ in range(1 if positive else 2):
                                    call('BROWSER_CLICK', {'by': 'text', 'target': '產生預檢'})
                                if page.evaluate('window.n') != (1 if positive else 2):
                                    raise ValueError('Actual DOM click count mismatch')
                            elif case_id == 'empty_directory':
                                (work / '尚未匯入').mkdir()
                                (work / '已經匯入').mkdir()
                                call('LIST_DIRECTORY', {'path': '尚未匯入' if positive else '已經匯入'})
                            check = check_contract(original, compiled['contract'], history, [x['name'] for x in catalog])
                            records.append({'id': case_id, 'positive_fixture': positive, 'expected': positive,
                                            'correct': check['evidence_satisfied'] == positive,
                                            'false_completion': check['evidence_satisfied'] and not positive,
                                            'trace': history, 'check': check})
                        except Exception as exc:
                            records.append({'id': case_id, 'positive_fixture': positive, 'error': str(exc), 'correct': False, 'trace': history})
                        finally:
                            page.close()
        finally:
            browser.close()
    report = {'supported_requests': len(supported), 'total_development_requests': len(cases),
              'skipped_requests': sorted(set(cases) - set(supported)), 'correct': sum(x['correct'] for x in records),
              'expected_observation_cases': 2 * len(supported), 'false_completions': sum(x.get('false_completion', False) for x in records),
              'records': records, 'runtime_sha256': runtime_hash, 'extractor_output_sha256': hashlib.sha256(extraction_path.read_bytes()).hexdigest(),
              'fixture_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'compiler_sha256': hashlib.sha256((ROOT / 'source_contract.py').read_bytes()).hexdigest(),
              'checker_sha256': hashlib.sha256((ROOT / 'evidence_contract.py').read_bytes()).hexdigest(),
              'scope': 'Five explicitly supported manually authored file/DOM fixtures. Frozen model extractions checked against actual handler observations. Not generated plans, recovery loop, native/target hardware, or complete request coverage.',
              'product_release_approved': False}
    with output.open('x', encoding='utf8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != 'records'}), flush=True)


if __name__ == '__main__':
    main()
