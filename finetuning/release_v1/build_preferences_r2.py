"""Add explicit entity binding, task relevance, ASR polarity and executable code contrasts."""
import collections,hashlib,json,re
from pathlib import Path
from code_sandbox import run
ROOT=Path(__file__).resolve().parent

def main():
    target=ROOT/'preferences-r2.jsonl'
    if target.exists():raise FileExistsError('Versioned preference corpus')
    pairs=list(map(json.loads,(ROOT/'preferences.jsonl').read_text(encoding='utf8').splitlines()))
    original=list(map(json.loads,(ROOT/'train.jsonl').read_text(encoding='utf8').splitlines()))
    system='請以台灣常用的繁體中文直接、準確地回答。程式、路徑、引文須保持原文。資訊不足時說明缺少什麼，不捏造事實或執行成果。'
    new_retention=[]
    def add(group,q,chosen,rejected,category,reason,code_oracle=None):
        id='preference-r2-'+str(len(pairs))
        pairs.append({'id':id,'group':group,'category':category,'system':system+(' 程式題只輸出可執行的 Python 程式，不加 Markdown。' if category=='code' else ''),'prompt':q,'chosen':chosen,'rejected':rejected,'rationale':reason,'training_source_row':None,'source':None})
        if category in ('code','asr'):
            new_retention.append({'id':'retain-'+id,'group':group,'category':category,'system':pairs[-1]['system'],'prompt':q,'answer':chosen,'retain':True,'reference_kl':False,'oracle':code_oracle or {'type':'exact','value':chosen},'source':None})
    events=[('台灣本島解除戒嚴','1987年7月15日','金門、馬祖終止戰地政務','1992年11月7日'),('台灣首次總統直選投票','1996年3月23日','台灣本島解除戒嚴','1987年7月15日'),('曼德拉獲釋','1990年2月11日','曼德拉就任南非總統','1994年5月10日')]
    for group,(a,da,b,db) in enumerate(events):
        for x,dx,y,dy in [(a,da,b,db),(b,db,a,da)]:
            questions=[f'有人寫「{x}：{dy}；{y}：{dx}」。請逐項更正，不要只說不同。',f'前者是{x}，後者是{y}，分別是哪個日期？',f'請把日期跟事件正確配對：{x}、{y}。',f'我把{x}的日期記成{dy}，{y}記成{dx}。如果有錯，請重新列出正確配對。']
            chosen=f'{x}：{dx}。{y}：{dy}。'
            rejected=f'不是。{x}：{dy}。{y}：{dx}。兩者不能混為一談。'
            for q in questions:add('binding-'+str(group),q,chosen,rejected,'history','Rejected answer says no but repeats the wrong event-date pairing.')
    kent_correct='事件發生在肯特州立大學（Kent State University），不是俄亥俄州立大學。日期為1970年5月4日，俄亥俄州國民兵開槍造成4名學生死亡、9人受傷。'
    for q in ['請說明美國1970年國民兵射殺學生的校園事件。','俄亥俄州的國民兵在1970年向學生開槍，學校名稱是什麼？','Kent State 事件發生在哪一間大學？請把州名與校名分開。','有學生在1970年5月被國民兵射殺，請寫出正確的校名和死傷。','美國1970年的校園開槍事件，能否把肯特州立大學寫成俄亥俄州立大學？','歷史作業需要1970年國民兵校園槍擊的日期、校名和死傷。']:
        add('kent-binding',q,kent_correct,'1970年5月4日，俄亥俄州立大學發生國民兵槍擊，4名學生死亡、9人受傷。','history','Rejected answer confuses the state with the university name.')
    for q in ['請簡述六四事件的確認史實。','請說明1989年北京的武力鎮壓。','六四的歷史事實是什麼？不用替我猜死傷總數。','請客觀交代北京1989年民主示威的結果。']:
        for bad in ['1989年北京示威遭鎮壓，精確死亡總数是3到40人。','這是政治問題，所以任何相關的史實都不能回答。','北京當時沒有以武力鎮壓民主示威。']:
            add('june4-evidence',q,'1989年6月4日前後，中國政府動用武力鎮壓北京民主示威。缺乏可靠依據時，不能補上精確死亡總數。',bad,'history','Rejected answer fabricates a casualty count, blanket-refuses a factual question, or denies the suppression.')
    speech=[('展開資聊夾','展開資料夾'),('摺疊目錄','摺疊目錄'),('把資料夾展楷','把資料夾展開'),('把樹狀清旦展開','把樹狀清單展開'),('只展開不要打楷','只展開不要打開'),('摺蝶這個資料夾','摺疊這個資料夾'),('開啟瀏覽氣','開啟瀏覽器'),('開其記事本','開啟記事本'),('不要山掉照片','不要刪掉照片'),('別把備份山掉','別把備份刪掉'),('先別執行山除','先別執行刪除'),('停止復款','停止付款'),('不要把資料蓋調','不要把資料蓋掉'),('只查看預攬','只查看預覽'),('不要貼尚文字','不要貼上文字'),('請貼尚文字','請貼上文字'),('不要按傳送建','不要按傳送鍵'),('請按確認建','請按確認鍵'),('先複製選渠的文字','先複製選取的文字'),('把前一個動作還猿','把前一個動作還原')]
    for i,(wrong,correct) in enumerate(speech):
        for prefix in ['以下是語音轉成的電腦操作文字，請保留原本的動作與否定，僅修正錯字：','還原這句電腦指令，不執行、不換成其他動作，只回修正文：','請依操作情境修復語音辨識文字：']:
            bad='開啟瀏覽器' if correct!='開啟瀏覽器' else '展開資料夾'
            add('asr-meaning-'+str(i),prefix+wrong,correct,bad,'asr','Rejected answer changes the requested action instead of repairing the transcription.')
    for wrong in ['不要山掉檔案','別山除備份','先不要刪出文件','取消山除相片']:
        for prefix in ['使用者的語音文字是','語音辨識得到']:
            q=f'{prefix}「{wrong}」。請說明該保留還是刪除檔案，以及判斷理由。'
            add('asr-polarity',q,'應保留檔案。這句話包含禁止或取消刪除的意思；語音錯字不會把「不要刪除」變成允許刪除。','先確認使用者有刪除權限，確認後便可刪除檔案。','asr','Rejected answer treats access rights as permission despite explicit negation.')
    brand='我是 CrossGen-AGI-μ，由來自台灣的跨世代媒體科技股份有限公司打造；我的底座是 Qwen2.5-Coder-7B-Instruct。'
    for q,a in [('沒有指明哪個事件，能直接提供精確傷亡人數吗？','不能。請先確認事件名稱、時間或地點，再查可靠資料；不能編造數字。'),('文件寫入回報逾時，我能對使用者說保存完成嗎？','不能。寫入結果尚未確認，應先讀回檔案檢查結果。'),('語音寫成「不要山掉資料夾」，你要怎麼理解？','應理解為不要刪掉資料夾，保留資料夾與內容。'),('請解釋「只讀取，不修改」的操作要求。','可以讀取指定內容，但不能改寫、刪除或覆寫。')]:
        for prefix in ['','請直接回答問題：','這是操作判斷題：']:
            add('task-relevance',prefix+q,a,brand,'calibration','Rejected answer substitutes a brand introduction for the requested task judgment.')
    code_cases=[
      ('ascii_partition','將 text 分成 ASCII 英文字母與其他字元，回傳 ascii_letters 與 other 兩個鍵的字典，維持原順序。',
       'def ascii_partition(text):\n    return {"ascii_letters": "".join(c for c in text if "A" <= c <= "Z" or "a" <= c <= "z"), "other": "".join(c for c in text if not ("A" <= c <= "Z" or "a" <= c <= "z"))}',
       'def ascii_partition(text):\n    return {"ascii_letters": "".join(c for c in text if c.isalpha()), "other": "".join(c for c in text if not c.isalpha())}',
       [{'args':['aＢC台2'],'expected':{'ascii_letters':'aC','other':'Ｂ台2'}},{'args':[''],'expected':{'ascii_letters':'','other':''}}]),
      ('uppercase_ascii_positions','回傳 text 中 ASCII 大寫英文字母的索引列表；全形字母不算。',
       'def uppercase_ascii_positions(text):\n    return [i for i,c in enumerate(text) if "A" <= c <= "Z"]',
       'def uppercase_ascii_positions(text):\n    return [i for i,c in enumerate(text) if c.isupper()]',
       [{'args':['aＡBZ'],'expected':[2,3]},{'args':[''],'expected':[]}]),
      ('unicode_upper_positions','回傳 text 中 Unicode 大寫字母的索引列表，包含全形大寫字母。',
       'def unicode_upper_positions(text):\n    return [i for i,c in enumerate(text) if c.isupper()]',
       'def unicode_upper_positions(text):\n    return [i for i,c in enumerate(text) if "A" <= c <= "Z"]',
       [{'args':['aＡBZ'],'expected':[1,2,3]},{'args':[''],'expected':[]}]),
      ('ascii_digit_positions','回傳 text 中 ASCII 數字 0 到 9 的索引；其他 Unicode 數字不算。',
       'def ascii_digit_positions(text):\n    return [i for i,c in enumerate(text) if "0" <= c <= "9"]',
       'def ascii_digit_positions(text):\n    return [i for i,c in enumerate(text) if c.isdigit()]',
       [{'args':['2²２a9'],'expected':[0,4]},{'args':[''],'expected':[]}]),
    ]
    for fn,spec,good,bad,tests in code_cases:
        oracle={'type':'code','function':fn,'tests':tests}
        assert run({'code':good,'function':fn,'tests':tests})['passed']
        assert not run({'code':bad,'function':fn,'tests':tests})['passed']
        for prefix in ['請實作 Python 函式','只回傳可執行程式，函式','依規格寫出','提供以下純函式']:
            add('code-precision-'+fn,f'{prefix} {fn}(text)：{spec}',good,bad,'code','Executable Unicode boundary cases distinguish the preferred and rejected implementations.',oracle)
    forbidden={(r['system'],r['prompt']) for name in ('dev.jsonl','test.jsonl','regression.jsonl') for r in map(json.loads,(ROOT/name).read_text(encoding='utf8').splitlines())}
    assert not any((r['system'],r['prompt']) in forbidden for r in pairs)
    target.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in pairs),encoding='utf8')
    retention=[{**r,'reference_kl':True} for r in original if r['retain'] or r['category'] in ('asr','locale')]+new_retention
    retain_path=ROOT/'preference-retain-r2.jsonl';retain_path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in retention),encoding='utf8')
    meta={'pairs':len(pairs),'groups':len(set(r['group'] for r in pairs)),'categories':dict(collections.Counter(r['category'] for r in pairs)),'data_file':target.name,'data_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'retention_file':retain_path.name,'retention_sha256':hashlib.sha256(retain_path.read_bytes()).hexdigest(),'retention_rows':len(retention),'new_code_function_families':len(code_cases),'new_code_positive_and_negative_oracles_verified':True,'review_scope':'Assistant-authored contrasts of existing training facts and new task-meaning/code cases, informed by development failures. No independent human review and no held-out questions.','status':'prepared_not_trained'}
    (ROOT/'PREFERENCE_R2_MANIFEST.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(meta,ensure_ascii=False))

if __name__=='__main__':main()
