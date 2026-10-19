"""Original eight requests, current desktop handlers, independent byte oracle.

The old tool-name-specific oracle is also retained in every result. The full
request oracle additionally recognizes cryptographically verified byte copy
and PATH_INFO, while enforcing the original existing-target no-source-read rule.
"""
import ast
import hashlib
import sys
import time
from pathlib import Path
from types import SimpleNamespace

R=Path(__file__).resolve().parent
ROOT=R.parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(R.parent/'release_v4'));sys.path.insert(0,str(R.parent/'contract_v8'))
from file_flow import Fixture as OriginalFixture,cases,evaluate as original_evaluate,relative
from desktop_contract import extend_scope
from desktop_session import install as install_desktop_guard
from explicit_reply import install_reply_completion_guard
from text_reader import completed_file_contents
from step_conditions import check_condition

DEPENDENCIES={
    'v4-file-01':{'訪談備份.txt':['訪談記錄.txt']},
    'v4-file-02':{'交付/錄影清單.txt':['錄影清單.txt'],'交付/錄音清單.txt':['錄音清單.txt']},
    'v4-file-03':{'總筆記.txt':['新增筆記.txt']},
    'v4-file-04':{'合稿.txt':['前半.txt','後半.txt']},
    'v4-file-05':{'空白副本.txt':['空白原稿.txt']},
    'v4-file-06':{},
    'v4-file-07':{'待核對.txt':['來源稿.txt']},
    'v4-file-08':{'長副本.txt':['長原稿.txt']},
}


class Fixture(OriginalFixture):
    def __init__(self,row,folder,model,gateway):
        super().__init__(row,folder,model,gateway)
        try:
            node=next(n for n in ast.parse((ROOT/'run_daemon.py').read_text(encoding='utf-8-sig')).body if getattr(n,'name','')=='tool_path_info')
            node.decorator_list=[]
            module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),node],type_ignores=[])
            exec(compile(ast.fix_missing_locations(module),'<actual desktop PATH_INFO>','exec'),self.scope)
            self.scope['TOOL_REGISTRY']['PATH_INFO'].handler=self.scope['tool_path_info']
            extend_scope(self.scope,self.catalog)
            self.catalog=self.scope['build_tool_catalog']();self.schema=self.scope['build_plan_schema'](self.settings)
            install_desktop_guard(SimpleNamespace(**self.scope));install_reply_completion_guard(self.scope['Planner'])
            actual=self.scope['UniversalAgent']._execute_step.__get__(self.agent)
            def bounded(ctx,step):
                result=None;dispatched=False
                try:
                    if len(self.trace)>=32 or time.monotonic()-self.started>300:raise ValueError('Fixture action/time budget exhausted')
                    if step.when is not None and not check_condition(step.when,ctx.step_results)[0]:
                        result=actual(ctx,step)
                        self.trace.append({'id':step.id,'tool':step.tool,'proposed_args':step.args,'dispatched':True,
                            'ok':result.ok,'error':result.error,'condition_skipped':bool((result.evidence or {}).get('condition_skipped'))})
                        return result
                    args=self.scope['resolve_references'](step.args,ctx.step_results,ctx.history)
                    name=step.tool
                    if name in ('BLOCKED','FINAL_RESPONSE'):
                        if args.get('copy_to_clipboard'):raise ValueError('Clipboard outside fixture')
                    elif name=='COPY_FILE_VERIFIED':
                        dest=relative(self.work,args['destination']);source=relative(self.work,args['source'])
                        allowed=DEPENDENCIES[row['id']].get(dest,[])
                        if row['id']=='v4-file-06':
                            if (source,dest,args.get('if_exists'))!=('原稿.txt','既有副本.txt','skip'):raise ValueError('Wrong conditional-copy request')
                        elif allowed!=[source] or 'WRITE_TEXT_FILE' not in row['write_targets'].get(dest,[]):raise ValueError('Copy not authorized by original request')
                    elif name in ('PATH_INFO','READ_TEXT_FILE','LIST_DIRECTORY','WRITE_TEXT_FILE','APPEND_TEXT_FILE','MAKE_DIRECTORY'):
                        path=relative(self.work,args.get('path','.'))
                        if name in ('WRITE_TEXT_FILE','APPEND_TEXT_FILE','MAKE_DIRECTORY'):
                            if name not in row['write_targets'].get(path,[]):raise ValueError('Mutation not authorized by original request')
                            if name=='WRITE_TEXT_FILE' and args.get('overwrite',False) is not False:raise ValueError('Overwrite forbidden')
                    else:raise ValueError('Tool outside disposable file scope')
                    dispatched=True;result=actual(ctx,step)
                except (ValueError,KeyError,TypeError) as exc:
                    result=self.scope['ToolResult'](False,error='Fixture pre-dispatch: '+str(exc))
                self.trace.append({'id':step.id,'tool':step.tool,'proposed_args':step.args,'dispatched':dispatched,
                    'ok':result.ok,'error':result.error,'condition_skipped':bool((result.evidence or {}).get('condition_skipped'))})
                return result
            self.agent._execute_step=bounded
            self.scope['console_print']=lambda *_:None
        except Exception:
            self.close();raise


