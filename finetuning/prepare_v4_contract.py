"""Refresh training/development prompts through the actual runtime, not templates.

Original answers and split membership are retained. Final holdout bytes are
hashed for lock verification only; questions are not parsed or sent to a model.
No invalid plan is silently removed or relabelled to make the audit pass.
"""
import collections
import hashlib
import json
import sys
import importlib.util
from pathlib import Path
from types import SimpleNamespace

F = Path(__file__).resolve().parent
ROOT = F.parent
V3 = F/'release_v3'
OUT = F/'release_v4'
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(V3));sys.path.insert(0,str(F))
from execute_plan_fixtures import load
from build_product_data import contract
trainer_spec=importlib.util.spec_from_file_location('crossgen_v3_training_helpers',V3/'train.py')
trainer=importlib.util.module_from_spec(trainer_spec)
trainer_spec.loader.exec_module(trainer)
verify_lock=trainer.verify_lock
tokenize_row=trainer.tokenize_row


def main():
    verify_lock()
    OUT.mkdir(exist_ok=False)
    scope,_=load('training-contract.json')
    catalog,schema,_,_=contract(max_plan_steps=24)
    settings=SimpleNamespace(max_plan_steps=24,default_tool_retries=0,planner_models=('authored-source',),review_plans=False,planner_num_ctx=12288)
    scope['TOOL_REGISTRY']={x['name']:SimpleNamespace(parameters=x['parameters']) for x in catalog}
    audits=[];splits={}
    class Capture:
        def __init__(self,answer):self.answer=answer;self.calls=[]
        def chat_json(self,*,messages,schema,models=None):
            self.calls.append({'messages':messages,'schema':schema})
            return self.answer,'authored-source'
    def refresh(row,origin):
        result=dict(row)
        try:answer=json.loads(row['answer'])
        except (ValueError,TypeError):return result
        planner=scope['Planner'].__new__(scope['Planner']);planner.settings=settings;planner.catalog=catalog;planner.schema=schema;planner.hint_engine=None;planner.gateway=Capture(answer)
        try:payload=json.loads(row['prompt'])
        except (ValueError,TypeError):payload=None
        if isinstance(answer,dict) and isinstance(answer.get('steps'),list):
            if isinstance(payload,dict) and 'user_request' in payload:
                request=payload['user_request'];runtime=payload.get('runtime_context',{});failure=payload.get('replanning_context')
            else:
                request=row['prompt'];runtime={};failure=None
            parsed=planner.plan(request,runtime,failure_context=failure,allow_deterministic=False)
            valid=parsed.model=='authored-source' and [(s.id,s.tool,s.args) for s in parsed.steps]==[(s['id'],s['tool'],s['args']) for s in answer['steps']]
            error=None if valid else str(parsed.steps[0].args)
        elif isinstance(answer,dict) and type(answer.get('complete')) is bool:
            if not isinstance(payload,dict) or 'observed_history' not in payload:raise ValueError('Missing completion history '+row['id'])
            actual,reason=planner.assess_completion(payload['user_request'],payload['observed_history'])
            valid=actual==answer['complete'] and bool(planner.gateway.calls)
            error=None if valid else reason
        else:return result
        audits.append({'id':row['id'],'origin':origin,'category':row['category'],'valid':valid,'error':error,'capture_calls':len(planner.gateway.calls)})
        if not planner.gateway.calls:return result
        first=planner.gateway.calls[0]
        result.update(system=first['messages'][0]['content'],prompt=first['messages'][1]['content'],source_prompt_sha256=hashlib.sha256((row['system']+'\n'+row['prompt']).encode()).hexdigest(),contract_migration='Current actual Planner envelope; answer and split preserved',source_dataset=origin)
        return result
    for split in ('train','dev'):
        source=[json.loads(x) for x in (V3/f'{split}.jsonl').read_text(encoding='utf8').splitlines()]
        if split=='train':
            source += [json.loads(x) for x in (V3/'file-curriculum-v1/training-candidate.jsonl').read_text(encoding='utf8').splitlines()]
        splits[split]=[refresh(row,'v3-file-teacher' if row['id'].startswith('file-curriculum-') else f'v3-{split}') for row in source]
        for row in splits[split]:
            if row['split']=='train-candidate':row['split']='train'
        (OUT/f'{split}-draft.jsonl').write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in splits[split]),encoding='utf8')
    (OUT/'CONTRACT_AUDIT.json').write_text(json.dumps(audits,ensure_ascii=False,indent=2),encoding='utf8')
    (OUT/'training-contract.json').write_text(json.dumps({'catalog':catalog,'schema':schema,'profile':{'max_plan_steps':24,'planner_num_ctx':12288}},ensure_ascii=False,indent=2),encoding='utf8')
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(V3/'artifacts/outputs/epoch-2',local_files_only=True,trust_remote_code=False)
    stats={}
    for split,rows in splits.items():
        values=[tokenize_row(tokenizer,row,12288) for row in rows]
        stats[split]={'rows':len(rows),'categories':dict(collections.Counter(row['category'] for row in rows)),'total_tokens':sum(len(x['ids']) for x in values),'max_tokens':max(len(x['ids']) for x in values),'answer_tokens':sum(len(x['ids'])-x['prefix'] for x in values),'assistant_only_mask_verified':True}
    # Exact repeats in v3 training are preserved; do not call them new examples.
    train_signatures={(row['system'],row['prompt']) for row in splits['train']}
    overlaps=[row['id'] for row in splits['dev'] if (row['system'],row['prompt']) in train_signatures]
    train_groups={row['group'] for row in splits['train']};dev_groups={row['group'] for row in splits['dev']}
    manifest={'stats':stats,'invalid_contract_rows':[x for x in audits if not x['valid']],'train_dev_exact_prompt_overlaps':overlaps,'train_dev_group_overlaps':sorted(train_groups&dev_groups),'final_holdout_question_content_inspected':False,'final_holdout_bytes_hashed_for_lock':True,'answers_changed':False,'trained':False,'release_approved':False,'ready_for_training':False,'note':'Draft only; independent new development tasks, complete source lock, retention review and cloud preflight still required.'}
    (OUT/'DRAFT_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(manifest,ensure_ascii=False))


if __name__=='__main__':main()
