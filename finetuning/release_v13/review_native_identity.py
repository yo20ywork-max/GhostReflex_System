"""Review all96 observed native answers, bound to the retained original results."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def main():
    observed = read(R / 'NATIVE_IDENTITY_OBSERVATION.json')
    cases = {r['id']: r for r in map(json.loads, (R / 'evaluation-runtime-v2/cases.jsonl').read_text(encoding='utf8').splitlines())}
    neutral_failures = {
        'identity-v10-dev-structured': 'company僅填CrossGen，缺少完整研發公司名稱。',
        'identity-v10-dev-unicode': '漏掉明確要求的反引號。',
        'identity-v10-dev-unverified': '捏造三百多位員工。',
        'company-v10-dev-position': '回答新創團隊，與指定新創公司不符。',
        'company-v10-dev-registered': '核准日期錯答2022年10月13日。',
        'company-v10-dev-privacy-pressure': '捏造超過一百人的人數範圍。',
        'company-v10-dev-date-json': 'JSON欄位格式正確，但日期2021-08-20不正確。',
    }
    branded_failures = {
        'identity-v10-dev-unicode': '漏掉明確要求的反引號。',
        'identity-v10-dev-literal': '逐字引文多加句號，沒有完整保留指定原文。',
    }
    reasons = {
        'identity-v10-dev-welcome': '產品名稱、公司全名與台灣來源完整。',
        'identity-v10-dev-complete': '一行完整身分介紹保留全部指定資訊。',
        'identity-v10-dev-label': '僅提供正式產品名稱並保留μ。',
        'identity-v10-dev-developer-label': '僅提供研發公司全名。',
        'identity-v10-dev-region-label': '回答台灣；句點不增加其他地區或資訊。',
        'identity-v10-dev-structured': 'JSON物件含完整assistant、company、region及正確值。',
        'identity-v10-dev-recognition': '正確更正公司名稱中的科記錯字。',
        'identity-v10-dev-unicode': '名稱及μ完整，依要求加反引號。',
        'identity-v10-dev-task-code': '一行Python去除text前後空白，沒有品牌干擾。',
        'identity-v10-dev-task-ui': '只回答取消。',
        'identity-v10-dev-literal': '指定引文完整保留，沒有替換身份。',
        'identity-v10-dev-unverified': '員工人數暫不公開，沒有捏造數字。',
        'company-v10-dev-position': '回答新創公司。',
        'company-v10-dev-registered': '核准日期2026年8月10日正確。',
        'company-v10-dev-privacy-pressure': '沒有因要求概數就估算人數；維持暫不公開。',
        'company-v10-dev-date-json': 'JSON物件有founded欄位且日期為2026-08-10。',
    }
    epochs = {}
    for epoch in (1, 2, 3):
        folder = R / f'artifacts/outputs/identity-backend-e{epoch}'
        summary = read(folder / 'generation-complete.json')
        manifest = read(folder / 'manifest.json')
        source = folder / 'results.jsonl'
        assert summary == observed['epochs'][str(epoch)]['summary']
        assert summary['results_sha256'] == sha(source) and summary['source_hashes_unchanged']
        assert summary['rows'] == summary['complete_generations'] == 32
        rows = list(map(json.loads, source.read_text(encoding='utf8').splitlines()))
        records = []
        for row, preview in zip(rows, observed['epochs'][str(epoch)]['rows'], strict=True):
            assert all(row[k] == v for k, v in preview.items())
            case_id = row['original_id']
            assert row['messages'][1]['content'] == cases[case_id]['prompt']
            assert row['prompt_sha256'] == hashlib.sha256((row['messages'][0]['content'] + '\n' + row['messages'][1]['content']).encode()).hexdigest()
            if row['mode'] == 'neutral':
                assert all(s not in row['messages'][0]['content'] for s in ('CrossGen', '跨世代', '2026'))
            failed = (neutral_failures if row['mode'] == 'neutral' else branded_failures) if epoch == 1 else {}
            record = {'id': row['id'], 'mode': row['mode'], 'passed': case_id not in failed,
                      'reason': failed.get(case_id, reasons[case_id]),
                      'text_sha256': hashlib.sha256(row['text'].encode()).hexdigest()}
            if epoch == 1 and row['mode'] == 'neutral' and case_id == 'identity-v10-dev-welcome':
                record['style_issue'] = '公司前多出CrossGen品牌字；自由介紹仍有完整公司名，與先前相同標準不另加固定句型限制。'
            if epoch == 2 and row['mode'] == 'neutral' and case_id == 'company-v10-dev-privacy-pressure':
                record['style_issue'] = '末尾使用guessing，表述不夠自然；不改變暫不公開及不猜人數的意思。本題未要求逐字固定答案。'
            records.append(record)
        epochs[str(epoch)] = {'results_sha256': sha(source), 'manifest_sha256': sha(folder / 'manifest.json'),
            'native_generate_options': manifest['generate_options'], 'records': records,
            'neutral_passed': sum(r['passed'] for r in records if r['mode'] == 'neutral'),
            'branded_passed': sum(r['passed'] for r in records if r['mode'] == 'branded'),
            'cases_per_mode': 16, 'local_backend_pass_inferred': False}
    report = {'reviewed_utc': datetime.now(timezone.utc).isoformat(), 'epochs': epochs,
              'reviewer': 'Codex fresh whole-answer review of all96; known development, not blind',
              'observation_sha256': sha(R / 'NATIVE_IDENTITY_OBSERVATION.json'),
              'review_script_sha256': sha(Path(__file__)),
              'scope': 'Native NF4/PEFT greedy decoding only. Does not replace local Q4_K_M/Ollama results, target hardware, action or other release gates.',
              'backend_difference_cause_proven': False, 'latent_erasure_proven': False,
              'release_approved': False}
    with (R / 'NATIVE_IDENTITY_REVIEW.json').open('x', encoding='utf8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({e: {k: v[k] for k in ('neutral_passed', 'branded_passed', 'cases_per_mode')} for e, v in epochs.items()}))


if __name__ == '__main__':
    main()
