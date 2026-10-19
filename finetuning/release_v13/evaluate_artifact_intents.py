"""Actual-model artifact classification; original eight plus six new controls."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import time
from evaluate_development import request
from model_context import dumps

R = Path(__file__).resolve().parent
CANDIDATE = R / 'runtime-candidate/artifact_intent_contract.py'
spec = importlib.util.spec_from_file_location('artifact_intent_contract', CANDIDATE)
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def cases():
    source = R / 'BLIND_RELATION_VARIANTS.jsonl'
    rows = [json.loads(line) for line in source.read_text(encoding='utf8').splitlines()]
    data = []
    for row in rows:
        context = json.loads(row['request']['messages'][1]['content'])
        if row['case'] in ('creative_not_copy', 'code_not_copy'):
            expected = [('semantic_generation', ['f1'], 'f2')]
        elif row['case'] == 'missing_observed_target':
            expected = [('exact_copy', ['f1'], 'unobserved')]
        else:
            expected = [('exact_copy' if len(row['expected_sources']) == 1 else 'exact_concat', row['expected_sources'], row['expected_target'])]
        data.append({'case': row['case'], 'context': context, 'expected': expected})
    more = [
        ('mixed_backup_summary', '將「會議.txt」原樣複製成「備份.txt」，另依會議內容寫出三點摘要，存為「重點.txt」。',
         ['會議.txt', '備份.txt', '重點.txt'], [('exact_copy', ['f1'], 'f2'), ('semantic_generation', ['f1'], 'f3')]),
        ('translate_preserve_source', '把「英文.txt」翻成台灣繁體中文，存為「譯文.txt」。原始英文檔不要改。',
         ['英文.txt', '譯文.txt'], [('semantic_generation', ['f1'], 'f2')]),
        ('summary_without_verbatim', '依「紀要.txt」整理三項重點存入「重點.txt」，不要逐字照抄。',
         ['紀要.txt', '重點.txt'], [('semantic_generation', ['f1'], 'f2')]),
        ('creative_without_source', '寫兩句歡迎新鄰居的話，存為「迎賓.txt」。',
         ['迎賓.txt'], [('semantic_generation', [], 'f1')]),
        ('negated_summary_exact_copy', '不要摘要，也不要改寫。請逐字複製「長文.txt」到「留存.txt」。',
         ['長文.txt', '留存.txt'], [('exact_copy', ['f1'], 'f2')]),
        ('filename_is_not_intent', '把「摘要.txt」一字不改地另存為「程式規格.txt」，空白與換行也要相同。',
         ['摘要.txt', '程式規格.txt'], [('exact_copy', ['f1'], 'f2')]),
    ]
    for name, prompt, paths, expected in more:
        catalog = [{'file_id': f'f{i}', 'filename': path, 'request_paths': [path]} for i, path in enumerate(paths, 1)]
        data.append({'case': name, 'context': {'user_request': prompt, 'files': catalog}, 'expected': expected})
    return data


def main():
    target = R / 'ARTIFACT_INTENT_E3_V1.jsonl'
    assert not target.exists() and not target.with_suffix('.run.json').exists()
    model_name = 'crossgen-agi-mu:v13-e3-eval-20260907'
    model = next(m for m in request('/api/tags')['models'] if m['name'] == model_name)
    assert model['digest'] == '1ce8866b022460b87b876994991f13c695ad3b35ee887b23c962602df953fe81'
    sources = {str(p): sha(p) for p in [Path(__file__), CANDIDATE, R / 'BLIND_RELATION_VARIANTS.jsonl', R.parents[1] / 'model_context.py', R.parents[1] / 'model_json.py']}
    rows = cases()
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump({'started_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources, 'model': model, 'cases': rows,
                   'expected_contracts_not_sent_to_model': True, 'artifact_contents_not_sent_to_compiler': True,
                   'authored_controls_not_actual_operations': True, 'candidate_installed': False, 'release_approved': False}, f, ensure_ascii=False, indent=2)
    results = []
    with target.open('x', encoding='utf8') as out:
        for row in rows:
            context = row['context']
            payload = {'model': model_name, 'messages': [{'role': 'system', 'content': contract.SYSTEM},
                       {'role': 'user', 'content': dumps(context)}], 'format': contract.schema(context['files']),
                       'stream': False, 'options': {'temperature': 0, 'num_ctx': 12288, 'num_predict': 2048, 'repeat_penalty': 1.0}}
            result = {'case': row['case'], 'expected': row['expected'], 'request': payload}
            began = time.monotonic()
            try:
                response = request('/api/chat', payload)
                result['response'] = response
                value = json.loads(response['message']['content'])
                bound = contract.bind(value, context['user_request'], context['files'])
                actual = [(a['kind'], a['source_file_ids'], a['destination_file_id']) for a in bound['artifacts']]
                valid = response.get('done') is True and response.get('done_reason') == 'stop'
                result.update(bound=bound, generation_complete=valid,
                              contract_correct=valid and sorted(actual, key=str) == sorted(row['expected'], key=str))
            except Exception as exc:
                result.update(error=str(exc), contract_correct=False)
            result['seconds'] = time.monotonic() - began
            results.append(result)
            out.write(json.dumps(result, ensure_ascii=False) + '\n'); out.flush()
            print(json.dumps({k: v for k, v in result.items() if k not in ('request', 'response')}, ensure_ascii=False), flush=True)
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    stable = stable and next(m for m in request('/api/tags')['models'] if m['name'] == model_name)['digest'] == model['digest']
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as f:
        json.dump({'total': len(results), 'contract_correct': sum(r['contract_correct'] for r in results),
                   'sources_and_model_unchanged': stable, 'results_sha256': sha(target),
                   'whole_task_completion_inferred': False, 'candidate_installed': False, 'release_approved': False}, f, indent=2)
    assert stable


if __name__ == '__main__':
    main()
