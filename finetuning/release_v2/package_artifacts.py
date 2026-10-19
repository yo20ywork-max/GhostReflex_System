"""Cloud-only finite export of this run's adapters and evidence, excluding foundation cache."""
import hashlib,json,tarfile
from pathlib import Path
R=Path(__file__).resolve().parent
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 if R.as_posix()!='/workspace/crossgen-release-v2':raise RuntimeError('Cloud workspace only')
 manifest=json.loads((R/'outputs/manifest.json').read_text())
 if not manifest.get('disk_reload_logits_verified'):raise RuntimeError('Training artifact reload not verified')
 paths=[p for p in (R/'outputs').rglob('*') if p.is_file()]
 paths += [R/n for n in ['DATA_LOCK.json','DATA_MANIFEST.json','config.json','contract.json','run.log']]
 if (R/'grammar-comparison.log').exists():
  paths += [R/n for n in ['GRAMMAR_EVAL_LOCK.json','XGRAMMAR_VERIFIED.json','grammar-comparison.log','evaluate_xgrammar.py','verify_xgrammar.py']]
 expected_models={'outputs/epoch-1/adapter_model.safetensors','outputs/epoch-2/adapter_model.safetensors'}
 if (R/'outputs-repair').exists():
  repair=json.loads((R/'outputs-repair/manifest.json').read_text())
  if not repair.get('disk_reload_logits_verified'):raise RuntimeError('Repair reload not verified')
  paths += [p for p in (R/'outputs-repair').rglob('*') if p.is_file()]
  paths += [R/n for n in ['REPAIR_LOCK.json','REPAIR_DATA_MANIFEST.json','REPAIR_HISTORY_LOCK.json','REPAIR_HISTORY_MANIFEST.json','repair-config.json','repair.log']]
  expected_models.add('outputs-repair/epoch-1/adapter_model.safetensors')
 rows=[];size=0
 for p in paths:
  if p.is_symlink() or not p.resolve().is_relative_to(R):raise ValueError('Unsafe member')
  size+=p.stat().st_size
  if size>2_000_000_000:raise ValueError('Adapter package exceeds 2GB bound')
  rows.append({'path':p.relative_to(R).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
 modelnames={x['path'] for x in rows if x['path'].endswith('adapter_model.safetensors')}
 if modelnames!=expected_models:raise ValueError('Unexpected checkpoint set')
 metadata=R/'ARTIFACT_CONTENTS.json';metadata.write_text(json.dumps({'files':rows,'total_bytes':size},indent=2))
 dest=R/'adapters-v2.tar.gz'
 if dest.exists():raise FileExistsError(dest)
 with tarfile.open(dest,'w:gz',compresslevel=1) as t:
  for p in [*paths,metadata]:
   # Large weights are verified through separate incremental transfers.
   if p.name!='adapter_model.safetensors':t.add(p,arcname=p.relative_to(R).as_posix(),recursive=False)
 receipt={'file':dest.name,'bytes':dest.stat().st_size,'sha256':sha(dest),'contents_sha256':sha(metadata),'adapter_count':len(expected_models),'weights_transferred_separately':True}
 (R/'adapters-v2.receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
if __name__=='__main__':main()
