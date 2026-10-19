import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
summary={}
for stem in ['transfer-final','integration-final']:
 p=R/(stem+'.jsonl.checks.json');c=json.loads(p.read_text(encoding='utf8'))
 assert not any(x['check']['passed'] is None for x in c['results'])
 receipt=json.loads((R/(stem+'.jsonl.provenance.json')).read_text(encoding='utf8'))
 assert receipt['complete'] and receipt['output_sha256']==sha(R/(stem+'.jsonl'))
 review={'checks_sha256':sha(p),'reviewer':'Codex assistant; no independent human review','verdicts':{},'all_plan_claims_reviewed':True,'notes':['All generated answers read. Transfer answers exactly match the requested provided fields. Integration plans all fail the strict contract and were not executed. No failed checks promoted.']}
 (R/(stem+'.review.json')).write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf8')
 summary[stem]={'counts':c['summary'],'data_sha256':c['data_sha256'],'output_sha256':receipt['output_sha256'],'checks_sha256':sha(p),'candidate_sha256':receipt['adapter_sha256'],'scope':'Provided-field lookup' if stem.startswith('transfer') else 'Full product prompt, HF NF4 unconstrained decoding; not Ollama schema-constrained inference'}
out={'summary_zh':'24 題新資料擷取／錯誤前提／引文指令題，原版與融合版皆 24／24，未呈現新增優勢。15 題完整產品提示在 HF NF4、不使用 JSON schema 約束的生成條件下，兩者皆 0／15 通過嚴格格式與參數檢查；融合版出現 tool_name／parameters 欄位漂移及不完整 JSON。這與本機原版使用 Ollama JSON schema 的 8／15 是不同推論條件，不能直接比較或當成新權重已接入產品的成績。尚未取得融合版在實際量化、schema 約束推論下的成績。','audits':summary,'actual_desktop_actions_executed':0,'weight_selection_changed':False,'training_after_frozen_test':False,'limitations':['Only eight fictional record groups, simple field extraction, not broad factual reasoning.','Full-prompt cases are derived from development; they are not independent held-out task workflows.','No target-device candidate benchmark; no quantized candidate export due existing release failures.']}
(R/'ADDITIONAL_AUDIT_REPORT.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
print(out['summary_zh'])
