"""Lock an initialization comparison; no changes to examples or held-out data."""
import datetime,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
cfg=json.loads((ROOT/'grounding-bf16-config.json').read_text())
path=ROOT/'fresh-config.json'
if path.exists():raise FileExistsError(path)
path.write_text(json.dumps(cfg,indent=2)+'\n',encoding='utf8')
lock=json.loads((ROOT/'GROUNDING_BF16_LOCK.json').read_text())
lock['locked_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
lock['sha256']['fresh-config.json']=hashlib.sha256(path.read_bytes()).hexdigest()
lock['note']='Fresh rank-16 LoRA on the unchanged pinned official base. Same 1588 examples, seed, LR, epochs, optimizer and losses as grounding continuation. Only initial adapter differs. Original held-out tests have not been generated or used for further training.'
(ROOT/'FRESH_LOCK.json').write_text(json.dumps(lock,indent=2)+'\n',encoding='utf8')
print('FRESH_INITIALIZATION_COMPARISON_LOCKED')
