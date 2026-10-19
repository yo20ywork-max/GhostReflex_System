"""Run one bounded post-training diagnostic on the already authorized pod."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

from remote import connection, REMOTE

R = Path(__file__).resolve().parent


def main():
    source = R / 'evaluate_native_adapter.py'
    content = source.read_text(encoding='utf8')
    assert len(content.encode()) < 20_000
    state = json.loads((R / 'CLOUD_RUN.json').read_text(encoding='utf8'))
    host, port, options = connection()
    program = '''import json,os,subprocess,sys
from pathlib import Path
r=Path(ROOT);os.chdir(r)
runner=json.loads((r/'train-runner.json').read_text())
manifest=json.loads((r/'outputs/manifest.json').read_text())
assert runner['status']=='command_completed'
assert manifest['training_completed'] and manifest['disk_reload_logits_verified']
target=r/'evaluate_native_adapter.py'
if target.exists():assert target.read_text()==CONTENT
else:
 with target.open('x') as f:f.write(CONTENT)
import evaluate_native_adapter as probe
probe.preflight(r,3)
env=dict(os.environ,PYTHONUNBUFFERED='1')
proc=subprocess.run([sys.executable,str(target),'--root',str(r),'--epoch','3','--deadline-utc',DEADLINE],env=env,timeout=330)
raise SystemExit(proc.returncode)
'''.replace('ROOT', repr(REMOTE)).replace('CONTENT', repr(content)).replace('DEADLINE', repr(state['spec']['terminateAfter']))
    compile(program, 'native-identity-launch', 'exec')
    claim = R / 'NATIVE_IDENTITY_LAUNCH.json'
    with claim.open('x', encoding='utf8') as f:
        json.dump({'pod_id': state['pod']['id'], 'epoch': 3,
                   'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                   'scope': '32 existing identity probes; max five minutes; cached weights only',
                   'release_approved': False}, f, indent=2)
    subprocess.run(['ssh', *options, '-p', port, host, 'python -c ' + shlex.quote(program)], check=True, timeout=360)


if __name__ == '__main__':
    main()