def evaluate(row,work,history,status,message,source_opens=(),trace=()):
    old=original_evaluate(row,work,history,status,message)
    issues=[]
    expected={n:v.encode('utf8') for n,v in row['expected_files'].items()}
    actual={p.relative_to(work).as_posix():p.read_bytes() for p in work.rglob('*') if p.is_file()}
    if actual!=expected:issues.append('Actual file set or exact bytes differ from original request')
    if any(not t['dispatched'] for t in trace):issues.append('Proposed unauthorized or unresolvable action')
    successful=[]
    for index,item in enumerate(history):
        if item.get('ok') is not True or item.get('verified') is not True or (item.get('evidence') or {}).get('condition_skipped'):continue
        successful.append((index,item))
    def path_of(item,key='path'):
        value=(item.get('evidence') or {}).get(key) or (item.get('args') or {}).get(key)
        return relative(work,value) if value is not None else None
    for dest,sources in DEPENDENCIES[row['id']].items():
        writes=[]
        for index,item in successful:
            if item['tool'] in ('WRITE_TEXT_FILE','APPEND_TEXT_FILE') and path_of(item)==dest:
                writes.append((index,item,False))
                if item['tool'] not in row['write_targets'].get(dest,[]):issues.append('Unauthorized mutation: '+dest)
            if item['tool']=='COPY_FILE_VERIFIED' and path_of(item,'destination')==dest and (item.get('evidence') or {}).get('copied') is True:
                writes.append((index,item,True))
        if len(writes)!=1:
            issues.append('Expected exactly one successful publication/write: '+dest);continue
        index,item,copied=writes[0]
        if copied:
            e=item.get('evidence') or {}
            expected_sha=hashlib.sha256(expected[dest]).hexdigest()
            if (len(sources)!=1 or path_of(item,'source')!=sources[0] or e.get('source_read') is not True
                or e.get('content_verified') is not True or e.get('destination_readback_verified') is not True
                or e.get('sha256')!=expected_sha or type(e.get('bytes')) is not int or e['bytes']!=len(expected[dest])):
                issues.append('Copy lacks matching complete-source and post-publication readback evidence: '+dest)
        else:
            before=completed_file_contents(history[:index]);after=completed_file_contents(history[index+1:])
            for source in sources:
                seen=before.get(str((work/source).resolve()))
                if seen is None or seen['text']!=row['initial_files'][source]:issues.append('Missing complete source before write: '+source)
            seen=after.get(str((work/dest).resolve()))
            if seen is None or seen['text'].encode('utf8')!=expected[dest]:issues.append('Missing exact complete post-write readback: '+dest)
    if row['id']=='v4-file-06':
        if source_opens:issues.append('Forbidden source open while destination already exists')
        for item in history:
            if item['tool']=='READ_TEXT_FILE' and path_of(item)=='原稿.txt' and not (item.get('evidence') or {}).get('condition_skipped'):
                issues.append('Forbidden source read attempted')
        observed=False
        for _,item in successful:
            e=item.get('evidence') or {};output=item.get('output')
            if item['tool']=='READ_TEXT_FILE' and path_of(item)=='既有副本.txt':observed=True
            if item['tool']=='LIST_DIRECTORY' and isinstance(output,list):
                observed |= any(isinstance(x,dict) and relative(work,x['path'])=='既有副本.txt' for x in output)
            if item['tool']=='PATH_INFO' and path_of(item)=='既有副本.txt' and isinstance(output,dict) and output.get('exists') is True:observed=True
            if item['tool']=='COPY_FILE_VERIFIED' and path_of(item,'destination')=='既有副本.txt':
                if e.get('skipped_existing') is True and e.get('source_read') is False:observed=True
                else:issues.append('Existing destination did not skip without reading source')
        if not observed:issues.append('Existing destination was not actually observed')
    if message!=row['expected_response']:issues.append('Original requested final reply not delivered')
    return {'passed':status=='completed' and not issues,'oracle_satisfied':not issues,'false_completion':status=='completed' and bool(issues),
        'issues':issues,'original_tool_specific_oracle':old,'file_sha256':{n:hashlib.sha256(v).hexdigest() for n,v in actual.items()}}
