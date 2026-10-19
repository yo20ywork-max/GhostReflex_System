import hashlib,json,sys
from pathlib import Path
from types import SimpleNamespace
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R.parent))
from build_product_data import contract
def main():
 catalog,schema,prompt,source=contract();system=prompt(SimpleNamespace(catalog=catalog,schema=schema))
 c={'catalog':catalog,'schema':schema,'system':system,'source_sha256':source}
 (R/'contract.json').write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding='utf8')
 old=list(map(json.loads,(R.parent/'release_v1/integration-dev.jsonl').read_text(encoding='utf8').splitlines()))
 for name,rows in [('baseline-old',old),('baseline-schema',[{**r,'system':system} for r in old])]:
  p=R/(name+'.jsonl');p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf8')
 manifest={'scope':'Paired development comparison, same cases/model/schema/context; only schema text differs','source_sha256':source,'system_characters':len(system),'tools':len(catalog),'input_sha256':{n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in ['contract.json','baseline-old.jsonl','baseline-schema.jsonl']}}
 (R/'CONTRACT_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
 print(json.dumps(manifest))
if __name__=='__main__':main()
