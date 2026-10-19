"""One read-only observation of the exact existing process and bounded logs."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import shlex
import subprocess
from remote import connection,REMOTE

R=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('preflight','train'));args=parser.parse_args()
    host,port,options=connection()
    program="""import json,os,subprocess
from pathlib import Path
r=Path(REMOTE);mode=MODE
handle=json.loads((r/('.'+mode+'_launch_claim')/'process.json').read_text())
proc=Path('/proc')/str(handle['pid']);live=False;proc_state=None
try:
 stat=(proc/'stat').read_text().split();proc_state=stat[2]
 live=stat[21]==handle['start_ticks'] and proc_state!='Z' and b'cloud_entry.py' in (proc/'cmdline').read_bytes()
except FileNotFoundError:pass
receipt=r/(mode+'-runner.json')
status=json.loads(receipt.read_text()) if receipt.exists() else None
log=r/('preflight.log' if mode=='preflight' else 'training.log')
with log.open('rb') as stream:
 stream.seek(max(0,log.stat().st_size-24000));tail=stream.read().decode('utf8',errors='replace')
details=None
report=r/('preflight/memory-time-preflight.json' if mode=='preflight' else 'outputs/manifest.json')
if report.exists():details=json.loads(report.read_text())
checkpoint_file=r/'outputs/checkpoints.json'
checkpoints=json.loads(checkpoint_file.read_text()) if checkpoint_file.exists() else []
training_tail=[]
if (r/'outputs/train.jsonl').exists():
 with (r/'outputs/train.jsonl').open('rb') as stream:
  stream.seek(max(0,(r/'outputs/train.jsonl').stat().st_size-4096));lines=stream.read().decode().splitlines()
  training_tail=[json.loads(line) for line in lines[-2:]]
gpu=subprocess.check_output(['nvidia-smi','--query-gpu=index,name,memory.used,memory.total,utilization.gpu','--format=csv,noheader'],text=True,timeout=10)
print(json.dumps({'handle':handle,'process_live':live,'process_state':proc_state,'runner':status,'report':details,'checkpoints':checkpoints,'training_tail':training_tail,'gpu':gpu,'log_tail':tail}))
""".replace('REMOTE',repr(REMOTE)).replace('MODE',repr(args.mode))
    compile(program,'remote-observe','exec')
    result=json.loads(subprocess.check_output(['ssh',*options,'-p',port,host,'python -c '+shlex.quote(program)],text=True,encoding='utf8',timeout=45))
    result['observed_utc']=datetime.now(timezone.utc).isoformat()
    folder=R/'observations';folder.mkdir(exist_ok=True)
    name=args.mode+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json'
    (folder/name).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    concise={k:v for k,v in result.items() if k not in ('log_tail','report','checkpoints')}
    concise['completed_epochs']=[x['epoch'] for x in result['checkpoints'] if x.get('full_epoch')]
    if result['report']:concise['report']=result['report']
    elif not result['training_tail'] or (result.get('runner') or {}).get('status')=='failed':concise['log_tail']=result['log_tail'][-1800:]
    print(json.dumps(concise,ensure_ascii=False))


if __name__=='__main__':main()
