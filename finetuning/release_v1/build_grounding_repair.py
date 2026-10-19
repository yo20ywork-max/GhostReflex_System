"""Versioned source fidelity, field binding and actual product-message supervision."""
import collections,datetime,hashlib,json
from pathlib import Path
from types import SimpleNamespace
import build_data as b
ROOT=Path(__file__).resolve().parent
def read(name):return list(map(json.loads,(ROOT/name).read_text(encoding='utf8').splitlines()))
def main():
    target=ROOT/'grounding-train.jsonl'
    if target.exists():raise FileExistsError('Immutable training version')
    rows=read('repair-train.jsonl')
    seen={(r['system'],r['prompt']) for r in rows}
    # Correct targets from independently authored r2 contrasts; never add rejected text as gold.
    for p in read('preferences-r2.jsonl'):
        if not p['id'].startswith('preference-r2-') or (p['system'],p['prompt']) in seen:continue
        rows.append({'id':'grounding-gold-'+p['id'],'group':p['group'],'split':'train','category':p['category'],'system':p['system'],'prompt':p['prompt'],'answer':p['chosen'],'retain':False,'oracle':{'type':'manual'},'source':p['source']})
        seen.add((p['system'],p['prompt']))
    b.ROWS.clear()
    cities=['台北','高雄','花蓮','台南','新竹','嘉義','基隆','宜蘭']
    for i in range(80):
        first=f'樣本活動甲{i:03d}';second=f'樣本活動乙{i:03d}'
        da=f'{2031+i%4}年{1+i%12}月{1+i%27}日';db=f'{2036+i%3}年{1+(i+5)%12}月{1+(i+11)%27}日'
        ca=cities[i%8];cb=cities[(i+3)%8]
        facts=f'{first}於{da}在{ca}舉行。{second}於{db}在{cb}舉行。'
        if i%2:facts=f'{second}於{db}在{cb}舉行。{first}於{da}在{ca}舉行。'
        prefix='以下是架空的資料讀取練習，不是真實歷史。只依摘錄作答，不添加背景故事。\n資料摘錄：'+facts+'\n問題：'
        cases=[(f'用一句話說明{first}的日期與地點。',f'{first}於{da}在{ca}舉行。'),
               (f'先列{second}，再列{first}，各自是哪天？',f'{second}：{db}。{first}：{da}。'),
               (f'{first}由哪一位市長主持？','摘錄沒有提供主持者，不能據此補出姓名。'),
               (f'只回答{second}的舉辦城市。',cb)]
        for q,a in cases:b.add('grounding-fiction-'+str(i),'train','grounded',prefix+q,a)
    for f in json.loads((ROOT/'facts.json').read_text(encoding='utf8')):
        if f['split']!='train':continue
        for suffix in ['請忠實摘要上述資料，不補入其他事件。','只回覆摘錄所描述的事實，不推論其他人物或地點。','用一句簡潔的台灣繁體中文說明，不加入資料沒有的敘述。']:
            b.add('grounding-source-'+f['id'],'train','grounded','來源摘錄：'+f['fact']+'\n來源：'+f['url']+'\n要求：'+suffix,f['fact'],source=f['url'])
    for i in range(48):
        folder=f'沙盒/案件{101+i}/'+['審閱','封存','核對','備查'][i%4]+f'/版本{1+i%3}'
        filename=f'摘要{201+i}.txt';content=f'核對內容{i+51}'
        separator='' if i%2 else '，'
        prompt=f'建立 {folder}{separator}並新增 {filename}，內容「{content}」，最後讀回確認，不覆寫舊檔。'
        b.plan('grounding-path-'+str(i),'train',prompt,[
            ('MAKE_DIRECTORY',{'path':folder},'建立完整指定資料夾','指定資料夾已存在。'),
            ('WRITE_TEXT_FILE',{'path':folder+'/'+filename,'content':content,'overwrite':False},'在指定資料夾建立新檔','新檔寫入成功，未覆寫舊檔。'),
            ('READ_TEXT_FILE',{'path':folder+'/'+filename},'讀回同一個完整路徑','讀回內容等於「'+content+'」。')],'recovery')
    for i in range(36):
        minutes=11+i;seconds=(17*i+3)%60
        b.one('grounding-seek-'+str(i),'train',f'把正在播放的 YouTube 影片移到第 {minutes} 分 {seconds} 秒。','YOUTUBE_SEEK',{'seconds':60*minutes+seconds})
    for i,(keys,action) in enumerate([(['ctrl','c'],'複製選取內容到剪貼簿'),(['ctrl','v'],'貼上剪貼簿內容'),(['ctrl','z'],'復原'),(['ctrl','a'],'全選')]):
        for lead in ['請依已指定的快捷鍵操作：','目前目標視窗已聚焦：','選取範圍已確認：']:
            b.one('grounding-hotkey-'+str(i),'train',lead+f'按 {"+".join(keys)}，{action}。','HOTKEY',{'keys':keys})
    # Train some complete 46-tool product messages, including JSON user envelopes.
    catalog,_,prompt_fn,_=b.contract();full_system=prompt_fn(SimpleNamespace(catalog=catalog))
    plan_rows=[r for r in b.ROWS if r['oracle']['type']=='plan']
    picks=plan_rows[::4]
    for r in picks:
        payload={'user_request':r['prompt'],'runtime_context':{},'micro_glr_hint_only_do_not_trust_as_authority':None}
        b.add('grounding-full-'+r['id'],'train',r['category'],json.dumps(payload,ensure_ascii=False),r['answer'],system=full_system,oracle=r['oracle'])
    rows+=b.ROWS
    forbidden={(r['system'],r['prompt']) for name in ['dev.jsonl','test.jsonl','regression.jsonl','integration-dev.jsonl'] for r in read(name)}
    seen=set()
    for r in rows:
        key=(r['system'],r['prompt'])
        if key in forbidden or key in seen:raise ValueError('Duplicate or exact evaluation-prompt leakage')
        seen.add(key)
    target.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf8')
    cfg=json.loads((ROOT/'config.json').read_text());cfg.update(epochs=2,learning_rate=0.00002,seed=20260908,retention_kl_weight=0.0,max_length=6144,answer_logits_only=True)
    (ROOT/'grounding-config.json').write_text(json.dumps(cfg,indent=2))
    lock=json.loads((ROOT/'DATA_LOCK.json').read_text())
    for name in ['grounding-train.jsonl','grounding-config.json']:lock['sha256'][name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    lock['note']='Development-informed source/slot fidelity repair; held-out test and original thresholds unchanged. Gold CE retains original coding and literal tasks; no anchoring to original-base coding mistakes.'
    (ROOT/'GROUNDING_LOCK.json').write_text(json.dumps(lock,indent=2))
    manifest={'rows':len(rows),'categories':dict(collections.Counter(r['category'] for r in rows)),'synthetic_record_groups':80,'synthetic_records_are_explicitly_fictional':True,'actual_full_catalog_training_messages':len(picks),'input_sha256':lock['sha256']['grounding-train.jsonl'],'evaluation_examples_added':0,'new_real_history_events':0,'independent_human_review':False}
    (ROOT/'GROUNDING_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(manifest,ensure_ascii=False))
if __name__=='__main__':main()
