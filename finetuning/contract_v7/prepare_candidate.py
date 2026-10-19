"""Migrate existing input contracts and verify data/masks, without training."""
import argparse
from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = HERE.parent/'release_v4'
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(OLD))
from model_json import dumps as model_json_dumps
from file_flow import runtime
from build_product_data import contract
from jsonschema import Draft202012Validator


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return [json.loads(x) for x in path.read_text(encoding='utf8').splitlines()]
def request_text(row):
    try: payload = json.loads(row['prompt'])
    except ValueError: return row['prompt']
    return payload.get('user_request', row['prompt']) if isinstance(payload, dict) else row['prompt']


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--curriculum',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    if any(Path(v).name!=v for v in (args.curriculum,args.output)):raise ValueError('Use directory names only')
    curriculum=HERE/args.curriculum;dest=HERE/args.output;dest.mkdir(exist_ok=False)
    marker=json.loads((curriculum/'manifest.json').read_text(encoding='utf8'))
    if not marker.get('corpus_exported') or marker['failures'] or not marker['sources_unchanged']:raise ValueError('Curriculum has not passed execution validation')
    for name,digest in marker['sources'].items():
        if sha(ROOT/name)!=digest:raise ValueError('Curriculum execution source changed: '+name)
    lock=json.loads((OLD/'DATA_LOCK.json').read_text(encoding='utf8'))
    for name,digest in lock['sha256'].items():
        if sha(OLD/name)!=digest:raise ValueError('Original immutable data changed: '+name)
    scope,_,_=runtime();catalog,schema,prompt_builder,_=contract(max_plan_steps=24)
    planner_system=prompt_builder(SimpleNamespace(catalog=catalog,schema=schema))
    validator=Draft202012Validator(schema);settings=SimpleNamespace(max_plan_steps=24,default_tool_retries=0)
    datasets={};changes=[];retained={};errors=[]
    for split in ('train','dev'):
        originals=read(OLD/(split+'.jsonl'));converted=[];retained[split]=Counter()
        for original in originals:
            row=copy.deepcopy(original);kind=row.get('oracle',{}).get('type')
            try:
                if kind in ('plan','actual_teacher_file_copy'):
                    plan=json.loads(row['answer']);payload=json.loads(row['prompt'])
                    context=payload.get('replanning_context') or {}
                    reserved={h['step_id'] for h in context.get('completed_and_failed_history',[]) if type(h.get('step_id')) is int}
                    reserved.update(context.get('reserved_step_ids',[]))
                    validator.validate(plan);scope['validate_plan'](plan,settings,'authored-migration',reserved)
                    row['system']=planner_system
                    row['prompt']=model_json_dumps(payload)
                elif kind=='completion':
                    payload=json.loads(row['prompt']);answer=json.loads(row['answer'])
                    class Capture:
                        messages=None
                        def chat_json(self,*,messages,schema,models=None):self.messages=messages;return answer,'authored-migration'
                    checker=scope['Planner'].__new__(scope['Planner']);checker.settings=SimpleNamespace(planner_num_ctx=12288);checker.gateway=Capture()
                    complete,_=checker.assess_completion(payload['user_request'],payload['observed_history'])
                    if checker.gateway.messages is None or complete!=answer['complete']:raise ValueError('Current deterministic behavior disagrees with retained target')
                    row['system']=checker.gateway.messages[0]['content'];row['prompt']=checker.gateway.messages[-1]['content']
                if row['answer']!=original['answer'] or request_text(row)!=request_text(original):raise ValueError('Gold answer or user request changed')
                if row['category'] in ('code','literal'):
                    retained[split][row['category']]+=1
                    if row['category']=='code' and (row['system'],row['prompt'])!=(original['system'],original['prompt']):raise ValueError('Code retention input changed')
                if (row['system'],row['prompt'])!=(original['system'],original['prompt']):
                    changes.append({'id':row['id'],'split':split,'category':row['category'],'answer_unchanged':True,'user_request_unchanged':True})
                converted.append(row)
            except Exception as exc:errors.append({'id':row['id'],'split':split,'error':str(exc)})
        datasets[split]=converted+read(curriculum/(split+'.jsonl'))
    if errors:
        (dest/'rejected.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2),encoding='utf8')
        raise ValueError('Migration failed; no candidate data exported')
    seen={};groups={};requests={}
    for split,rows in datasets.items():
        if len({r['id'] for r in rows})!=len(rows):raise ValueError('Duplicate row ID')
        seen[split]={(r['system'],r['prompt']) for r in rows}
        if len(seen[split])!=len(rows):raise ValueError('Duplicate model input within split')
        groups[split]={r['group'] for r in rows};requests[split]={request_text(r) for r in rows}
        for row in rows:
            if row['oracle']['type'] in ('plan','actual_teacher_file_copy'):
                plan=json.loads(row['answer']);validator.validate(plan)
                if row.get('category')=='conditional_plan':scope['validate_plan'](plan,settings,'authored-new')
    for values in (seen,groups,requests):
        if values['train']&values['dev']:raise ValueError('Train/dev overlap')
    # Preserve the original separate file-development set; never read final tests.
    file_dev=read(OLD/'file-development-v2.jsonl')
    if {r['user_request'] for r in file_dev}&requests['train']:raise ValueError('Training repeats file development request')
    from transformers import AutoTokenizer
    tokenizer_path=OLD/'artifacts/outputs/epoch-3'
    tokenizer=AutoTokenizer.from_pretrained(tokenizer_path,local_files_only=True,trust_remote_code=False)
    spec=importlib.util.spec_from_file_location('retained_answer_mask_helper',OLD/'train.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    stats={}
    for split,rows in datasets.items():
        lengths=[];answers=[]
        for index,row in enumerate(rows,1):
            for field in ('system','prompt','answer'):
                original_text=row[field]
                decoded=tokenizer.decode(tokenizer.encode(original_text,add_special_tokens=False),skip_special_tokens=False,clean_up_tokenization_spaces=False)
                if decoded!=original_text:raise ValueError('Tokenizer changed '+field+' in '+row['id'])
            if row['oracle']['type'] in ('plan','actual_teacher_file_copy','completion') and len(tokenizer.encode(row['answer'],add_special_tokens=False))+2>2048:raise ValueError('Structured answer exceeds runtime output budget: '+row['id'])
            encoded=helper.tokenize_row(tokenizer,row,12288)
            prefix=encoded['prefix'];labels=encoded['labels'];ids=encoded['ids']
            if any(x!=-100 for x in labels[:prefix]) or labels[prefix:]!=ids[prefix:]:raise ValueError('Mask mismatch')
            lengths.append(len(ids));answers.append(len(ids)-prefix)
            if index%200==0:print(json.dumps({'split':split,'tokenized':index,'total':len(rows)}),flush=True)
        stats[split]=dict(rows=len(rows),categories=dict(Counter(r['category'] for r in rows)),total_tokens=sum(lengths),max_tokens=max(lengths),answer_tokens=sum(answers),answer_only_mask_verified=True)
    paths=[Path(__file__),ROOT/'run_daemon.py',ROOT/'model_json.py',HERE/'build_curriculum.py',curriculum/'manifest.json',curriculum/'train.jsonl',curriculum/'dev.jsonl',curriculum/'episodes.jsonl',
           OLD/'DATA_LOCK.json',OLD/'train.jsonl',OLD/'dev.jsonl',OLD/'train.py',tokenizer_path/'tokenizer.json',tokenizer_path/'tokenizer_config.json']
    sources={str(p.relative_to(ROOT)):sha(p) for p in paths}
    for split,rows in datasets.items():
        with (dest/(split+'.jsonl')).open('x',encoding='utf8') as stream:
            for row in rows:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    (dest/'model_json.py').write_bytes((ROOT/'model_json.py').read_bytes())
    (dest/'runtime_source.py').write_bytes((ROOT/'run_daemon.py').read_bytes())
    (dest/'training-contract.json').write_text(json.dumps({'catalog':catalog,'schema':schema},ensure_ascii=False,indent=2),encoding='utf8')
    manifest=dict(sources=sources,stats=stats,retention_counts={k:dict(v) for k,v in retained.items()},migrated_inputs=changes,
                  gold_answers_unchanged=True,user_requests_unchanged=True,old_files_unchanged=all(sha(OLD/n)==h for n,h in lock['sha256'].items()),
                  group_split_disjoint=True,exact_requests_disjoint=True,final_holdout_files_read=False,blind_review=False,
                  new_data_scope='Five filesystem condition/literal families, paraphrase groups and both branch states. Not native apps or broad language/factual coverage.',
                  tokenizer_text_roundtrip_verified=True,structured_answers_within_runtime_budget=True,data_preflight_passed=True,cloud_started=False,training_started=False,gpu_preflight_passed=False,release_approved=False)
    manifest['output_sha256']={name:sha(dest/name) for name in ('train.jsonl','dev.jsonl','runtime_source.py','training-contract.json','model_json.py')}
    (dest/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in manifest.items() if k in ('stats','retention_counts','data_preflight_passed','gold_answers_unchanged','old_files_unchanged','training_started','release_approved')},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
