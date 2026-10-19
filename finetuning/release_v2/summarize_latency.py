"""Describe observed evaluation latency; never extrapolate to untested hardware."""
import hashlib,json,math,statistics
from pathlib import Path
R=Path(__file__).resolve().parent
def stats(rows):
 times=sorted(x['seconds'] for x in rows)
 return {'calls':len(times),'median_seconds':statistics.median(times),'p95_seconds':times[max(0,math.ceil(len(times)*.95)-1)],'max_seconds':max(times),'total_seconds':sum(times)}
def main():
 candidates={}
 for name in ['base','epoch1','epoch2','prior-fusion','repair']:
  path=R/f'local-{name}-dev.jsonl';rows=list(map(json.loads,path.read_text(encoding='utf8').splitlines()))
  if len(rows)!=73 or not all(x['completed'] for x in rows):raise ValueError('Incomplete outputs '+name)
  categories={c:stats([x for x in rows if x['category']==c]) for c in sorted({x['category'] for x in rows})}
  candidates[name]={'model':rows[0]['model'],'model_digest':rows[0]['model_digest'],'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'all_calls':stats(rows),'first_call_seconds':rows[0]['seconds'],'remaining_calls':stats(rows[1:]),'categories':categories}
 report={'scope':'Observed model-only serial Ollama calls on current development host. Includes generation/request latency, not tool execution/UI/voice latency. Cache warmth and model loading vary; first call shown separately. Not a controlled target-machine benchmark.','num_ctx':12288,'num_predict':1024,'temperature':0,'target_24gb_ram_6gb_vram_verified':False,'candidates':candidates}
 (R/'LATENCY_REPORT.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v['remaining_calls'] for k,v in candidates.items()}))
if __name__=='__main__':main()
