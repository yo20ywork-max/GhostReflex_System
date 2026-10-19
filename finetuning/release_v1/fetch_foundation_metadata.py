"""Preserve upstream licensing even when a candidate fails export qualification."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
    from huggingface_hub import hf_hub_download
    cfg=json.loads((ROOT/'config.json').read_text())
    records=[]
    for source,target in [('LICENSE','FOUNDATION_LICENSE.txt'),('README.md','FOUNDATION_MODEL_CARD.md')]:
        path=Path(hf_hub_download(cfg['base'],source,revision=cfg['revision']))
        data=path.read_bytes()
        if len(data)>1_000_000:raise ValueError('Metadata bound exceeded')
        destination=ROOT/target
        if destination.exists() and destination.read_bytes()!=data:raise ValueError('Pinned metadata changed')
        destination.write_bytes(data)
        records.append({'upstream_file':source,'local_file':target,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    (ROOT/'FOUNDATION_METADATA.json').write_text(json.dumps({'base':cfg['base'],'revision':cfg['revision'],'files':records},indent=2))
    print('PINNED_FOUNDATION_METADATA_PRESERVED')
if __name__=='__main__':main()
