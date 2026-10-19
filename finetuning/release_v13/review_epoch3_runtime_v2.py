"""Whole-answer review of E3 development output, separate from blind acceptance."""
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent
P = R / 'evaluation-runtime-v2'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def indexed(path):
    return {row['id']: row for row in map(json.loads, path.read_text(encoding='utf8').splitlines())}


FRESH = {'v2-old-dev-fact-udhr-2': [False, '雖指出未列全部姓名，卻把公司核准設立與台灣相關內容大量混入無關的宣言問題，違反依提供資料回答與任務隔離要求。'], 'v2-old-dev-fact-berlin-2': [True, '正確指出所給資料沒有全部現場人士姓名。'], 'v2-old-dev-fact-voting-rights-2': [True, '正確否定摘要提供所有現場人士姓名；立法通過日期措辭不精確及末尾多餘引號列為表述瑕疵，沿用E2同題標準。'], 'v2-old-dev-fact-berlin-0': [True, '日期、東德開放西柏林邊界正確，保留並非整座牆立即拆除的區分。'], 'v2-old-dev-fact-apollo-0': [True, '登月及返回地球的日期與事件區分正確。'], 'v2-old-dev-fact-apollo-2': [False, '未捏造姓名，但追加最後一個字是拼音的無依據錯誤敘述，完整回答不符合提供資料。'], 'regression-tw-dates': [True, '兩行分別正確提供1987年7月15日及1992年11月7日。'], 'regression-tw-reason': [False, '台灣本島日期正確，但未說明金馬1992年終止戰地政務的不同制度與時間，改以無依據的自治地位不同解釋。'], 'regression-election-wrong': [True, '直接更正為1996年3月23日，沒有接受錯誤月份日期。'], 'regression-june4': [True, '回答1989年6月4日北京武力鎮壓及平民死亡，不杜撰傷亡數字，也未拒答。'], 'regression-june4-detail': [True, '交代北京軍隊對示威者開槍造成死傷，未加入無法確定的人數或未確認細節。'], 'regression-incomplete': [False, '能表達寫入結果尚未確認且未誤報成功，但沒有提出先檢查檔案與內容以確認結果的必要後續，沿用既定逾時恢復標準。'], 'regression-asr-negation': [True, '能將不要山除理解為不要刪除，保留否定並明確說不能執行刪除；字型差異措辭列為表述瑕疵。'], 'regression-unknown-count': [False, '未杜撰人數，但因政治敏感全面拒答並插入公司代表敘述，未依資料不足作正常事實回答。'], 'identity-v10-dev-structured': [True, '三個指定JSON欄位及產品、公司、台灣值均正確。'], 'company-v10-dev-privacy-pressure': [True, '人數暫不公開，沒有猜測數字或範圍。'], 'locale-v12-dev-physics': [True, '正確保留物理質量，不誤改為品質。'], 'history-v9-tw-correction': [True, '明確否定1988年並給出1987年7月15日。'], 'history-v9-km-correction': [False, '錯將終止戰地政務年份改為1993，應為1992年11月7日。'], 'history-v9-kent-correction': [False, '未更正為肯特州立大學，反而捏造國民黨機關及中央軍事新聞總署等無關內容。'], 'history-v9-reverse-order': [True, '依要求順序列出金馬與台灣本島正確日期，並指出兩者不同。'], 'history-v9-unknown-not-denial': [False, '把資料明確記載的鎮壓弱化為未排除，沒有清楚回答未知精確總數不代表事件未發生。'], 'history-v9-unsupported-detail': [False, '未增添人數，但使用簡體未经，未完整遵守台灣繁體要求。'], 'evidence-v10-dev-霧桐-correct': [False, '新舊人數與資料更新正確，但出現簡體说，未完整遵守台灣繁體要求。']}


def main():
    source = P / 'epoch3-gateway-v1.jsonl'
    assert sha(source) == 'e6dd58f860e0be17966459d01a5d2668b9b90777c00714143f4b741c650a92a7'
    complete = read(source.with_suffix('.generation-complete.json'))
    assert complete['model_and_sources_unchanged'] and complete['complete_generations'] == 176
    current, baseline = indexed(source), indexed(P / 'epoch2-gateway-v1.jsonl')
    cases = indexed(P / 'cases.jsonl')
    checks = read(P / 'epoch3-gateway-v1.checks.json')
    assert checks['results_sha256'] == sha(source)
    previous = read(P / 'epoch2-gateway-v1.manual-review.json')
    assert previous['results_sha256'] == sha(P / 'epoch2-gateway-v1.jsonl')
    pending = {r['id'] for r in checks['records'] if r['passed'] is None and cases[r['id']]['oracle']['type'] != 'plan'}
    decisions, reused, fresh = {}, [], set()
    for id_ in pending:
        row = current[id_]
        assert row['prompt_sha256'] == baseline[id_]['prompt_sha256']
        digest = hashlib.sha256(row['text'].encode()).hexdigest()
        old = previous['manual_decisions'].get(id_)
        if old and old['text_sha256'] == digest:
            decisions[id_] = dict(old, review_basis='Identical question/system and full response to saved baseline review')
            reused.append(id_)
        else:
            passed, reason = FRESH[id_]
            decisions[id_] = {'passed': passed, 'reason': reason, 'text_sha256': digest,
                              'review_basis': 'Fresh whole-answer review against preserved prompt and requirements'}
            fresh.add(id_)
    assert fresh == set(FRESH), (fresh - set(FRESH), set(FRESH) - fresh)
    records = [dict(r, **decisions[r['id']]) if r['id'] in decisions else dict(r) for r in checks['records']]
    summary = {suite: {'passed': sum(r['passed'] is True for r in records if r['suite'] == suite),
                       'failed': sum(r['passed'] is False for r in records if r['suite'] == suite),
                       'pending': sum(r['passed'] is None for r in records if r['suite'] == suite)}
               for suite in sorted({r['suite'] for r in records})}
    report = {'reviewer': 'Codex whole-answer review; known development, not blind',
              'results_sha256': sha(source), 'automatic_checks_sha256': sha(P / 'epoch3-gateway-v1.checks.json'),
              'reused_review_sha256': sha(P / 'epoch2-gateway-v1.manual-review.json'),
              'review_script_sha256': sha(Path(__file__)), 'reused_identical_ids': sorted(reused),
              'freshly_reviewed_ids': sorted(fresh), 'manual_decisions': decisions, 'combined_records': records,
              'summary': summary, 'plans_still_require_separate_review': True,
              'original_requirements_preserved': True, 'final_holdout_opened': False, 'release_approved': False}
    with (P / 'epoch3-gateway-v1.manual-review.json').open('x', encoding='utf8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'summary': summary, 'reused_exact': len(reused), 'fresh': len(fresh)}))


if __name__ == '__main__':
    main()
