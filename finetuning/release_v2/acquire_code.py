"""Bounded public dataset acquisition; downloaded code is data, never executed."""
import hashlib,json,time,urllib.parse,urllib.request
from pathlib import Path
R=Path(__file__).resolve().parent
def get(url,limit=8_000_000):
 with urllib.request.urlopen(url,timeout=60) as f:
  b=f.read(limit+1)
 if len(b)>limit:raise ValueError('Response exceeds byte bound')
 return b
def main():
 out=R/'sources';out.mkdir(exist_ok=True)
 repo='nvidia/OpenCodeInstruct';meta=json.loads(get('https://huggingface.co/api/datasets/'+repo))
 card=get('https://huggingface.co/datasets/'+repo+'/raw/'+meta['sha']+'/README.md')
 (out/'OpenCodeInstruct-README.md').write_bytes(card)
 rows=[];receipts=[];total=0
 for page,offset in enumerate(range(0,500000,10000)):
  path=out/f'code-page-{offset}.json'
  url='https://datasets-server.huggingface.co/rows?'+urllib.parse.urlencode({'dataset':repo,'config':'train','split':'train','offset':offset,'length':100})
  b=path.read_bytes() if path.exists() else get(url)
  total+=len(b)
  if total>64_000_000:raise ValueError('Acquisition exceeds 64MB bound')
  path.write_bytes(b);data=json.loads(b)
  rows.extend(x['row'] for x in data['rows']);receipts.append({'url':url,'file':path.name,'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)})
  print(json.dumps({'pages':page+1,'rows':len(rows),'bytes':total}),flush=True)
 end=json.loads(get('https://huggingface.co/api/datasets/'+repo))
 if end['sha']!=meta['sha']:raise ValueError('Dataset revision changed during acquisition')
 (out/'code-source.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows),encoding='utf8')
 manifest={'dataset':repo,'revision_observed_before_and_after':meta['sha'],'viewer_snapshot_note':'Rows API is not revision-pinned. Raw responses and hashes retained; repository revision unchanged during retrieval.','license':'cc-by-4.0','attribution':'NVIDIA, OpenCodeInstruct, https://huggingface.co/datasets/nvidia/OpenCodeInstruct','rows':len(rows),'bytes':total,'responses':receipts,'execution':'No downloaded code or tests executed'}
 (out/'SOURCE_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
if __name__=='__main__':main()
