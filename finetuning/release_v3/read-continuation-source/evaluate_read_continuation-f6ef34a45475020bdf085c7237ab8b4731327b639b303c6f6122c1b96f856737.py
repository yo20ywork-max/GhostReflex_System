"""Real-file recovery diagnostic seeded with a deliberately partial first read."""
import argparse
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

R=Path(__file__).resolve().parent;ROOT=R.parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(R.parent))
from execute_plan_fixtures import load
from build_product_data import contract
from evaluate_local import request
from task_journal import TaskJournal
from text_reader import uncovered_file_reads


def main():
    p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    output=R/a.output
    if output.exists():raise FileExistsError(output)
    s,runtime_hash=load('training-contract.json');catalog,schema,_,_=contract(max_plan_steps=8)
    s['TOOL_REGISTRY']={x['name']:SimpleNamespace(parameters=x['parameters'],handler=s.get('tool_'+x['name'].lower()),risk=x['risk']) for x in catalog}
    calls=[];trace=[];started=time.monotonic()
    model=next(x for x in request('/api/tags')['models'] if x['name']==a.model)
    class Gateway:
        def chat_json(self,*,messages,schema,models=None):
            if len(calls)>=8 or time.monotonic()-started>180:raise RuntimeError('Diagnostic inference budget exhausted')
            record={'messages':messages,'schema':schema};calls.append(record)
            response=request('/api/chat',{'model':a.model,'messages':messages,'format':schema,'stream':False,'truncate':False,'shift':False,
                                          'options':{'temperature':0,'num_ctx':12288,'num_predict':1536,'repeat_penalty':1.0}})
            record['response']=response
            if response.get('done_reason')!='stop':raise ValueError('Incomplete generation')
            return json.loads(response['message']['content']),a.model
    with tempfile.TemporaryDirectory(dir=R,prefix='read-loop-') as temporary:
        work=Path(temporary).resolve()
        if not work.is_relative_to(R.resolve()):raise ValueError('Fixture workspace escaped')
        text='  台灣製作\t\r\n'+''.join(f'第{i:02}行原稿。' for i in range(30))+'\r\n片尾原文  '
        file=work/'工作稿.txt';file.write_bytes(text.encode('utf8'));original_sha=hashlib.sha256(file.read_bytes()).hexdigest()
        settings=SimpleNamespace(workspace=work,allow_outside_workspace=False,max_plan_steps=8,default_tool_retries=0,
                                 log_prompts=False,max_replans=2,planner_num_ctx=12288,planner_models=(a.model,),review_plans=False)
        journal=TaskJournal(work/'receipt.sqlite3');runtime=SimpleNamespace(journal=journal)
        gateway=Gateway();planner=s['Planner'].__new__(s['Planner']);planner.settings=settings;planner.catalog=catalog;planner.schema=schema;planner.hint_engine=None;planner.gateway=gateway
        actual_plan=planner.plan;first=True
        def plan(*args,**kwargs):
            nonlocal first
            if first:
                first=False
                return s['TaskPlan']('讀取全文',[],[s['PlanStep'](1,'讀取檔案','READ_TEXT_FILE',{'path':'工作稿.txt','max_chars':100},'讀回完整內容','replan',0)],['全文讀齊'],model=a.model)
            return actual_plan(*args,**kwargs)
        planner.plan=plan
        agent=s['UniversalAgent'].__new__(s['UniversalAgent']);agent.settings=settings;agent.runtime=runtime;agent.gateway=gateway;agent.planner=planner
        agent._confirm_step=lambda *_:True;agent.runtime_context=lambda:{'workspace':str(work)};agent.print_plan=lambda _:None
        execute=agent._execute_step
        def bounded(ctx,step):
            if step.tool not in {'READ_TEXT_FILE','FINAL_RESPONSE','BLOCKED'} or (step.tool=='FINAL_RESPONSE' and step.args.get('copy_to_clipboard')):
                return s['ToolResult'](False,error='Tool outside isolated read-only fixture',terminal=True)
            if len(trace)>=10:return s['ToolResult'](False,error='Fixture step limit',terminal=True)
            result=execute(ctx,step);trace.append({'id':step.id,'tool':step.tool,'args':step.args,'ok':result.ok,'error':result.error,'evidence':result.evidence})
            return result
        agent._execute_step=bounded
        try:
            result=agent.run('完整讀取「工作稿.txt」，不要修改檔案；讀完後只回覆「已讀完」。')
            reads=[x for x in result.history if x['tool']=='READ_TEXT_FILE' and x['ok']]
            gaps=uncovered_file_reads(result.history)
            continued=any(x['args'].get('offset_chars',0)>0 for x in reads)
            unchanged=hashlib.sha256(file.read_bytes()).hexdigest()==original_sha
            report={'status':result.status,'message':result.message,'history':result.history,'calls':calls,'trace':trace,
                    'complete_file_coverage':not gaps,'gaps':gaps,'continued_by_offset':continued,'source_unchanged':unchanged,
                    'passed':result.status=='completed' and not gaps and unchanged and result.message=='已讀完',
                    'receipts':journal.read(result.request_id)}
        finally:journal.close()
    report.update(model_digest=model['digest'],seconds=time.monotonic()-started,runtime_normalized_sha256=runtime_hash,
                  helper_sha256=hashlib.sha256((ROOT/'text_reader.py').read_bytes()).hexdigest(),fixture_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  scope='One actual file recovery diagnostic; first 100-character read manually seeded. Subsequent plans and completion use the specified local model and current runtime. Not native/target hardware or general release acceptance.',product_release_approved=False)
    with output.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k not in {'history','calls','trace','receipts'}}),flush=True)


if __name__=='__main__':main()
