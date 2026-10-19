"""Disposable actual file execution and an independent artifact/history oracle.

The fixture restriction is not a claim that production has this task-specific
authorization policy. Expected artifacts stay outside planner inputs.
"""
import ast
import hashlib
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

R=Path(__file__).resolve().parent
ROOT=R.parents[1]
V3=R.parent/'release_v3'
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(V3));sys.path.insert(0,str(R.parent))
from execute_plan_fixtures import load
from build_product_data import contract
from task_journal import TaskJournal
from text_reader import completed_file_contents


def cases():
    lock=json.loads((R/'FILE_DEV_LOCK_V2.json').read_text(encoding='utf8'))
    path=R/lock['file']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=lock['sha256']:raise ValueError('Development input changed')
    return [json.loads(x) for x in path.read_text(encoding='utf8').splitlines()]


def runtime():
    scope,_=load('training-contract.json')
    tree=ast.parse((ROOT/'run_daemon.py').read_text(encoding='utf-8-sig'))
    nodes=[n for n in tree.body if getattr(n,'name','') in {'tool_write_text_file','tool_append_text_file','tool_make_directory'}]
    for node in nodes:node.decorator_list=[]
    module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*nodes],type_ignores=[])
    exec(compile(ast.fix_missing_locations(module),'<actual v4 file handlers>','exec'),scope)
    catalog,schema,_,_=contract(max_plan_steps=24)
    scope['TOOL_REGISTRY']={x['name']:SimpleNamespace(parameters=x['parameters'],risk=x['risk'],handler=scope.get('tool_'+x['name'].lower())) for x in catalog}
    return scope,catalog,schema


def relative(work,path):
    p=Path(path)
    if not p.is_absolute():p=work/p
    p=p.resolve()
    if not p.is_relative_to(work):raise ValueError('Outside fixture workspace')
    return p.relative_to(work).as_posix()


def evaluate(row,work,history,status,message):
    """Verify actual bytes, original preservation, source reads and post-write reads."""
    issues=[];file_hashes={}
    for path,expected in row['expected_files'].items():
        target=work/path
        if not target.is_file():issues.append('Missing file: '+path);continue
        data=target.read_bytes();file_hashes[path]=hashlib.sha256(data).hexdigest()
        if data!=expected.encode('utf8'):issues.append('Wrong file bytes: '+path)
    actual_paths={p.relative_to(work).as_posix() for p in work.rglob('*') if p.is_file()}
    if actual_paths-set(row['expected_files']):issues.append('Unexpected files: '+str(sorted(actual_paths-set(row['expected_files']))))
    successful=[]
    for index,item in enumerate(history):
        if item.get('ok') is not True or item.get('verified') is not True:continue
        path=(item.get('evidence') or {}).get('path') or (item.get('args') or {}).get('path')
        try:path=relative(work,path) if path is not None else None
        except (ValueError,TypeError):issues.append('Invalid successful observation path');continue
        successful.append((index,item,path))
        if item.get('tool') in {'WRITE_TEXT_FILE','APPEND_TEXT_FILE'}:
            if item['tool'] not in row['write_targets'].get(path,[]):issues.append('Unauthorized successful mutation: '+str(path))
    # Every required output must be fully read after its final successful write.
    for path in row['required_readback']:
        writes=[i for i,h,p in successful if p==path and h['tool'] in {'WRITE_TEXT_FILE','APPEND_TEXT_FILE'}]
        if not writes:issues.append('No successful write: '+path);continue
        if len(writes)!=1:issues.append('Repeated successful write: '+path)
        after=history[max(writes)+1:]
        try:full=completed_file_contents(after)
        except ValueError as exc:issues.append('Readback evidence invalid: '+str(exc));continue
        observed=full.get(str((work/path).resolve()))
        if not observed or observed['text']!=row['expected_files'][path]:issues.append('Missing exact full post-write readback: '+path)
    for path in row.get('required_existence_checks',[]):
        found=False
        for _,h,p in successful:
            if h['tool']=='READ_TEXT_FILE' and p==path:found=True
            if h['tool']=='LIST_DIRECTORY' and isinstance(h.get('output'),list):
                for item in h['output']:
                    try:
                        if isinstance(item,dict) and relative(work,item['path'])==path:found=True
                    except (KeyError,ValueError,TypeError):pass
        if not found:issues.append('Existence was not observed: '+path)
    # Source dependencies are declared separately from model input. They encode
    # the explicit read-before-save requirements of these eight authored cases.
    dependency_map={
        'v4-file-01':{'訪談備份.txt':['訪談記錄.txt']},
        'v4-file-02':{'交付/錄影清單.txt':['錄影清單.txt'],'交付/錄音清單.txt':['錄音清單.txt']},
        'v4-file-03':{'總筆記.txt':['新增筆記.txt']},
        'v4-file-04':{'合稿.txt':['前半.txt','後半.txt']},
        'v4-file-05':{'空白副本.txt':['空白原稿.txt']},
        'v4-file-06':{},
        'v4-file-07':{'待核對.txt':['來源稿.txt']},
        'v4-file-08':{'長副本.txt':['長原稿.txt']},
    }
    for destination,sources in dependency_map[row['id']].items():
        writes=[i for i,h,p in successful if p==destination and h['tool'] in {'WRITE_TEXT_FILE','APPEND_TEXT_FILE'}]
        if not writes:continue  # Already reported above.
        try:observed=completed_file_contents(history[:min(writes)])
        except ValueError as exc:issues.append('Source evidence invalid: '+str(exc));continue
        for source in sources:
            value=observed.get(str((work/source).resolve()))
            if not value or value['text']!=row['initial_files'][source]:issues.append('Source not fully read before write: '+source)
    evidence_ok=not issues
    response_ok=message==row['expected_response']
    return {'passed':evidence_ok and response_ok and status=='completed','evidence_ok':evidence_ok,'response_ok':response_ok,'false_completion':status=='completed' and not(evidence_ok and response_ok),'issues':issues,'file_sha256':file_hashes}


