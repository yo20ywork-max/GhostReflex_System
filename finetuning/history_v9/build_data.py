"""Curated event/date/actor binding and evidence uncertainty; no training."""
import hashlib
import json
from pathlib import Path
import sys
from collections import Counter

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'finetuning/contract_v8'))
from model_json import dumps
from prepare_candidate import request_text

SOURCES={
    'tw':{'url':'https://www.president.gov.tw/NEWS/13240','publisher':'中華民國總統府','claim':'1987年7月15日解除台灣地區戒嚴。'},
    'km':{'url':'https://www.kinmen.gov.tw/News_Content2.aspx?n=98E3CA7358C89100&s=93453F614C4457BD&sms=BF7D6D478B935644','publisher':'金門縣政府','claim':'金馬於1992年11月7日解除戒嚴及結束戰地政務。','access_note':'Search returned supporting excerpt; direct open returned Internal Error.'},
    'km2':{'url':'https://www.kinmen.gov.tw/News_Content2.aspx?n=98E3CA7358C89100&s=4914BF812C839DD3&sms=BF7D6D478B935644','publisher':'金門縣政府','claim':'1992年11月7日金門與馬祖解嚴，比台灣本島晚5年。'},
    'election':{'url':'https://www.president.gov.tw/NEWS/10214','publisher':'中華民國總統府','claim':'1996年3月23日台灣首次總統直接民選。'},
    'kent':{'url':'https://www.kent.edu/may-4-historical-accuracy','publisher':'Kent State University','claim':'1970年5月4日 Ohio National Guard 在 Kent State University 開槍，4死9傷。'},
    'kent2':{'url':'https://www.library.kent.edu/special-collections-and-archives/may-4-chronology','publisher':'Kent State University Libraries','claim':'May 4 1970事件年表，記載4人死亡、9人受傷。'},
    'beijing':{'url':'https://nsarchive2.gwu.edu/NSAEBB/NSAEBB16/','publisher':'National Security Archive, George Washington University','claim':'1989年6月4日前後北京軍隊鎮壓；所整理當年電報包含不同傷亡估計，不能把單一估計當成核定總數。'},
}

SYSTEM='使用台灣繁體中文，依可靠史料回答。把事件、地點、日期、行動者與數量正確配對；錯誤前提應更正。區分確定的事件與尚無法由資料確定的細節，不附加沒有依據的数字、動機或政治口號。'


