"""Reuse inspected answers only after exact text, prompt and model equality."""
import hashlib,json,statistics,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
old={r['id']:r for r in map(json.loads,(ROOT/'integration-base-local.jsonl').read_text(encoding='utf8').splitlines())}
rows=list(map(json.loads,(ROOT/'integration-base-default-local.jsonl').read_text(encoding='utf8').splitlines()))
for r in rows:
    for key in ['text','prompt_sha256','model_digest','completed']:
        if r[key]!=old[r['id']][key]:raise ValueError('New semantic review needed')
path=ROOT/'integration-base-default-local.jsonl.checks.json'
checks=json.loads(path.read_text(encoding='utf8'))
prior=json.loads((ROOT/'integration-base-local.review.json').read_text(encoding='utf8'))
review={**prior,'checks_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'review_reuse':'All 15 answers, prompt hashes, model digests and completion flags match the already inspected 6144-context baseline exactly; only timing and configured context differ.'}
(ROOT/'integration-base-default-local.review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf8')
with urllib.request.urlopen('http://127.0.0.1:11434/api/ps',timeout=15) as response:resident=json.load(response)
times=[r['seconds'] for r in rows]
passed=sum(r['check']['passed'] if r['check']['passed'] is not None else review['verdicts']['base/'+r['id']]['passed'] for r in checks['results'])
report={'context_tokens':12288,'context_basis':'run_daemon.py source default; this benchmark does not attest to environment overrides of an already running EXE','model':rows[0]['model'],'digest':rows[0]['model_digest'],'plans_passed':passed,'plans_total':len(rows),'first_request_seconds':times[0],'subsequent_median_seconds':statistics.median(times[1:]),'subsequent_min_seconds':min(times[1:]),'subsequent_max_seconds':max(times[1:]),'all_15_outputs_identical_to_6144_profile':True,'actual_desktop_actions_executed':0,'target_machine_verified':False,'ollama_residency':resident,'raw_outputs':'integration-base-default-local.jsonl','review':'integration-base-default-local.review.json'}
(ROOT/'LOCAL_DEFAULT_BASELINE.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
model=next(m for m in resident['models'] if m['name']==rows[0]['model'])
text=f'''# 原始碼預設 context 的本機基準

相同原版 Q4_K_M、完整產品提示與 schema，改用原始碼預設 12,288 tokens。這不是已執行 EXE 的設定鑑識；環境變數可能覆寫預設。

- 15 份答案與先前 6,144 profile 逐字相同，仍為 {passed}/15 份計畫通過。沒有執行桌面動作。
- 首筆 {times[0]:.2f} 秒，後續中位數 {statistics.median(times[1:]):.2f} 秒，範圍 {min(times[1:]):.2f}～{max(times[1:]):.2f} 秒。
- Ollama 回報此模型駐留 VRAM {model['size_vram']/2**30:.2f} GiB，context {model['context_length']}。這不是 GPU 全程序尖峰用量。

硬體為開發機 RX 6700 XT／約 32GB RAM。尚未驗證 24GB RAM／6GB VRAM 的目標機，也未量測 ASR、視覺模型或整個桌面任務延遲。提示快取與模型是否已載入會影響時間。
'''
(ROOT/'LOCAL_DEFAULT_BASELINE.md').write_text(text,encoding='utf8')
print(json.dumps(report,ensure_ascii=False,indent=2))
