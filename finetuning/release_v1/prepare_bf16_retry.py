"""Version the execution fix without modifying locked data or previous run config."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
config_path=ROOT/'grounding-bf16-config.json'
if config_path.exists():raise FileExistsError(config_path)
cfg=json.loads((ROOT/'grounding-config.json').read_text());cfg.update(bf16_autocast=True,longest_sample_preflight=True)
config_path.write_text(json.dumps(cfg,indent=2))
lock=json.loads((ROOT/'GROUNDING_LOCK.json').read_text());lock['sha256'][config_path.name]=hashlib.sha256(config_path.read_bytes()).hexdigest()
lock['execution_fix']='Explicit BF16 autocast and expandable allocator segments; longest-sample forward/backward preflight. Same full data, epochs, LR and thresholds.'
(ROOT/'GROUNDING_BF16_LOCK.json').write_text(json.dumps(lock,indent=2))
print('VERSIONED_BF16_EXECUTION_FIX')
