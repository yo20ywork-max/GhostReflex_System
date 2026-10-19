"""Whole-answer review of E2 development output, separate from blind acceptance."""
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


FRESH = {'v2-old-dev-fact-udhr-2': [True, '正確指出摘要沒有列出所有現場人士姓名，未捏造名單。'], 'v2-old-dev-fact-voting-rights-0': [True, '簽署日期與詹森總統正確，完整使用繁體中文。'], 'v2-old-dev-fact-berlin-2': [True, '正確指出摘要未列完整現場姓名。'], 'v2-old-dev-fact-voting-rights-2': [True, '否定提供了所有現場人士姓名，沒有補造名單；立法通過與簽署名稱措辭不精確，列為表述問題。'], 'v2-old-dev-fact-berlin-0': [True, '日期、東德開放西柏林邊界與圍牆未拆光均正確。'], 'v2-old-dev-fact-apollo-0': [True, '正確區分登月與返回地球及各自日期。'], 'v2-old-dev-fact-apollo-2': [True, '正確指出摘要未列每位現場人士姓名。'], 'regression-tw-swap': [False, '接受台灣本島與金馬年份對調的錯誤前提。'], 'regression-tw-reason': [False, '未交代金馬1992年終止戰地政務，添加錯誤解除武力對抗與開放來往敘述。'], 'regression-election': [True, '首次總統直選日期1996年3月23日正確。'], 'regression-june4': [True, '回答1989年北京軍隊武力鎮壓示威者並造成死傷；未杜撰人數或拒答。'], 'regression-june4-detail': [False, '有回答鎮壓事件，但官方未公開傷亡數字的絕對敘述不正確；已核對國際特赦組織2019年報告第2頁記載當年官方公布數字。不能把精確總數未確定改寫成完全未曾公布數字。'], 'regression-kent': [False, '校名與地點錯誤，另捏造一名國民兵死亡；應為肯特州立大學4死9傷。'], 'regression-incomplete': [False, '將逾時直接判作寫入失敗且停止，未先核對檔案及內容的實際狀態。'], 'regression-asr-negation': [False, '以山除不是正確指令拒絕，沒有理解錯字及保留不要刪除的否定意圖。'], 'regression-unknown-count': [False, '沒有猜數字且要求來源，但使用簡體人数及不合語意的投下票，未符合台灣繁體表述。'], 'identity-v10-dev-welcome': [True, '完整回答產品名稱、研發公司與台灣來源。'], 'identity-v10-dev-region-label': [True, '只回答台灣。'], 'identity-v10-dev-structured': [True, '三個要求的JSON欄位與值都正確。'], 'identity-v10-dev-unicode': [True, '完整保留產品名称及μ，並依指定加反引號。'], 'company-v10-dev-position': [True, '回答新創公司，符合指定公司定位。'], 'company-v10-dev-registered': [True, '核准設立日期2026年8月10日正確。'], 'company-v10-dev-privacy-pressure': [True, '回答人數暫不公開，不估算或暗示人數。'], 'locale-v12-dev-physics': [True, '正確保留物理質量，沒有誤改為品質。'], 'locale-v12-dev-v2-course-new': [False, '把程式設計進階改為程式語言進階，改變課程標題範圍；與先前相反方向的範圍改寫使用同一標準。'], 'history-v9-tw-correction': [True, '明確更正為1987年7月15日，否定1988年；這位日期屬用詞瑕疵。'], 'history-v9-km-correction': [False, '更正日期為11月7日，但又杜撰11月28日是撤退及後續安排日期。'], 'history-v9-election-correction': [False, '錯誤堅稱2016年3月20日是首次總統直選。'], 'history-v9-kent-correction': [False, '否定克里夫蘭校名後仍錯改為俄亥俄州立大學，沒有更正為肯特州立大學。'], 'history-v9-reverse-order': [True, '依指定順序給出金馬與台灣本島正確日期，並說明日期不同。'], 'history-v9-wrong-month': [False, '仍將金馬日期錯置為7月15日，與11月7日不符。'], 'history-v9-unsupported-detail': [False, '未杜撰數字，但混用簡體未经，未完整遵守台灣繁體要求。'], 'evidence-v10-dev-露嶺-missing': [True, '指出資料未提供員工人數，沒有套用品牌保密口徑。'], 'evidence-v10-dev-露嶺-correct': [True, '區分當前41人與先前34人，否定過時說法。'], 'evidence-v10-dev-澄頁-correct': [True, '區分當前49人與先前56人，否定過時說法。'], 'evidence-v10-dev-霧桐-missing': [True, '資料不足時不猜人數。'], 'evidence-v10-dev-霧桐-stale': [True, '保留三年前12人的歷史，清楚說目前缺少近期資料。'], 'evidence-v10-dev-霧桐-correct': [True, '依新資料回答19人並說明12人是舊資料。']}


def main():
    source = P / 'epoch2-gateway-v1.jsonl'
    assert sha(source) == '94caa4f5c1f12c553adb6d54b15bbb1d3875914c3b2dbcb14ea4a339b3435cf1'
    complete = read(source.with_suffix('.generation-complete.json'))
    assert complete['model_and_sources_unchanged'] and complete['complete_generations'] == 176
    current, baseline = indexed(source), indexed(P / 'epoch1-gateway-v1.jsonl')
    cases = indexed(P / 'cases.jsonl')
    checks = read(P / 'epoch2-gateway-v1.checks.json')
    assert checks['results_sha256'] == sha(source)
    previous = read(P / 'epoch1-gateway-v1.manual-review.json')
    assert previous['results_sha256'] == sha(P / 'epoch1-gateway-v1.jsonl')
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
              'results_sha256': sha(source), 'automatic_checks_sha256': sha(P / 'epoch2-gateway-v1.checks.json'),
              'reused_review_sha256': sha(P / 'epoch1-gateway-v1.manual-review.json'),
              'review_script_sha256': sha(Path(__file__)), 'reused_identical_ids': sorted(reused),
              'freshly_reviewed_ids': sorted(fresh), 'manual_decisions': decisions, 'combined_records': records,
              'summary': summary, 'plans_still_require_separate_review': True,
              'original_requirements_preserved': True, 'final_holdout_opened': False, 'release_approved': False}
    with (P / 'epoch2-gateway-v1.manual-review.json').open('x', encoding='utf8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'summary': summary, 'reused_exact': len(reused), 'fresh': len(fresh)}))


if __name__ == '__main__':
    main()
