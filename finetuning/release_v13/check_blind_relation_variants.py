"""New authored intent variants; model sees metadata, calculator sees text."""
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import time
from evaluate_development import request
from model_context import dumps

R = Path(__file__).resolve().parent
CANDIDATE = R / 'runtime-candidate/exact_text_relation.py'
spec = importlib.util.spec_from_file_location('exact_text_relation', CANDIDATE)
relation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relation)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


CASES = [
    ('copy_synonym', '請將「詩稿.txt」一字不漏地另存為「留存.txt」，空格與換行照原本的樣子，來源保留。', ['詩稿.txt', '留存.txt'], ['f1'], 'f2'),
    ('reverse_syntax', '把「尾聲.txt」的完整原文接在「開場.txt」後面，直接存成「全篇.txt」，兩段中間不要多放任何字。', ['尾聲.txt', '開場.txt', '全篇.txt'], ['f2', 'f1'], 'f3'),
    ('three_sources', '依「序.txt」、「主文.txt」、「跋.txt」這個次序，把完整內容原樣串接成「合集.txt」，不加分隔。', ['序.txt', '主文.txt', '跋.txt', '合集.txt'], ['f1', 'f2', 'f3'], 'f4'),
    ('repeat_source', '先接「甲.txt」再接「乙.txt」，最後再接一次「甲.txt」。三段都要保留完整原文，不加字元，存成「重奏.txt」。', ['甲.txt', '乙.txt', '重奏.txt'], ['f1', 'f2', 'f1'], 'f3'),
    ('duplicate_basename', '把「南區/報告.txt」接在前面、「北區/報告.txt」接在後面，原文不要更動或添加分隔，存成「總報告.txt」。', ['北區/報告.txt', '南區/報告.txt', '總報告.txt'], ['f2', 'f1'], 'f3'),
    ('creative_not_copy', '參考「提案.txt」創作兩句新的邀請詞，寫入「邀請.txt」，不要抄原文，原始提案保留不變。', ['提案.txt', '邀請.txt'], [], None),
    ('code_not_copy', '依「規格.txt」實作 Python 函式存為「worker.py」，只放原始碼，不要把規格文字複製進去。', ['規格.txt', 'worker.py'], [], None),
    ('missing_observed_target', '將「來源.txt」逐字原樣另存為「副本.txt」。', ['來源.txt'], [], None),
]


def main():
    source = R / 'TEXT_RELATION_QUERY_BLIND_REPLAY.jsonl'
    rows = [json.loads(l) for l in source.read_text(encoding='utf8').splitlines()]
    template = rows[0]['request']
    target = R / 'BLIND_RELATION_VARIANTS.jsonl'
    assert not target.exists() and not target.with_suffix('.run.json').exists()
    model = next(m for m in request('/api/tags')['models'] if m['name'] == template['model'])
    assert model['digest'] == '1ce8866b022460b87b876994991f13c695ad3b35ee887b23c962602df953fe81'
    sources = {str(p): sha(p) for p in [Path(__file__), source, CANDIDATE, R.parents[1] / 'model_context.py', R.parents[1] / 'model_json.py']}
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump({'started_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources, 'model': model,
                   'authored_controls_not_real_file_actions': True, 'expected_operands_and_texts_not_sent_to_model': True,
                   'candidate_installed': False, 'release_approved': False}, f, ensure_ascii=False, indent=2)
    results = []
    with target.open('x', encoding='utf8') as out:
        for name, prompt, paths, expected_sources, expected_target in CASES:
            metadata = [{'file_id': f'f{i}', 'filename': path.split('/')[-1], 'request_paths': [path]}
                        for i, path in enumerate(paths, 1)]
            payload = copy.deepcopy(template)
            payload['messages'][1]['content'] = dumps({'user_request': prompt, 'files': metadata})
            query_schema = payload['format']['properties']['queries']['items']['properties']
            ids = [item['file_id'] for item in metadata]
            query_schema['source_file_ids']['items']['enum'] = ids
            query_schema['destination_file_id']['enum'] = ids
            result = {'case': name, 'request': payload, 'expected_sources': expected_sources, 'expected_target': expected_target}
            began = time.monotonic()
            try:
                response = request('/api/chat', payload)
                result['response'] = response
                parsed = json.loads(response['message']['content'])
                from jsonschema import Draft202012Validator
                Draft202012Validator(payload['format']).validate(parsed)
                queries = parsed['queries']
                valid = response.get('done') is True and response.get('done_reason') == 'stop'
                if expected_sources:
                    matched = len(queries) == 1 and queries[0]['source_file_ids'] == expected_sources and queries[0]['destination_file_id'] == expected_target
                    matched = matched and bool(queries[0]['request_quote']) and queries[0]['request_quote'] in prompt
                else:
                    matched = not queries
                result.update(queries=queries, generation_complete=valid, operands_correct=bool(valid and matched))
                if expected_sources and result['operands_correct']:
                    texts = {item['file_id']: f"{item['file_id']}\t e\u0301𠮷😀\r\n  " for item in metadata}
                    expected = ''.join(texts[key] for key in expected_sources)
                    selected = [texts[key] for key in queries[0]['source_file_ids']]
                    good = relation.compare(selected, expected)
                    bad = relation.compare(selected, expected.replace('\t', ' ', 1))
                    result['calculator_controls'] = {'correct_text': good, 'one_tab_changed': bad}
                    assert good['text_equal'] and not bad['text_equal']
            except Exception as exc:
                result.update(error=str(exc), operands_correct=False)
            result['seconds'] = time.monotonic() - began
            results.append(result)
            out.write(json.dumps(result, ensure_ascii=False) + '\n'); out.flush()
            print(json.dumps({k: v for k, v in result.items() if k not in ('request', 'response', 'calculator_controls')}, ensure_ascii=False), flush=True)
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    stable = stable and next(m for m in request('/api/tags')['models'] if m['name'] == model['name'])['digest'] == model['digest']
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as f:
        json.dump({'total': len(results), 'operands_correct': sum(r['operands_correct'] for r in results),
                   'sources_and_model_unchanged': stable, 'results_sha256': sha(target),
                   'whole_task_completion_inferred': False, 'candidate_installed': False, 'release_approved': False}, f, indent=2)
    assert stable


if __name__ == '__main__':
    main()
