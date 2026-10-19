"""Freeze v4 only after input contracts, retention anchors and masks pass.

The v3 final holdout stays in place and is only referenced by its existing lock.
This script does not load model weights, provision resources or start training.
"""
import ast
import collections
import hashlib
import importlib.util
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from transformers import AutoTokenizer

R=Path(__file__).resolve().parent
V3=R.parent/'release_v3'


def main():
    if (R/'DATA_LOCK.json').exists():raise FileExistsError('Training already frozen')
    spec=importlib.util.spec_from_file_location('v4_locked_training_helper',R/'train.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    config=json.loads((R/'config-draft.json').read_text(encoding='utf8'))
    validator=Draft202012Validator(json.loads((R/'training-contract.json').read_text(encoding='utf8'))['schema'])
    tokenizer=AutoTokenizer.from_pretrained(V3/'artifacts/outputs/epoch-2',local_files_only=True,trust_remote_code=False)
    stats={};splits={};prompts={};groups={};requests={};identities={}
    for split,filename in [('train','train-draft-v2.jsonl'),('dev','dev-draft.jsonl')]:
        rows=[json.loads(x) for x in (R/filename).read_text(encoding='utf8').splitlines()]
        prompts[split]=set();groups[split]=set();requests[split]=set();identities[split]=set();lengths=[];answer_lengths=[]
        for row in rows:
            assert row['id'] not in identities[split],row['id'];identities[split].add(row['id'])
            key=(row['system'],row['prompt'])
            if key in prompts[split]:raise ValueError('Duplicate migrated input: '+row['id'])
            prompts[split].add(key);groups[split].add(row['group'])
            try:payload=json.loads(row['prompt'])
            except ValueError:payload=None
            requests[split].add(payload['user_request'] if isinstance(payload,dict) and isinstance(payload.get('user_request'),str) else row['prompt'])
            encoded=helper.tokenize_row(tokenizer,row,config['max_length']);lengths.append(len(encoded['ids']));answer_lengths.append(len(encoded['ids'])-encoded['prefix'])
            try:answer=json.loads(row['answer'])
            except ValueError:answer=None
            if isinstance(answer,dict) and 'steps' in answer:validator.validate(answer)
            if row['oracle']['type']=='completion':
                assert type(answer['complete']) is bool and answer['complete']==row['oracle']['complete']
        splits[split]=rows
        stats[split]={'rows':len(rows),'categories':dict(collections.Counter(row['category'] for row in rows)),'total_tokens':sum(lengths),'max_tokens':max(lengths),'answer_tokens':sum(answer_lengths),'assistant_only_mask_verified':True,'within_split_duplicate_inputs':0}
    for values in (prompts,groups,requests,identities):
        if values['train']&values['dev']:raise ValueError('Cross-split overlap')
    new_dev=[json.loads(x) for x in (R/'file-development-v2.jsonl').read_text(encoding='utf8').splitlines()]
    assert not {x['user_request'] for x in new_dev}&requests['train']
    reused={}
    for split in ('train','dev'):
        prior={x['id']:x for x in map(json.loads,(V3/f'{split}.jsonl').read_text(encoding='utf8').splitlines())}
        count=collections.Counter()
        for row in splits[split]:
            if row['category'] not in {'code','literal'}:continue
            old=prior[row['id']]
            for key in ('answer','oracle','retain'):
                if row[key]!=old[key]:raise ValueError('Retention anchor changed: '+row['id']+' '+key)
            if row['system']!=old['system'] or row['prompt']!=old['prompt']:
                # Some literal-preservation rows are tool plans. Their outer
                # runtime envelope was intentionally migrated; target literals,
                # original request and oracle must still be identical.
                if old['oracle']['type']!='plan':raise ValueError('Non-plan retention input changed: '+row['id'])
                expected_hash=hashlib.sha256((old['system']+'\n'+old['prompt']).encode()).hexdigest()
                assert row['source_prompt_sha256']==expected_hash
                try:old_payload=json.loads(old['prompt'])
                except ValueError:old_payload=None
                original_request=old_payload['user_request'] if isinstance(old_payload,dict) and 'user_request' in old_payload else old['prompt']
                assert json.loads(row['prompt'])['user_request']==original_request
                count['literal_plan_envelope_refreshed']+=1
            count[row['category']]+=1
        reused[split]=dict(count)
    for name,rows in [('train.jsonl',splits['train']),('dev.jsonl',splits['dev'])]:
        with (R/name).open('x',encoding='utf8') as f:
            for row in rows:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    with (R/'config.json').open('x',encoding='utf8') as f:json.dump(config,f,ensure_ascii=False,indent=2)
    with (R/'runtime_source.py').open('xb') as f:f.write((R.parents[1]/'run_daemon.py').read_bytes())
    source_lock={'v3_data_lock_sha256':hashlib.sha256((V3/'DATA_LOCK.json').read_bytes()).hexdigest(),'final_holdout':'../release_v3/test.jsonl and provenance-audit.jsonl remain governed by existing selection policy','final_questions_inspected_or_copied':False,'retention_targets_unchanged':reused,'literal_plan_envelopes_refreshed_where_counted':True,'gold_code_tests_rerun_this_preflight':0,'gold_code_validation_reused_from_v3':True}
    with (R/'RETENTION_AND_HOLDOUT_REFERENCE.json').open('x',encoding='utf8') as f:json.dump(source_lock,f,ensure_ascii=False,indent=2)
    files=['train.jsonl','dev.jsonl','config.json','training-contract.json','train.py','answer_loss.py','requirements-cloud.txt','cloud_run.sh','runtime_source.py','RETENTION_AND_HOLDOUT_REFERENCE.json','FILE_COMPLETION_TRAINING.json','FILE_DEV_LOCK_V2.json','file-development-v2.jsonl','freeze_training.py']
    for name in files:
        if name.endswith('.py'):ast.parse((R/name).read_text(encoding='utf8'))
    lock={'sha256':{name:hashlib.sha256((R/name).read_bytes()).hexdigest() for name in files},'preflight':stats,'retention_and_holdout':source_lock,'gpu_preflight_passed':False,'training_started':False,'release_approved':False}
    with (R/'DATA_LOCK.json').open('x',encoding='utf8') as f:json.dump(lock,f,ensure_ascii=False,indent=2)
    print(json.dumps({'preflight':stats,'retention_anchors':reused,'locked_files':len(files),'gpu_preflight_passed':False}))


if __name__=='__main__':main()