def main():
    dest=HERE/'draft-v1';dest.mkdir(exist_ok=False)
    rows=[]
    def add(split,key,prompt,answer,sources):
        rows.append(dict(id='history-v9-'+key,group='history-v9-'+key,split=split,category='history',system=SYSTEM.replace('数字','數字'),
                         prompt=prompt,answer=answer,retain=False,oracle={'type':'source_backed_event_binding','source_ids':sources},
                         source='Author-curated facts and paraphrases; sources.json records claim-level references.'))
    facts=[
        ('tw',{'事件':'台灣地區解除戒嚴','日期':'1987-07-15'},'1987年7月15日，台灣地區解除戒嚴。','台灣地區解除戒嚴的年表註記要如何寫，才能保留確切日期？','把台灣地區解除戒嚴的日期寫成1988年，是否正確？','不正確，應為1987年7月15日。',['tw']),
        ('km',{'事件':'金門、馬祖解除戒嚴並終止戰地政務','日期':'1992-11-07'},'1992年11月7日，金門與馬祖解除戒嚴並終止戰地政務。','金門、馬祖結束戰地政務的歷史說明，請列出事件及完整日期。','有份稿件將金馬結束戰地政務記作1992年11月28日，請更正。','應更正為1992年11月7日，金門、馬祖解除戒嚴並終止戰地政務。',['km','km2']),
        ('election',{'事件':'台灣首次總統直接民選','日期':'1996-03-23'},'1996年3月23日，台灣舉行首次總統直接民選。','請替台灣首次總統直接民選寫一筆含年月日的年表。','有人把台灣首次總統直選寫成2016年3月20日，這段日期該如何訂正？','台灣首次總統直接民選的日期是1996年3月23日，並非2016年3月20日。',['election']),
        ('kent',{'事件':'肯特州立大學槍擊事件','日期':'1970-05-04','地點':'美國俄亥俄州肯特州立大學','行動者':'俄亥俄州國民兵','死亡人數':4,'受傷人數':9},'1970年5月4日，俄亥俄州國民兵在美國肯特州立大學開槍，造成4人死亡、9人受傷。','肯特州立大學1970年的槍擊事件，請簡述日期、行動者與死傷。','稿件說1970年5月4日4死9傷的槍擊發生在克里夫蘭州立大學，這個校名對嗎？','校名不對，應是美國俄亥俄州的肯特州立大學；當天俄亥俄州國民兵開槍，造成4人死亡、9人受傷。',['kent','kent2']),
    ]
    for key,metadata,answer,prompt,wrong,correction,source_ids in facts:
        add('train',key+'-yearbook',prompt,answer,source_ids)
        add('train',key+'-record','以下已核對的事件記錄，請用一句話完整轉述，不混用其他事件：'+dumps(metadata),answer,source_ids)
        add('dev',key+'-correction',wrong,correction,source_ids)
        add('dev',key+'-structured','請將這份記錄整理成 JSON，保留所列事件及所有欄位：'+dumps(metadata),dumps(metadata),source_ids)
    comparisons=[
        ('train','two-places','編輯把台灣與金馬的解嚴列在同一天。請用兩筆清楚區分日期、地區及事件。','台灣地區：1987年7月15日解除戒嚴。金門、馬祖：1992年11月7日解除戒嚴並終止戰地政務。'),
        ('train','event-types','為什麼不能把台灣解嚴、金馬結束戰地政務和首次總統直選合寫成一次事件？','它們的事件範圍與日期不同：台灣地區解除戒嚴是1987年7月15日；金門、馬祖解除戒嚴並終止戰地政務是1992年11月7日；首次總統直接民選是1996年3月23日。'),
        ('dev','reverse-order','請先寫金馬結束戰地政務的年月日，再寫台灣解除戒嚴的年月日，並說明兩者不是同一日期。','金馬：1992年11月7日解除戒嚴並終止戰地政務。台灣地區：1987年7月15日解除戒嚴。兩者地區與事件範圍不同，日期不能對調或合併。'),
        ('dev','wrong-month','台灣解嚴和金馬終止戰地政務是不是都在7月15日，只是年份不同？','不是。台灣地區解除戒嚴是1987年7月15日；金門、馬祖解除戒嚴並終止戰地政務是1992年11月7日，不僅年份不同，月份與日期也不同。'),
    ]
    for split,key,prompt,answer in comparisons:add(split,key,prompt,answer,['tw','km','km2','election'] if key=='event-types' else ['tw','km','km2'])
    evidence='資料記載1989年6月4日前後，中國軍隊在北京對示威者進行武力鎮壓並造成死傷；所整理的當年電報出現不同傷亡估計，這段摘要沒有提供已核定的總死亡數。'
    uncertain=[
        ('train','uncertainty','只根據以下資料，寫一段確認事件但不杜撰精確死亡數的摘要：'+evidence,'1989年6月4日前後，中國軍隊在北京武力鎮壓示威者並造成死傷。這段資料沒有足以確定總死亡數的證據，不能把某個估計改寫成精確定論。'),
        ('train','estimates','某份當年電報的估計，能不能不加說明就當成六四事件已核定的總死亡數？','不能。當年電報的估計要保留來源與不確定性，不能當成已核定總數。1989年6月4日前後北京發生軍隊武力鎮壓與死傷，這個事件事實和總數是否確定是不同問題。'),
        ('dev','unknown-not-denial','依以下資料，無法報出精確總數是否代表沒有發生軍隊鎮壓？'+evidence,'不代表。資料確認1989年6月4日前後北京發生軍隊武力鎮壓及死傷；總死亡數未能由摘要確定，不能因此否定事件，也不能自行填入一個數字。'),
        ('dev','unsupported-detail','請只依以下資料答覆：可以再加上一個未提供的死亡估計或軍隊動機嗎？'+evidence,'不可以加入這段資料沒有支持的數字或動機。可以說明1989年6月4日前後北京軍隊鎮壓造成死傷，並清楚標示摘要未確定總死亡數。'),
    ]
    for split,key,prompt,answer in uncertain:add(split,key,prompt,answer,['beijing'])
    previous=[json.loads(x) for s in ('train','dev') for x in (ROOT/'finetuning/contract_v8/candidate-data-v2'/(s+'.jsonl')).read_text(encoding='utf8').splitlines()]
    regression=[json.loads(x) for x in (ROOT/'finetuning/release_v3/regression.jsonl').read_text(encoding='utf8').splitlines()]
    if {r['prompt'] for r in rows}&{request_text(r) for r in previous+regression}:raise ValueError('Exact overlap with existing data/regression')
    from transformers import AutoTokenizer
    tok=AutoTokenizer.from_pretrained(ROOT/'finetuning/release_v4/artifacts/outputs/epoch-3',local_files_only=True,trust_remote_code=False)
    import importlib.util
    spec=importlib.util.spec_from_file_location('history_masks',ROOT/'finetuning/release_v4/train.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    lengths=[]
    for row in rows:
        lengths.append(len(helper.tokenize_row(tok,row,12288)['ids']))
        for field in ('system','prompt','answer'):
            value=row[field]
            if tok.decode(tok.encode(value,add_special_tokens=False),clean_up_tokenization_spaces=False)!=value:raise ValueError('Tokenizer changed text')
    for split in ('train','dev'):
        (dest/(split+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows if r['split']==split),encoding='utf8')
    (dest/'sources.json').write_text(json.dumps(SOURCES,ensure_ascii=False,indent=2),encoding='utf8')
    manifest=dict(rows=len(rows),splits=dict(Counter(r['split'] for r in rows)),max_tokens=max(lengths),
                  tokenizer_roundtrip_passed=True,assistant_mask_passed=True,exact_prompt_overlap=False,
                  scope='Known historical development facts with event/date/actor binding and supplied-evidence uncertainty. Topics overlap original regressions; not blind or unseen-fact generalization.',
                  final_holdout_files_read=False,merged_into_training_bundle=False,model_evaluated=False,training_started=False,release_approved=False)
    manifest['sources']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),ROOT/'finetuning/release_v3/regression.jsonl',ROOT/'finetuning/contract_v8/candidate-data-v2/train.jsonl',ROOT/'finetuning/contract_v8/candidate-data-v2/dev.jsonl')}
    (dest/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(manifest,ensure_ascii=True))


if __name__=='__main__':main()
