"""Snapshot costs, or delete exactly this run's pod after local artifact verification."""
import argparse,datetime,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent
CLI=str(R.parent/'tools/runpodctl.exe')
def call(*args):return json.loads(subprocess.check_output([CLI,*args],text=True,encoding='utf8'))
def main():
 p=argparse.ArgumentParser();p.add_argument('--delete',action='store_true');a=p.parse_args()
 state=json.loads((R/'CLOUD_RUN.json').read_text());podid=state['pod']['id'];pods=call('pod','list');user=call('user')
 record={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'pod_id':podid,'starting_balance':state['starting_balance'],'balance':user['clientBalance'],'account_balance_decrease':state['starting_balance']-user['clientBalance'],'account_current_spend_per_hour':user['currentSpendPerHr'],'scope':'Account balance decrease includes pre-existing storage and billing lag; not a per-pod invoice.'}
 if a.delete:
  verification=json.loads((R/'ARTIFACT_VERIFIED.json').read_text())
  if not verification['verified'] or len(verification['models'])<2:raise RuntimeError('Artifacts not safely retained')
  active=next((x for x in pods if x['id']==podid),None)
  if active and active['name']!=state['spec']['name']:raise RuntimeError('Pod identity mismatch')
  if active:subprocess.run([CLI,'pod','delete',podid],check=True,capture_output=True)
  after=call('pod','list')
  if any(x['id']==podid for x in after):raise RuntimeError('Deletion not yet verified')
  user=call('user');record.update(deletion_verified=True,remaining_pod_ids=[x['id'] for x in after],final_balance_snapshot=user['clientBalance'],final_account_balance_decrease=state['starting_balance']-user['clientBalance'],existing_network_volumes_untouched=True)
  (R/'CLOUD_CLEANUP.json').write_text(json.dumps(record,indent=2));state['status']='deleted';(R/'CLOUD_RUN.json').write_text(json.dumps(state,indent=2))
 else:(R/'COST_SNAPSHOT.json').write_text(json.dumps(record,indent=2))
 print(json.dumps(record))
if __name__=='__main__':main()
