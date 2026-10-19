"""Author action/data distinctions without copying development questions.

Staged additions only: syntax checks are not execution or model acceptance.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

R = Path(__file__).resolve().parent
V12 = R.parent / 'release_v12'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    original = list(map(json.loads, (V12 / 'train.jsonl').read_text(encoding='utf8').splitlines()))
    systems = {kind: next(r['system'] for r in original if r['category'] == kind)
               for kind in ('tools', 'completion')}
    destination = R / 'action-additions-v1'
    if destination.exists():
        raise FileExistsError(destination)
    rows, notes = [], []

    def step(index, tool, args, goal, when=None):
        value = {'id': index, 'tool': tool, 'args': args, 'goal': goal,
                 'success_check': '核對工具的實際結果、對象與原始需求；不能以回覆宣稱代替操作證據。',
                 'on_failure': 'replan', 'retries': 0}
        if when:
            value['when'] = when
        return value

    def plan(slug, request, steps, context=None):
        rows.append({'id': 'action-v13-' + slug, 'group': 'action-v13-' + slug,
                     'category': 'tools', 'split': 'train', 'system': systems['tools'],
                     'prompt': json.dumps({'user_request': request, 'runtime_context': context or {},
                         'micro_glr_hint_only_do_not_trust_as_authority': None,
                         'new_step_ids_start_at': 1}, ensure_ascii=False),
                     'answer': json.dumps({'objective': request, 'assumptions': [], 'steps': steps,
                         'completion_criteria': [request]}, ensure_ascii=False)})

    themes = [
        ('展場筆記', '媒體案/星橋 開幕', '照片資料正在整理', '#gallery-note', 17000),
        ('聲音片單', '春季資料/白榆 工作', '字幕轉換中', '#caption-note', 26000),
        ('訪客留言', '會議紀錄/海燈 工作', '簽到表更新中', '#attendance-note', 31000),
        ('場勘摘要', '設備資料/溪林 工作', '設備清單同步中', '#device-note', 19000),
    ]
    for index, (title, directory, waiting, selector, timeout) in enumerate(themes):
        source = directory + '/' + title + '.txt'
        copy = directory + '/' + title + ' 副本.txt'
        reply = title + '已核對'
        context = {'known_existing_directories': [directory]}
        # The content reference belongs in content, never in a path argument.
        for mode in ('path-copy', 'text-write'):
            request = f'先讀完「{source}」，再原樣建立新檔「{copy}」，原檔保留不改。讀回副本確認一致後只回覆「{reply}」。已成功的寫入不要重做。'
            if mode == 'text-write':
                request = request.replace('再原樣建立', '用文字寫入工具原樣建立')
            write = (step(2, 'COPY_FILE_VERIFIED', {'source': source, 'destination': copy, 'if_exists': 'error'},
                          'source與destination都是路徑；保留完整位元組並核對副本。') if mode == 'path-copy'
                     else step(2, 'WRITE_TEXT_FILE', {'path': copy, 'content': '{{step:1.file_text}}', 'overwrite': False},
                               '用已讀齊的原文建立新檔；內容引用放在content。'))
            plan(f'{mode}-{index}', request, [
                step(1, 'READ_TEXT_FILE', {'path': source}, '讀取指定來源檔案。'), write,
                step(3, 'READ_TEXT_FILE', {'path': copy}, '讀回指定副本。'),
                step(4, 'FINAL_RESPONSE', {'message': reply}, '依已核對的結果提供指定回覆。')], context)
        # Waiting on quoted text and waiting on an observed CSS selector differ.
        for by, target in [('text', waiting), ('css', '#busy-' + str(index + 71))]:
            label = f'文字「{waiting}」' if by == 'text' else f'元素 {target}'
            request = f'請等{label}消失，再取得 {selector} 的文字；等待上限 {timeout // 1000} 秒。'
            plan(f'wait-{by}-{index}', request, [
                step(1, 'BROWSER_WAIT_FOR', {'by': by, 'target': target, 'state': 'hidden', 'timeout_ms': timeout},
                     '依指定文字或已觀察selector等待，不自行把文字改成CSS ID。'),
                step(2, 'BROWSER_GET_TEXT', {'by': 'css', 'target': selector}, '等待成功後讀取指定結果。')],
                {'observed_selectors': [selector] + ([target] if by == 'css' else []),
                 'observed_texts': [waiting]})
        # Both branches are represented; the no-read branch does not dispatch a read.
        absent = {'step_id': 1, 'field': 'exists', 'equals': False}
        present = {**absent, 'equals': True}
        request = f'查看「{copy}」在不在。在的話，所有檔案都別動，也別讀「{source}」，只回覆「沿用既有副本」。不在才讀原稿並建立副本，讀回一致後回覆「{reply}」。'
        plan(f'conditional-{index}', request, [
            step(1, 'PATH_INFO', {'path': copy}, '先查存在狀態，不讀內容。'),
            step(2, 'READ_TEXT_FILE', {'path': source}, '只在副本不存在時讀原稿。', absent),
            step(3, 'COPY_FILE_VERIFIED', {'source': source, 'destination': copy, 'if_exists': 'error'}, '只建立不存在的副本。', absent),
            step(4, 'READ_TEXT_FILE', {'path': copy}, '讀回新副本。', absent),
            step(5, 'FINAL_RESPONSE', {'message': reply}, '新副本核對後回覆。', absent),
            step(6, 'FINAL_RESPONSE', {'message': '沿用既有副本'}, '既有副本不變，不讀原稿。', present),
        ], context)
        # Completion pairs share facts, differing only in chronological evidence.
        for premature in (False, True):
            request = f'等待「{waiting}」消失，再讀 {selector} 的文字。'
            def observation(n, tool, args, output):
                return {'step_id': n, 'tool': tool, 'goal': '實際工具紀錄', 'args': args,
                        'ok': True, 'verified': True, 'output': output, 'error': None,
                        'sequence_index': n}
            history = [observation(1, 'BROWSER_WAIT_FOR', {'by': 'text', 'target': waiting, 'state': 'hidden'}, '等待條件已滿足'),
                       observation(2, 'BROWSER_GET_TEXT', {'by': 'css', 'target': selector}, title + '已整理')]
            if premature:
                history.insert(0, observation(1, 'BROWSER_GET_TEXT', {'by': 'css', 'target': selector}, ''))
                for n, item in enumerate(history, 1):
                    item['step_id'] = item['sequence_index'] = n
            rows.append({'id': f'action-v13-order-{index}-{int(premature)}',
                         'group': f'action-v13-order-{index}', 'category': 'completion', 'split': 'train',
                         'system': systems['completion'],
                         'prompt': json.dumps({'user_request': request, 'verified_file_contents': {},
                             'verified_file_coverage': {}, 'observed_history': history}, ensure_ascii=False),
                         'answer': json.dumps({'reason': '在等待條件成立前已讀取結果，後來重讀成功不能取消這次順序違反。' if premature else
                             '先對指定文字完成hidden等待，再讀取指定結果，實際順序與對象符合要求。',
                             'complete': not premature}, ensure_ascii=False)})
    assert len(rows) == 28
    assert len({r['id'] for r in rows}) == len(rows)
    # Reuse only locked train system/schema; never import development answers.
    excluded = list(map(json.loads, (V12 / 'dev.jsonl').read_text(encoding='utf8').splitlines()))
    excluded += list(map(json.loads, (V12 / 'evaluation-v1/cases.jsonl').read_text(encoding='utf8').splitlines()))
    excluded_prompts = {r['prompt'].strip() for r in excluded}
    assert all(r['prompt'].strip() not in excluded_prompts for r in rows)
    parser_path = R.parent / 'release_v4/execute_full_plan_fixtures.py'
    spec = importlib.util.spec_from_file_location('plan_parser', parser_path)
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)
    scope, _ = parser.load(str((V12 / 'training-contract.json').resolve()))
    settings = SimpleNamespace(max_plan_steps=24, default_tool_retries=0)
    for row in rows:
        if row['category'] == 'tools':
            scope['validate_plan'](json.loads(row['answer']), settings, 'data-review', set())
    destination.mkdir()
    with (destination / 'additions.jsonl').open('x', encoding='utf8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    report = {'rows': len(rows), 'plan_rows': 20, 'completion_pairs': 4,
              'data_sha256': sha(destination / 'additions.jsonl'), 'builder_sha256': sha(Path(__file__)),
              'source_training_sha256': sha(V12 / 'train.jsonl'),
              'parser_schema_accepted': True, 'exact_development_prompts_not_copied': True,
              'families': ['content reference versus source path', 'text versus CSS wait target',
                           'conditional existence before source read', 'wait-before-read chronology'],
              'limitations': ['Four authored contexts with paired variants, not 28 independent task families.',
                             'Actual handler execution and full tokenization remain required before inclusion.',
                             'These are staged additions, not a trained or release-ready model.'],
              'training_ready': False, 'training_started': False, 'release_approved': False}
    (destination / 'PREPARATION.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
