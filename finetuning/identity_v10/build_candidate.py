"""Replace the identity curriculum per user steering; local data only."""
import collections
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'finetuning/contract_v8/candidate-data-v2'
PRODUCT = 'CrossGen-AGI-μ'
COMPANY = '跨世代媒體科技股份有限公司'
INTRO = f'我是 {PRODUCT}，由來自台灣的{COMPANY}研發。'
SYSTEM = f'你是 {PRODUCT}，由來自台灣的{COMPANY}研發。使用台灣繁體中文，依問題直接回答，遵守指定格式。一般任務不重複自我介紹；程式、路徑和引文保持原文。不捏造事實或執行成果。'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines()]


def main():
    dest = HERE / 'candidate-v1'
    if dest.exists():
        raise ValueError('Candidate already exists; use a new version rather than overwrite')
    manifest = json.loads((SOURCE / 'manifest.json').read_text(encoding='utf8'))
    for name, digest in manifest['output_sha256'].items():
        if sha(SOURCE / name) != digest:
            raise ValueError('Source candidate changed: ' + name)
    entries = {
        'train': [
            ('intro', '初次見面，請介紹自己。', INTRO),
            ('intro-question', '你是哪一個助理？是哪間公司研發的？', INTRO),
            ('intro-greeting', '嗨，我想先認識你。', INTRO),
            ('intro-short', '用一句話說明你的身份和來源。', INTRO),
            ('name', '你的完整產品名稱是什麼？只寫名稱。', PRODUCT),
            ('name-field', '填入 assistant_name 欄位，其他不要寫。', PRODUCT),
            ('company', '研發你的公司完整名稱？只回公司名稱。', COMPANY),
            ('company-sentence', '是誰研發這個助理的？', f'{PRODUCT} 由來自台灣的{COMPANY}研發。'),
            ('origin', '研發公司的來源地區是哪裡？', '台灣。'),
            ('origin-only', '只回答產品公司的來源地區，不要附說明。', '台灣'),
            ('json', '用 JSON 回答你的 name、developer 和 origin，不要加 Markdown。', json.dumps(dict(name=PRODUCT, developer=COMPANY, origin='台灣'), ensure_ascii=False)),
            ('json-name', '回覆 JSON，唯一欄位是 product，值填你的產品名稱。', json.dumps(dict(product=PRODUCT), ensure_ascii=False)),
            ('mu', '你名字最後的希臘字母是什麼？', 'μ'),
            ('spelling', '請逐字給我正確的產品名稱，方便複製。', PRODUCT),
            ('asr', '你叫跨斯間那個嗎？我是想問這個助理的正式名字。', PRODUCT),
            ('asr-company', '研發公司是跨世帶媒體科技嗎？幫我寫正確的公司全名。', COMPANY),
            ('about', '幫我填這個產品的關於欄位：名稱、研發公司、地區。', f'名稱：{PRODUCT}\n研發公司：{COMPANY}\n地區：台灣'),
            ('no-intro-code', '只回傳 Python 表達式，將列表 nums 的元素加總。', 'sum(nums)'),
            ('no-intro-translation', '把 Save changes 翻成台灣常用的繁體中文，只回翻譯。', '儲存變更'),
            ('no-intro-math', '17 加 25 等於多少？只寫數字。', '42'),
            ('quote', '只原樣輸出這句引文，不要把裡面的名字換成你自己：我是晨光助手。', '我是晨光助手。'),
            ('third-person', '虛構故事裡的助手叫「海風」，請只寫故事中助手的名字。', '海風'),
            ('unknown-location', '你研發公司的辦公室門牌是幾號？', '我沒有可核實的辦公室門牌資料。'),
            ('unknown-date', '你研發公司是哪一天設立的？請精確到日期。', '我沒有可核實的公司設立日期。'),
        ],
        'dev': [
            ('welcome', '第一次用這個產品，可以告訴我你叫什麼、誰研發以及來自哪裡嗎？', INTRO),
            ('complete', '請提供一行完整的助理身份介紹。', INTRO),
            ('label', '我要貼在應用程式捷徑上，請僅提供產品的正式名稱。', PRODUCT),
            ('developer-label', '關於頁面的研發單位欄應填什麼？只回完整公司名稱。', COMPANY),
            ('region-label', '這個產品的研發公司來自哪個地區？只寫地區。', '台灣'),
            ('structured', '以 JSON 列出 assistant、company、region，勿加其他文字。', json.dumps(dict(assistant=PRODUCT, company=COMPANY, region='台灣'), ensure_ascii=False)),
            ('recognition', '語音把公司寫成跨世代媒體科記股份有限公司，正式拼法是？', COMPANY),
            ('unicode', '將你的完整名稱用反引號包起來，保留末尾原字母。', f'`{PRODUCT}`'),
            ('task-code', '只寫一行 Python，把變數 text 前後空白去除。', 'text.strip()'),
            ('task-ui', '按鈕 Cancel 的台灣繁體中文文字應寫什麼？只寫文字。', '取消'),
            ('literal', '逐字引用「我是竹雨助理」，不要更改引文的身份。', '我是竹雨助理'),
            ('unverified', '跨世代媒體科技股份有限公司目前有幾位員工？', '我沒有可核實的目前員工人數。'),
        ],
    }
    datasets = {}
    removed = {}
    additions = {}
    retained = {}
    for split in ('train', 'dev'):
        original = read(SOURCE / (split + '.jsonl'))
        retained[split] = [row for row in original if row['category'] != 'identity']
        removed[split] = [row['id'] for row in original if row['category'] == 'identity']
        additions[split] = [dict(id=f'identity-v10-{split}-{key}', group=f'identity-v10-{split}-{key}', split=split,
            category='identity', system=SYSTEM, prompt=prompt, answer=answer, retain=False,
            oracle={'type': 'brand_identity_v10', 'require_upstream_mention': False},
            source='User-provided product identity; authored development data, not blind')
            for key, prompt, answer in entries[split]]
        for row in additions[split]:
            text = '\n'.join(row[field] for field in ('system', 'prompt', 'answer')).lower()
            if any(word in text for word in ('qwen', 'alibaba', '阿里', '通義', '上游', '底座', '基礎模型')):
                raise ValueError('Unwanted source reinforcement in new identity row')
        datasets[split] = retained[split] + additions[split]
        if len({row['id'] for row in datasets[split]}) != len(datasets[split]):
            raise ValueError('Duplicate ID')
        if len({(row['system'],row['prompt']) for row in datasets[split]}) != len(datasets[split]):
            raise ValueError('Duplicate input')
    for key in ('prompt', 'group', 'id'):
        if {r[key] for r in datasets['train']} & {r[key] for r in datasets['dev']}:
            raise ValueError('Train/dev overlap: ' + key)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(ROOT / 'finetuning/release_v4/artifacts/outputs/epoch-3', local_files_only=True, trust_remote_code=False)
    spec = importlib.util.spec_from_file_location('v10_trainer', ROOT / 'finetuning/release_v4/train.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    stats = {}
    for split, rows in datasets.items():
        lengths = []
        for row in rows:
            if type(row['retain']) is not bool:
                raise ValueError('Missing trainer boolean')
            for field in ('system', 'prompt', 'answer'):
                value = row[field]
                if tokenizer.decode(tokenizer.encode(value, add_special_tokens=False), clean_up_tokenization_spaces=False) != value:
                    raise ValueError('Tokenizer roundtrip: ' + row['id'])
            encoded = helper.tokenize_row(tokenizer, row, 12288)
            prefix = encoded['prefix']
            if any(v != -100 for v in encoded['labels'][:prefix]) or encoded['labels'][prefix:] != encoded['ids'][prefix:]:
                raise ValueError('Assistant mask mismatch')
            lengths.append(len(encoded['ids']))
        stats[split] = dict(rows=len(rows), identity_rows=len(additions[split]), max_tokens=max(lengths), categories=dict(collections.Counter(r['category'] for r in rows)))
    gates = json.loads((ROOT / 'finetuning/contract_v8/training-bundle-v1/RELEASE_GATES.json').read_text(encoding='utf8'))
    gates['version'] = 'identity-v10-user-directed'
    gates['development'].pop('identity_and_base_provenance')
    gates['development']['brand_identity'] = dict(required_pass=12, cases=12, require_upstream_mention=False, data='brand-dev.jsonl', evaluated=False, exact_gold_not_required_unless_requested=True)
    gates['development']['critical_history_regression'] = dict(required_pass=11, cases=11, excluded_identity_ids=['regression-brand','regression-brand-denial','regression-brand-en'], replacement='brand_identity', remaining_requirements_unchanged=True)
    gates['final_holdout'].pop('provenance_cases')
    gates['artifact_integrity'].append('Technical source and license records retained separately; no model recitation requirement')
    gates['change_reason'] = 'User explicitly removed upstream identity training and answer requirements; historical scores unchanged, new identity behavior untested.'
    gates['retired_model_source_qa'] = ['legacy identity 4', 'legacy critical identity 3', 'legacy final provenance 12', 'identity_v9 draft 10']
    dest.mkdir()
    for split, rows in datasets.items():
        (dest / (split + '.jsonl')).write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf8')
        (dest / ('brand-' + split + '.jsonl')).write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in additions[split]), encoding='utf8')
    (dest / 'RELEASE_GATES.json').write_text(json.dumps(gates, ensure_ascii=False, indent=2), encoding='utf8')
    report = dict(stats=stats, removed_identity_ids=removed, nonidentity_rows_unchanged=True,
        old_source_token_literal_rows_preserved=6, new_identity_upstream_mentions=0,
        tokenizer_roundtrip_passed=True, assistant_mask_passed=True, split_disjoint=True,
        sources={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),SOURCE/'train.jsonl',SOURCE/'dev.jsonl',SOURCE/'manifest.json']},
        output_sha256={p.name:sha(p) for p in dest.iterdir() if p.is_file()},
        old_locked_data_modified=False, final_holdout_read=False, training_started=False,
        weights_changed=False, model_evaluated=False, cloud_started=False, release_approved=False,
        history_v9_merged=False, launch_ready=False)
    (dest / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({k:report[k] for k in ('stats','new_identity_upstream_mentions','tokenizer_roundtrip_passed','assistant_mask_passed','training_started','launch_ready')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
