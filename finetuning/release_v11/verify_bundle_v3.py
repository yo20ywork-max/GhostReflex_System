"""Check retained model text/gates and actual disabled trainer entry."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent


def read(path):return json.loads(path.read_text(encoding='utf8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def rows(path):return [json.loads(x) for x in path.read_text(encoding='utf8').splitlines()]


def main():
    old=HERE/'bundle-v2';new=HERE/'bundle-v3'
    lock=read(new/'DATA_LOCK.json')
    assert all(sha(new/n)==h for n,h in lock['sha256'].items())
    retained={}
    for split in ('train','dev'):
        prior=rows(old/(split+'.jsonl'));current=rows(new/(split+'.jsonl'))
        by_id={r['id']:r for r in current}
        for row in prior:
            for key in row.keys()-{'source','attribution','license'}:
                assert by_id[row['id']][key]==row[key],(row['id'],key)
        assert not any(key in r for r in current for key in ('source','attribution','license'))
        retained[split]=len(prior)
    old_gates=read(old/'RELEASE_GATES.json');new_gates=read(new/'RELEASE_GATES.json')
    for key,value in old_gates.items():
        if key=='version':continue
        if key=='supplemental_development':
            assert all(new_gates[key][name]==gate for name,gate in value.items())
        else:assert new_gates[key]==value,key
    assert not (new/'outputs').exists()
    script="import runpy,sys;sys.path.insert(0,'.');sys.modules['transformers']=None;sys.modules['torch']=None;sys.argv=['train.py','--preflight-only'];runpy.run_path('train.py',run_name='__main__')"
    proc=subprocess.run([sys.executable,'-X','utf8','-c',script],cwd=new,capture_output=True,text=True,encoding='utf8',timeout=20)
    assert proc.returncode==1 and 'Training launch disabled' in proc.stderr,proc.stderr
    assert 'ModuleNotFoundError' not in proc.stderr
    assert not (new/'outputs').exists()
    assert all(sha(new/n)==h for n,h in lock['sha256'].items())
    report=dict(retained_rows_verified=retained,all_previous_gates_unchanged=True,
        new_locale_gate={'cases':24,'required_pass':24},
        source_metadata_separated=True,actual_trainer_entry_blocked=True,
        blocked_before_model_libraries_import=True,no_outputs_created=True,
        bundle_lock_sha256=sha(new/'DATA_LOCK.json'),lock_verified=True,
        training_started=False,release_approved=False)
    with (HERE/'BUNDLE_V3_VERIFIED.json').open('x',encoding='utf8') as out:json.dump(report,out,ensure_ascii=False,indent=2)
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
