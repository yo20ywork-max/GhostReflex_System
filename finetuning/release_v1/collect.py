"""Cloud-side bounded artifact archive; excludes base-model cache and credentials."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
ROOT=Path(__file__).resolve().parent

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--name',default='formal-deliverables.tar.gz');p.add_argument('--checkpoint-snapshot',action='store_true');args=p.parse_args()
    if Path(args.name).name!=args.name:raise ValueError('Basename only')
    if args.checkpoint_snapshot:
        for stage in ['outputs','outputs/repair-r1','outputs/preferences-r1','outputs/grounding-r1']:
            manifest=json.loads((ROOT/stage/'manifest.json').read_text())
            if not manifest.get('training_completed') or not manifest.get('disk_reload_logits_verified'):
                raise RuntimeError('Snapshot requires complete, reloaded checkpoints: '+stage)
    files=[]
    for path in ROOT.glob('*'):
        if path.is_file() and path.name not in ('integrity.json',args.name+'.json') and path.suffix in ('.py','.json','.jsonl','.sh','.txt','.log','.md') and not (args.checkpoint_snapshot and path.suffix=='.log'):
            files.append(path)
    checkpoint_files={'adapter_model.safetensors','adapter_config.json','tokenizer.json','tokenizer_config.json','special_tokens_map.json','vocab.json','merges.txt','added_tokens.json','manifest.json','environment.txt','train.jsonl','base_dev_nll.json','checkpoints.json','reference-logps.jsonl','longest-preflight.json'}
    if (ROOT/'outputs').exists():files+=list(p for p in (ROOT/'outputs').rglob('*') if p.is_file() and (not args.checkpoint_snapshot or p.name in checkpoint_files))
    if (ROOT/'export-metadata').exists():files+=list(p for p in (ROOT/'export-metadata').rglob('*') if p.is_file())
    files=list(dict.fromkeys(files))
    if any(p.is_symlink() for p in files) or sum(p.stat().st_size for p in files)>2_000_000_000:raise ValueError('Archive bound exceeded')
    integrity={str(p.relative_to(ROOT)):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in files}
    (ROOT/'integrity.json').write_text(json.dumps(integrity,indent=2))
    with tarfile.open(ROOT/args.name,'w:gz',compresslevel=1) as archive:
        for path in files:archive.add(path,arcname=str(path.relative_to(ROOT)),recursive=False)
        archive.add(ROOT/'integrity.json',arcname='integrity.json')
    receipt={'file':args.name,'bytes':(ROOT/args.name).stat().st_size,'sha256':sha(ROOT/args.name),'members':len(files)+1,'checkpoint_snapshot':args.checkpoint_snapshot,'scope':'Completed checkpoint and training metadata snapshot; later inference results, final reports and GGUF are separate artifacts.' if args.checkpoint_snapshot else 'Run metadata and outputs snapshot.'}
    (ROOT/(args.name+'.json')).write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))

if __name__=='__main__':main()
