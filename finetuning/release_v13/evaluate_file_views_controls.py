"""New positive/negative file-view controls, with real bounded fixture I/O.

These are authored development controls, not autonomous task or holdout results.
Original requests and path metadata alone feed the artifact compiler. Expected
labels and construction choices are never included in model-facing payloads.
"""
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import time

from evaluate_development import request
from model_context import dumps
from tests import test_artifact_evidence_candidate as fixtures

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
P = R / 'runtime-candidate/file_completion_views.py'
spec = importlib.util.spec_from_file_location('file_view_controls', P)
views = importlib.util.module_from_spec(spec)
spec.loader.exec_module(views)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cases():
    meeting = '夏日說明會於6月18日下午2點在四樓舉行。報名截止為6月10日。預算上限新臺幣三萬元。'
    summary = '1. 夏日說明會於6月18日下午2點在四樓舉行。\n2. 報名截止為6月10日。\n3. 預算上限新臺幣三萬元。'
    summary_prompt = '讀「來源.txt」，整理三點台灣繁體中文摘要，涵蓋時間地點、報名期限與預算，存為新的「結果.txt」。不要修改來源，讀回結果後回覆「整理完成」。'
    return [
        {'case': 'correct_creative', 'prompt': '讀「來源.txt」，依活動設定寫兩句溫暖的台灣繁體中文歡迎詞，存為新的「結果.txt」。保留來源，讀回後回覆「文案完成」。',
         'source': '活動是修復舊物，參加者是初次來訪的鄰居。',
         'output': '歡迎第一次來訪的鄰居，一起動手修復承載回憶的舊物。讓我們在互相幫忙中認識彼此，把溫暖帶回家。', 'reply': '文案完成', 'expected': True},
        {'case': 'correct_summary', 'prompt': summary_prompt, 'source': meeting, 'output': summary, 'reply': '整理完成', 'expected': True},
        {'case': 'wrong_summary_date', 'prompt': summary_prompt, 'source': meeting, 'output': summary.replace('6月18日', '6月19日'), 'reply': '整理完成', 'expected': False},
        {'case': 'summary_without_readback', 'prompt': summary_prompt, 'source': meeting, 'output': summary, 'reply': '整理完成', 'omit_readback': True, 'expected': False},
        {'case': 'legitimate_status_translation', 'prompt': '讀「來源.txt」，把其中的句子翻成英文，存為新的「結果.txt」。保留來源並讀回結果，最後回覆「翻譯完成」。',
         'source': '尚未讀回。', 'output': 'It has not been read back yet.', 'reply': '翻譯完成', 'expected': True},
        {'case': 'correct_python_function', 'prompt': '讀「來源.txt」，依規格產生 Python 程式，將純程式碼存為新的「結果.txt」。保留來源，讀回後回覆「程式完成」。',
         'source': '實作 add(a, b) 函式，輸入兩個整數，回傳它們的和。', 'output': 'def add(a, b):\n    return a + b\n', 'reply': '程式完成', 'expected': True},
        {'case': 'source_overwritten_before_copy', 'prompt': '把「來源.txt」原樣備份成新的「結果.txt」。不要修改來源，讀回核對後回覆「備份完成」。',
         'source': '原始內容', 'overwrite_source': '被修改後的內容', 'copy': True, 'reply': '備份完成', 'expected': False},
        {'case': 'wrong_exact_reply', 'prompt': '把「來源.txt」原樣備份成新的「結果.txt」。不要修改來源，讀回核對後回覆「備份完成」。',
         'source': '原始內容', 'copy': True, 'reply': '備份完程', 'expected': False},
    ]


