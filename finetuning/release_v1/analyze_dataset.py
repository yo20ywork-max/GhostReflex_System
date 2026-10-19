"""Describe corpus diversity without treating paraphrases as independent skills."""
import collections,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
rows=list(map(json.loads,(ROOT/'grounding-train.jsonl').read_text(encoding='utf8').splitlines()))
stats={}
for category in sorted({r['category'] for r in rows}):
    subset=[r for r in rows if r['category']==category]
    answers=collections.Counter(r['answer'] for r in subset)
    stats[category]={'rows':len(subset),'declared_groups':len({r['group'] for r in subset}),'unique_answers':len(answers),'most_repeated_answer_count':answers.most_common(1)[0][1],'source_urls':sorted({r['source'] for r in subset if r.get('source')})}
report={'file':'grounding-train.jsonl','sha256':hashlib.sha256((ROOT/'grounding-train.jsonl').read_bytes()).hexdigest(),'rows':len(rows),'categories':stats,'note':'Declared groups, generated fictional records and paraphrases are not independent real-world tasks. This is a finite product-adaptation corpus, not broad pretraining or evidence of AGI.'}
(ROOT/'CORPUS_DIVERSITY.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
lines=['# 訓練資料覆蓋範圍','','此版共 1,588 筆，是產品適配與能力保留資料；不是全面重新預訓練。正式執行代表輸入鎖定、實際更新、保留 checkpoint 與如實驗收，不代表這個資料量已足以支撐所有螢幕任務。','','| 類別 | 筆數 | 宣告群組 | 不同參考答案 | 單一答案最高重複次數 |','|---|---:|---:|---:|---:|']
for c,s in stats.items():lines.append(f"| {c} | {s['rows']} | {s['declared_groups']} | {s['unique_answers']} | {s['most_repeated_answer_count']} |")
lines+=['','宣告群組仍可能來自同一範本或語言技能，不能把群組數當成獨立工作流數。來源欄位可能出現在工具題中，不能把所有 URL 當成歷史文獻。','身份敘述的固定答案重複是預期現象；來源摘要、比較句與拒絕補充未知資訊若反覆共用模板，則可能形成不必要套句。這只是資料與輸出的觀察，尚非唯一成因的證明。','此資料沒有涵蓋任意桌面軟體的視覺狀態、完整多輪操作軌跡、長時間中斷恢復或全部台灣語音口音。因此小型題庫全對，也不足以保證真實任務全對。','後續擴充應優先納入真實、去識別化的任務軌跡與工具結果，跨程式／網站／表達方式保留獨立驗收組；先審查事實與意圖標註，再增加資料量，避免只對同一答案增加問法。']
(ROOT/'CORPUS_DIVERSITY.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
print(json.dumps({k:{x:v for x,v in s.items() if x!='source_urls'} for k,s in stats.items()},ensure_ascii=False))
