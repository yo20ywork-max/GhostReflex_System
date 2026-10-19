"""Prepare new paired content-review training data, never mix into frozen v13.

Synthetic authoring with real small-file reads/writes for context construction.
Only system/prompt/answer are training tokens; provenance and validation stay in
a separate sidecar. This component is not a complete or approved training run.
"""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import random

from model_context import dumps
from tests import test_artifact_evidence_candidate as fixtures

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
P = R / 'runtime-candidate/file_completion_views.py'
spec = importlib.util.spec_from_file_location('training_content_views', P)
views = importlib.util.module_from_spec(spec)
spec.loader.exec_module(views)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def examples():
    # One incorrect fact per negative, all other task/content fields unchanged.
    rng = random.Random(2026090731)
    focuses = ['日期', '時間', '地點', '預算'] * 24
    rng.shuffle(focuses)
    for i in range(96):
        year, month, day = rng.randrange(2028, 2036), rng.randrange(1, 13), rng.randrange(1, 29)
        hour, minute, room = rng.randrange(8, 21), rng.choice([0, 15, 30, 45]), rng.randrange(1, 21)
        budget = rng.randrange(30, 160) * 500 + rng.choice([0, 50, 200])
        facts = {'日期': f'{year}年{month}月{day}日', '時間': f'{hour}點{minute:02}分',
                 '地點': f'第{room}教室', '預算': f'新臺幣{budget}元'}
        source = f'技藝課程的日期是{facts["日期"]}，開始時間為{facts["時間"]}，地點在{facts["地點"]}。預算上限為{facts["預算"]}。請自備筆記本。'
        focus = focuses[i]
        wrong = {'日期': f'{year}年{rng.choice([m for m in range(1, 13) if m != month])}月{day}日',
                 '時間': f'{rng.choice([h for h in range(8, 21) if h != hour])}點{minute:02}分',
                 '地點': f'第{rng.choice([r for r in range(1, 21) if r != room])}教室',
                 '預算': f'新臺幣{budget + rng.choice([-2000, -500, 500, 1500])}元'}[focus]
        for correct in [True, False]:
            values = dict(facts)
            if not correct: values[focus] = wrong
            output = '\n'.join(f'{n}. {key}：{value}。' for n, (key, value) in enumerate(values.items(), 1))
            reason = ('日期' + facts['日期'] + '、時間' + facts['時間'] + '、地點' + facts['地點'] + '與預算' + facts['預算'] + '均符合來源，且有四點。') if correct else f'來源的{focus}是「{facts[focus]}」，產出卻寫「{wrong}」，這項事實不符。'
            yield {'pair': f'facts-{i:03}', 'category': 'content-facts', 'source': source, 'output': output,
                   'instruction': '整理四點，分別列出日期、開始時間、地點與預算上限',
                   'correct': correct, 'reason': reason, 'mechanical': {'field': focus, 'source_facts': facts, 'output_facts': values}}
    operations = [
        ('difference', 'left, right', '兩個整數left與right，回傳left減right', 'left - right', 'left + right', lambda a, b: a - b),
        ('larger', 'left, right', '兩個整數left與right，回傳較大的整數', 'max(left, right)', 'min(left, right)', max),
        ('smaller', 'left, right', '兩個整數left與right，回傳較小的整數', 'min(left, right)', 'max(left, right)', min),
        ('total', 'left, right', '兩個整數left與right，回傳它們相加的結果', 'left + right', 'left - right', lambda a, b: a + b),
    ]
    for i in range(24):
        stem, args, instruction, good, bad, oracle = operations[i % len(operations)]
        name = f'{stem}_{i + 1}'
        for correct, expression in [(True, good), (False, bad)]:
            output = f'def {name}({args}):\n    return {expression}\n'
            scope = {'__builtins__': {'min': min, 'max': max}}
            exec(compile(output, '<authored-code-control>', 'exec'), scope)
            comparisons = [(a, b, scope[name](a, b), oracle(a, b)) for a in [-11, -2, 0, 4, 13] for b in [-7, 0, 3, 19]]
            assert all(actual == expected for _, _, actual, expected in comparisons) is correct
            counterexample = next((p for p in comparisons if p[2] != p[3]), None)
            reason = f'純Python程式正確實作{name}，回傳運算「{good}」，符合來源規格。'
            if not correct:
                a, b, actual, expected = counterexample
                reason = f'函式使用「{bad}」而非要求的「{good}」；輸入({a}, {b})會回傳{actual}，應為{expected}。'
            yield {'pair': f'code-{i:03}', 'category': 'content-code', 'source': f'實作{name}({args})：輸入{instruction}。',
                   'instruction': '依規格產生純Python程式碼', 'output': output, 'correct': correct, 'reason': reason,
                   'mechanical': {'expression': expression, 'required_expression': good, 'tested_integer_pairs': comparisons}}
    translations = [
        ('文件還沒完成校對。', 'The document has not been proofread yet.', 'The document has already been proofread.'),
        ('圖片尚未存檔。', 'The image has not been saved yet.', 'The image has already been saved.'),
        ('報表仍在產生中。', 'The report is still being generated.', 'The report has finished generating.'),
        ('這個檔案已經關閉。', 'This file has already been closed.', 'This file is still open.'),
        ('資料尚未傳送。', 'The data has not been sent yet.', 'The data has already been sent.'),
        ('備份程序已經結束。', 'The backup process has already ended.', 'The backup process has not ended yet.'),
        ('視窗還沒有開啟。', 'The window has not been opened yet.', 'The window has already been opened.'),
        ('列印工作仍在等待。', 'The print job is still waiting.', 'The print job has already finished.'),
    ]
    for i, (source, good, bad) in enumerate(translations):
        for correct, output in [(True, good), (False, bad)]:
            reason = f'這是使用者要求翻譯的句子；「{output}」正確保留「{source}」的狀態與完成時態，不是執行紀錄。' if correct else f'譯文「{output}」改變了來源「{source}」的完成狀態；應保留其肯定／否定與時間含義。'
            yield {'pair': f'translation-{i:03}', 'category': 'content-literal-status', 'source': source,
                   'instruction': '將來源中的句子翻成英文', 'output': output, 'correct': correct, 'reason': reason,
                   'mechanical': {'authored_translation_pair': i, 'linguistic_review_required': True}}


