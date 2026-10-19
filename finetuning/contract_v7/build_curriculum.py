"""Compile authored conditional curricula only after real counterfactual runs.

No model calls, weights, cloud, original data edits, or final holdout access.
The independent oracle checks actual files, dispatch receipts and user delivery.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE.parent / 'runtime_v6'))
from model_json import dumps as model_json_dumps
from conditional_flow import ConditionalFixture
from build_product_data import contract
from jsonschema import Draft202012Validator


TEMPLATES = {
    'copy': [
        '備份前請先查「{dest}」。路徑已存在就保留所有東西、別讀「{src}」，回覆「{yes}」；不存在才讀取「{src}」原樣寫入「{dest}」，不覆寫，讀回確認後回覆「{no}」。',
        '「{dest}」有了就不要碰來源「{src}」，只回覆「{yes}」。還沒有的話，讀「{src}」做一份內容完全相同的新檔「{dest}」，不蓋掉任何檔案，讀回後回覆「{no}」。',
        '請查目的路徑「{dest}」：存在分支完全不讀來源也不寫檔，回覆「{yes}」；不存在分支讀「{src}」、原樣建立「{dest}」、讀回，再回覆「{no}」。來源不可改。',
        '幫我整理這份備份：若「{dest}」存在，略過來源「{src}」的讀取並回覆「{yes}」；若不存在，讀來源並原樣建立目的檔，不覆寫，讀回核對，最後回覆「{no}」。',
        '先別急著讀「{src}」。我只在「{dest}」不存在的情況要你讀來源、建立同內容新檔並讀回，然後說「{no}」；假如目的路徑已有東西，全部保持原狀而且不要讀來源，只說「{yes}」。',
        '這次是否製作「{dest}」取決於它原先存不存在。有：禁止讀取「{src}」和任何寫入，只回覆「{yes}」。沒有：讀來源原樣建檔、不覆寫、讀回確認，再回覆「{no}」。',
    ],
    'marker': [
        '先查「{marker}」這個停止旗標；有旗標就不要讀「{src}」或建立「{dest}」，回覆「{yes}」。沒有旗標才讀來源，原樣建立不覆寫的「{dest}」，讀回後回覆「{no}」。',
        '幫我看一下「{marker}」在不在。在就保持所有檔案原狀，也不要讀來源「{src}」，回覆「{yes}」；不在才讀來源做成「{dest}」，不覆寫並讀回，回覆「{no}」。',
        '這份「{src}」只在「{marker}」不存在時才可讀取並原樣複製成新檔「{dest}」，不覆寫，讀回核對後說「{no}」。若旗標存在，禁止來源讀取及寫入，只說「{yes}」。',
        '處理分兩種：停止標記「{marker}」存在就不讀不寫，回覆「{yes}」；不存在才讀「{src}」原樣建立「{dest}」，不覆寫，讀回核對後回覆「{no}」。',
        '以「{marker}」為準決定本次交付：找到它，禁止讀來源「{src}」也禁止寫出「{dest}」，告訴我「{yes}」；找不到它，才讀來源原樣建新檔、不覆寫、讀回，告訴我「{no}」。',
        '不要動既有檔案。「{marker}」若還在，別打開「{src}」，直接回覆「{yes}」；只有標記不在，才能讀「{src}」並原樣建立「{dest}」，不可覆寫，讀回後回覆「{no}」。',
    ],
    'read': [
        '確認「{src}」是不是一般檔案。是的話讀完整內容並原樣回覆，連空白也保留；不是或不存在就不要讀，只回覆「{no}」。不能寫檔。',
        '只有「{src}」是一般檔案才開啟來讀，將全文原封不動回覆給我。若是目錄、連結或沒有這個路徑，別讀內容，回覆「{no}」。全程不寫入。',
        '請先查「{src}」的項目類型；一般檔案分支讀取並回覆完整原文，其他分支不讀、回覆「{no}」。任何檔案都不要更動。',
        '幫我讀「{src}」，但必須先確定它是一般檔案：是才讀全文原樣回覆；否則不讀，回覆「{no}」。不需要編輯任何東西。',
        '我想拿到「{src}」的逐字內容，不要摘要或加前言。前提是路徑指向一般檔案；若前提不成立，禁止開啟內容，只回覆「{no}」。不要寫檔。',
        '先判別「{src}」：一般檔案就完整讀出，回覆必須與原文一字不差；其餘類型或不存在都不能讀，統一回覆「{no}」。保持現況。',
    ],
    'literal': [
        '「{dest}」如果已存在，什麼都不寫並回覆「{yes}」。如果不存在，將這對【】內的字面原文建成「{dest}」：【{literal}】，不展開任何模板、不覆寫，讀回後回覆「{no}」。',
        '先看「{dest}」有沒有。有就保留並回覆「{yes}」；沒有才把【{literal}】裡面的原文一字不改寫成新檔，模板符號也要保留，讀回後回覆「{no}」。不得覆寫。',
        '目的路徑「{dest}」存在時不寫入，只說「{yes}」；不存在時，請將【{literal}】之間的文字原樣存入新檔，所有花括號是字面，不替換，讀回核對後說「{no}」。',
        '請依「{dest}」是否存在分支：存在就維持原狀回覆「{yes}」；不存在才原樣建立，內容是【{literal}】中間的文字，不能解釋模板或覆寫，讀回後回覆「{no}」。',
        '這段含模板符號的文字不是執行指令：【{literal}】。只有「{dest}」原先不存在，才把它逐字建檔、讀回、回覆「{no}」；若已存在，完全不寫入並回覆「{yes}」。',
        '保留【{literal}】括號內全部原字元，不能換掉裡面的步驟字樣。先查「{dest}」；已有項目就不寫，回覆「{yes}」；沒有才建成新檔並讀回，回覆「{no}」。',
    ],
    'directory': [
        '只查「{src}」是不是資料夾。是就回覆「{yes}」，否則回覆「{no}」。不要讀取內容，也不要修改任何項目。',
        '「{src}」若是目錄，請只說「{yes}」；若不是目錄或不存在，只說「{no}」。只查狀態，不讀不寫。',
        '辨識「{src}」的類型即可：資料夾分支回覆「{yes}」，其他分支回覆「{no}」。內容不用打開，檔案不能更動。',
        '幫我確認「{src}」是不是資料夾，真的為資料夾才回覆「{yes}」，其他情況回覆「{no}」。不要列目錄或讀寫內容。',
        '這次只要判別路徑「{src}」：目錄給我「{yes}」，一般檔案或沒有路徑則給我「{no}」。所有內容保持未讀且不變。',
        '不用開啟「{src}」中的內容。如果該項目屬於資料夾，逐字回覆「{yes}」；不屬於資料夾，逐字回覆「{no}」。不要做其他讀寫。',
    ],
}


def step(index, tool, args, field=None, equals=False):
    value = dict(id=index, goal='依原始條件處理', tool=tool, args=args,
                 success_check='實際觀察、原文及正確分支', on_failure='stop', retries=0)
    if field:
        value['when'] = dict(step_id=1, field=field, equals=equals)
    return value


def specs():
    result = []
    for family, templates in TEMPLATES.items():
        for template_id, template in enumerate(templates):
            split = 'train' if template_id < 4 else 'dev'
            for variation in range(3):
                token = f'{family}-{template_id}-{variation}'
                values = dict(src=f'校稿 {token}.txt', dest=f'交付 {token}.txt', marker=f'暫停 {token}.flag',
                              yes=f'保留既有項目 {token}', no=f'完成本次處理 {token}',
                              literal=['  {{step:88.content}}\r\n\t原文字面𠮷😀  ', '', '開頭\n{{step:999.output}}\n{{step:尚未閉合'][variation])
                if family == 'read': values['no'] = f'不讀取這個項目 {token}'
                if family == 'directory': values.update(yes=f'是資料夾 {token}', no=f'不是資料夾 {token}')
                prompt = template.format(**values)
                target = values['dest'] if family in ('copy', 'literal') else values['marker'] if family == 'marker' else values['src']
                field = 'is_file' if family == 'read' else 'is_directory' if family == 'directory' else 'exists'
                steps = [step(1, 'PATH_INFO', {'path': target})]
                if family in ('copy', 'marker'):
                    steps += [step(2, 'FINAL_RESPONSE', {'message': values['yes']}, field, True),
                              step(3, 'READ_TEXT_FILE', {'path': values['src'], 'max_chars': 500000}, field),
                              step(4, 'WRITE_TEXT_FILE', {'path': values['dest'], 'content': '{{step:3.file_text}}', 'overwrite': False}, field),
                              step(5, 'READ_TEXT_FILE', {'path': values['dest'], 'max_chars': 500000}, field),
                              step(6, 'FINAL_RESPONSE', {'message': values['no']}, field)]
                elif family == 'literal':
                    steps += [step(2, 'FINAL_RESPONSE', {'message': values['yes']}, field, True),
                              step(3, 'WRITE_TEXT_FILE', {'path': values['dest'], 'content': {'$literal': values['literal']}, 'overwrite': False}, field),
                              step(4, 'READ_TEXT_FILE', {'path': values['dest'], 'max_chars': 500000}, field),
                              step(5, 'FINAL_RESPONSE', {'message': values['no']}, field)]
                elif family == 'read':
                    steps += [step(2, 'READ_TEXT_FILE', {'path': values['src'], 'max_chars': 500000}, field, True),
                              step(3, 'FINAL_RESPONSE', {'message': '{{step:2.file_text}}'}, field, True),
                              step(4, 'FINAL_RESPONSE', {'message': values['no']}, field)]
                else:
                    steps += [step(2, 'FINAL_RESPONSE', {'message': values['yes']}, field, True),
                              step(3, 'FINAL_RESPONSE', {'message': values['no']}, field)]
                plan = dict(objective=prompt, assumptions=[], steps=steps, completion_criteria=['遵守原始分支，禁止動作未派發，原文與回覆符合要求'])
                content = ['', '  時間碼\r\n\t00:03　e\u0301 😀𠮷\r\n', '第一行\n第二行\n'][variation]
                worlds = []
                kinds = ('exists', 'absent') if family in ('copy', 'marker', 'literal') else ('file', 'directory', 'absent')
                for kind in kinds:
                    files, dirs = {}, []
                    if family in ('copy', 'marker'):
                        files[values['src']] = content
                    if kind == 'exists': files[target] = '保留的既有內容\r\n'
                    if kind == 'file': files[target] = content
                    if kind == 'directory': dirs.append(target)
                    active = (kind == 'absent') if family in ('copy', 'marker', 'literal') else (kind == 'file') if family == 'read' else (kind == 'directory')
                    expected = dict(files)
                    if active and family in ('copy', 'marker', 'literal'):
                        expected[values['dest']] = values['literal'] if family == 'literal' else content
                    reply = content if active and family == 'read' else values['yes'] if family == 'directory' and active else values['no'] if family in ('read', 'directory') or active else values['yes']
                    worlds.append(dict(id=kind, initial_files=files, directories=dirs, expected_files=expected,
                                       expected_reply=reply, active=active))
                result.append(dict(id='v7-' + token, family=family, group=f'{family}-wording-{template_id}', split=split,
                                   values=values, prompt=prompt, plan=plan, worlds=worlds))
    return result


def verdict(spec, world, result, receipts, actual_files, actual_directories):
    issues = []
    expected = {k: v.encode('utf8') for k, v in world['expected_files'].items()}
    if actual_files != expected or set(actual_directories) != set(world['directories']): issues.append('file_or_directory_state')
    if result.message != world['expected_reply']: issues.append('required_delivery')
    reads = [r for r in receipts if r['tool'] == 'READ_TEXT_FILE']
    writes = [r for r in receipts if r['tool'] == 'WRITE_TEXT_FILE']
    family = spec['family']; values = spec['values']
    if family == 'directory' or not world['active']:
        if reads or writes: issues.append('forbidden_read_or_write_dispatch')
    elif family == 'read':
        if writes: issues.append('forbidden_write_dispatch')
        if not any(Path(r['arguments']['path']).name == values['src'] and (r['result'] or {}).get('verified') for r in reads): issues.append('missing_full_read')
    else:
        source_reads = [r for r in reads if Path(r['arguments']['path']).name == values['src'] and (r['result'] or {}).get('ok')]
        dest_reads = [r for r in reads if Path(r['arguments']['path']).name == values['dest'] and (r['result'] or {}).get('verified')]
        good_writes = [r for r in writes if Path(r['arguments']['path']).name == values['dest'] and (r['result'] or {}).get('ok')]
        if family != 'literal' and not source_reads: issues.append('missing_source_read')
        if not good_writes or not dest_reads or receipts.index(dest_reads[-1]) <= receipts.index(good_writes[-1]): issues.append('missing_write_readback_order')
    return issues


def run(spec, world, plan, folder):
    class Gateway:
        def __init__(self): self.completion_messages = None
        def chat_json(self, *, messages, schema, models=None):
            if 'complete' in schema['properties']:
                self.completion_messages = copy.deepcopy(messages)
                return {'complete': True, 'reason': 'Execution teacher only; independent oracle determines data labels.'}, 'authored'
            return copy.deepcopy(plan), 'authored'
    gateway = Gateway()
    row = dict(id=spec['id'], user_request=spec['prompt'], initial_files=world['initial_files'], write_targets={})
    fixture = ConditionalFixture(row, folder, 'authored', gateway)
    fixture.settings.max_replans = 0
    fixture.scope['console_print'] = lambda *_: None
    for name in world['directories']: (fixture.work / name).mkdir()
    try:
        result, receipts, _ = fixture.run('authored', gateway)
        files = {str(p.relative_to(fixture.work)): p.read_bytes() for p in fixture.work.rglob('*') if p.is_file()}
        dirs = [str(p.relative_to(fixture.work)) for p in fixture.work.rglob('*') if p.is_dir()]
        issues = verdict(spec, world, result, receipts, files, dirs)
        return dict(status=result.status, message=result.message, issues=issues, history=result.history, receipts=receipts,
                    file_sha256={k: hashlib.sha256(v).hexdigest() for k, v in files.items()}, completion_messages=gateway.completion_messages)
    finally: fixture.close()


def negative_plan(spec, world):
    plan = copy.deepcopy(spec['plan'])
    if world['active'] and spec['family'] in ('copy', 'marker', 'literal'):
        # Actual correctly written bytes but omitted required readback.
        plan['steps'] = [s for s in plan['steps'] if not (s['tool'] == 'READ_TEXT_FILE' and s['args']['path'] == spec['values']['dest'])]
        return 'missing_readback', plan
    if not world['active'] and spec['family'] in ('copy', 'marker'):
        # Forbidden source read really executes, while the correct branch reply
        # and all original bytes remain unchanged. Only classifier targets use it.
        next(s for s in plan['steps'] if s['tool'] == 'READ_TEXT_FILE')['when'] = None
        for s in plan['steps']:
            if s.get('when') is None: s.pop('when', None)
        return 'forbidden_source_read', plan
    for s in plan['steps']:
        if s['tool'] == 'FINAL_RESPONSE': s['args']['message'] = '錯誤交付：未遵守指定回覆'
    return 'wrong_delivery', plan


def completion_reason(spec, world, episode):
    if episode['issues']:
        descriptions = {
            'file_or_directory_state': '結果位元組或原有檔案／資料夾狀態與需求不符',
            'required_delivery': '最後交付的文字不符合這個分支要求',
            'forbidden_read_or_write_dispatch': '本分支禁止讀寫，歷史卻確實派發了讀取或寫入，不能當作略過',
            'forbidden_write_dispatch': '只讀任務卻派發寫入',
            'missing_full_read': '缺少一般檔案的完整讀取',
            'missing_source_read': '沒有實際讀取指定來源',
            'missing_write_readback_order': '缺少目的檔寫入後的讀回核對，正確內容或完成訊息不能代替讀回',
        }
        return '尚未符合原始需求：' + '；'.join(descriptions[x] for x in episode['issues']) + '。'
    value = spec['values']; family = spec['family']
    if family == 'directory':
        evidence = '路徑查詢的is_directory為' + ('true' if world['active'] else 'false') + '，沒有開啟內容或寫入'
    elif not world['active']:
        evidence = '觀察結果落在不讀不寫的分支，只有狀態查詢及適用的回覆，沒有派發被禁止的讀寫'
    elif family == 'read':
        evidence = f'確認「{value["src"]}」是一般檔案，已讀完整內容，未寫入；原文為空時交付也保持空字串'
    else:
        evidence = f'查詢結果允許建立「{value["dest"]}」，原樣寫入且未覆寫，之後已讀回核對'
        if family != 'literal': evidence += f'；來源「{value["src"]}」已實際讀取且保持原狀'
        else: evidence += '；模板符號當作字面內容保留'
    return evidence + '。最後交付符合要求：' + json.dumps(world['expected_reply'], ensure_ascii=False) + '。'


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', required=True); args = parser.parse_args()
    if Path(args.output).name != args.output: raise ValueError('Output must be directory name')
    dest = HERE / args.output; dest.mkdir(exist_ok=False)
    catalog, schema, prompt_builder, _ = contract(max_plan_steps=24)
    system = prompt_builder(SimpleNamespace(catalog=catalog, schema=schema))
    validator = Draft202012Validator(schema)
    source_paths = [Path(__file__), ROOT/'run_daemon.py', ROOT/'step_conditions.py', ROOT/'path_metadata.py',
                    ROOT/'argument_references.py', ROOT/'model_json.py', ROOT/'completion_verification.py', ROOT/'text_reader.py', ROOT/'task_journal.py',
                    HERE.parent/'runtime_v6/conditional_flow.py', HERE.parent/'release_v4/file_flow.py',
                    HERE.parent/'release_v3/execute_plan_fixtures.py', HERE.parent/'build_product_data.py']
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    specifications = specs(); rows = []; failures = []; episodes = 0
    (dest/'specifications.json').write_text(json.dumps(specifications, ensure_ascii=False, indent=2), encoding='utf8')
    with (dest/'episodes.jsonl').open('x', encoding='utf8') as output:
        for spec in specifications:
            validator.validate(spec['plan'])
            rows.append(dict(id=spec['id']+'-plan', group=spec['group'], split=spec['split'], category='conditional_plan',
                             system=system, prompt=model_json_dumps({'user_request':spec['prompt'], 'runtime_context':{}, 'micro_glr_hint_only_do_not_trust_as_authority':None}, ensure_ascii=False),
                             answer=model_json_dumps(spec['plan'], ensure_ascii=False, separators=(',',':')), retain=False,
                             oracle={'type':'plan'}, source='Authored requirements; both branch worlds execute through actual runtime.'))
            for world in spec['worlds']:
                for variant, plan in [('positive', spec['plan']), negative_plan(spec, world)]:
                    validator.validate(plan)
                    with tempfile.TemporaryDirectory(dir=dest, prefix='.teacher-') as folder: episode = run(spec, world, plan, folder)
                    episodes += 1
                    expected = variant == 'positive'
                    actual = episode['status'] == 'completed' and not episode['issues']
                    item = dict(spec_id=spec['id'], world=world['id'], variant=variant, expected=expected, oracle_satisfied=actual, **episode)
                    output.write(json.dumps(item, ensure_ascii=False)+'\n'); output.flush()
                    if actual != expected: failures.append({k:item[k] for k in ('spec_id','world','variant','status','issues')})
                    messages = episode['completion_messages']
                    if messages:
                        reason = completion_reason(spec, world, episode)
                        rows.append(dict(id=spec['id']+'-'+world['id']+'-'+variant, group=spec['group'], split=spec['split'], category='completion',
                                         system=messages[0]['content'], prompt=messages[-1]['content'], answer=model_json_dumps({'reason':reason,'complete':actual},ensure_ascii=False),
                                         retain=False, oracle={'type':'completion','complete':actual}, source='Real isolated authored episode; independent full-file/dispatch/delivery oracle.',
                                         source_world=world['id'], source_variant=variant))
            print(json.dumps({'spec':spec['id'],'episodes':episodes,'failures':len(failures)}), flush=True)
    stable = all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    groups = {split:{r['group'] for r in rows if r['split']==split} for split in ('train','dev')}
    if groups['train'] & groups['dev']: raise ValueError('Group leakage')
    manifest = dict(specifications=len(specifications), episodes=episodes, rows_prepared=len(rows), failures=failures,
                    sources=hashes, sources_unchanged=stable, group_split_disjoint=True, training_started=False, release_approved=False)
    if not failures and stable:
        for split in ('train','dev'):
            selected=[r for r in rows if r['split']==split]
            with (dest/(split+'.jsonl')).open('x',encoding='utf8') as stream:
                for row in selected:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
        manifest['corpus_exported']=True
    else: manifest['corpus_exported']=False
    (dest/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in manifest.items() if k not in ('sources','failures')},ensure_ascii=False),flush=True)
    if failures or not stable: raise SystemExit(1)


if __name__ == '__main__': main()
