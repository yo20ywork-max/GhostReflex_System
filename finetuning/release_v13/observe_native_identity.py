"""One bounded read of completed native probes; no launch, retry or polling loop."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
from remote import connection, REMOTE

R = Path(__file__).resolve().parent


def main():
    host, port, options = connection()
    program = '''import hashlib,json
from pathlib import Path
r=Path(ROOT);out={}
for epoch in (1,2,3):
 p=r/'outputs'/('identity-backend-e'+str(epoch))
 source=p/'results.jsonl';summary=json.loads((p/'generation-complete.json').read_text())
 assert source.stat().st_size<1000000
 assert summary['results_sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
 assert summary['rows']==summary['complete_generations']==32 and summary['source_hashes_unchanged']
 rows=list(map(json.loads,source.read_text().splitlines()))
 out[str(epoch)]={'summary':summary,'rows':[{k:row[k] for k in ('id','original_id','mode','messages','text','completed','prompt_sha256')} for row in rows]}
print(json.dumps(out,ensure_ascii=False))
'''.replace('ROOT', repr(REMOTE))
    data = json.loads(subprocess.check_output(['ssh', *options, '-p', port, host,
        'python -c ' + shlex.quote(program)], text=True, encoding='utf8', timeout=60))
    record = {'observed_utc': datetime.now(timezone.utc).isoformat(),
              'pod_id': json.loads((R / 'CLOUD_RUN.json').read_text(encoding='utf8'))['pod']['id'],
              'epochs': data, 'scope': 'Read-only semantic review preview; final verified backup remains required.'}
    dest = R / 'NATIVE_IDENTITY_OBSERVATION.json'
    with dest.open('x', encoding='utf8') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'observation': str(dest), 'completed_generations': sum(x['summary']['rows'] for x in data.values())}))


if __name__ == '__main__':
    main()