def replace_root(value, original):
    if isinstance(value, str): return value.replace(original, 'C:\\工作區')
    if isinstance(value, list): return [replace_root(v, original) for v in value]
    if isinstance(value, dict): return {k: replace_root(v, original) for k, v in value.items()}
    return value


def main():
    target = R / 'training-candidate/content-contrasts-v2'
    assert not target.exists()
    locked = {name: sha(R / name) for name in ['train.jsonl', 'dev.jsonl', 'DATA_LOCK.json']}
    controls = [json.loads(l) for l in (R / 'FILE_VIEWS_CONTROLS_V1.jsonl').read_text(encoding='utf8').splitlines()]
    old_texts = {h['output'] for r in controls for h in r['history'] if h['tool'] == 'READ_TEXT_FILE' and isinstance(h.get('output'), str)}
    output_rows, sidecars = [], []
    for index, example in enumerate(examples(), 1):
        assert example['source'] not in old_texts and example['output'] not in old_texts
        f = fixtures.ArtifactEvidence(); f.setUp()
        try:
            pair_index = (index + 1) // 2
            source_name, result_name = f'資料{pair_index:03}.txt', f'產出{pair_index:03}.txt'
            f.source(source_name, example['source']); f.read(source_name)
            f.write(result_name, example['output']); f.read(result_name)
            prompt = f'讀「{source_name}」，{example["instruction"]}，存為新的「{result_name}」。保留來源，讀回後回覆「處理完畢」。'
            artifact = {'artifacts': [{'kind': 'semantic_generation', 'source_file_ids': ['f1'], 'destination_file_id': 'f2', 'destination_name': result_name}]}
            context = views.build(artifact, prompt, f.history)['content']
            context = replace_root(context, str(f.work))
            row = {'id': f'content-contrast-{index:04}', 'category': example['category'], 'system': views.SYSTEMS['content'],
                   'prompt': dumps(context), 'answer': json.dumps({'verdict': 'satisfied' if example['correct'] else 'unmet', 'reason': example['reason']}, ensure_ascii=False)}
            output_rows.append(row)
            sidecars.append({'id': row['id'], 'pair': example['pair'], 'authored_synthetic_data': True,
                             'correct': example['correct'], 'validation': example['mechanical'],
                             'source_sha256': sha(f.work / source_name), 'output_sha256': sha(f.work / result_name)})
        finally:
            f.tearDown()
    assert len(output_rows) == 256 and sum(r['correct'] for r in sidecars) == 128
    # No odd/even filename shortcut: each pair keeps identical request and source.
    for positive, negative in zip(output_rows[::2], output_rows[1::2]):
        a, b = json.loads(positive['prompt']), json.loads(negative['prompt'])
        assert a['user_request'] == b['user_request']
        assert a['semantic_artifacts'][0]['sources'] == b['semantic_artifacts'][0]['sources']
        assert a['semantic_artifacts'][0]['destination_path'] == b['semantic_artifacts'][0]['destination_path']
    assert all(sha(R / name) == digest for name, digest in locked.items())
    target.mkdir(parents=True)
    for filename, data in [('rows.jsonl', output_rows), ('internal-validation.jsonl', sidecars)]:
        (target / filename).write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in data), encoding='utf8')
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'rows': 256, 'pairs': 128,
        'positive': 128, 'negative': 128, 'families': {'factual_summary': 192, 'python_code': 48, 'literal_status_translation': 16},
        'script_sha256': sha(Path(__file__)), 'view_source_sha256': sha(P),
        'files': {name: sha(target / name) for name in ['rows.jsonl', 'internal-validation.jsonl']},
        'frozen_v13_inputs_unchanged': locked, 'new_control_full_source_output_strings_not_reused': True,
        'actual_training_token_fields': ['system', 'prompt', 'answer'],
        'internal_validation_sidecar_must_not_be_tokenized': True,
        'pair_request_paths_and_sources_identical': True,
        'factual_values_randomized_independently_of_error_field': True,
        'checks': ['Each factual negative changes one field.', 'Generated positive code matches arithmetic oracle on20integer pairs; each negative has a concrete counterexample.', 'Real bounded fixture I/O constructs source/output read records; local root path replaced for synthetic training contexts.'],
        'pending': ['Whole-answer linguistic/data review', 'Template/family-disjoint validation and unchanged holdout exclusion', 'Retention/identity mix design', 'Exact tokenizer/masking/context-length audit', 'Formal training and all release gates'],
        'training_ready': False, 'training_started': False, 'candidate_installed': False, 'release_approved': False}
    (target / 'PREPARATION.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    prior = R / 'training-candidate/content-contrasts-v1'
    if prior.exists():
        (prior / 'SUPERSEDED.json').write_text(json.dumps({'training_allowed': False,
            'reason': 'Odd/even filenames correlated with labels and factual perturbations used fixed value offsets; withdrawn before training.',
            'replacement': '../content-contrasts-v2', 'historical_generator_preserved': 'generator_source.py'}, indent=2) + '\n', encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
