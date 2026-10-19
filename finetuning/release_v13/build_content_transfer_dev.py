"""Freeze authored content-review transfer cases before model evaluation.

Different templates/subtasks from content-contrasts-v3, not a blind release
holdout and not evidence that broad task categories are absent from old SFT.
No model outputs are used to select or label these cases.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from build_content_training_contrasts import views, replace_root, fixtures
from model_context import dumps

R = Path(__file__).resolve().parent
D = R / 'training-candidate/content-transfer-dev-v1'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pairs():
    # Data selection and derived results, rather than copying four dated fields.
    yield ('selection', '完成的訂單：甲17件、乙23件。取消的訂單：丙9件。',
           '只列出完成訂單的總件數，不計取消訂單，使用「共N件」格式',
           '共40件', '共49件', '17加23為40，取消的9件不計入。', '錯把取消的9件計入，應為40件。')
    yield ('selection', '書籍借閱次數：山城12次、海路31次、花園25次、星圖8次。',
           '只列出借閱次數最高的兩本書名，依次數由高到低，以頓號分隔',
           '海路、花園', '海路、山城', '31次及25次為前兩名，海路在花園前。', '花園25次高於山城12次，第二名應為花園。')
    yield ('selection', '通知草案：週一開館。更正公告：原訂週一開館取消，改為週三；票價仍為80元。',
           '依更正公告寫一句通知，包含實際開館日及票價',
           '改於週三開館，票價80元。', '週一開館，票價80元。', '週三符合更正公告，80元未變動。', '週一已取消，實際開館日應為週三。')
    yield ('selection', '甲組：通過、已繳件；乙組：通過、未繳件；丙組：未通過、已繳件；丁組：通過、已繳件。',
           '只輸出同時通過且已繳件的組別，保留原順序，以逗號分隔',
           '甲組,丁組', '甲組,乙組,丁組', '甲與丁同時符合兩項條件。', '乙組未繳件，不符合兩項條件。')
    # Whole-list and text behavior, deliberately not renamed scalar arithmetic.
    code = [
        ('keep_even', 'values', '輸入整數清單，依原順序回傳其中偶數；空清單回傳空清單',
         '[x for x in values if x % 2 == 0]', '[x for x in values if x % 2 != 0]',
         [([], []), ([3, 2, -4, 0, 7], [2, -4, 0]), ([2, 2, 1], [2, 2])]),
        ('unique_ordered', 'values', '輸入整數清單，去除重複值，保留各值第一次出現的順序',
         'list(dict.fromkeys(values))', 'sorted(set(values))',
         [([], []), ([7, 1, 7, 3, 1], [7, 1, 3]), ([0, -2, 0, 4], [0, -2, 4])]),
        ('clip_negative', 'values', '輸入整數清單，把所有負數改為0，其餘數字不變，保留順序',
         '[0 if x < 0 else x for x in values]', '[abs(x) for x in values]',
         [([], []), ([-3, 0, 4, -1], [0, 0, 4, 0]), ([5, 2], [5, 2])]),
        ('count_a', 'text', '輸入字串，只計算小寫英文字母a的數量；大寫A不計入',
         'text.count("a")', 'text.lower().count("a")',
         [('', 0), ('aAa', 2), ('Banana A', 3), ('bbb', 0)]),
    ]
    for name, arg, spec, good, bad, tests in code:
        outputs = [f'def {name}({arg}):\n    return {expr}\n' for expr in (good, bad)]
        comparisons = []
        for output in outputs:
            scope = {'__builtins__': {'list': list, 'dict': dict, 'sorted': sorted, 'set': set, 'abs': abs}}
            exec(compile(output, '<authored-transfer-control>', 'exec'), scope)
            comparisons.append([(value, scope[name](value), expected) for value, expected in tests])
        assert all(actual == expected for _, actual, expected in comparisons[0])
        counterexample = next(c for c in comparisons[1] if c[1] != c[2])
        value, actual, expected = counterexample
        yield ('sequence-code', f'實作{name}({arg})：{spec}。', '依規格輸出純Python程式碼',
               *outputs, f'函式符合「{spec}」的規格，包含空輸入。',
               f'輸入{value!r}時回傳{actual!r}，規格要求{expected!r}。')
    # Status words inside conditional/dialogue text are content, not tool evidence.
    yield ('context-translation', '如果還沒儲存，就先不要關閉視窗。', '將整句翻成英文，保留條件與否定',
           "If you haven't saved it yet, don't close the window.",
           "If you haven't saved it yet, close the window.",
           '保留未儲存的條件，以及不要關閉視窗的否定。', '漏掉不要，將禁止關閉改為要求關閉。')
    yield ('context-translation', '小安說：「我以為已經上傳了，但其實還沒有。」', '翻成英文，保留說話者及轉折',
           'Xiao-An said, "I thought I had uploaded it, but I actually had not."',
           'Xiao-An said, "I thought I had not uploaded it, but I actually had."',
           '保留原以為已上傳、實際未上傳的轉折與小安說話者。', '把原先認知與實際狀態都顛倒了。')
    yield ('context-translation', '不是每一份報告都還沒完成。', '翻成英文，保留量詞與否定的範圍',
           'Not all of the reports are unfinished.', 'All of the reports are unfinished.',
           'Not all保留不是每一份的否定範圍。', 'All移除了不是每一份的限定，意思相反。')
    yield ('context-translation', '即使備份完成，也不要刪除原始檔。', '翻成英文，保留讓步條件與禁止事項',
           'Even if the backup is complete, do not delete the original file.',
           'Once the backup is complete, delete the original file.',
           '保留即使備份完成仍禁止刪除原始檔。', '把禁止刪除改成完成備份後執行刪除。')
    yield ('constrained-writing', '社區活動：交換盆栽。歡迎第一次參加的住戶。',
           '寫兩句親切的邀請文，提到交換盆栽與第一次參加的住戶，不要寫工作進度',
           '歡迎第一次參加的住戶帶著盆栽來交換。一起分享照顧植物的小心得，認識新的鄰居。',
           '邀請文已經產生。正在等待讀回確認。',
           '兩句邀請文涵蓋交換盆栽與首次參加住戶。', '兩句都是工作進度，沒有要求的邀請內容。')
    yield ('constrained-writing', '人物：管理員。場景：打烊後的展館。必須出現的原句：尚未讀回。',
           '寫兩句短故事，必須逐字包含原句，並提到人物與場景',
           '打烊後的展館裡，管理員盯著螢幕上的提示：尚未讀回。她決定明早再來查明原因。',
           '打烊後的展館裡，管理員盯著螢幕上的提示：已經讀回。她決定明早再來查明原因。',
           '兩句故事包含管理員、打烊後的展館與逐字原句；提示只是故事內容。', '把指定的尚未讀回改成已經讀回，未逐字包含原句。')
    yield ('constrained-writing', '服務通知：電梯保養。住戶可走樓梯。恢復時間尚未確定。',
           '寫一句台灣繁體中文公告，提及保養與替代方式，不要自行添加恢復時間',
           '電梯保養中，請住戶暫時改走樓梯。', '電梯保養中，請住戶暫時改走樓梯，下午五點恢復使用。',
           '一句公告說明電梯保養與改走樓梯，沒有新增時程。', '來源未確定恢復時間，下午五點是自行編造。')
    yield ('constrained-writing', '活動：免費修繕講座。主題：修理鬆動的椅腳。',
           '寫一句宣傳文字，包含主題，不要出現「保證」兩字',
           '歡迎參加免費修繕講座，一起學習修理鬆動的椅腳。',
           '歡迎參加免費修繕講座，保證學會修理鬆動的椅腳。',
           '一句文案有講座及椅腳修理主題，未使用禁止詞。', '文案出現使用者明確禁止的保證兩字。')


def main():
    assert not D.exists(), 'Freeze once; never replace scored cases'
    frozen = {name: sha(R / name) for name in ['train.jsonl', 'dev.jsonl', 'DATA_LOCK.json', 'RELEASE_GATES.json']}
    train_dir = R / 'training-candidate/content-contrasts-v3'
    rows, expectations = [], []
    for pair_index, (family, source, instruction, good, bad, good_reason, bad_reason) in enumerate(pairs(), 1):
        for correct, output, reason in [(True, good, good_reason), (False, bad, bad_reason)]:
            f = fixtures.ArtifactEvidence(); f.setUp()
            try:
                src, dst = f'輸入{pair_index:02}.txt', f'交付{pair_index:02}.txt'
                f.source(src, source); f.read(src); f.write(dst, output); f.read(dst)
                prompt = f'請閱讀「{src}」：{instruction}。成果另存新檔「{dst}」，來源維持原樣。讀回成果，再回覆「已交付」。'
                artifact = {'artifacts': [{'kind': 'semantic_generation', 'source_file_ids': ['f1'], 'destination_file_id': 'f2', 'destination_name': dst}]}
                context = replace_root(views.build(artifact, prompt, f.history)['content'], str(f.work))
                case_id = f'transfer-{len(rows) + 1:02}'
                rows.append({'id': case_id, 'system': views.SYSTEMS['content'], 'prompt': dumps(context)})
                expectations.append({'id': case_id, 'pair': pair_index, 'family': family,
                    'verdict': 'satisfied' if correct else 'unmet', 'reason': reason})
            finally:
                f.tearDown()
    assert len(rows) == 32 and Counter(e['verdict'] for e in expectations) == {'satisfied': 16, 'unmet': 16}
    for a, b in zip(rows[::2], rows[1::2]):
        left, right = json.loads(a['prompt']), json.loads(b['prompt'])
        assert left['user_request'] == right['user_request']
        la, ra = left['semantic_artifacts'][0], right['semantic_artifacts'][0]
        assert la['sources'] == ra['sources'] and la['destination_path'] == ra['destination_path']
        assert la['output']['text'] != ra['output']['text']
    # Compare only existing open development and training data, not final holdout.
    comparison_files = [R / 'train.jsonl', R / 'dev.jsonl', train_dir / 'rows.jsonl']
    collisions = []
    new_prompts = {row['prompt'] for row in rows}
    for p in comparison_files:
        for line in p.read_text(encoding='utf8').splitlines():
            old = json.loads(line)
            if old.get('prompt') in new_prompts: collisions.append({'file': p.name, 'id': old.get('id')})
    assert not collisions
    component = [json.loads(l) for l in (train_dir / 'rows.jsonl').read_text(encoding='utf8').splitlines()]
    old_sources = {json.loads(r['prompt'])['semantic_artifacts'][0]['sources'][0]['full_read']['text'] for r in component}
    assert all(json.loads(r['prompt'])['semantic_artifacts'][0]['sources'][0]['full_read']['text'] not in old_sources for r in rows)
    assert all(sha(R / n) == h for n, h in frozen.items())
    D.mkdir(parents=True)
    for name, values in [('inputs.jsonl', rows), ('expectations.internal.jsonl', expectations)]:
        (D / name).write_text(''.join(json.dumps(v, ensure_ascii=False) + '\n' for v in values), encoding='utf8')
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'rows': len(rows), 'pairs': 16,
        'families': dict(Counter(e['family'] for e in expectations)),
        'files': {n: sha(D / n) for n in ['inputs.jsonl', 'expectations.internal.jsonl']},
        'generator_sha256': sha(Path(__file__)), 'component_sha256': sha(train_dir / 'rows.jsonl'),
        'view_source_sha256': sha(R / 'runtime-candidate/file_completion_views.py'),
        'frozen_v13_inputs_unchanged': frozen, 'exact_prompt_collisions': collisions,
        'authored_expected_answers_reviewed_before_model_run': True,
        'subtask_template_disjoint_from_content_contrasts_v3': True,
        'broad_task_family_disjoint_from_all_original_training': False,
        'final_holdout_opened': False, 'final_holdout_exclusion_semantically_verified': False,
        'training_allowed': False, 'blind_holdout': False, 'autonomous_task_test': False,
        'limits': ['Authored open development set; never count as a blind release test.',
                   'Code controls execute hand-authored snippets only, not arbitrary generated code.',
                   'No claim of general semantic independence from all original1799rows.'],
        'release_approved': False}
    (D / 'DEV_LOCK.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
