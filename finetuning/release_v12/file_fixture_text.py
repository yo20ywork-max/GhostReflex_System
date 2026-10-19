"""User-authorized local MODEL_GENERATE extension; original file8 oracle stays.

This exposes the real product handler, not an oracle answer or a remote API.
"""
import ast
from dataclasses import replace
import time
from file_fixture import R,ROOT,Fixture as FileFixture,cases,evaluate


class Fixture(FileFixture):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        try:
            node=next(n for n in ast.parse((ROOT/'run_daemon.py').read_text(encoding='utf-8-sig')).body if getattr(n,'name','')=='tool_model_generate')
            node.decorator_list=[]
            module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),node],type_ignores=[])
            exec(compile(ast.fix_missing_locations(module),'<actual local MODEL_GENERATE>','exec'),self.scope)
            registry=self.scope['TOOL_REGISTRY']
            registry['MODEL_GENERATE']=replace(registry['MODEL_GENERATE'],handler=self.scope['tool_model_generate'])
            previous=self.agent._execute_step;actual=self.scope['UniversalAgent']._execute_step.__get__(self.agent)
            def bounded(ctx,step):
                if step.tool!='MODEL_GENERATE':return previous(ctx,step)
                dispatched=False
                if len(self.trace)>=32 or time.monotonic()-self.started>300:
                    result=self.scope['ToolResult'](False,error='Fixture action/time budget exhausted',terminal=True)
                else:dispatched=True;result=actual(ctx,step)
                self.trace.append({'id':step.id,'tool':step.tool,'proposed_args':step.args,'dispatched':dispatched,
                    'ok':result.ok,'error':result.error,'condition_skipped':bool((result.evidence or {}).get('condition_skipped'))})
                return result
            self.agent._execute_step=bounded
        except Exception:self.close();raise
