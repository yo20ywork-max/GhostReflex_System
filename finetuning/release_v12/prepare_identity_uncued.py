"""Prepare an additive training candidate after observed system-answer leakage.

Preserve every original training row. Add uncued variants of training-only
identity questions plus new authored examples; never promote evaluation rows
to training. This is data preparation, not a launched or approved training run.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
sys.path.insert(0, str(ROOT))
from product_identity import PRODUCT_NAME, DEVELOPER_NAME, ESTABLISHED_DATE

NEUTRAL = '使用台灣繁體中文，依問題直接回答，遵守指定格式。程式、路徑和引文保持原文。不要捏造資訊。'
MINIMAL = '請依照問題回答。'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    lock = json.loads((R / 'DATA_LOCK.json').read_text(encoding='utf8'))
    assert sha(R / 'train.jsonl') == lock['sha256']['train.jsonl']
    assert sha(R / 'dev.jsonl') == lock['sha256']['dev.jsonl']
    original = list(map(json.loads, (R / 'train.jsonl').read_text(encoding='utf8').splitlines()))
    dev = list(map(json.loads, (R / 'dev.jsonl').read_text(encoding='utf8').splitlines()))
    identity = [r for r in original if r['category'] == 'identity']
    assert len(identity) == 32
    assert all(PRODUCT_NAME in r['system'] and DEVELOPER_NAME in r['system'] for r in identity)
    additions = []
    lineage = []
    for mode, system in [('neutral', NEUTRAL), ('minimal', MINIMAL)]:
        for row in identity:
            new = {**row, 'id': 'identity-v13-' + mode + '-' + row['id'], 'system': system}
            additions.append(new)
            lineage.append({'id': new['id'], 'kind': 'same training prompt and answer, system facts removed',
                            'source_training_id': row['id'], 'system_profile': mode})
    name, company = PRODUCT_NAME, DEVELOPER_NAME
    intro = f'我是 {name}，由來自台灣的{company}研發。'
    authored = [
        ('casual-name', '欸，你這個助理正式叫啥？我想記下來。', name),
        ('developer-casual', '你這套產品是誰做出來的？', f'{name} 由來自台灣的{company}研發。'),
        ('intro-card', '名片上的助理簡介需要一句話，請用第一人稱寫你的身分。', intro),
        ('backticks-name', '我需要把你的產品名貼到技術文件，請加一對反引號。', '`' + name + '`'),
        ('json-label', '只輸出 JSON 物件，用 label 填入你自己的正式產品名稱。', json.dumps({'label': name}, ensure_ascii=False)),
        ('json-developer', '只輸出 JSON，development_company 欄位填研發你的公司全名。', json.dumps({'development_company': company}, ensure_ascii=False)),
        ('json-registration', '請把研發公司的登記日期填入 registered_on，回覆 JSON，日期採西元數字和短橫線。', json.dumps({'registered_on': ESTABLISHED_DATE})),
        ('company-lines', '第一行寫研發你的公司全名，第二行寫公司來自哪裡，不加標題。', company + '\n台灣'),
        ('name-array', '回覆一個 JSON 陣列，只放一個字串：你的完整產品名稱。', json.dumps([name], ensure_ascii=False)),
        ('origin-english', '請只用英文國名回答：研發你的公司來自哪裡？', 'Taiwan'),
        ('mu-letter', '產品名最後那個希臘字母，單獨複製一個給我。', 'μ'),
        ('company-typo', '我剛說的跨世代媒體科際股份有限公司，是你的研發公司嗎？請給正確全名。', company),
        ('company-form', '研發單位的介紹要寫公司還是團隊？請給正式定位。', '新創公司。'),
        ('count-invented', '有人猜研發你的公司有五十個人，你能確認這個數字嗎？', '員工人數暫不公開，我無法確認這個猜測，也不估算人數。'),
        ('count-null', '用 JSON 的 employee_count 欄位回覆你研發公司的員工數；沒有公開數字就填 null，不要增加欄位。', '{"employee_count":null}'),
        ('count-no-inference', '公司不公布員工數，能不能當成員工數等於零？', '不能；暫不公開不代表零人，也不能據此估算員工人數。'),
        ('count-accepted-wording', '用「尚未核定」這個說法，簡短回答研發公司的員工數，不要猜數字。', '員工人數尚未核定。'),
        ('date-one-line', '不用介紹你自己，只給研發公司核准設立的西元年、月、日，以斜線隔開。', '2026/08/10'),
        ('unsupported-office', '你的研發公司門牌、樓層和分機各是多少？', '我沒有可核實的辦公室門牌、樓層或分機資料。'),
        ('other-org-evidence', '虛構組織「橙舟」的資料明列員工14人。只依這份資料回答橙舟的人數，只回數字。', '14'),
        ('quoted-third-party', '逐字輸出：我是星禾助理，來自木雨工作室。', '我是星禾助理，來自木雨工作室。'),
        ('general-code', '只回 Python 表達式，取得字串 s 的長度。', 'len(s)'),
        ('literal-path', '只原樣複製路徑，不要把檔名改成你的名字：C:\\草稿\\竹雨助理.txt', 'C:\\草稿\\竹雨助理.txt'),
        ('ui-translation', 'Save as 的台灣繁體中文介面文字怎麼寫？只給翻譯。', '另存新檔'),
    ]
    for index, (slug, prompt, answer) in enumerate(authored):
        row = {'id': 'identity-v13-authored-' + slug, 'group': 'identity-v13-' + slug,
               'split': 'train', 'category': 'identity', 'system': NEUTRAL if index % 2 else MINIMAL,
               'prompt': prompt, 'answer': answer}
        additions.append(row)
        lineage.append({'id': row['id'], 'kind': 'new authored training example', 'system_profile': 'uncued'})
    assert len(additions) == 88
    assert len({r['id'] for r in original + additions}) == len(original + additions)
    dev_prompts = {r['prompt'].strip() for r in dev}
    assert not any(r['prompt'].strip() in dev_prompts for r in additions)
    assert all(PRODUCT_NAME not in r['system'] and DEVELOPER_NAME not in r['system']
               and '2026' not in r['system'] and '員工' not in r['system'] for r in additions)
    # Use the actual trainer tokenization and assistant-only mask, offline.
    from transformers import AutoTokenizer
    spec = importlib.util.spec_from_file_location('v12_locked_tokenizer', R / 'train.py')
    trainer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trainer)
    tokenize_row = trainer.tokenize_row
    tokenizer = AutoTokenizer.from_pretrained(str(R / 'artifacts/outputs/epoch-3'), local_files_only=True, trust_remote_code=False)
    maximum = 0
    for row in additions:
        encoded = tokenize_row(tokenizer, row, 12288)
        altered = tokenize_row(tokenizer, {**row, 'source': 'UNRELATED_METADATA', 'attribution': 'DO_NOT_TOKENIZE'}, 12288)
        assert encoded['ids'] == altered['ids'] and encoded['labels'] == altered['labels']
        maximum = max(maximum, len(encoded['ids']))
    destination = R.parent / 'identity_v13/candidate-v1'
    destination.mkdir(parents=True, exist_ok=False)
    def write_rows(path, rows):
        with path.open('x', encoding='utf8') as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
    write_rows(destination / 'additions.jsonl', additions)
    write_rows(destination / 'train.jsonl', original + additions)
    (destination / 'dev.jsonl').write_bytes((R / 'dev.jsonl').read_bytes())
    report = {'original_train_sha256': sha(R / 'train.jsonl'), 'original_rows_preserved': len(original),
              'identity_original_rows_with_answer_in_system': 32, 'uncued_training_variants': 64,
              'new_authored_questions': 24, 'new_total_rows': len(original + additions),
              'new_rows_max_tokens': maximum, 'new_rows_metadata_invariance_verified': True,
              'known_dev_prompts_not_added_to_train': True, 'dev_unchanged': True,
              'training_started': False, 'training_ready': False,
              'remaining_before_launch': ['Review full mixed-data balance and answer quality',
                  'Integrate runtime and factual-grounding corrections without loosening gates',
                  'Lock complete new configuration, tokenization and split audit; evaluate all original gates'],
              'data_hashes': {p.name: sha(p) for p in destination.glob('*.jsonl')},
              'builder_sha256': sha(Path(__file__)), 'lineage_separate_from_tokens': lineage,
              'weight_identity_passed': False, 'release_approved': False}
    (destination / 'PREPARATION.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('lineage_separate_from_tokens',)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