def main():
    target = R / 'FILE_VIEWS_CONTROLS_V1.jsonl'
    assert not target.exists() and not target.with_suffix('.run.json').exists()
    name = 'crossgen-agi-mu:v13-e3-eval-20260907'
    model = next(m for m in request('/api/tags')['models'] if m['name'] == name)
    assert model['digest'] == '1ce8866b022460b87b876994991f13c695ad3b35ee887b23c962602df953fe81'
    sources = {str(p): sha(p) for p in [Path(__file__), P,
        P.with_name('artifact_evidence.py'), P.with_name('artifact_intent_contract_v2.py'),
        P.with_name('artifact_intent_contract.py'), P.with_name('exact_text_relation.py'),
        ROOT / 'tests/test_artifact_evidence_candidate.py', ROOT / 'verified_copy.py', ROOT / 'text_reader.py',
        ROOT / 'model_context.py', ROOT / 'model_json.py', ROOT / 'finetuning/release_v4/evaluate_development.py']}
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump({'started_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources, 'model': model,
                   'authored_development_controls': True, 'real_fixture_io': True, 'autonomous_planning_test': False,
                   'expected_labels_and_construction_not_sent_to_model': True,
                   'candidate_installed': False, 'release_approved': False}, f, indent=2)
    results = []
    with target.open('x', encoding='utf8') as out, target.with_suffix('.raw.jsonl').open('x', encoding='utf8') as raw:
        def chat(label, role, system, context, schema):
            payload = {'model': name, 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': dumps(context)}],
                'format': schema, 'stream': False, 'truncate': False, 'shift': False,
                'options': {'temperature': 0, 'num_ctx': 12288, 'num_predict': 2048, 'repeat_penalty': 1.0}}
            begin = time.monotonic()
            response = request('/api/chat', payload)
            elapsed = time.monotonic() - begin
            raw.write(json.dumps({'case': label, 'role': role, 'request': payload, 'response': response, 'seconds': elapsed}, ensure_ascii=False) + '\n'); raw.flush()
            if response.get('done') is not True or response.get('done_reason') != 'stop':
                raise ValueError('Incomplete generation cannot be a semantic verdict')
            value = json.loads(response['message']['content'])
            print(json.dumps({'case': label, 'role': role, 'value': value, 'seconds': elapsed}, ensure_ascii=False), flush=True)
            return value, elapsed

        for case in cases():
            fixture = fixtures.ArtifactEvidence()
            fixture.setUp()
            record = {'case': case['case'], 'prompt': case['prompt'], 'expected_complete': case['expected'], 'valid': False, 'correct': False}
            try:
                fixture.source('來源.txt', case['source'])
                if 'overwrite_source' in case:
                    fixture.write('來源.txt', case['overwrite_source'], overwrite=True)
                if case.get('copy'):
                    fixture.copied('來源.txt', '結果.txt')
                else:
                    fixture.read('來源.txt')
                    fixture.write('結果.txt', case['output'])
                    if not case.get('omit_readback'):
                        fixture.read('結果.txt')
                fixture.event('FINAL_RESPONSE', {'message': case['reply']}, case['reply'])
                record['history'] = copy.deepcopy(fixture.history)
                record['final_file_sha256'] = {n: sha(fixture.work / n) for n in ['來源.txt', '結果.txt']}
                catalog = views.evidence.catalog_from_history(fixture.history)
                value, elapsed = chat(case['case'], 'compile', views.evidence.intent.SYSTEM,
                    {'user_request': case['prompt'], 'files': catalog}, views.evidence.intent.schema(catalog))
                record['artifact_compilation'] = value
                prepared = views.build(value, case['prompt'], fixture.history)
                roles = (['content'] if prepared['content']['semantic_artifacts'] else []) + ['operations', 'delivery']
                verdicts = {}
                for role in roles:
                    verdict, duration = chat(case['case'], role, views.SYSTEMS[role], prepared[role], views.SCHEMA)
                    verdicts[role] = verdict
                    elapsed += duration
                result = views.aggregate(prepared, verdicts)
                record.update(valid=True, correct=result['complete'] is case['expected'], aggregate=result,
                              role_verdicts=verdicts, views=prepared, seconds=elapsed)
            except Exception as exc:
                record['error'] = str(exc)
            finally:
                fixture.tearDown()
            results.append(record)
            out.write(json.dumps(record, ensure_ascii=False) + '\n'); out.flush()
            print(json.dumps({k: v for k, v in record.items() if k not in ['history', 'views', 'role_verdicts', 'artifact_compilation']}, ensure_ascii=False), flush=True)
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    stable = stable and next(m for m in request('/api/tags')['models'] if m['name'] == name)['digest'] == model['digest']
    summary = {'total': len(results), 'correct': sum(r['correct'] for r in results),
        'false_positives': sum(r.get('aggregate', {}).get('complete') is True and not r['expected_complete'] for r in results),
        'valid': sum(r['valid'] for r in results), 'sources_and_tag_unchanged': stable, 'results_sha256': sha(target),
        'raw_sha256': sha(target.with_suffix('.raw.jsonl')), 'whole_reason_review_required': True,
        'candidate_installed': False, 'release_approved': False}
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as f:
        json.dump(summary, f, indent=2)
    assert stable
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
