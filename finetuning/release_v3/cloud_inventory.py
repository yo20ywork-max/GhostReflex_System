"""Create a bounded final artifact inventory only after disk reload verification."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()

def main():
    if 'TRAINING_AND_RELOAD_COMPLETE' not in (R/'cloud_run.log').read_text():raise RuntimeError('Cloud launcher has not reported successful completion')
    manifest=json.loads((R/'outputs/manifest.json').read_text())
    if not all(manifest.get(k) for k in ('adapter_changed','training_completed','disk_reload_logits_verified')):
        raise RuntimeError('Training/reload verification incomplete; preserve partial checkpoints separately')
    if len(manifest['epochs'])!=3 or not all(e['full_epoch'] for e in manifest['epochs']):
        raise RuntimeError('Expected three completed checkpoints')
    paths=[p for p in (R/'outputs').rglob('*') if p.is_file()]
    paths += [R/n for n in ['DATA_LOCK.json','HOLDOUT_LOCK.json','RUNTIME_INPUT_LOCK.json','runtime_source.py','config.json','train.py','answer_loss.py','requirements-cloud.txt','training-contract.json','cloud_run.sh','cloud_run.log']]
    paths += [R/n for n in ['cloud_compare_known.py','regression.jsonl'] if (R/n).is_file()]
    records=[]
    for p in sorted(paths):
        if p.is_symlink() or not p.resolve().is_relative_to(R) or p.stat().st_size>400_000_000:raise ValueError('Unexpected artifact')
        records.append({'path':p.relative_to(R).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
    if sum(r['bytes'] for r in records)>1_300_000_000:raise ValueError('Artifact size budget exceeded')
    report={'verified_training_completion':True,'files':records,'total_bytes':sum(r['bytes'] for r in records),'release_approved':False}
    (R/'FINAL_ARTIFACT_INVENTORY.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'files':len(records),'bytes':report['total_bytes']}))

if __name__=='__main__':main()
