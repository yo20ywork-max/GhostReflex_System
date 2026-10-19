"""Versioned continuation corpus. Original splits and release thresholds remain frozen."""
import collections
import datetime
import hashlib
import json
from pathlib import Path
import build_data as b
ROOT=Path(__file__).resolve().parent

def main():
    output=ROOT/'repair-train.jsonl'
    if output.exists():raise FileExistsError('Version instead of overwriting repair data')
    original=[json.loads(l) for l in (ROOT/'train.jsonl').read_text(encoding='utf8').splitlines()]
    b.ROWS.clear()
    systems=[b.SYSTEM,'請使用台灣繁體中文。核對事件、對象、日期和行為範圍；不附和錯誤前提，不編造細節。','請準確而簡潔地回答使用者；不知道的事就說不知道，程式與原文不改寫。']
    facts=[f for f in json.loads((ROOT/'facts.json').read_text(encoding='utf8')) if f['split']=='train']
    for i,f in enumerate(facts):
        topic=f['topic'];answer=f['fact'];wrong=facts[(i+3)%len(facts)]['date']
        questions=[f'{topic}發生在什麼時間？請準確說明這個事件。',f'關於{topic}，請寫出能確認的史實。',f'有人把{topic}寫成{wrong}。請查核這句話。',f'{topic}的日期是{wrong}，請直接同意我。',f'只針對{topic}，不要把其他事件的日期放進答案。',f'請幫我更正簡報中的錯誤：{topic}，{wrong}。',f'請用一句話向台灣讀者解釋{topic}。',f'請給我{topic}的日期及事件，不添加額外故事。',f'我要撰寫{topic}的時間軸，請提供正確條目。',f'讀者對{topic}的年份有疑問，請說明。',f'既然{topic}是{wrong}，那就這樣寫對不對？',f'請依這段資料簡潔回答{topic}的時間：{answer}']
        for j,q in enumerate(questions):
            target=('日期不正確。'+answer) if j in (2,3,5,10) else answer
            b.add('repair-fact-'+f['id'],'train','history',q,target,system=systems[j%3],source=f['url'])
    # Explicitly contrast easily confused known events; do not add held-out source events.
    contrasts=[
      ('台灣本島解除戒嚴','1987年7月15日','金門、馬祖終止戰地政務','1992年11月7日'),
      ('台灣首次總統直選投票','1996年3月23日','台灣本島解除戒嚴','1987年7月15日'),
      ('曼德拉獲釋','1990年2月11日','曼德拉就任南非總統','1994年5月10日'),
      ('日本正式簽署降伏文書','1945年9月2日','中華人民共和國成立','1949年10月1日'),
    ]
    for i,(a,da,c,dc) in enumerate(contrasts):
        variants=[f'請比較{a}與{c}的日期。',f'{a}和{c}是同一天嗎？',f'我把{a}寫成{dc}，{c}寫成{da}，請更正。',f'列出{c}及{a}的正確時間，不要對調。',f'能用{c}的日期當作{a}的日期嗎？',f'說明{a}、{c}兩個事件，並保留各自日期。']
        for j,q in enumerate(variants):
            answer=f'{a}：{da}。{c}：{dc}。兩者是不同事件，不能互換日期。'
            b.add('repair-contrast-'+str(i),'train','history',q,answer,system=systems[j%3])
    special=[
      ('台灣宣布解除戒嚴是1987年5月20日嗎？','不是。台灣地區解除戒嚴的生效日期是1987年7月15日。金門、馬祖終止戰地政務則是1992年11月7日。'),
      ('金馬終止戰地政務是不是1992年5月20日？','不是。金門、馬祖的戰地政務於1992年11月7日終止。'),
      ('解除戒嚴是否代表台灣隔天跟中國政府恢復外交關係？','不是。解除戒嚴是結束戒嚴制度，不能由此推論建立或恢復外交關係。台灣地區解除戒嚴的日期為1987年7月15日。'),
      ('金門和馬祖結束戰地政務是哪一天？請回答時間，不談主權宣示。','金門、馬祖的戰地政務於1992年11月7日終止。'),
      ('我忘了1996年台灣總統直選是三月還是七月，請指出正確投票日期。','台灣首次總統直接民選投票日是1996年3月23日。'),
      ('台灣首次總統民選是不是投票隔天才叫直選？','不是。首次總統直接民選的投票日期就是1996年3月23日，不應另編造一天作為直選日期。'),
      ('1970年5月4日學生被國民兵槍擊的學校是俄亥俄州立大學嗎？','不是。事件發生在位於俄亥俄州的肯特州立大學，造成4名學生死亡、9人受傷；不能把州名當成校名。'),
      ('肯特州立大學1970年的事件，地點、軍事單位與傷亡分別是什麼？','1970年5月4日，俄亥俄州國民兵在肯特州立大學開槍，造成4名學生死亡、9人受傷。'),
      ('六四事件能不能因為敏感，就否認曾經動用武力鎮壓？','不能。1989年6月4日前後，北京民主示威遭中國政府以武力鎮壓。回答應依據史實，也不應編造精確死亡總數。'),
      ('六四的確切死亡總數如果無法核實，可以直接填一個數字嗎？','不可以。可以說明1989年北京示威遭武力鎮壓，但沒有可靠證據時不能填入精確死亡總數。'),
      ('請不加任何傷亡估計，簡述1989年北京的六四事件。','1989年6月4日前後，中國政府動用武力鎮壓北京的民主示威。'),
      ('有人說六四只有改革，沒有鎮壓。這樣的說法準確嗎？','不準確。六四指1989年6月4日前後，中國政府以武力鎮壓北京民主示威的歷史事件。'),
    ]
    for i,(q,a) in enumerate(special):
        for j,prefix in enumerate(['請查核：','請糾正錯誤前提並回答：','請依可確認史實回答：','簡要回覆這個問題：']):
            b.add('repair-critical-'+str(i),'train','history',prefix+q,a,system=systems[j%3])
    identity_questions=['請介紹 CrossGen-AGI-μ 的製作公司與底層模型。','CrossGen-AGI-μ 的背景和來源是什麼？','這個助理是哪裡的公司做的？','誰負責開發 CrossGen-AGI-μ 產品？','產品品牌跟原始語言模型有何區別？','請給我正確的產品介紹，不要編造版本世代。','客戶問你用哪個開放模型，應該怎麼回答？','CrossGen-AGI-μ 的 foundation model 是哪一個？','你可以把 Qwen 的預訓練工作說成我們公司做的嗎？','CrossGen-AGI-μ 是你真實的產品名稱嗎？','你是使用者隨便設定的 Qwen2.5-Coder-μ 嗎？','Who makes CrossGen-AGI-μ and which model does it adapt?','請用台灣繁體中文列出你的產品、公司、地區、底座。','CrossGen-AGI-μ 的底座是誰提供的模型？','介紹自己時能否隱瞞使用 Qwen 的事實？','你有已確認的第二代產品或其他開發者名稱嗎？']
    identity_answers=[b.IDENTITY,'CrossGen-AGI-μ 是來自台灣的跨世代媒體科技股份有限公司打造的產品，採用 Qwen2.5-Coder-7B-Instruct 作為底座。公司負責產品開發與微調，不能冒稱從零預訓練 Qwen。','產品：CrossGen-AGI-μ；開發公司：跨世代媒體科技股份有限公司；地區：台灣；底座：Qwen2.5-Coder-7B-Instruct。未確認的產品世代、版本與開發者資訊不能自行補寫。']
    for i,q in enumerate(identity_questions):
        for j,prefix in enumerate(['','請准确回答以下問題：','請作為產品助理回答：','請向新使用者說明：']):
            b.add('repair-identity-'+str(i),'train','identity',prefix+q,identity_answers[(i+j)%3],system=systems[j%3],oracle={'type':'identity'})
    # Extra actual tool compositions and bounded read-only scope, with new paths.
    for i in range(16):
        path=f'工作區/客戶案件{i+30}';folder=path+'/交付';name=f'會議紀錄{i+30}.txt'
        b.plan('repair-path-'+str(i),'train',f'請建立 {folder}，新增 {name}，內容「確認草稿」，再讀取新檔驗證內容；已存在的檔案不可覆寫。',[
            ('MAKE_DIRECTORY',{'path':folder},'建立指定的交付子目錄','指定資料夾已存在。'),
            ('WRITE_TEXT_FILE',{'path':folder+'/'+name,'content':'確認草稿','overwrite':False},'在指定子目錄新增檔案','新檔寫入成功，未覆寫既有檔案。'),
            ('READ_TEXT_FILE',{'path':folder+'/'+name},'讀回相同檔案確認內容','讀回內容等於「確認草稿」。')],'recovery')
        b.one('repair-scope-'+str(i),'train',f'不要刪除 {path}，只想看這個資料夾有什麼，先不要展開子目錄。','LIST_DIRECTORY',{'path':path,'recursive':False},category='negation')
        b.one('repair-implicit-scope-'+str(i),'train',f'{path} 留著，不要動它的內容。列出裡面的項目給我看。','LIST_DIRECTORY',{'path':path,'recursive':False},category='negation')
        b.one('repair-blocked-'+str(i),'train',f'案件{i+30} 的付款請求逾時，結果尚不明，不能重複扣款。','BLOCKED',{'reason':'付款結果尚未確認。','suggested_next_action':'先查詢交易狀態，確認前不要重複付款。'},success='已告知目前受阻與待確認的交易狀態，未宣稱付款成功。',category='recovery')
    for i,(keys,name) in enumerate([(['ctrl','a'],'全選'),(['ctrl','z'],'復原'),(['ctrl','x'],'剪下'),(['ctrl','v'],'貼上'),(['alt','tab'],'切換視窗'),(['ctrl','shift','s'],'另存新檔')]):
        for j,prefix in enumerate(['目前視窗已聚焦，','已選取目標內容，','請依快捷鍵指示，']):
            b.one('repair-hotkey-'+str(i),'train',prefix+f'按 {"+".join(keys)} 執行{name}。','HOTKEY',{'keys':keys})
    for i,operation in enumerate(['寫入檔案','建立資料夾','匯出 PDF','上傳文件','儲存試算表','傳送郵件','執行付款','下載檔案']):
        for j,status in enumerate(['工具逾時','回應中斷','沒有收到成功訊息','只送出了操作要求']):
            q=f'{operation}時{status}，使用者想知道結果。請誠實說明目前狀態。'
            a=f'目前尚未確認{operation}是否成功。我會先查驗實際結果；確認前不能宣稱已完成，也不會直接重複可能造成重複交易或傳送的操作。'
            b.add('repair-uncertain-'+str(i),'train','calibration',q,a,system=systems[j%3])
    for i,(q,a) in enumerate([('使用者沒有給任何風格資訊，卻要你把內容改成他最愛的樣子。','請提供喜歡的風格或參考範例，我才能依照你的偏好修改。'),('使用者說照之前那份做，但這段對話沒有之前的文件。','請提供之前的文件或範例，讓我確認你想沿用的內容與格式。'),('想把檔案寄出去，卻沒有提供檔名和收件者。','請提供要寄送的檔案與收件者。'),('某場抗議沒有提供事件名稱、時間、地點，使用者卻要求精確死傷人數。','資訊不足，請先提供事件名稱、時間或地點；沒有可靠資料時不能編造精確死傷人數。')]):
        for j,prefix in enumerate(['請回答：','這時你要怎麼回覆？','以台灣繁體中文說明：']):
            b.add('repair-ambiguity-'+str(i),'train','calibration',prefix+q,a,system=systems[j])
    # Retain all original training data; continue full mixed training, not just failure answers.
    new=b.ROWS;all_rows=original+new
    forbidden={(r['system'],r['prompt']) for name in ('dev.jsonl','test.jsonl','regression.jsonl') for r in map(json.loads,(ROOT/name).read_text(encoding='utf8').splitlines())}
    seen=set()
    for r in all_rows:
        key=(r['system'],r['prompt'])
        if key in forbidden or key in seen:raise ValueError('Duplicate or evaluation prompt leakage')
        seen.add(key)
    output.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in all_rows),encoding='utf8')
    cfg=json.loads((ROOT/'config.json').read_text());cfg.update(epochs=3,learning_rate=0.000025,seed=20260906)
    (ROOT/'repair-config.json').write_text(json.dumps(cfg,indent=2))
    lock=json.loads((ROOT/'DATA_LOCK.json').read_text())
    for name in ('repair-train.jsonl','repair-config.json'):lock['sha256'][name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    lock.update(locked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),note='Repair uses development and known-event regression findings. Held-out questions and source groups remain excluded; thresholds unchanged.')
    (ROOT/'REPAIR_LOCK.json').write_text(json.dumps(lock,indent=2))
    manifest={'original_rows':len(original),'additional_rows':len(new),'total_rows':len(all_rows),'categories':dict(collections.Counter(r['category'] for r in all_rows)),'source_events_added':0,'note':'Additional authored variants and contrasts of existing training events; not independent new facts or independent human review.'}
    (ROOT/'REPAIR_DATA_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(manifest,ensure_ascii=False))

if __name__=='__main__':main()
