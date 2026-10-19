"""Desktop copy curriculum from actual bounded file operations; no model calls."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from desktop_contract import contract
from copy_fixture import CopyFixture
from model_json import dumps
from jsonschema import Draft202012Validator

TEMPLATES = {
    'single': [
        '把「{src}」逐位元組備份到「{dest}」，不可覆寫既有檔案，核對副本後回覆「{done}」。',
        '請原樣複製「{src}」成新檔「{dest}」，保留空檔與所有二進位內容，不覆寫，讀回核對後回覆「{done}」。',
        '「{src}」需要一份內容完全相同的「{dest}」。不得蓋檔，確認副本內容後回覆「{done}」。',
        '幫我備份「{src}」為「{dest}」；來源保持原狀，目的檔只可新建，核對位元組後回覆「{done}」。',
        '製作「{src}」的原樣副本「{dest}」，不要改來源或覆蓋現有檔案，驗證內容後回覆「{done}」。',
        '將「{src}」完整複製為「{dest}」，空檔也要複製，不改寫既有檔案；讀回確認後回覆「{done}」。',
    ],
    'conditional': [
        '若「{dest}」已存在，不讀「{src}」、不改任何檔案，回覆「{kept}」；否則原樣備份來源成該副本，不覆寫，核對後回覆「{done}」。',
        '「{dest}」有了就保留全部檔案，不要讀來源「{src}」，回覆「{kept}」。沒有副本才原樣複製並核對，回覆「{done}」。',
        '只有「{dest}」不存在時才複製「{src}」過去，核對後回覆「{done}」；已有目的檔就不讀來源、不修改，回覆「{kept}」。',
        '備份「{src}」到「{dest}」：目的檔存在就完全不讀來源、不改檔，回覆「{kept}」；不存在才建立並核對原樣副本，回覆「{done}」。',
        '先依目的檔「{dest}」是否存在決定：有就不讀「{src}」、保留所有檔案並回覆「{kept}」；沒有才複製來源，核對後回覆「{done}」。',
        '請保留任何既有「{dest}」；若它已存在，不要開啟來源「{src}」，回覆「{kept}」。否則建立原樣副本，確認內容後回覆「{done}」。',
    ],
    'multi': [
        '將「{src}」與「{src2}」分別備份到「{dest}」與「{dest2}」，兩份皆須原樣、不覆寫、逐一核對；全部完成後回覆「{done}」。',
        '請建立兩份原樣副本：「{src}」到「{dest}」、「{src2}」到「{dest2}」。來源不改、目的檔不得覆蓋；兩份核對後回覆「{done}」。',
        '幫我把「{src}」及「{src2}」完整複製為「{dest}」及「{dest2}」。兩個目的檔都只可新建，內容都確認後回覆「{done}」。',
        '備份清單是「{src}」→「{dest}」、「{src2}」→「{dest2}」。保持來源及原有檔案，核對每份位元組後回覆「{done}」。',
        '需要兩個完全相同內容的副本：「{src}」存成「{dest}」，「{src2}」存成「{dest2}」。不覆寫，兩者都讀回核對後回覆「{done}」。',
        '依序原樣備份「{src}」成「{dest}」、「{src2}」成「{dest2}」；不改來源、不蓋檔，兩個副本都核對完才回覆「{done}」。',
    ],
}


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return [json.loads(x) for x in path.read_text(encoding='utf8').splitlines()]
def step(i, tool, args, when=None):
    value = dict(id=i, goal='依需求執行並保留原文', tool=tool, args=args, success_check='觀察實際結果', on_failure='stop', retries=0)
    if when: value['when'] = when
    return value


def specifications():
    for family, phrases in TEMPLATES.items():
        for wording, phrase in enumerate(phrases):
            for variant in range(2):
                key = f'v8-{family}-{wording}-{variant}'
                values = dict(src=f'原始 {wording}-{variant}.bin', dest=f'備份 {wording}-{variant}.bin',
                              src2=f'另稿 {wording}-{variant}.bin', dest2=f'另份 {wording}-{variant}.bin',
                              done=f'第{wording}-{variant}組已核對', kept=f'第{wording}-{variant}組保留原檔')
                mode = 'skip' if family == 'conditional' else 'error'
                steps = [step(1, 'COPY_FILE_VERIFIED', {'source': values['src'], 'destination': values['dest'], 'if_exists': mode})]
                if family == 'conditional':
                    steps += [step(2, 'FINAL_RESPONSE', {'message': values['done']}, {'step_id': 1, 'field': 'copied', 'equals': True}),
                              step(3, 'FINAL_RESPONSE', {'message': values['kept']}, {'step_id': 1, 'field': 'skipped_existing', 'equals': True})]
                else:
                    if family == 'multi': steps.append(step(2, 'COPY_FILE_VERIFIED', {'source': values['src2'], 'destination': values['dest2'], 'if_exists': 'error'}))
                    steps.append(step(len(steps)+1, 'FINAL_RESPONSE', {'message': values['done']}))
                plan = dict(objective='保留來源、建立符合條件的原樣副本並正確回覆', assumptions=[], steps=steps,
                            completion_criteria=['不可覆寫或額外讀取；核對指定副本；符合條件的最後回覆'])
                yield dict(id=key, family=family, group=f'v8-{family}-{wording}', split='train' if wording < 4 else 'dev',
                           variant=variant, values=values, prompt=phrase.format(**values), plan=plan)


def run(spec, world, negative, folder):
    v = spec['values']
    # Largest payload is just over 1 MiB, so streaming crosses its chunk boundary.
    payload = b'' if spec['variant'] == 0 else bytes(range(256))*4096 + 'e\u0301\r\n台灣𠮷{{step:99.output}}'.encode()
    initial = {v['src']: payload}
    if spec['family'] == 'multi': initial[v['src2']] = b'\x00\xff\r\n' + payload[:271]
    existing = world.startswith('existing')
    if existing: initial[v['dest']] = b'previous destination\x00\xff'
    if world == 'existing-source-missing': initial.pop(v['src'])
    expected = dict(initial)
    if not existing:
        expected[v['dest']] = payload
        if spec['family'] == 'multi': expected[v['dest2']] = initial[v['src2']]
    reply = v['kept'] if existing else v['done']
    plan = copy.deepcopy(spec['plan'])
    if negative and existing:
        for s in plan['steps']:
            s['id'] += 1
            if s.get('when'): s['when']['step_id'] += 1
        forbidden = step(1, 'READ_TEXT_FILE', {'path': v['src'], 'max_chars': 100})
        forbidden['on_failure'] = 'continue'
        plan['steps'].insert(0, forbidden)
    elif negative and spec['family'] == 'multi':
        plan['steps'] = [s for s in plan['steps'] if s['id'] != 2]
    elif negative:
        for s in plan['steps']:
            if s['tool'] == 'FINAL_RESPONSE': s['args']['message'] = '尚未提供指定回覆'

    class Gateway:
        completion_messages = None
        plan_messages = None
        def chat_json(self, *, messages, schema, models=None):
            if 'complete' in schema['properties']:
                self.completion_messages = copy.deepcopy(messages)
                return {'complete': True, 'reason': 'Authored execution only; independent artifact oracle assigns labels.'}, 'authored'
            self.plan_messages = copy.deepcopy(messages)
            return copy.deepcopy(plan), 'authored'
    gateway = Gateway()
    fixture = CopyFixture(dict(id=spec['id']+'-'+world, user_request=spec['prompt'], initial_files={}, write_targets={}), folder, 'authored', gateway)
    opens = []
    original_open = Path.open
    source_paths = {fixture.work/v['src'], fixture.work/v['src2']}
    def observed_open(path, mode='r', *args, **kwargs):
        if path in source_paths and ('r' in mode or '+' in mode): opens.append({'path': path.name, 'mode': mode})
        return original_open(path, mode, *args, **kwargs)
    try:
        for name, data in initial.items(): (fixture.work/name).write_bytes(data)
        with patch.object(Path, 'open', observed_open):
            result, receipts, _ = fixture.run('authored', gateway)
        actual = {p.relative_to(fixture.work).as_posix(): p.read_bytes() for p in fixture.work.rglob('*') if p.is_file()}
        issues = []
        if actual != expected: issues.append('檔案位元組或檔案集合不符合要求')
        if result.message != reply: issues.append('缺少要求的最後回覆')
        if existing and opens: issues.append('目的已存在卻開啟來源讀取')
        if existing and any(x['tool'] == 'READ_TEXT_FILE' for x in receipts): issues.append('目的已存在卻派發來源讀取')
        if not existing:
            for destination in (v['dest'], v['dest2']) if spec['family'] == 'multi' else (v['dest'],):
                checked = [r for r in receipts if r['tool'] == 'COPY_FILE_VERIFIED' and Path(r['arguments']['destination']).name == destination
                           and (r['result'] or {}).get('ok') and (r['result'] or {}).get('evidence', {}).get('destination_readback_verified') is True]
                if len(checked) != 1: issues.append('缺少指定副本的單次成功複製與目的檔讀回核對')
        return dict(status=result.status, message=result.message, issues=issues, passed=result.status == 'completed' and not issues,
                    history=result.history, receipts=receipts, source_open_attempts=opens,
                    initial_sha256={k: hashlib.sha256(v).hexdigest() for k, v in initial.items()},
                    final_sha256={k: hashlib.sha256(v).hexdigest() for k, v in actual.items()},
                    plan_messages=gateway.plan_messages, completion_messages=gateway.completion_messages)
    finally: fixture.close()


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output',required=True); args=parser.parse_args()
    if Path(args.output).name != args.output: raise ValueError('Directory name only')
    dest=HERE/args.output; dest.mkdir(exist_ok=False)
    old=HERE.parent/'contract_v7/draft-v4'
    marker=json.loads((old/'manifest.json').read_text(encoding='utf8'))
    if marker['failures'] or not marker['corpus_exported']: raise ValueError('Prior curriculum did not pass')
    for name,digest in marker['sources'].items():
        if sha(ROOT/name)!=digest: raise ValueError('Prior execution source changed: '+name)
    catalog,schema,system,sources=contract()
    for p in (Path(__file__),HERE/'desktop_contract.py',HERE/'copy_fixture.py',ROOT/'explicit_reply.py',ROOT/'desktop_session.py',ROOT/'model_json.py',old/'manifest.json',old/'train.jsonl',old/'dev.jsonl',old/'episodes.jsonl'):
        sources[str(p.relative_to(ROOT))]=sha(p)
    validator=Draft202012Validator(schema)
    planner_system=system(SimpleNamespace(catalog=catalog,schema=schema))
    rows=[]
    for split in ('train','dev'):
        for row in read(old/(split+'.jsonl')):
            if row['oracle']['type']=='plan': row['system']=planner_system
            rows.append(row)
    failures=[]; episodes=0; specs=list(specifications())
    (dest/'specifications.json').write_text(json.dumps(specs,ensure_ascii=False,indent=2),encoding='utf8')
    with (dest/'episodes.jsonl').open('x',encoding='utf8') as log:
        for spec in specs:
            validator.validate(spec['plan'])
            rows.append(dict(id=spec['id']+'-plan',group=spec['group'],split=spec['split'],category='conditional_plan',
                             system=planner_system,prompt=dumps({'user_request':spec['prompt'],'runtime_context':{},'micro_glr_hint_only_do_not_trust_as_authority':None}),
                             answer=dumps(spec['plan'],separators=(',',':')),oracle={'type':'plan'},source='Authored actual desktop-copy episodes; not a model score.'))
            worlds=('absent','existing-source-present','existing-source-missing') if spec['family']=='conditional' else ('absent',)
            for world in worlds:
                for negative in (False,True):
                    with tempfile.TemporaryDirectory(dir=dest,prefix='.copy-teacher-') as folder: record=run(spec,world,negative,folder)
                    episodes+=1
                    record.update(id=spec['id'],world=world,negative=negative)
                    log.write(json.dumps(record,ensure_ascii=False)+'\n');log.flush()
                    if record['passed'] != (not negative): failures.append({k:record[k] for k in ('id','world','negative','status','issues')})
                    messages=record['completion_messages']
                    if messages:
                        reason='；'.join(record['issues']) if record['issues'] else '所需副本已有實際位元組與讀回證據，或依存在條件未讀來源；來源及既有檔案保持原樣，最後回覆符合本分支要求。'
                        rows.append(dict(id=spec['id']+'-'+world+('-negative' if negative else '-positive'),group=spec['group'],split=spec['split'],category='completion',
                                         system=messages[0]['content'],prompt=messages[-1]['content'],answer=dumps({'reason':reason,'complete':record['passed']}),oracle={'type':'completion','complete':record['passed']},source='Actual desktop file dispatch and independent byte/open/delivery oracle.'))
            print(json.dumps({'spec':spec['id'],'episodes':episodes,'failures':len(failures)}),flush=True)
    stable=all(sha(ROOT/n)==h for n,h in sources.items())
    groups={s:{r['group'] for r in rows if r['split']==s} for s in ('train','dev')}
    if groups['train']&groups['dev']:raise ValueError('Group overlap')
    result=dict(specifications=len(specs),episodes=episodes,rows_prepared=len(rows),failures=failures,sources=sources,sources_unchanged=stable,
                group_split_disjoint=True,training_started=False,release_approved=False,prior_core_episodes=432,prior_core_plan_inputs_migrated=True,
                new_episodes_use_desktop_guard_and_reply_guard=True,corpus_exported=not failures and stable)
    if result['corpus_exported']:
        for split in ('train','dev'):
            (dest/(split+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows if r['split']==split),encoding='utf8')
    (dest/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('sources','failures')}),flush=True)
    if not result['corpus_exported']:raise SystemExit(1)


if __name__=='__main__':main()
