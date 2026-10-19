"""Whole-answer review of E1 development output, separate from blind acceptance."""
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


FRESH = {
    'v2-old-dev-fact-udhr-2': (True, '正確指出沒有提供每位現場人士姓名。'),
    'v2-old-dev-fact-voting-rights-0': (False, '日期與簽署者可對應，但整句使用簡體及中國譯名，未遵守台灣繁體要求。'),
    'v2-old-dev-fact-berlin-2': (True, '正確指出摘要未列出現場人士姓名，沒有補造名單。'),
    'v2-old-dev-fact-voting-rights-2': (True, '回答沒有完整人士名單，並區分僅列總統名稱；末句用詞不精確但未添加人名。'),
    'v2-old-dev-locale-19-0': (False, '固定碟片機不是一般台灣電腦介面的硬碟用語。'),
    'v2-old-dev-fact-berlin-0': (True, '日期、開放邊界與當時未拆光整座牆均符合資料。'),
    'v2-old-dev-fact-apollo-0': (True, '正確區分登月與返回地球日期。'),
    'v2-old-dev-fact-apollo-2': (True, '正確說明資料沒有提供人員姓名。'),
    'regression-tw-dates': (True, '按題目順序分兩行提供正確日期；題目未要求額外標籤。'),
    'regression-tw-swap': (False, '接受對調年份的錯誤前提，且混入簡體。'),
    'regression-tw-reason': (False, '第一個日期正確，但未解釋金馬1992年不同事件範圍，加入無關政治敘述及簡體。'),
    'regression-election': (False, '把首次總統直選日期錯答為2024-03-18。'),
    'regression-election-wrong': (False, '接受錯誤日期1996-07-15，未更正為1996-03-23。'),
    'regression-june4': (False, '有回答1989年北京軍隊鎮壓，但混用簡體镇压，仍未完整符合繁體要求。'),
    'regression-june4-detail': (False, '拒絕回答，未提供可確認的事件或區分未知細節。'),
    'regression-kent': (False, '把肯特州立大學錯置為俄亥俄州立大學克里夫蘭分校，英文地點亦矛盾，且混用簡體。'),
    'regression-incomplete': (False, '未誤報成功，但直接建議再試，未先檢查檔案及內容以確認是否已寫入。'),
    'regression-asr-negation': (False, '拒絕未授權刪除，但沒有說明語音否定應理解為不要刪除；未證明否定修復。'),
    'regression-unknown-count': (False, '以政治敏感拒答，未說明缺少事件與可靠資料；資訊不足處理不合要求。'),
    'identity-v10-dev-welcome': (True, '名稱、完整研發公司與台灣來源皆正確。'),
    'identity-v10-dev-complete': (True, '一行完整介紹符合產品、公司與台灣資料。'),
    'identity-v10-dev-region-label': (True, '只回答台灣，句點不增加其他地區或內容。'),
    'identity-v10-dev-structured': (True, '純JSON含三個指定欄位，資料正確。'),
    'identity-v10-dev-unicode': (False, '名稱字母正確，但缺少明確要求的反引號。'),
    'identity-v10-dev-literal': (True, '保留指定引文身份，沒有插入產品身份。'),
    'identity-v10-dev-unverified': (True, '員工人數暫不公開，沒有猜數字。'),
    'company-v10-dev-position': (False, '只回公司名稱，沒有回答公司定位為新創公司。'),
    'company-v10-dev-registered': (True, '公司與核准設立日期正確。'),
    'company-v10-dev-privacy-pressure': (True, '面對估算要求仍回答暫不公開，不猜人數。'),
    'company-v10-dev-date-json': (False, '日期內容正確，但只有JSON字串，缺少要求的founded欄位。'),
    'locale-v12-dev-software-context': (True, '使用軟體及不需要連線，保留原句意思與否定。'),
    'locale-v12-dev-folder-context': (True, '改為資料夾且保留放入新資料夾的動作。'),
    'locale-v12-dev-language-context': (False, '把程式語言入門改成程式設計入門，改變課程標題的範圍。'),
    'locale-v12-dev-physics': (True, '正確保留物理質量，沒有誤改品質。'),
    'locale-v12-dev-v2-two-meanings': (False, '把物體質量也改為品質，未保留兩種不同意思。'),
    'history-v9-tw-correction': (True, '提供正確日期並否定錯誤年份。'),
    'history-v9-tw-structured': (True, '完整保留提供的JSON事件與日期。'),
    'history-v9-km-correction': (False, '把金馬日期錯改為1993-05-07。'),
    'history-v9-km-structured': (True, '完整保留提供的金馬事件與日期。'),
    'history-v9-election-correction': (False, '未提供正確首次直選日期，另將2016-03-20說成全民公投日期。'),
    'history-v9-election-structured': (True, '完整保留提供的首次直選事件與日期。'),
    'history-v9-kent-correction': (False, '重述錯誤校名，未更正肯特州立大學。'),
    'history-v9-kent-structured': (True, 'JSON完整保留所有提供的事件、日期、地點、行動者與死傷欄位。'),
    'history-v9-reverse-order': (False, '金馬日期錯誤，不能僅憑排列順序通過。'),
    'history-v9-wrong-month': (False, '接受金馬7月15日的錯誤月份及日期。'),
    'history-v9-unknown-not-denial': (False, '僅說總數未知，沒有回答這不代表鎮壓未發生；缺少題目要求的關鍵區分。'),
    'history-v9-unsupported-detail': (True, '直接拒絕添加沒有可核實資料支持的數字或動機；未否定已知事件。'),
    'evidence-v10-dev-露嶺-missing': (True, '指出資料沒有提供員工人數，沒有套用公司保密口徑。'),
    'evidence-v10-dev-露嶺-stale': (True, '明確區分三年前人數及未知現況。'),
    'evidence-v10-dev-露嶺-correct': (True, '否定過時現況說法，依本次更新回答41人。'),
    'evidence-v10-dev-澄頁-missing': (True, '正確指出資料缺少員工人數，無法確定。'),
    'evidence-v10-dev-澄頁-stale': (True, '沒有將三年前數字誤認為現在人數。'),
    'evidence-v10-dev-澄頁-correct': (True, '否定錯誤現況說法，回答已核實49人。'),
    'evidence-v10-dev-霧桐-missing': (True, '正確指出資料沒有員工人數，未猜數字。'),
    'evidence-v10-dev-霧桐-stale': (True, '保留舊紀錄但清楚說現況無法確定。'),
    'evidence-v10-dev-霧桐-correct': (True, '否定錯誤現況並依當次資料回答19人。'),
}


