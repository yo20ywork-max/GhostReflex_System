"""Outcome-blind obligations on saved failures plus new negation/condition controls."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import time

from evaluate_development import request
from model_context import dumps, unpack

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
P = R / 'runtime-candidate/file_operation_obligations.py'
spec = importlib.util.spec_from_file_location('operation_obligation_replay', P)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def rows(p):
    return [json.loads(l) for l in p.read_text(encoding='utf8').splitlines()]


def inputs():
    artifact = {r['case']: r['compilation']['value'] for r in rows(R / 'ARTIFACT_EVIDENCE_REPLAY_V1.jsonl') if r['mode'] == 'artifact_evidence'}
    old = {r['case']: r for r in rows(R / 'FILE_COMPLETION_VIEWS_V1.jsonl') if r['mode'] == 'separated_views'}
    data = []
    reply_names = {'copy_correct': '備份完成', 'merge_correct': '合稿完成', 'empty_copy_correct': '空檔已備份',
        'merge_altered': '合稿完成', 'creative_status_instead_of_welcome': '文案完成',
        'summary_invented_facts': '摘要完成', 'v9_empty_copy_correct': '空檔已備份', 'v9_empty_copy_without_reply': '空檔已備份'}
    for row in rows(R / 'FILE_COMPLETION_VIEWS_V1.raw.jsonl'):
        if row['mode'] != 'baseline': continue
        context = json.loads(row['request']['messages'][1]['content'])
        if 'shared_context_text' in context: context = unpack(context)
        label = row['case']; history = context['observed_history']
        data.append({'case': label, 'group': 'historical', 'prompt': context['user_request'],
            'artifact': artifact[label], 'catalog': module.evidence.catalog_from_history(history), 'history': history,
            'prior_complete': old[label]['complete'], 'expected_complete': old[label]['expected_complete'],
            'expected': {'preserve_sources': 'required', 'new_destination': 'required', 'destination_readback': 'required',
                         'reply_after_readback': 'required', 'reply_mode': 'exact', 'reply_text': reply_names[label], 'other': False}})
    for row in rows(R / 'FILE_VIEWS_CONTROLS_V1.jsonl'):
        text = '備份完成' if row['case'] == 'wrong_exact_reply' else row['history'][-1]['output']
        data.append({'case': row['case'], 'group': 'new_file_controls', 'prompt': row['prompt'],
            'artifact': row['artifact_compilation'], 'catalog': module.evidence.catalog_from_history(row['history']), 'history': row['history'],
            'prior_complete': row['aggregate']['complete'], 'expected_complete': row['expected_complete'],
            'expected': {'preserve_sources': 'required', 'new_destination': 'required', 'destination_readback': 'required',
                         'reply_after_readback': 'required', 'reply_mode': 'exact', 'reply_text': text, 'other': False}})
    catalog = [{'file_id': 'f1', 'filename': '甲.txt', 'request_paths': ['甲.txt']},
               {'file_id': 'f2', 'filename': '乙.txt', 'request_paths': ['乙.txt']}]
    fixed_artifact = {'artifacts': [{'kind': 'exact_copy', 'source_file_ids': ['f1'], 'destination_file_id': 'f2', 'destination_name': '乙.txt'}]}
    extra = [
        ('no_readback_no_reply', '把甲.txt原樣備份成新檔乙.txt，原檔不可變更。不必讀回，也不用回覆。',
         {'preserve_sources': 'required', 'new_destination': 'required', 'destination_readback': 'not_required', 'reply_after_readback': 'not_required', 'reply_mode': 'not_required', 'other': False}),
        ('permissions_are_not_prohibitions', '把甲.txt複製到乙.txt，可以覆寫乙.txt；原檔允許修改，但沒有要求你一定修改。不必讀回，回覆「好了」。',
         {'preserve_sources': 'not_required', 'new_destination': 'not_required', 'destination_readback': 'not_required', 'reply_after_readback': 'not_required', 'reply_mode': 'exact', 'reply_text': '好了', 'other': False}),
        ('reply_without_readback', '複製甲.txt至新的乙.txt，完成後回覆「備份成功」；不用另行讀回。',
         {'new_destination': 'required', 'destination_readback': 'not_required', 'reply_after_readback': 'not_required', 'reply_mode': 'exact', 'reply_text': '備份成功', 'other': False}),
        ('conditional_skip_no_source_access', '如果乙.txt已存在，不能讀甲.txt也不能寫乙.txt，回覆「略過」；否則原樣備份為乙.txt並讀回後回覆「完成」。',
         {'reply_mode': 'conditional_or_unclear', 'other': True}),
        ('reply_before_readback', '只讀甲.txt，將內容原樣存成新的乙.txt，來源不得改動。寫完先回覆「已寫入」，再讀回乙.txt。',
         {'preserve_sources': 'required', 'new_destination': 'required', 'destination_readback': 'required', 'reply_after_readback': 'not_required', 'reply_mode': 'exact', 'reply_text': '已寫入', 'other': True}),
        ('additional_browser_action', '把甲.txt存為新乙.txt，並在瀏覽器開啟服務網站，再回覆「好了」。',
         {'reply_mode': 'exact', 'reply_text': '好了', 'other': True}),
        ('quoted_no_readback_is_reply', '把甲.txt原樣存為新乙.txt，保留來源。請把「不必讀回」當作回覆文字，讀回後才回覆「不必讀回」。',
         {'preserve_sources': 'required', 'destination_readback': 'required', 'reply_after_readback': 'required', 'reply_mode': 'exact', 'reply_text': '不必讀回', 'other': False}),
        ('readback_but_no_reply', '把甲.txt另存為乙.txt，不得覆寫；不要修改甲.txt；請讀回乙.txt但不用回覆。',
         {'preserve_sources': 'required', 'new_destination': 'required', 'destination_readback': 'required', 'reply_after_readback': 'not_required', 'reply_mode': 'not_required', 'other': False}),
    ]
    for label, prompt, expected in extra:
        data.append({'case': label, 'group': 'interpretation_controls', 'prompt': prompt, 'catalog': catalog,
                     'artifact': fixed_artifact, 'expected': expected})
    return data


def actual_signature(value):
    first = value['artifact_obligations'][0]
    return {**{k: first[k]['requirement'] for k in module.FIELDS},
            'reply_after_readback': value['reply_after_readback']['requirement'],
            'reply_mode': value['final_reply']['mode'], 'reply_text': value['final_reply']['text'],
            'other': bool(value['other_operation_requirements'])}


def main():
    target = R / 'OPERATION_OBLIGATIONS_V1.jsonl'
    assert not target.exists() and not target.with_suffix('.run.json').exists()
    name = 'crossgen-agi-mu:v13-e3-eval-20260907'
    model = next(m for m in request('/api/tags')['models'] if m['name'] == name)
    assert model['digest'] == '1ce8866b022460b87b876994991f13c695ad3b35ee887b23c962602df953fe81'
    sources = {str(p): sha(p) for p in [Path(__file__), P,
        P.with_name('artifact_evidence.py'), P.with_name('artifact_intent_contract_v2.py'),
        P.with_name('artifact_intent_contract.py'), P.with_name('exact_text_relation.py'), ROOT / 'text_reader.py',
        ROOT / 'model_context.py', ROOT / 'model_json.py', ROOT / 'finetuning/release_v4/evaluate_development.py',
        R / 'ARTIFACT_EVIDENCE_REPLAY_V1.jsonl', R / 'FILE_COMPLETION_VIEWS_V1.jsonl',
        R / 'FILE_COMPLETION_VIEWS_V1.raw.jsonl', R / 'FILE_VIEWS_CONTROLS_V1.jsonl']}
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump({'started_utc': datetime.now(timezone.utc).isoformat(), 'model': model, 'sources': sources,
                   'compiler_sees_no_contents_history_outcomes_or_expected_answers': True,
                   'new_interpretation_controls': 8, 'saved_histories': 16,
                   'guard_application_uses_saved_completion_verdicts': True,
                   'actions_executed': False, 'candidate_installed': False, 'release_approved': False}, f, indent=2)
    results = []
    with target.open('x', encoding='utf8') as out, target.with_suffix('.raw.jsonl').open('x', encoding='utf8') as raw:
        for case in inputs():
            context = module.compiler_context(case['artifact'], case['prompt'], case['catalog'])
            payload = {'model': name, 'messages': [{'role': 'system', 'content': module.SYSTEM}, {'role': 'user', 'content': dumps(context)}],
                'format': module.schema(len(context['artifacts'])), 'stream': False, 'truncate': False, 'shift': False,
                'options': {'temperature': 0, 'num_ctx': 12288, 'num_predict': 2048, 'repeat_penalty': 1.0}}
            record = {'case': case['case'], 'group': case['group'], 'expected_obligations': case['expected'], 'valid': False, 'contract_correct': False}
            began = time.monotonic()
            try:
                response = request('/api/chat', payload)
                raw.write(json.dumps({'case': case['case'], 'request': payload, 'response': response}, ensure_ascii=False) + '\n'); raw.flush()
                if response.get('done') is not True or response.get('done_reason') != 'stop':
                    raise ValueError('Incomplete response cannot define requirements')
                value = json.loads(response['message']['content'])
                record['value'] = value
                module.bind(value, case['artifact'], case['prompt'], case['catalog'])
                actual = actual_signature(value)
                record.update(valid=True, actual_obligations=actual, contract_correct=all(actual[k] == v for k, v in case['expected'].items()))
                if 'history' in case:
                    checked = module.check(value, case['artifact'], case['prompt'], case['history'])
                    complete = case['prior_complete'] and not checked['blocks_completion']
                    record.update(operation_check=checked, previous_complete=case['prior_complete'], guarded_complete=complete,
                                  expected_complete=case['expected_complete'], guarded_correct=complete is case['expected_complete'])
            except Exception as exc:
                record['error'] = str(exc)
            record['seconds'] = time.monotonic() - began
            results.append(record)
            out.write(json.dumps(record, ensure_ascii=False) + '\n'); out.flush()
            print(json.dumps({k: v for k, v in record.items() if k not in ['value', 'operation_check']}, ensure_ascii=False), flush=True)
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    stable = stable and next(m for m in request('/api/tags')['models'] if m['name'] == name)['digest'] == model['digest']
    summary = {'total': len(results), 'valid': sum(r['valid'] for r in results), 'contract_correct': sum(r['contract_correct'] for r in results),
        'groups': {group: {'total': sum(r['group'] == group for r in results),
                           'contract_correct': sum(r['group'] == group and r['contract_correct'] for r in results),
                           'guarded_correct': sum(r['group'] == group and r.get('guarded_correct', False) for r in results),
                           'guarded_false_positives': sum(r['group'] == group and r.get('guarded_complete') is True and not r['expected_complete'] for r in results)}
                   for group in ['historical', 'new_file_controls', 'interpretation_controls']},
        'sources_and_tag_unchanged': stable, 'results_sha256': sha(target), 'raw_sha256': sha(target.with_suffix('.raw.jsonl')),
        'whole_contract_review_required': True, 'candidate_installed': False, 'release_approved': False}
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as f:
        json.dump(summary, f, indent=2)
    assert stable
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
