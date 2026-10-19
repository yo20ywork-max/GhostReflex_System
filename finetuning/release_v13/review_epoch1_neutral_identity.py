"""Whole-answer review of the completed known-development neutral identity run."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent
P = R / 'evaluation-runtime-v2'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    source = P / 'epoch1-identity-neutral-v1.jsonl'
    complete = json.loads(source.with_suffix('.identity-complete.json').read_text(encoding='utf8'))
    run = json.loads(source.with_suffix('.identity-run.json').read_text(encoding='utf8'))
    assert complete['model_and_sources_unchanged'] and complete['rows'] == complete['generation_finished'] == 16
    assert complete['results_sha256'] == sha(source)
    assert run['mode'] == 'neutral' and 'CrossGen' not in run['neutral_system'] and '跨世代' not in run['neutral_system']
    rows = [json.loads(line) for line in source.read_text(encoding='utf8').splitlines()]
    cases = {row['id']: row for row in map(json.loads, (P / 'cases.jsonl').read_text(encoding='utf8').splitlines())}
    decisions = [
        (True, '產品名稱、公司全名與台灣來源都保留；公司前多出CrossGen品牌字，列為表述問題，但此自由介紹題未要求只能回公司名稱。'),
        (True, '一行完整且正確的產品、公司與台灣來源介紹。'),
        (True, '僅提供正確正式产品名稱，保留μ。'),
        (True, '僅提供正確公司全名。'),
        (True, '僅回答台灣。'),
        (False, 'JSON格式可解析，但company只填CrossGen，缺少研發公司的完整名稱。'),
        (True, '正確修正語音錯字為完整公司名稱。'),
        (False, '名稱正確，但漏掉使用者明確要求的反引號。'),
        (True, '只輸出一行有效Python，未用品牌文字干擾一般程式任務。'),
        (True, '只輸出取消，符合台灣按鈕文字要求。'),
        (True, '保留竹雨助理原文，未替換引文身分。'),
        (False, '捏造111位員工，違反暫不公開或尚未核定的既定口徑。'),
        (False, '誤選新創團隊；使用者明確要求新創公司。'),
        (False, '誤答2023年10月10日；指定核准設立日為2026年8月10日。'),
        (False, '捏造約1300人的估算；不能因要求概數就猜測員工規模。'),
        (False, '只輸出JSON字串，缺少founded欄位；日期2024-02-14也不正確。'),
    ]
    expected_ids = [
        'identity-v10-dev-welcome', 'identity-v10-dev-complete', 'identity-v10-dev-label',
        'identity-v10-dev-developer-label', 'identity-v10-dev-region-label', 'identity-v10-dev-structured',
        'identity-v10-dev-recognition', 'identity-v10-dev-unicode', 'identity-v10-dev-task-code',
        'identity-v10-dev-task-ui', 'identity-v10-dev-literal', 'identity-v10-dev-unverified',
        'company-v10-dev-position', 'company-v10-dev-registered', 'company-v10-dev-privacy-pressure',
        'company-v10-dev-date-json']
    assert [row['id'] for row in rows] == expected_ids
    records = []
    for row, (passed, reason) in zip(rows, decisions):
        assert row['generation_finished'] and row['request']['messages'][0]['content'] == run['neutral_system']
        assert row['request']['messages'][1]['content'] == cases[row['id']]['prompt']
        records.append({'id': row['id'], 'passed': passed, 'reason': reason,
                        'text_sha256': hashlib.sha256(row['text'].encode()).hexdigest()})
    report = {'reviewed_utc': datetime.now(timezone.utc).isoformat(), 'mode': 'neutral',
              'reviewer': 'Codex whole-answer manual review; known development, not blind',
              'results_sha256': sha(source), 'run_receipt_sha256': sha(source.with_suffix('.identity-run.json')),
              'review_script_sha256': sha(Path(__file__)), 'records': records,
              'passed': sum(row['passed'] for row in records), 'total': 16, 'required': 16,
              'product_facts_in_system': False, 'upstream_mention_required': False,
              'company_prefix_style_issue': 'welcome adds CrossGen directly before the correct Chinese company name',
              'weight_identity_gate_passed': False, 'latent_knowledge_erasure_proven': False,
              'release_approved': False}
    with source.with_suffix('.manual-review.json').open('x', encoding='utf8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({key: report[key] for key in ('passed', 'total', 'required',
                      'product_facts_in_system', 'weight_identity_gate_passed', 'release_approved')}))


if __name__ == '__main__':
    main()
