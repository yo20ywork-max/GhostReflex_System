"""Verify the known archive hash and extract only bounded regular files."""
import hashlib
import json
from pathlib import Path
import tarfile
from safetensors import safe_open

root=Path(__file__).resolve().parent/'artifacts/pilot-20260905'
archive=root/'deliverables.tar.gz'
expected='b01763cad6c07f1a46d80cc58e171d6c80d9c8f865bed8ffa8626375ef7b5d57'
with archive.open('rb') as file:
    actual=hashlib.file_digest(file,'sha256').hexdigest()
if actual!=expected:
    raise RuntimeError('Archive hash differs from the cloud copy')
with tarfile.open(archive,'r:gz') as bundle:
    members=bundle.getmembers()
    if len(members)>300 or sum(m.size for m in members)>1024**3:
        raise RuntimeError('Archive exceeds extraction bounds')
    for member in members:
        if not (member.isfile() or member.isdir()) or not (root/member.name).resolve().is_relative_to(root.resolve()):
            raise RuntimeError('Unexpected archive member')
    bundle.extractall(root,filter='data')
files=[]
for weight in sorted((root/'outputs').rglob('adapter_model.safetensors')):
    with weight.open('rb') as file:
        digest=hashlib.file_digest(file,'sha256').hexdigest()
    with safe_open(weight,framework='pt',device='cpu') as state:
        import math
        parameters=sum(math.prod(state.get_slice(key).get_shape()) for key in state.keys())
    files.append({'path':str(weight.relative_to(root)),'sha256':digest,
                  'bytes':weight.stat().st_size,'adapter_parameters':parameters})
if len(files)!=6:
    raise RuntimeError('Expected four trained adapters and two signed compositions')
manifests=[]
for path in sorted((root/'outputs').glob('*/manifest.json')):
    manifest=json.loads(path.read_text(encoding='utf-8'))
    if not manifest['adapter_changed'] or not manifest['disk_reload_logits_verified']:
        raise RuntimeError('Training or reload verification failed')
    manifests.append({'run':path.parent.name,'steps':len(manifest['steps'])})
if len(manifests)!=4:
    raise RuntimeError('Expected four completed training runs')
report={'archive_sha256':actual,'weights':files,'training_runs':manifests,
        'release_approved':False,'quality_gate':'failed; see RESULT.md'}
(root/'integrity.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
