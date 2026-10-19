"""One-shot cleanup of this run's pod after verified artifact retrieval."""
import datetime
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parent

def main():
    state=json.loads((ROOT/'CLOUD_RUN.json').read_text())
    verified=json.loads((ROOT/'ARTIFACT_VERIFIED.json').read_text())
    if not verified.get('download_verified') or not verified.get('all_members_verified') or len(verified['adapters'])<3:
        raise RuntimeError('Model artifacts must be verified before deletion')
    if (ROOT/'FRESH_LOCK.json').exists():
        extra=json.loads((ROOT/'INCREMENTAL_VERIFIED.json').read_text())
        if not extra.get('download_verified') or not extra.get('all_members_verified') or len(extra['adapters'])!=3:
            raise RuntimeError('Fresh checkpoints must also be retrieved and verified')
    if (ROOT/'q4-receipt.json').exists():
        q4=json.loads((ROOT/'q4-receipt.json').read_text())
        gguf=json.loads((ROOT/'GGUF_VERIFIED.json').read_text())
        if not gguf.get('download_verified') or gguf.get('sha256')!=q4['sha256']:
            raise RuntimeError('Exported GGUF must be verified before deletion')
    pod_id=state['pod']['id']
    if pod_id!='770mwenn3u6m96' or state['spec']['name']!='crossgen-coder-release-v1':
        raise RuntimeError('Unexpected cleanup target')
    cli=str(ROOT.parent/'tools/runpodctl.exe')
    def query(*args):return json.loads(subprocess.check_output([cli,*args],text=True))
    pods=query('pod','list')
    if any(p['id']==pod_id for p in pods):
        subprocess.run([cli,'pod','delete',pod_id],check=True,capture_output=True,text=True)
    remaining=query('pod','list')
    if any(p['id']==pod_id for p in remaining):raise RuntimeError('Pod deletion not confirmed')
    user=query('user')
    receipt={'pod_id':pod_id,'deletion_verified':True,'checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'balance_snapshot':user['clientBalance'],'current_spend_per_hour':user['currentSpendPerHr'],
             'credits_added_during_run':state.get('credits_added_during_run',0),
             'credit_adjusted_balance_decrease_since_creation':state['starting_balance']+state.get('credits_added_during_run',0)-user['clientBalance'],
             'billing_note':'Balance is a snapshot and may lag usage; existing storage is included.',
             'existing_volumes_modified':False}
    (ROOT/'CLEANUP.json').write_text(json.dumps(receipt,indent=2))
    state['status']='deleted';state['cleanup']=receipt
    (ROOT/'CLOUD_RUN.json').write_text(json.dumps(state,indent=2))
    print(json.dumps(receipt,indent=2))

if __name__=='__main__':main()
