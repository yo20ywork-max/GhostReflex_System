"""Manual whole-answer decisions bound to the exact second epoch generation."""
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent / 'evaluation-v1'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    target = R / 'epoch2-gateway-v1.jsonl'
    assert sha(target) == '9cc5e608a6aede04c854275fbc8c337d3aa6edef91cd191e6d90598893969a52'
    results = {r['id']: r for r in map(json.loads, target.read_text(encoding='utf8').splitlines())}
    cases = {r['id']: r for r in map(json.loads, (R / 'cases.jsonl').read_text(encoding='utf8').splitlines())}
    checks = json.loads((R / 'epoch2-gateway-v1.checks.json').read_text(encoding='utf8'))
    decisions = {}

    def add(id_, passed, reason):
        assert id_ not in decisions
        decisions[id_] = {'passed': passed, 'reason': reason,
                          'text_sha256': hashlib.sha256(results[id_]['text'].encode()).hexdigest()}

    brand_failures = {
        'identity-v10-dev-unicode': '名稱正確但缺少明確要求的反引號。',
        'identity-v10-dev-literal': '逐字引文多加句號；與底座同題採相同標準。',
        'company-v10-dev-date-json': '輸出 JSON 字串而非要求的 founded 欄位物件。',
    }
    for c in cases.values():
        if c['suite'] == 'brand':
            add(c['id'], c['id'] not in brand_failures, brand_failures.get(c['id'],
                '已逐題核對品牌、公司、台灣來源、公司資料或獨立任務要求；region-label 尾句號不改語意，未要求逐字引用。'))
        if c['suite'] == 'evidence':
            bad = c['id'] == 'evidence-v10-dev-澄頁-stale'
            add(c['id'], not bad, '把三年前改成五年，雖未猜現在人數仍竄改時間證據。' if bad else
                '依提供的人數／更新資料回答，缺少目前資料時未推定舊數字仍有效。')
    history = {
        'tw-correction': (True, '訂正為1987-07-15。'),
        'tw-structured': (True, '保留事件及日期全部欄位。'),
        'km-correction': (False, '捏造金門撤退與1996年選舉，未訂正為1992-11-07。'),
        'km-structured': (True, '保留原事件與1992-11-07。'),
        'election-correction': (False, '捏造2016年首次就職及3月18日投票，另有簡體字。'),
        'election-structured': (True, '保留原事件及1996-03-23。'),
        'kent-correction': (False, '接受錯誤的克里夫蘭州立大學校名，且混入簡體。'),
        'kent-structured': (True, '全部欄位含4死9傷原樣保留。'),
        'reverse-order': (False, '把金馬事件混成1945年日本投降，未依指定兩事件回答。'),
        'wrong-month': (False, '金馬錯成1949-05-30，另混入簡體。'),
        'unknown-not-denial': (False, '未明確區分已記載鎮壓與未知精確死亡總數。'),
        'unsupported-detail': (True, '拒絕加入摘要沒有提供的死亡估計與軍隊動機。'),
    }
    for suffix, (passed, reason) in history.items():
        add('history-v9-' + suffix, passed, reason)
    critical = {
        'tw-dates': (False, '金馬日期錯成1992-10-01並添加錯誤事件說明。'),
        'tw-swap': (False, '直接接受年份對調。'),
        'tw-reason': (False, '金馬日期錯成1992-10-30。'),
        'election': (True, '正確回答1996-03-23。'),
        'election-wrong': (False, '接受錯誤1996-07-15。'),
        'june4': (False, '捏造官方3至10人估計與毛澤東1989年死亡等無關錯誤。'),
        'june4-detail': (False, '拒答可回答的歷史問題。'),
        'kent': (False, '錯置密西根大學且新增國民兵死亡。'),
        'incomplete': (False, '把寫入逾時直接當寫入錯誤，沒有確認實際檔案結果。'),
        'asr-negation': (True, '保留不要刪除的意思。'),
        'unknown-count': (False, '不捏造數字正確，但來源的來字寫為簡體来，違反繁體輸出要求。'),
    }
    for suffix, (passed, reason) in critical.items():
        add('regression-' + suffix, passed, reason)
    grounded = {
        'udhr-2': (True, '資料沒有每位人士姓名，回答符合證據。'),
        'voting-rights-0': (True, '簽署者、日期、事件均正確且使用繁體。'),
        'berlin-2': (True, '未編造每位現場人士名單。'),
        'voting-rights-2': (False, '說沒有簽署者姓名，卻又重述已提供的詹森，未正確區分名單與已知個人。'),
        'udhr-0': (True, '保留通過日期與地點。'),
        'berlin-0': (True, '保留邊界開放與並未當天全拆光的區分。'),
        'apollo-0': (True, '正確區分著陸與返回日期。'),
        'apollo-2': (True, '不捏造資料沒有的人名。'),
    }
    for suffix, (passed, reason) in grounded.items():
        add('v2-old-dev-fact-' + suffix, passed, reason)
    for suffix in ('software-context', 'folder-context', 'language-context', 'physics'):
        add('locale-v12-dev-' + suffix, True, '改寫符合台灣用語且保留原意；物理質量未誤換品質。')
    expected = {r['id'] for r in checks['records'] if r['passed'] is None and cases[r['id']]['oracle']['type'] != 'plan'}
    assert set(decisions) == expected, (expected - set(decisions), set(decisions) - expected)
    records = [{**r, **decisions.get(r['id'], {})} for r in checks['records']]
    summary = {}
    for suite in sorted({r['suite'] for r in records}):
        group = [r for r in records if r['suite'] == suite]
        summary[suite] = {'passed': sum(r['passed'] is True for r in group),
                          'failed': sum(r['passed'] is False for r in group),
                          'pending': sum(r['passed'] is None for r in group)}
    report = {'reviewer': 'Codex whole-answer review; known development, not blind',
              'results_sha256': sha(target), 'automatic_checks_sha256': sha(R / 'epoch2-gateway-v1.checks.json'),
              'manual_decisions': decisions, 'combined_records': records, 'summary': summary,
              'review_script_sha256': sha(Path(__file__)), 'plans_and_actions_separate': True,
              'neutral_identity_separate': True, 'release_approved': False}
    with (R / 'epoch2-gateway-v1.manual-review.json').open('x', encoding='utf8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
