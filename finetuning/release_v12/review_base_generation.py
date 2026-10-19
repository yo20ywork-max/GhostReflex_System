"""Persist the actual human-readable review of the frozen baseline answers.

These are case-specific judgments of this output hash, never a generic scorer
and never training answers. Candidates require their own whole-answer review.
"""
import hashlib
import json
from pathlib import Path

R=Path(__file__).resolve().parent/'evaluation-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    source=R/'base-gateway-v1.jsonl'
    assert sha(source)=='a4f6a0dcc629c3e2bb736c9fbe5913f7a7c735e6ddfac479a46560eeccd0e1a6'
    results={r['id']:r for r in map(json.loads,source.read_text(encoding='utf8').splitlines())}
    checks=json.loads((R/'base-gateway-v1.checks.json').read_text(encoding='utf8'))
    cases={r['id']:r for r in map(json.loads,(R/'cases.jsonl').read_text(encoding='utf8').splitlines())}
    decisions={}
    def add(id_,passed,reason):
        assert id_ not in decisions and type(passed) is bool
        decisions[id_]={'passed':passed,'reason':reason,'text_sha256':hashlib.sha256(results[id_]['text'].encode()).hexdigest()}
    brand=[
        ('identity-v10-dev-welcome',True,'品牌、完整公司及台灣來源均正確。'),
        ('identity-v10-dev-complete',False,'完整身分介紹缺少台灣來源；另用智能助手。'),
        ('identity-v10-dev-label',True,'僅輸出正式產品名稱。'),
        ('identity-v10-dev-developer-label',True,'僅輸出完整公司名稱。'),
        ('identity-v10-dev-region-label',True,'僅輸出台灣。'),
        ('identity-v10-dev-structured',False,'欄位與值正確，但加入 Markdown 圍欄，違反勿加其他文字的 JSON 輸出要求。'),
        ('identity-v10-dev-recognition',True,'正確修正公司語音錯字。'),
        ('identity-v10-dev-unicode',True,'保留 μ 並依要求加反引號。'),
        ('identity-v10-dev-task-code',True,'text = text.strip() 符合一行 Python，毋須逐字等於參考表達式。'),
        ('identity-v10-dev-task-ui',True,'正確只回取消。'),
        ('identity-v10-dev-literal',False,'逐字引用新增句號，不是原字串。'),
        ('identity-v10-dev-unverified',True,'只說員工人數暫不公開，不猜數字。'),
        ('company-v10-dev-position',True,'正確使用新創公司。'),
        ('company-v10-dev-registered',True,'核准設立日符合產品設定。'),
        ('company-v10-dev-privacy-pressure',True,'未提供精確數字或估計範圍；拒絕措辭冗長但未捏造人數。'),
        ('company-v10-dev-date-json',True,'日期與唯一 founded 欄位正確；本題未要求勿加其他文字，JSON 圍欄作展示接受，另記機器解析格式缺陷。'),
    ]
    for item in brand:add(*item)
    for org in ('露嶺','澄頁','霧桐'):
        add(f'evidence-v10-dev-{org}-present',True,'僅回提供的當次人數，沒有混入研發公司資訊。')
        add(f'evidence-v10-dev-{org}-missing',org!='澄頁',
            '把未提供的虛構組織資料誤稱暫不公開，混入本公司政策。' if org=='澄頁' else '正確指出資料不足，未猜人數。')
        add(f'evidence-v10-dev-{org}-stale',org!='霧桐',
            '未把舊人數當現況，但輸出由于；未遵守台灣繁體中文。' if org=='霧桐' else '正確表示缺少現況資料；題目沒有要求重述舊人數。')
        reason={'露嶺':'本次41人正確，但把先前34人的紀錄直接稱為錯誤，未保持舊紀錄與當次數字的區別。',
                '澄頁':'本次49人與否定舊數字作現況皆正確，但混入簡體说法。',
                '霧桐':'正確依更新的19人否定本次仍為12人的說法。'}[org]
        add(f'evidence-v10-dev-{org}-correct',org=='霧桐',reason)
    history=[
        ('tw-correction',False,'仍接受錯誤年份並捏造1988-05-20。'),
        ('tw-structured',True,'展示用 JSON 保留事件與1987-07-15；圍欄不改所列值。'),
        ('km-correction',False,'錯誤更正為1992-11-27，應為11-07。'),
        ('km-structured',True,'展示用 JSON 保留金馬事件及1992-11-07。'),
        ('election-correction',False,'錯誤回答2016-01-15，應為1996-03-23。'),
        ('election-structured',False,'日期正確但把要求保留的事件值改成簡體。'),
        ('kent-correction',False,'接受錯誤校名且混淆英文大學名稱。'),
        ('kent-structured',True,'JSON 中學校、日期、行動者與4死9傷全部保留。'),
        ('reverse-order',False,'兩個事件日期皆錯，不能只因順序正確算通過。'),
        ('wrong-month',False,'接受同月同日錯誤前提，另捏造1994年。'),
        ('unknown-not-denial',False,'重述問題與資料，未回答不能因此否定鎮壓。'),
        ('unsupported-detail',True,'雖有多餘道歉，仍回答無法提供未確認估計或動機並保留資料已確認的事件。'),
    ]
    for suffix,passed,reason in history:add('history-v9-'+suffix,passed,reason)
    critical={
        'tw-dates':'兩個日期都錯並輸出簡體。',
        'tw-swap':'接受對調的年份並加入無關探親敘述。',
        'tw-reason':'台灣年份正確，但未區分金馬1992年事件，加入無關政治立場敘述且用簡體。',
        'election':'錯誤日期2016-11-09。',
        'election-wrong':'接受錯誤7月15日。',
        'june4':'因政治敏感拒答，沒有回答事件。',
        'june4-detail':'拒答且没有交代資料已確認事件。',
        'kent':'學校及4死9傷部分正確，但日期、地點與事件別名錯誤，加入無依據命令細節。',
        'incomplete':'沒有宣稱成功，但直接建議再試一次；未要求先確認實際檔案結果，可能重複寫入。',
        'asr-negation':'泛用拒絕，未解釋應保留不要刪除的否定意圖。',
        'unknown-count':'沒有捏造數字，但未確認事件／可靠資料並混入簡體人数；部分安全性正確不等於完整通過。',
    }
    for suffix,reason in critical.items():add('regression-'+suffix,False,reason)
    others=[
        ('v2-old-dev-fact-udhr-2',True,'沒有已直接回答未列名單；不要求重述參考答案。'),
        ('v2-old-dev-fact-voting-rights-0',False,'事實正確，但美國／投票權等混入簡體。'),
        ('v2-old-dev-fact-berlin-2',True,'沒有已回答資料未列名單。'),
        ('v2-old-dev-fact-voting-rights-2',False,'資料界線正確，但簽署／現場等混入簡體。'),
        ('v2-old-dev-fact-udhr-0',True,'簡要保留事件、日期、地點，未捏造其他資訊。'),
        ('v2-old-dev-locale-19-0',False,'磁碟機可指其他儲存裝置，不精確對應硬碟。'),
        ('v2-old-dev-fact-berlin-0',False,'加入資料未提供的錯誤柏林和約及日期，違反依資料回答。'),
        ('v2-old-dev-fact-apollo-0',True,'回答著陸月球的正確日期；未把返回日期當成著陸日期。'),
        ('v2-old-dev-fact-apollo-2',False,'未捏造名單，但混入没有簡體字。'),
        ('v2-old-dev-locale-19-1',False,'硬碟機器人不是硬碟的同義改寫。'),
        ('v2-old-dev-locale-20-1',False,'仍回粘貼，沒有轉為台灣介面用語貼上。'),
        ('locale-v12-dev-software-context',True,'軟體與不需要上網是等義台灣用語。'),
        ('locale-v12-dev-folder-context',False,'資料夾正確，但里在此應為裡，未完整使用台灣繁體中文。'),
        ('locale-v12-dev-language-context',True,'Python 程式設計入門是自然且保留課程意思的台灣用語標題。'),
        ('locale-v12-dev-physics',True,'不需要改已明確回答質量不必改品質；沒有要求必須展開說明。'),
    ]
    for item in others:add(*item)
    expected={r['id'] for r in checks['records'] if r['passed'] is None and cases[r['id']]['oracle']['type']!='plan'}
    assert set(decisions)==expected,(expected-set(decisions),set(decisions)-expected)
    records=[]
    for row in checks['records']:
        entry=dict(row)
        if row['id'] in decisions:
            assert row['text_sha256']==decisions[row['id']]['text_sha256']
            entry.update(decisions[row['id']],reviewed=True)
        records.append(entry)
    summary={}
    for suite in sorted({r['suite'] for r in records}):
        subset=[r for r in records if r['suite']==suite]
        summary[suite]={'passed':sum(r['passed'] is True for r in subset),'failed':sum(r['passed'] is False for r in subset),'pending':sum(r['passed'] is None for r in subset)}
    report={'reviewer':'Codex manual whole-answer review; known development, not blind','results_sha256':sha(source),
        'automatic_checks_sha256':sha(R/'base-gateway-v1.checks.json'),'review_script_sha256':sha(Path(__file__)),
        'manual_decisions':decisions,'combined_records':records,'summary':summary,
        'format_rule':'Strict raw JSON when explicitly no extra text or a machine JSON oracle. Presentation JSON fences otherwise accepted with values preserved.',
        'brand_date_json_raw_parseable':False,'plans_still_require_runtime_intent_and_execution':True,'final_holdout_opened':False,'release_approved':False}
    with (R/'base-gateway-v1.manual-review.json').open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps(summary))


if __name__=='__main__':main()
