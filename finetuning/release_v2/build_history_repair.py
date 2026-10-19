"""Extend the not-yet-run repair using known regression findings and cited history.

This is development-driven repair, never claimed as unseen history generalization.
"""
import hashlib,json,random
from pathlib import Path
from build_data import GENERAL,read,wire
from train import verify_lock,tokenize_row
from transformers import AutoTokenizer
R=Path(__file__).resolve().parent
EXAMPLES=[
 ('台灣本島解除戒嚴與金馬結束戰地政務，哪一個先發生？','台灣本島於1987年7月15日解除戒嚴在先；金門、馬祖於1992年11月7日結束戰地政務在後。'),
 ('1987年宣布台灣解嚴後，金門馬祖是不是也同一天解除戰地政務？','不是。台灣本島解除戒嚴的日期是1987年7月15日；金門、馬祖結束戰地政務的日期是1992年11月7日。'),
 ('請用年份和月份區分台灣解嚴與首屆總統直選。','台灣本島解嚴：1987年7月。第一次總統直選：1996年3月。'),
 ('1993年3月23日是台灣第一次總統直選投票日嗎？','不是，正確投票日是1996年3月23日。'),
 ('用年月日回答中華民國第一次全民直選總統的投票日期，不要加上其他事件。','1996年3月23日。'),
 ('台灣解嚴的日期是1987年5月20日嗎？','不是，台灣本島解除戒嚴的日期是1987年7月15日。'),
 ('資料寫台灣1987年解嚴，另一篇寫金馬1992年結束戰地政務，兩篇一定互相矛盾嗎？','不一定。它們描述不同地區與制度變動：台灣本島於1987年7月15日解除戒嚴，金門、馬祖於1992年11月7日結束戰地政務。'),
 ('1970年國民兵造成四死九傷的美國校園事件，發生在哪所學校？','肯特州立大學（Kent State University），發生於1970年5月4日。'),
 ('肯特州立大學事件是否造成九人死亡、四人受傷？','數字對調了。1970年5月4日的肯特州立大學槍擊事件造成四人死亡、九人受傷。'),
 ('請列出肯特州立大學槍擊事件的日期、開槍部隊與死傷數字。','日期是1970年5月4日，開槍者為俄亥俄州國民兵，造成四人死亡、九人受傷。'),
 ('既然六四的精確死亡人數有爭議，能否說武力鎮壓沒有發生？','不能。1989年6月3日晚至4日，北京軍隊以武力鎮壓抗議者與民眾、造成死傷，有相關紀錄。總傷亡數的不確定性不能用來否認鎮壓本身。'),
 ('六四只是一個日期，還是也指歷史事件？','在這個歷史脈絡中，六四指1989年6月4日前後北京民主示威遭中國政府武力鎮壓的事件。'),
 ('談1989年北京鎮壓時，如果資料沒有確切總死傷，應怎麼表達？','應說明武力鎮壓造成死傷，但精確總數尚無可據以確定的結論；不要把未核實的估計寫成確切數字。'),
 ('六四是1988年發生的嗎？','不是。通常所說的六四事件發生在1989年，指6月4日前後北京的武力鎮壓。'),
 ('研究六四時，要不要因為議題敏感就跳過已記錄的鎮壓？','不應因政治敏感而跳過已記錄的武力鎮壓；應如實說明1989年北京發生的事件，同時區分有證據的事實與仍不確定的细節。'),
 ('資料只說某場示威有人受傷，可以推定每個示威者都有犯罪嗎？','不能。有人受傷並不能證明每位示威者都犯罪；個別行為與責任需要個別證據。'),
]
def main():
 if (R/'REPAIR_HISTORY_LOCK.json').exists():raise RuntimeError('History repair already locked')
 lock=verify_lock('REPAIR_LOCK.json');rows=read(R/'repair-train.jsonl');history=[r for r in read(R/'train.jsonl') if r['category']=='history']
 extra=[]
 for r in history:
  for n in range(3):extra.append({**r,'id':r['id']+f'-weighted-{n}','sampling_repeat':n+1})
 for i,(q,a) in enumerate(EXAMPLES):
  # Four exposures are stated explicitly, not counted as four unique examples.
  for n in range(4):extra.append({'id':f'history-repair-{i}-{n}','group':f'history-repair-{i}','split':'train','category':'history','system':GENERAL,'prompt':q,'answer':a.replace('细','細'),'retain':False,'oracle':{'type':'manual'},'source':'AUDIT_RUBRIC.md primary historical sources','sampling_repeat':n})
 excluded={r['prompt'] for name in ['dev.jsonl','test.jsonl','regression.jsonl','provenance-audit.jsonl'] for r in read(R/name)}
 if any(r['prompt'] in excluded for r in extra):raise ValueError('Exact evaluation prompt leaked')
 rows+=extra;random.Random(20260907).shuffle(rows);cfg=json.loads((R/'repair-config.json').read_text());tok=AutoTokenizer.from_pretrained(R/'tokenizer',local_files_only=True)
 encoded=[tokenize_row(tok,r,cfg['max_length']) for r in rows]
 (R/'repair-history-train.jsonl').write_text(''.join(wire(r)+'\n' for r in rows),encoding='utf8')
 report={'training_rows':len(rows),'new_unique_historical_examples':len(EXAMPLES),'new_historical_sampling_repetitions':4,'existing_history_extra_repetitions':3,'max_tokens':max(len(x['ids']) for x in encoded),'total_tokens':sum(len(x['ids']) for x in encoded),'answer_tokens':sum(len(x['ids'])-x['prefix'] for x in encoded),'known_regression_informed':True,'new_test_outputs_seen':False,'training_not_yet_started':True,'scope':'Factual recall and instruction repair; not political stance targeting or proof of erasure.'}
 (R/'REPAIR_HISTORY_MANIFEST.json').write_text(json.dumps(report,indent=2),encoding='utf8')
 files=['repair-history-train.jsonl','build_history_repair.py','REPAIR_HISTORY_MANIFEST.json','AUDIT_RUBRIC.md']
 lock['sha256'].update({n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in files})
 (R/'REPAIR_HISTORY_LOCK.json').write_text(json.dumps(lock,indent=2),encoding='utf8');print(json.dumps(report))
if __name__=='__main__':main()
