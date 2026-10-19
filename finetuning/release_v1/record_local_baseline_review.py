"""Actual product-message baseline: plan-only review and observed latency."""
import hashlib,json,math,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parent
path=ROOT/'integration-base-local.jsonl.checks.json';checks=json.loads(path.read_text(encoding='utf8'))
decisions={
 'integration-tool-6-slot-9-0':(False,'Adds a read-before-create conditional expressed only as prose; goals and completion permit overwriting despite the explicit no-overwrite request.'),
 'integration-tool-9-slot-9-0':(False,'Invents a requirement for an external foreground browser and stops on its failure before opening the independent built-in browser.'),
 'integration-tool-16-slot-9-0':(False,'Returns bounded file contents through a placeholder instead of opening the requested file in an application.'),
 'integration-extra-ctrlc-0':(True,'Read-only foreground check precedes the requested Ctrl+C; correct hotkey and clipboard-result condition, with no changed target or added mutation.'),
 'integration-blocked-9-0':(False,'Invents payment URL and selectors and attempts another payment while the earlier result is unknown.'),
 'integration-write-read-9-0':(False,'Drops the required output subdirectory and omits its creation.'),
 'integration-wait-read-9-0':(True,'Correct navigation, visible-text wait and read of the specified locator. The added read cap is documented; this fixture does not request an unbounded article export.'),
}
verdicts={'base/'+k:{'passed':v[0],'reason':v[1]} for k,v in decisions.items()}
pending={r['candidate']+'/'+r['id'] for r in checks['results'] if r['check']['passed'] is None}
if pending!=set(verdicts):raise ValueError('Review coverage mismatch')
review={'checks_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'reviewer':'Codex assistant; no independent human review','verdicts':verdicts,'all_plan_claims_reviewed':True,'limitations':['All 15 generated plans inspected; none executed.','The wait/read plan limits returned text to 1000 characters; this does not verify complete export of longer unseen content.','The full product system message and schema constraint differ from the reduced-menu raw HF benchmark.'],'release_approved':False}
(ROOT/'integration-base-local.review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf8')
rows=checks['results'];times=[r['seconds'] for r in rows];following=times[1:]
passed=sum((r['check']['passed'] if r['check']['passed'] is not None else verdicts['base/'+r['id']]['passed']) for r in rows)
report={'model':rows[0]['model'],'digest':rows[0]['model_digest'],'context_tokens':6144,'schema_constrained':True,'plans_semantically_passed':passed,'plans_total':len(rows),'first_request_seconds':times[0],'subsequent_median_seconds':statistics.median(following),'subsequent_min_seconds':min(following),'subsequent_max_seconds':max(following),'total_generation_seconds':sum(times),'actual_desktop_actions_executed':0,'target_24gb_6gb_machine_verified':False,'hardware_receipt':'LOCAL_HARDWARE.json','raw_outputs':'integration-base-local.jsonl','review_file':'integration-base-local.review.json'}
(ROOT/'LOCAL_BASELINE_REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
text=f'''# 本機原版模型：完整產品提示量測

模型：{report['model']}，Q4_K_M；使用完整工具提示、6144 context 與產品 JSON schema。

- 15 份計畫中，{passed} 份通過參數與語意檢查。沒有執行任何桌面動作。
- 首筆產生計畫：{times[0]:.2f} 秒。
- 後續 14 筆中位數：{statistics.median(following):.2f} 秒；範圍 {min(following):.2f}～{max(following):.2f} 秒。
- 主要問題：翻譯了實際路徑、遺漏子目錄、在付款結果未知時另擬付款步驟，以及不必要的前置條件。

這是目前開發機上的模型計畫生成量測，包含 schema 約束與可能的提示快取。它不是整個桌面任務完成時間，也不是 24GB RAM／6GB VRAM 目標機的實測。硬體與模型雜湊保存在 JSON。
'''
(ROOT/'LOCAL_BASELINE_REPORT.md').write_text(text,encoding='utf8')
print(json.dumps(report,ensure_ascii=False,indent=2))
