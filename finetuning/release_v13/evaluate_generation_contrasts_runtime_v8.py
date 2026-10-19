"""Known development synthesis contrasts for source-preservation guidance.

Use real planning, generation, file handlers and completion. Semantic review is
separate from filesystem/readback checks; this is not a replacement release gate.
"""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile
import time
from types import SimpleNamespace
import ollama
from file_fixture_text import Fixture
from evaluate_development import request
from text_reader import completed_file_contents

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
MODEL = 'crossgen-agi-mu:v13-e3-eval-20260907'
CASES = [
    {'id': 'summary', 'source': '會議資料.txt', 'destination': '摘要.txt', 'reply': '摘要完成',
     'text': '春季交流會於4月12日上午10點在三樓舉行。報名截止為4月5日。預算上限新臺幣兩萬元。聯絡人為小林。',
     'request': '讀取「會議資料.txt」，用台灣繁體中文摘要為三點，涵蓋活動時間地點、報名期限與預算。摘要存成新的「摘要.txt」，保留來源，讀回後回覆「摘要完成」。'},
    {'id': 'creative', 'source': '活動設定.txt', 'destination': '歡迎文案.txt', 'reply': '文案完成',
     'text': '活動主題是修復舊物，參與者是第一次參加的鄰居；語氣溫暖。',
     'request': '先讀「活動設定.txt」，依設定創作兩句台灣繁體中文歡迎詞，不要只是複製設定。存成新的「歡迎文案.txt」，保留來源，讀回後回覆「文案完成」。'},
    {'id': 'code', 'source': '函式需求.txt', 'destination': 'calculator.py', 'reply': '程式完成',
     'text': '用Python實作sum_even(values)，回傳values中所有偶數整數的總和；負偶數也要計入，空清單回傳0。不讀檔、不連網，不要頂層示範執行。',
     'request': '讀取「函式需求.txt」，依需求撰寫Python程式，存成新的「calculator.py」，檔案內只放可執行的Python原始碼，不要Markdown標記。保留需求檔，讀回後回覆「程式完成」。'},
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    folder = R / 'evaluation-runtime-v8'
    target = folder / 'epoch3-generation-contrasts-v1.jsonl'
    if target.exists() or target.with_suffix('.manifest.json').exists():
        raise FileExistsError('Never overwrite previous contrast results')
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf8'))
    sources = dict(manifest['source_hashes'])
    for p in (Path(__file__), R / 'file_fixture_text.py', R / 'file_fixture.py', R.parent / 'release_v4/file_flow.py'):
        sources[str(p.relative_to(ROOT))] = sha(p)
    assert all(sha(ROOT / p) == h for p, h in sources.items())
    model = next(m for m in request('/api/tags')['models'] if m['name'] == MODEL)
    tree = ast.parse((ROOT / 'run_daemon.py').read_text(encoding='utf-8-sig'))
    nodes = [n for n in tree.body if getattr(n, 'name', '') in ('OllamaGateway', 'extract_json_object')]
    scope = {'ollama': ollama, 'json': json, 're': re}
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), *nodes], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), '<actual product gateway>', 'exec'), scope)
    actual = scope['OllamaGateway'](SimpleNamespace(planner_models=(MODEL,), planner_num_ctx=12288))
    calls = []
    def sent(req):
        calls.append({'request': json.loads(req.content)})
    def received(resp):
        resp.read()
        calls[-1]['response'] = resp.json()
    actual.client._client.event_hooks['request'].append(sent)
    actual.client._client.event_hooks['response'].append(received)
    with target.with_suffix('.manifest.json').open('x', encoding='utf8') as f:
        json.dump({'started_utc': datetime.now(timezone.utc).isoformat(), 'model': model,
                   'sources': sources, 'cases': CASES, 'known_development': True,
                   'semantic_review_required': True, 'release_approved': False}, f, ensure_ascii=False, indent=2)
    records = []
    try:
        with target.open('x', encoding='utf8') as out:
            for case in CASES:
                calls.clear()
                began = time.monotonic()
                class BoundedGateway:
                    def chat_json(self, **kw):
                        if len(calls) >= 12 or time.monotonic() - began > 240:
                            raise RuntimeError('Contrast inference budget exhausted')
                        return actual.chat_json(**{**kw, 'models': (MODEL,)})
                    def chat_text(self, **kw):
                        if len(calls) >= 12 or time.monotonic() - began > 240:
                            raise RuntimeError('Contrast inference budget exhausted')
                        return actual.chat_text(**{**kw, 'models': (MODEL,)})
                row = {'id': 'synthesis-' + case['id'], 'user_request': case['request'],
                       'initial_files': {case['source']: case['text']},
                       'write_targets': {case['destination']: ['WRITE_TEXT_FILE']}}
                with tempfile.TemporaryDirectory(dir=R, prefix='.synthesis-contrast-') as temp:
                    fixture = Fixture(row, temp, MODEL, BoundedGateway())
                    try:
                        result, _, _ = fixture.run(MODEL, fixture.agent.gateway)
                        dest = fixture.work / case['destination']
                        generated = dest.read_bytes() if dest.is_file() else None
                        source_ok = (fixture.work / case['source']).read_bytes() == case['text'].encode()
                        writes = [i for i, h in enumerate(result.history) if h['tool'] == 'WRITE_TEXT_FILE' and h['ok']]
                        before_write = completed_file_contents(result.history[:writes[0]]) if writes else {}
                        observed_source = before_write.get(str((fixture.work / case['source']).resolve()))
                        source_read = observed_source is not None and observed_source['text'] == case['text']
                        read_after = completed_file_contents(result.history[writes[-1]+1:]) if writes else {}
                        readback = read_after.get(str(dest.resolve()))
                        readback_ok = generated is not None and readback is not None and readback['text'].encode() == generated
                        actual_files = {p.relative_to(fixture.work).as_posix() for p in fixture.work.rglob('*') if p.is_file()}
                        model_generated = any(h['tool'] == 'MODEL_GENERATE' and h['ok'] for h in result.history)
                        mechanical = source_ok and source_read and readback_ok and len(writes) == 1 and model_generated and actual_files == {case['source'], case['destination']} and result.status == 'completed' and result.message == case['reply']
                        record = {'id': case['id'], 'status': result.status, 'message': result.message,
                                  'mechanical_passed': mechanical, 'semantic_passed': None,
                                  'source_unchanged': source_ok, 'full_post_write_readback': readback_ok,
                                  'source_read_before_write': source_read,
                                  'model_generation_executed': model_generated,
                                  'output_text': generated.decode('utf8') if generated is not None else None,
                                  'history': result.history, 'trace': fixture.trace, 'calls': list(calls),
                                  'seconds': time.monotonic() - began}
                    finally:
                        fixture.close()
                records.append(record)
                out.write(json.dumps(record, ensure_ascii=False) + '\n'); out.flush()
                print(json.dumps({k: v for k, v in record.items() if k not in ('history', 'trace', 'calls', 'output_text')}, ensure_ascii=False), flush=True)
    finally:
        actual.close()
    stable = all(sha(ROOT / p) == h for p, h in sources.items())
    stable = stable and next(m for m in request('/api/tags')['models'] if m['name'] == MODEL)['digest'] == model['digest']
    report = {'total': len(records), 'mechanical_passed': sum(r['mechanical_passed'] for r in records),
              'source_and_model_unchanged': stable, 'results_sha256': sha(target),
              'semantic_review_pending': True, 'release_approved': False}
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as f:
        json.dump(report, f, indent=2)
    assert stable
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
