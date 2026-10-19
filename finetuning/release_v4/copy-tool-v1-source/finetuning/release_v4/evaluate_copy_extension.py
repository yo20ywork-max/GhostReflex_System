"""New copy-tool protocol, isolated actual planner/handlers; original v4 scores unchanged."""
import argparse
import ast
import hashlib
import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from file_flow import Fixture,ROOT,R,relative
from evaluate_development import request
from verified_copy import register


def extend(fixture):
    scope=fixture.scope
    tree=ast.parse((ROOT/'run_daemon.py').read_text(encoding='utf-8-sig'))
    names={'ToolSpec','tool','object_schema','build_plan_schema','build_tool_catalog'}
    nodes=[n for n in tree.body if getattr(n,'name',None) in names]
    module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*nodes],type_ignores=[])
    exec(compile(ast.fix_missing_locations(module),'<actual extended catalog>','exec'),scope)
    for item in fixture.catalog:
        spec=scope['TOOL_REGISTRY'][item['name']]
        spec.name=item['name'];spec.description=item['description']
    register(SimpleNamespace(**scope))
    fixture.catalog=scope['build_tool_catalog']();fixture.schema=scope['build_plan_schema'](fixture.settings)
    prior=fixture.agent._execute_step
    actual=scope['UniversalAgent']._execute_step.__get__(fixture.agent)
    def execute(ctx,step):
        if step.tool!='COPY_FILE_VERIFIED':return prior(ctx,step)
        if len(fixture.trace)>=32 or time.monotonic()-fixture.started>300:
            return scope['ToolResult'](False,error='Bounded copy fixture exhausted',terminal=True)
        try:
            args=scope['resolve_references'](step.args,ctx.step_results,ctx.history)
            pair=(relative(fixture.work,args['source']),relative(fixture.work,args['destination']))
            if pair not in fixture.row['copy_pairs']:raise ValueError('Copy pair outside isolated request scope')
            result=actual(ctx,step)
        except (ValueError,KeyError,TypeError) as exc:result=scope['ToolResult'](False,error=str(exc))
        fixture.trace.append({'id':step.id,'tool':step.tool,'proposed_args':step.args,'ok':result.ok,'error':result.error})
        return result
    fixture.agent._execute_step=execute


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    if Path(args.output).name!=args.output:raise ValueError('Output must be a file name')
    target=R/args.output
    if target.exists():raise FileExistsError(target)
    literal='\ufeff  台灣收音\t\r\n'+('備註𠮷😀  \r\n'*117)+'字面{{step:99.output}}\x00  '
    rows=[{'id':'copy-extension-01','user_request':'把「收音原稿.txt」和「空白原稿.txt」各自原樣備份到現有的「備份」資料夾。不改來源、不覆寫任何既有檔案，保留全部位元組，空檔也要有副本。核對兩份副本後回覆「備份已核對」。',
           'initial_files':{'收音原稿.txt':literal,'空白原稿.txt':'','備份/保留.txt':'既有資料'},
           'copy_pairs':[('收音原稿.txt','備份/收音原稿.txt'),('空白原稿.txt','備份/空白原稿.txt')],
           'expected_files':{'收音原稿.txt':literal,'空白原稿.txt':'','備份/保留.txt':'既有資料','備份/收音原稿.txt':literal,'備份/空白原稿.txt':''},
           'expected_response':'備份已核對','write_targets':{}},
          {'id':'copy-extension-02','user_request':'只有「既有副本.txt」不存在時，才把「來源.txt」原樣備份成該副本；如果副本已存在，不要讀來源、不要改任何檔案，回覆「保留既有版本」。',
           'initial_files':{'既有副本.txt':'其他人保留的版本'},'copy_pairs':[('來源.txt','既有副本.txt')],
           'expected_files':{'既有副本.txt':'其他人保留的版本'},'expected_response':'保留既有版本','write_targets':{}}]
    paths=[Path(__file__),R/'file_flow.py',ROOT/'verified_copy.py',ROOT/'run_daemon.py',ROOT/'text_reader.py',ROOT/'task_journal.py',ROOT/'desktop_ui/app.py']
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    model=next(m for m in request('/api/tags')['models'] if m['name']==args.model)
    with target.with_suffix('.manifest.json').open('x',encoding='utf8') as f:
        json.dump({'model':model,'sources':hashes,'cases':rows,'release_approved':False,'scope':'New COPY_FILE_VERIFIED catalog protocol; authored two-case development, not original eight-case score or native UI.'},f,ensure_ascii=False,indent=2)
    results=[]
    with target.open('x',encoding='utf8') as output:
        for row in rows:
            calls=[];began=time.monotonic()
            class Gateway:
                def chat_json(self,*,messages,schema,models=None):
                    if len(calls)>=12 or time.monotonic()-began>240:raise RuntimeError('Inference budget exhausted')
                    body={'model':args.model,'messages':messages,'format':schema,'options':{'temperature':0,'num_ctx':12288,'num_predict':2048,'repeat_penalty':1.0},'stream':False,'truncate':False,'shift':False}
                    record={'request':body};calls.append(record);response=request('/api/chat',body);record['response']=response
                    if response.get('done_reason')!='stop':raise ValueError('Incomplete generation')
                    return json.loads(response['message']['content']),args.model
            with tempfile.TemporaryDirectory(prefix='copy-model-dev-',dir=R) as folder:
                assert Path(folder).resolve().is_relative_to(R.resolve())
                fixture=Fixture(row,folder,args.model,Gateway());record={'id':row['id'],'model_digest':model['digest']}
                try:
                    extend(fixture);result,receipts,seed=fixture.run(args.model,fixture.agent.gateway)
                    actual={p.relative_to(fixture.work).as_posix():p.read_bytes() for p in fixture.work.rglob('*') if p.is_file()}
                    expected={name:text.encode('utf8') for name,text in row['expected_files'].items()}
                    evidence_ok=actual==expected
                    if row['id']=='copy-extension-02':
                        evidence_ok=evidence_ok and not any(h['tool']=='READ_TEXT_FILE' and Path(h['args']['path']).name=='來源.txt' for h in result.history)
                    response_ok=result.message==row['expected_response']
                    record.update(passed=evidence_ok and response_ok and result.status=='completed',evidence_ok=evidence_ok,response_ok=response_ok,status=result.status,
                                  message=result.message,false_completion=result.status=='completed' and not(evidence_ok and response_ok),history=result.history,receipts=receipts,
                                  file_sha256={name:hashlib.sha256(data).hexdigest() for name,data in actual.items()})
                except Exception as exc:record.update(passed=False,error=repr(exc),status='evaluation_error',false_completion=False)
                finally:fixture.close()
                record.update(calls=calls,trace=fixture.trace,seconds=time.monotonic()-began)
            output.write(json.dumps(record,ensure_ascii=False)+'\n');output.flush();results.append(record)
            print(json.dumps({k:record.get(k) for k in ['id','passed','status','false_completion','error','seconds']}),flush=True)
    after=next(m for m in request('/api/tags')['models'] if m['name']==args.model)
    summary={'cases':len(results),'passed':sum(r['passed'] for r in results),'false_completions':sum(r['false_completion'] for r in results),'evaluation_errors':sum(r['status']=='evaluation_error' for r in results),
             'model_digest_unchanged':model['digest']==after['digest'],'sources_unchanged':all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==digest for p,digest in hashes.items()),'output_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'release_approved':False}
    target.with_suffix('.summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8');print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