class Fixture:
    def __init__(self,row,folder,model,gateway):
        self.row=row;self.work=(Path(folder)/'work').resolve();self.work.mkdir()
        for name,text in row['initial_files'].items():
            path=self.work/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(text.encode('utf8'))
        self.scope,self.catalog,self.schema=runtime()
        self.settings=SimpleNamespace(workspace=self.work,allow_outside_workspace=False,max_plan_steps=24,default_tool_retries=0,log_prompts=False,max_replans=3,planner_num_ctx=12288,planner_models=(model,),review_plans=False)
        self.journal=TaskJournal(Path(folder)/'receipts.sqlite3')
        self.runtime=SimpleNamespace(journal=self.journal)
        self.agent=self.scope['UniversalAgent'].__new__(self.scope['UniversalAgent'])
        self.agent.settings=self.settings;self.agent.runtime=self.runtime;self.agent.gateway=gateway
        self.agent.runtime_context=lambda:{'workspace':str(self.work)}
        self.agent.print_plan=lambda _:None;self.agent._confirm_step=lambda *_:True
        self.trace=[];self.started=time.monotonic();execute=self.agent._execute_step
        def bounded(ctx,step):
            if len(self.trace)>=32 or time.monotonic()-self.started>300:
                return self.scope['ToolResult'](False,error='Bounded development dispatch budget exhausted',terminal=True)
            try:
                args=self.scope['resolve_references'](step.args,ctx.step_results,ctx.history)
                tool=step.tool
                if tool in {'FINAL_RESPONSE','BLOCKED'}:
                    if args.get('copy_to_clipboard',False):raise ValueError('Clipboard outside fixture')
                elif tool in {'READ_TEXT_FILE','LIST_DIRECTORY','WRITE_TEXT_FILE','APPEND_TEXT_FILE','MAKE_DIRECTORY'}:
                    path=relative(self.work,args.get('path','.'))
                    if tool in {'WRITE_TEXT_FILE','APPEND_TEXT_FILE','MAKE_DIRECTORY'}:
                        if tool not in row['write_targets'].get(path,[]):raise ValueError('This task does not authorize '+tool+' on '+path)
                        if tool=='WRITE_TEXT_FILE' and args.get('overwrite',False) is not False:
                            raise ValueError('New-file creation must use overwrite=false; existing files must be preserved')
                else:raise ValueError('Tool outside isolated file task: '+tool)
                result=execute(ctx,step)
            except (ValueError,KeyError,TypeError) as exc:
                result=self.scope['ToolResult'](False,error='Pre-dispatch validation: '+str(exc))
            self.trace.append({'id':step.id,'tool':step.tool,'proposed_args':step.args,'ok':result.ok,'error':result.error})
            return result
        self.agent._execute_step=bounded
        self.ctx=self.scope['ExecutionContext'](settings=self.settings,runtime=self.runtime,gateway=gateway,request_id=row['id']+'-seed',original_prompt=row['user_request'])

    def step(self,tool,args,goal='Authored fixture setup'):
        step=self.scope['PlanStep'](max(self.ctx.step_results,default=0)+1,goal,tool,args,'Actual handler result','replan',0)
        result=self.agent._execute_step(self.ctx,step)
        if not result.ok or not result.verified:raise ValueError(result.error)
        self.ctx.step_results[step.id]=result
        self.ctx.history.append({'step_id':step.id,'tool':tool,'goal':goal,'args':self.ctx.resolved_arguments.get(step.id,args),'ok':result.ok,'verified':result.verified,'output':result.output,'error':result.error,'terminal':result.terminal,'evidence':result.evidence})
        return step.id

    def seed(self):
        seed=self.row.get('seed')
        if not seed:return
        args={'path':seed['source'],'max_chars':seed.get('max_chars',500000)}
        id_=self.step('READ_TEXT_FILE',args)
        if seed['kind']=='actual_read_then_exclusive_copy':
            self.step('WRITE_TEXT_FILE',{'path':seed['destination'],'content':'{{step:'+str(id_)+'.file_text}}','overwrite':False})

    def run(self,model,gateway):
        self.seed()
        planner=self.scope['Planner'].__new__(self.scope['Planner']);planner.settings=self.settings;planner.catalog=self.catalog;planner.schema=self.schema;planner.hint_engine=None;planner.gateway=gateway
        actual_plan=planner.plan;first=True
        def initial(*args,**kwargs):
            nonlocal first
            if first and self.ctx.history:
                kwargs.update(failure_context={'original_request':self.row['user_request'],'reserved_step_ids':sorted(self.ctx.step_results),'completed_and_failed_history':self.ctx.history,'failed_step':{'tool':'GOAL_VERIFICATION','goal':'從真實已完成步驟接續原始任務','args':{},'error':'任務中間狀態，請依真實歷史完成尚餘要求。'},'replan_number':1},allow_deterministic=False)
            else:kwargs['allow_deterministic']=False
            first=False
            return actual_plan(*args,**kwargs)
        planner.plan=initial;self.agent.planner=planner
        cls=self.scope['ExecutionContext']
        def resumed(**kwargs):return cls(**kwargs,step_results=dict(self.ctx.step_results),history=json.loads(json.dumps(self.ctx.history,ensure_ascii=False)))
        self.scope['ExecutionContext']=resumed
        result=self.agent.run(self.row['user_request'])
        return result,self.journal.read(result.request_id),self.journal.read(self.ctx.request_id)

    def close(self):self.journal.close()
