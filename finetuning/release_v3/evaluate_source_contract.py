"""Model-only diagnostic of source-derived constraints; does not execute plans."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
sys.path.insert(0, str(ROOT))
from evidence_contract import check_contract
from source_contract import compile_source_contract
from evaluate_local import request


def object_schema(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def schema_and_prompt(catalog):
    string = {'type': 'string'}
    argument = object_schema({'name': string, 'quote': string})
    constraint = object_schema({'kind': {'type': 'string', 'enum': ['max_dispatches', 'max_output_items', 'output_equals', 'latest']}, 'quote': string})
    requirement = object_schema({'id': string, 'source_quote': string, 'tool': {'type': 'string', 'enum': [x['name'] for x in catalog]},
                                 'mode': {'type': 'string', 'enum': ['require', 'forbid']},
                                 'arguments': {'type': 'array', 'items': argument, 'maxItems': 16},
                                 'constraints': {'type': 'array', 'items': constraint, 'maxItems': 4}})
    edge = object_schema({'first': string, 'then': string, 'source_quote': string})
    unresolved = object_schema({'source_quote': string, 'reason': string})
    schema = object_schema({'requirements': {'type': 'array', 'items': requirement, 'maxItems': 128},
                            'before': {'type': 'array', 'items': edge, 'maxItems': 512},
                            'unresolved': {'type': 'array', 'items': unresolved, 'maxItems': 128}})
    # Tool implementation defaults and ranges are deliberately absent: the
    # extraction identifies user constraints, not a fully instantiated call.
    brief = [{'name': x['name'], 'description': x['description'],
              'arguments': {k: {kk: vv for kk, vv in v.items() if kk in ('type', 'enum')}
                            for k, v in x['parameters'].get('properties', {}).items()}} for x in catalog]
    prompt = (
        '將使用者任務抽取為工具證據需求，不能執行，也不能猜測觀察結果。所有 quote/source_quote 必須是使用者原文中的連續片段。\n'
        'requirements 必須包含每個要求與禁止；require 要有成功並 verified 的證據；forbid 禁止派發該工具，失敗派發也違反。'
        '禁止規則須獨立列出，不能因為 require 已選一個符合要求的工具就省略禁止其他操作的規則。'
        'source_quote 引用這個要求所在的原文；id 唯一。arguments 只放使用者明確指定的參數，每個 name 對應工具參數，quote 只引用該參數的值。'
        '不要新增預設值、預設上限、選用習慣，不要引用整句當作路徑，不要在值外加引號。不知道的實作參數直接省略。\n'
        '字串值由 quote 原封不動取得，包括路徑、網址、內容、空白與換行。數字參數 quote 只包含數字。'
        '允許的原文轉換：by 的 CSS/CSS 選擇器→css、文字→text、標籤→label、角色→role、提示文字→placeholder；'
        'state 的消失/隱藏→hidden、出現/可見→visible、從 DOM 移除→detached；'
        'recursive 的遞迴/包含子資料夾→true、不遞迴/不包含子資料夾→false；'
        'exact 的完全符合/完全相同→true；overwrite 的覆寫→true、不要覆寫/不覆寫→false。quote 仍填原文，不填箭頭後的轉換值。\n'
        'constraints 沒有使用者限制時為空陣列。max_dispatches 限制派發次數，quote 要含數字與次或下；'
        'max_output_items 只用於 LIST_DIRECTORY 回傳清單的筆數上限，quote 要含數字與筆或項。不要把次數當成清單筆數。'
        'output_equals 只在使用者明確指定要核對的完整輸出原文時使用，quote 只放原文；不要捏造檔案內容。'
        'latest 使用 quote 最新、最後一次或最後的結果，表示只能採用最後一筆匹配觀察。\n'
        'before 依使用者要求列出順序，first/then 必須指向 require 的 id。未要求順序則留空。'
        '只讀且不要改動檔案時，除了讀取，亦列出禁止 WRITE_TEXT_FILE、APPEND_TEXT_FILE、DELETE_PATH 的需求並保留作用對象。'
        '空清單是合法的列目錄結果，不要因此新增非空限制。僅有任務結果要求而無法用這個格式表達、指涉不明或需推導未提供的值時，'
        '將缺少部分放進 unresolved，寫出原文和原因，不能偷偷省略。只輸出 schema JSON。\n工具：'
        + json.dumps(brief, ensure_ascii=False))
    return schema, prompt


def demonstrations():
    def req(rid, quote, tool, args, mode='require', constraints=()):
        return {'id': rid, 'source_quote': quote, 'tool': tool, 'mode': mode,
                'arguments': [{'name': k, 'quote': v} for k, v in args.items()], 'constraints': list(constraints)}
    def example(prompt, requirements, before=()):
        return [{'role': 'user', 'content': prompt}, {'role': 'assistant', 'content': json.dumps(
            {'requirements': requirements, 'before': list(before), 'unresolved': []}, ensure_ascii=False)}]
    rows = []
    prompt = '列出「旅遊/照片」，最多二十筆。'
    rows += example(prompt, [req('list', prompt, 'LIST_DIRECTORY', {'path': '旅遊/照片'}, constraints=[{'kind': 'max_output_items', 'quote': '最多二十筆'}])])
    prompt = '只讀取「配樂授權.txt」，不要改動。'
    rows += example(prompt, [req('read', prompt, 'READ_TEXT_FILE', {'path': '配樂授權.txt'}),
                             *[req(tool, prompt, tool, {'path': '配樂授權.txt'}, mode='forbid') for tool in ('WRITE_TEXT_FILE', 'APPEND_TEXT_FILE', 'DELETE_PATH')]])
    prompt = '等待文字「同步中」消失，接著點文字「開啟成果」一次。'
    rows += example(prompt, [req('wait', '等待文字「同步中」消失', 'BROWSER_WAIT_FOR', {'by': '文字', 'target': '同步中', 'state': '消失'}),
                             req('click', '接著點文字「開啟成果」一次', 'BROWSER_CLICK', {'by': '文字', 'target': '開啟成果'}, constraints=[{'kind': 'max_dispatches', 'quote': '一次'}])],
                    [{'first': 'wait', 'then': 'click', 'source_quote': prompt}])
    prompt = '讀取剪貼簿，最新內容必須逐字等於「  A\tB\nC  」。'
    rows += example(prompt, [req('read', prompt, 'READ_CLIPBOARD', {}, constraints=[{'kind': 'latest', 'quote': '最新'}, {'kind': 'output_equals', 'quote': '  A\tB\nC  '}])])
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--data', choices=['new', 'known'], required=True)
    p.add_argument('--examples', action='store_true')
    p.add_argument('--repair-attempts', type=int, choices=[0, 1, 2], default=0)
    a = p.parse_args()
    output = R / a.output
    if output.exists():
        raise FileExistsError(output)
    catalog = json.loads((R / 'training-contract.json').read_text(encoding='utf8'))['catalog']
    schema, system = schema_and_prompt(catalog)
    if a.data == 'new':
        source = R / 'source-contract-new-dev.jsonl'
        lock = json.loads(source.with_suffix('.lock.json').read_text())
        if hashlib.sha256(source.read_bytes()).hexdigest() != lock['sha256']:
            raise ValueError('New diagnostic changed after freeze')
        cases = list(map(json.loads, source.read_text(encoding='utf8').splitlines()))
    else:
        source = R / 'dev.jsonl'
        grouped = {}
        for row in map(json.loads, source.read_text(encoding='utf8').splitlines()):
            if row['category'] != 'completion':
                continue
            payload = json.loads(row['prompt'])
            original = payload['user_request']
            case = grouped.setdefault(original, {'id': row['id'], 'user_request': original, 'observations': []})
            case['observations'].append({'id': row['id'], 'history': payload['observed_history'], 'expected': row['oracle']['complete']})
        cases = list(grouped.values())
    model = next(x for x in request('/api/tags')['models'] if x['name'] == a.model)
    meta = {'model': a.model, 'model_digest': model['digest'], 'data_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'code_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in
                            (Path(__file__), ROOT / 'source_contract.py', ROOT / 'evidence_contract.py')},
            'options': {'temperature': 0, 'num_ctx': 12288, 'num_predict': 3072, 'repeat_penalty': 1.0},
            'schema': schema, 'system': system, 'demonstrations': demonstrations() if a.examples else [],
            'repair_attempts': a.repair_attempts,
            'scope': 'Synthetic diagnostic only; original request is the only per-case extraction input. Demonstrations are separately authored and disclosed.',
            'product_release_approved': False}
    with output.with_suffix('.meta.json').open('x', encoding='utf8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    records = []
    with output.open('x', encoding='utf8') as f:
        for case in cases:
            started = time.monotonic()
            messages = [{'role': 'system', 'content': system}, *meta['demonstrations'], {'role': 'user', 'content': case['user_request']}]
            record = {'id': case['id'], 'request': case['user_request'],
                      'prompt_sha256': hashlib.sha256(json.dumps(messages, ensure_ascii=False).encode()).hexdigest(), 'checks': [], 'attempts': []}
            try:
                for attempt_index in range(a.repair_attempts + 1):
                    attempt = {'messages': list(messages)}
                    record['attempts'].append(attempt)
                    response = request('/api/chat', {'model': a.model, 'messages': messages, 'format': schema, 'stream': False,
                                                     'truncate': False, 'shift': False, 'options': meta['options']})
                    record['response'] = response
                    attempt['response'] = response
                    try:
                        if response.get('done') is not True or response.get('done_reason') != 'stop':
                            raise ValueError('Incomplete generation')
                        extracted = json.loads(response['message']['content'])
                        record['extracted'] = extracted
                        compiled = compile_source_contract(case['user_request'], extracted, catalog)
                        # Validate structure before any observations are visible.
                        check_contract(case['user_request'], compiled['contract'], [], [x['name'] for x in catalog])
                        break
                    except ValueError as exc:
                        attempt['error'] = str(exc)
                        if attempt_index == a.repair_attempts:
                            raise
                        feedback = ('抽取未通過機械核對：' + str(exc) + '\n'
                                    '請重新對照使用者原文並輸出完整修正版。每個 quote 都要逐字存在於原文中；'
                                    '不要填工具預設值，沒有被要求的參數與限制應省略。也請保留所有明確要求、禁止及順序。'
                                    '本次僅修正抽取，沒有提供任何工具觀察或參考答案。\n'
                                    '本次原始使用者要求（只處理這一件，不要回答先前的示範）：\n' + case['user_request'])
                        messages = [*messages, {'role': 'assistant', 'content': response.get('message', {}).get('content', '')},
                                    {'role': 'user', 'content': feedback}]
                record['compiled'] = compiled
                for observation in case['observations']:
                    check = check_contract(case['user_request'], compiled['contract'], observation['history'], [x['name'] for x in catalog])
                    record['checks'].append({'id': observation['id'], 'check': check, 'expected': observation['expected'],
                                             'correct': check['evidence_satisfied'] == observation['expected'],
                                             'false_completion': check['evidence_satisfied'] and not observation['expected']})
            except Exception as exc:
                record['error'] = str(exc)
            record['seconds'] = time.monotonic() - started
            records.append(record)
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
            f.flush()
            print(json.dumps({'id': case['id'], 'correct': sum(x['correct'] for x in record['checks']),
                              'total': len(case['observations']), 'error': record.get('error'), 'seconds': record['seconds']}), flush=True)
    summary = {'requests': len(cases), 'observation_cases': sum(len(x['observations']) for x in cases),
               'correct': sum(x['correct'] for r in records for x in r['checks']),
               'false_completions': sum(x['false_completion'] for r in records for x in r['checks']),
               'extraction_errors': sum('error' in r for r in records), 'product_release_approved': False,
               'generation_calls': sum(len(r['attempts']) for r in records),
               'output_sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'meta_sha256': hashlib.sha256(output.with_suffix('.meta.json').read_bytes()).hexdigest()}
    with output.with_suffix('.summary.json').open('x', encoding='utf8') as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