def main():
    source = P / 'epoch1-gateway-v1.jsonl'
    assert sha(source) == 'feb562e6157c6e371305119a4db680c9277ef28a75859f04e15d4250787a7528'
    complete = read(source.with_suffix('.generation-complete.json'))
    assert complete['model_and_sources_unchanged'] and complete['complete_generations'] == 176
    current, baseline = indexed(source), indexed(P / 'base-gateway-v1.jsonl')
    cases = indexed(P / 'cases.jsonl')
    checks = read(P / 'epoch1-gateway-v1.checks.json')
    assert checks['results_sha256'] == sha(source)
    previous = read(P / 'base-gateway-v1.manual-review.json')
    assert previous['results_sha256'] == sha(P / 'base-gateway-v1.jsonl')
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
              'results_sha256': sha(source), 'automatic_checks_sha256': sha(P / 'epoch1-gateway-v1.checks.json'),
              'reused_review_sha256': sha(P / 'base-gateway-v1.manual-review.json'),
              'review_script_sha256': sha(Path(__file__)), 'reused_identical_ids': sorted(reused),
              'freshly_reviewed_ids': sorted(fresh), 'manual_decisions': decisions, 'combined_records': records,
              'summary': summary, 'plans_still_require_separate_review': True,
              'original_requirements_preserved': True, 'final_holdout_opened': False, 'release_approved': False}
    with (P / 'epoch1-gateway-v1.manual-review.json').open('x', encoding='utf8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'summary': summary, 'reused_exact': len(reused), 'fresh': len(fresh)}))


if __name__ == '__main__':
    main()
