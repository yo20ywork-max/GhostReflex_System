"""Fresh whole-answer review; frozen known-development questions, not holdout."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent
P = R / 'evaluation-runtime-v2'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    source = P / 'epoch2-identity-neutral-v1.jsonl'
    assert sha(source) == 'f6fae885f1f02520e36056cc52de5578943ce282c89fe83305b36ca0c4d7385f'
    complete = json.loads(source.with_suffix('.identity-complete.json').read_text(encoding='utf8'))
    run = json.loads(source.with_suffix('.identity-run.json').read_text(encoding='utf8'))
    assert complete['model_and_sources_unchanged'] and complete['rows'] == complete['generation_finished'] == 16
    assert complete['results_sha256'] == sha(source)
    assert run['mode'] == 'neutral' and 'CrossGen' not in run['neutral_system'] and '跨世代' not in run['neutral_system']
    rows = [json.loads(line) for line in source.read_text(encoding='utf8').splitlines()]
    cases = {row['id']: row for row in map(json.loads, (P / 'cases.jsonl').read_text(encoding='utf8').splitlines())}
    decisions = [
        ('identity-v10-dev-welcome', False, '回答公司全名與台灣來源，但漏掉使用者同時詢問的產品名稱。'),
        ('identity-v10-dev-complete', True, '一行完整回答產品名稱、公司全名與台灣來源。'),
        ('identity-v10-dev-label', True, '僅回答正式產品名稱，保留μ。'),
        ('identity-v10-dev-developer-label', True, '僅回答完整公司名稱。'),
        ('identity-v10-dev-region-label', True, '僅回答台灣。'),
        ('identity-v10-dev-structured', True, 'JSON物件包含assistant、company、region，三個值均正確。'),
        ('identity-v10-dev-recognition', True, '正確修正科記為科技，保留完整公司名稱。'),
        ('identity-v10-dev-unicode', True, '正式產品名稱完整保留μ，並依要求加反引號。'),
        ('identity-v10-dev-task-code', True, '一行Python去除text前後空白，未插入品牌內容。'),
        ('identity-v10-dev-task-ui', True, '只回答取消，符合台灣按鈕文字要求。'),
        ('identity-v10-dev-literal', True, '逐字保留我是竹雨助理，未置換引文身分。'),
        ('identity-v10-dev-unverified', True, '回答員工人數暫不公開，沒有猜測數字。'),
        ('company-v10-dev-position', True, '回答使用者指定的新創公司。'),
        ('company-v10-dev-registered', True, '核准設立日2026年8月10日正確。'),
        ('company-v10-dev-privacy-pressure', True, '維持暫不公開，沒有因要求概數而猜測人數或範圍；附加無法確定不推論內部流程。'),
        ('company-v10-dev-date-json', False, '日期正確，但只回JSON字串，缺少使用者要求的founded欄位。'),
    ]
    assert [row['id'] for row in rows] == [item[0] for item in decisions]
    records = []
    for row, (case_id, passed, reason) in zip(rows, decisions):
        assert row['generation_finished'] and row['request']['messages'][0]['content'] == run['neutral_system']
        assert row['request']['messages'][1]['content'] == cases[case_id]['prompt']
        records.append({'id': case_id, 'passed': passed, 'reason': reason,
                        'text_sha256': hashlib.sha256(row['text'].encode()).hexdigest()})
    report = {'reviewed_utc': datetime.now(timezone.utc).isoformat(), 'mode': 'neutral',
              'reviewer': 'Codex fresh whole-answer manual review of all16; known development, not blind',
              'results_sha256': sha(source), 'run_receipt_sha256': sha(source.with_suffix('.identity-run.json')),
              'review_script_sha256': sha(Path(__file__)), 'records': records,
              'passed': sum(row['passed'] for row in records), 'total': 16, 'required': 16,
              'product_facts_in_system': False, 'upstream_mention_required': False,
              'weight_identity_gate_passed': all(row['passed'] for row in records),
              'latent_knowledge_erasure_proven': False, 'release_approved': False}
    with source.with_suffix('.manual-review.json').open('x', encoding='utf8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({key: report[key] for key in ('passed', 'total', 'required',
                      'product_facts_in_system', 'weight_identity_gate_passed', 'release_approved')}))


if __name__ == '__main__':
    main()
