"""Snapshot all generation development gates; never open final holdouts."""
import ast
import hashlib
import json
from pathlib import Path
import sys

R=Path(__file__).resolve().parent
ROOT=R.parents[1]
sys.path.insert(0,str(ROOT))
from product_identity import GENERATION_SYSTEM,generation_system


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf8'))
def rows(path):return [json.loads(x) for x in path.read_text(encoding='utf8').splitlines()]
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')


def main():
    dest=R/'evaluation-v1'
    if dest.exists():raise FileExistsError(dest)
    lock=read(R/'DATA_LOCK.json')
    assert all(sha(R/n)==h for n,h in lock['sha256'].items())
    assert sha(ROOT/'run_daemon.py')==sha(R/'runtime_source.py'),'Current runtime changed'
    old=R.parent/'release_v4';old_lock=read(old/'DATA_LOCK.json')
    assert sha(old/'dev.jsonl')==old_lock['sha256']['dev.jsonl']
    current={r['id']:r for r in rows(R/'dev.jsonl')}
    original=rows(old/'dev.jsonl');core=[]
    for row in original:
        if row['category']=='identity':continue # superseded only by explicit user policy
        chosen=current[row['id']]
        assert all(chosen[k]==row[k] for k in ('prompt','answer','oracle')),'Original criterion changed'
        core.append(chosen)
    regression=R.parent/'release_v3/regression.jsonl'
    assert sha(regression)==sha(R.parent/'release_v2/regression.jsonl')
    excluded=set(read(R/'RELEASE_GATES.json')['development']['critical_history_regression']['excluded_identity_ids'])
    critical=[r for r in rows(regression) if r['id'] not in excluded]
    paths={'brand':R/'brand-dev.jsonl','locale_context':R.parent/'locale_v12/candidate-v2/dev.jsonl',
           'history_binding':R.parent/'history_v9/draft-v1/dev.jsonl','evidence':R.parent/'identity_v10/evidence-draft-v1/dev.jsonl'}
    suites={'core':core,'critical':critical}
    for name,path in paths.items():
        source=rows(path);data=[]
        for row in source:
            migrated=current[row['id']]
            assert all(row[k]==migrated[k] for k in ('prompt','answer','oracle')),'Supplemental criterion changed'
            data.append(migrated)
        suites[name]=data
    expected={'core':101,'critical':11,'brand':16,'locale_context':24,'history_binding':12,'evidence':12}
    assert {k:len(v) for k,v in suites.items()}==expected
    flat=[]
    for suite,data in suites.items():
        for original in data:
            row={k:v for k,v in original.items() if k not in ('source','license','attribution')}
            row['suite']=suite
            # Avoid adding the product prefix twice when migrated task systems
            # already contain it. User instruction text itself is unchanged.
            prefix=GENERATION_SYSTEM+'\n\n本次任務要求：\n'
            system=row['system']
            task=system[len(prefix):] if system.startswith(prefix) else ('' if system==GENERATION_SYSTEM else system)
            row['gateway_task_system']=task
            row['gateway_system']=system if row['oracle']['type'] in ('plan','completion') else generation_system(task)
            flat.append(row)
    assert len({r['id'] for r in flat})==len(flat)
    schemas=[]
    for node in ast.walk(ast.parse((R/'runtime_source.py').read_text(encoding='utf-8-sig'))):
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='schema' for t in node.targets):
            try:value=ast.literal_eval(node.value)
            except (ValueError,TypeError):continue
            if isinstance(value,dict) and set(value.get('properties',{}))=={'complete','reason'}:schemas.append(value)
    assert len(schemas)==1
    dest.mkdir()
    (dest/'cases.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in flat),encoding='utf8')
    write(dest/'schemas.json',{'plan':read(R/'training-contract.json')['schema'],'completion':schemas[0]})
    source_paths=[Path(__file__),R/'DATA_LOCK.json',R/'dev.jsonl',R/'RELEASE_GATES.json',old/'dev.jsonl',regression,
        R.parent/'release_v2/regression.jsonl',ROOT/'run_daemon.py',ROOT/'product_identity.py',*paths.values()]
    write(dest/'manifest.json',{'counts':expected,'total':len(flat),'source_hashes':{str(p.relative_to(ROOT)):sha(p) for p in source_paths},
        'outputs':{p.name:sha(p) for p in dest.iterdir() if p.is_file()},
        'original_core_questions_answers_oracles_unchanged':True,'retired_identity_only':True,
        'runtime_profile':'Actual chat_json (temp0,predict2048) / chat_text (temp0.2) at context12288; separately rerun same-profile baseline',
        'user_task_text_preserved':True,'final_holdout_opened':False,'generation_only_not_actual_action_acceptance':True,'release_approved':False})
    print(json.dumps({'total':len(flat),'counts':expected,'final_holdout_opened':False}))


if __name__=='__main__':main()
