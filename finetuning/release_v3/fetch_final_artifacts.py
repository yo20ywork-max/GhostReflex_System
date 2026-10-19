"""Fetch final records with original paths; reuse already verified checkpoints."""
import json,subprocess
from pathlib import Path,PurePosixPath
from remote import connection
from fetch_checkpoint import sha
R=Path(__file__).resolve().parent

def main():
    host,port,options=connection();remote='/workspace/crossgen-release-v3/'
    inventory=json.loads(subprocess.check_output(['ssh',*options,'-p',port,host,'cat '+remote+'FINAL_ARTIFACT_INVENTORY.json'],text=True))
    if not inventory['verified_training_completion'] or inventory['total_bytes']>1_300_000_000:raise ValueError('Incomplete or oversized inventory')
    root=R/'artifacts';root.mkdir(exist_ok=True);records=[]
    for row in inventory['files']:
        rel=PurePosixPath(row['path'])
        if rel.is_absolute() or '..' in rel.parts or any(not p.replace('-','').replace('_','').replace('.','').isalnum() for p in rel.parts):raise ValueError('Invalid artifact path')
        target=root.joinpath(*rel.parts)
        if not target.resolve().is_relative_to(root.resolve()):raise ValueError('Artifact escapes destination')
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            if target.stat().st_size!=row['bytes'] or sha(target)!=row['sha256']:raise ValueError('Existing artifact mismatch: '+str(rel))
        else:
            partial=target.with_name(target.name+'.part')
            subprocess.run(['scp',*options,'-P',port,host+':'+remote+str(rel),str(partial)],check=True)
            if partial.stat().st_size!=row['bytes'] or sha(partial)!=row['sha256']:raise ValueError('Transfer mismatch: '+str(rel))
            partial.replace(target)
        records.append(row)
        print(json.dumps({'verified':str(rel),'bytes':row['bytes']}),flush=True)
    manifest=json.loads((root/'outputs/manifest.json').read_text())
    if not all(manifest.get(k) for k in ('adapter_changed','training_completed','disk_reload_logits_verified')):raise ValueError('Unverified training')
    for name in ['DATA_LOCK.json','HOLDOUT_LOCK.json','RUNTIME_INPUT_LOCK.json','runtime_source.py','config.json','train.py','answer_loss.py','training-contract.json']:
        if sha(root/name)!=sha(R/name):raise ValueError('Cloud input differs from local lock: '+name)
    (root/'FINAL_ARTIFACT_INVENTORY.json').write_text(json.dumps(inventory,indent=2))
    report={'verified':True,'models':[e['epoch'] for e in manifest['epochs']],'files':records,'disk_reload_logits_verified':True,'weights_changed':True,'training_completed':True,'release_approved':False}
    report['logit_reload_scope']='Trainer compared live versus disk-reloaded logits for the last epoch only. All checkpoint files separately hash-verified; do not infer three independent live-logit comparisons.'
    (R/'ARTIFACT_VERIFIED.json').write_text(json.dumps(report,indent=2));print(json.dumps({'verified':True,'files':len(records)}))

if __name__=='__main__':main()
