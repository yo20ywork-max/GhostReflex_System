"""Exercise actual tool handlers and retry loop in a bounded temporary workspace."""
import ast,json,os,re,time,tempfile,unittest
from dataclasses import dataclass,field
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
def load():
    tree=ast.parse((ROOT/'run_daemon.py').read_text(encoding='utf-8-sig'))
    wanted={'ToolResult','PlanStep','TaskPlan','UniversalAgent','validate_tool_arguments','resolve_references','is_path_inside','resolve_user_path','tool_write_text_file','tool_read_text_file','tool_append_text_file','tool_make_directory'}
    nodes=[n for n in tree.body if getattr(n,'name',None) in wanted or (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='REFERENCE_RE' for t in n.targets))]
    for n in nodes:
        if isinstance(n,ast.FunctionDef):n.decorator_list=[]
    scope={'Path':Path,'os':os,'dataclass':dataclass,'field':field,'json':json,'re':re,'time':SimpleNamespace(sleep=lambda _:None),'REFERENCE_RE':re.compile(r'\{\{step:(\d+)\.output\}\}'),'compact_json':json.dumps,'write_event':Mock()}
    mod=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*nodes],type_ignores=[])
    exec(compile(ast.fix_missing_locations(mod),'<actual executor>','exec'),scope)
    return scope

class Recovery(unittest.TestCase):
    def setUp(self):
        self.s=load();parent=ROOT/'finetuning/release_v2';self.temp=tempfile.TemporaryDirectory(dir=parent,prefix='execution-check-')
        self.workspace=Path(self.temp.name).resolve();self.assertTrue(self.workspace.is_relative_to(parent.resolve()))
        self.ctx=SimpleNamespace(settings=SimpleNamespace(workspace=self.workspace,allow_outside_workspace=False),request_id='isolated-check',step_results={})
    def tearDown(self):self.temp.cleanup()
    def agent(self,tool,handler,props):
        self.s['TOOL_REGISTRY']={tool:SimpleNamespace(handler=handler,parameters={'type':'object','properties':props,'additionalProperties':False})}
        agent=self.s['UniversalAgent'].__new__(self.s['UniversalAgent']);agent.settings=self.ctx.settings;agent._confirm_step=lambda *_:True
        return agent
    def test_real_unicode_file_write_read_and_no_overwrite(self):
        write=self.s['tool_write_text_file'];read=self.s['tool_read_text_file']
        path='活動原稿/字幕（繁體）.txt';content='臺灣\n不是\\n跳脫字串'
        self.assertTrue(write(self.ctx,path,content).ok)
        self.assertFalse(write(self.ctx,path,'取代舊內容').ok)
        result=read(self.ctx,path);self.assertTrue(result.verified);self.assertEqual(result.output,content)
        self.assertFalse(write(self.ctx,'../outside-test.txt','不應寫出').ok)

    def test_journal_failure_before_dispatch_prevents_the_write(self):
        journal=Mock();journal.begin.side_effect=OSError('disk full');self.ctx.runtime=SimpleNamespace(journal=journal)
        handler=Mock();agent=self.agent('APPEND_TEXT_FILE',handler,{'path':{'type':'string'},'content':{'type':'string'}})
        step=self.s['PlanStep'](1,'追加','APPEND_TEXT_FILE',{'path':'audit.txt','content':'一次'},'工具結果','retry',3)
        result=agent._execute_step(self.ctx,step)
        self.assertFalse(result.ok);self.assertTrue(result.terminal);handler.assert_not_called()

    def test_actual_read_extent_survives_persisted_receipt(self):
        from task_journal import TaskJournal
        path='完整原文.txt';(self.workspace/path).write_text('甲'*151,encoding='utf8')
        journal=TaskJournal(self.workspace/'journal.sqlite3');self.ctx.runtime=SimpleNamespace(journal=journal)
        try:
            agent=self.agent('READ_TEXT_FILE',self.s['tool_read_text_file'],{'path':{'type':'string'},'max_chars':{'type':'integer'}})
            step=self.s['PlanStep'](1,'讀取','READ_TEXT_FILE',{'path':path,'max_chars':100},'讀回','stop',0)
            result=agent._execute_step(self.ctx,step)
            self.assertTrue(result.evidence['truncated']);self.assertEqual(len(result.output),100)
            saved=journal.read(self.ctx.request_id)[0]['result']
            self.assertEqual(saved['evidence'],result.evidence);self.assertEqual(saved['evidence']['chars'],151)
            self.assertEqual(saved['terminal'],result.terminal)
        finally:journal.close()

    def test_journal_failure_after_dispatch_never_retries_the_write(self):
        journal=Mock();journal.finish.side_effect=OSError('disk full');self.ctx.runtime=SimpleNamespace(journal=journal)
        handler=Mock(side_effect=lambda ctx,**args:self.s['tool_append_text_file'](ctx,**args))
        agent=self.agent('APPEND_TEXT_FILE',handler,{'path':{'type':'string'},'content':{'type':'string'}})
        step=self.s['PlanStep'](1,'追加','APPEND_TEXT_FILE',{'path':'audit.txt','content':'一次'},'工具結果','retry',3)
        result=agent._execute_step(self.ctx,step)
        self.assertFalse(result.ok);self.assertTrue(result.terminal);self.assertEqual(handler.call_count,1)
        self.assertEqual((self.workspace/'audit.txt').read_text(encoding='utf8'),'一次')
    def test_lost_append_response_never_duplicates_side_effect(self):
        calls=[]
        def handler(ctx,**args):
            calls.append(args);self.s['tool_append_text_file'](ctx,**args)
            return self.s['ToolResult'](False,error='回應中斷，寫入是否成功未知')
        agent=self.agent('APPEND_TEXT_FILE',handler,{'path':{'type':'string'},'content':{'type':'string'}})
        step=self.s['PlanStep'](1,'追加','APPEND_TEXT_FILE',{'path':'audit.txt','content':'一次'},'工具結果','retry',3)
        result=agent._execute_step(self.ctx,step)
        self.assertFalse(result.ok);self.assertEqual(len(calls),1)
        self.assertEqual((self.workspace/'audit.txt').read_text(encoding='utf8'),'一次')
    def test_file_created_during_write_check_is_not_overwritten(self):
        target=self.workspace/'race.txt';original_exists=Path.exists;inserted=[]
        def exists(path):
            if path==target and not inserted:
                inserted.append(True);target.write_bytes('別人的新檔'.encode('utf8'))
                return False
            return original_exists(path)
        with patch.object(Path,'exists',exists):
            result=self.s['tool_write_text_file'](self.ctx,'race.txt','不應覆寫')
        self.assertFalse(result.ok)
        self.assertEqual(target.read_text(encoding='utf8'),'別人的新檔')
    def test_transient_read_failure_can_retry_then_return_actual_file(self):
        self.s['tool_write_text_file'](self.ctx,'saved.txt','已保存')
        calls=[]
        def handler(ctx,**args):
            calls.append(1)
            return self.s['ToolResult'](False,error='暫時鎖定') if len(calls)==1 else self.s['tool_read_text_file'](ctx,**args)
        agent=self.agent('READ_TEXT_FILE',handler,{'path':{'type':'string'}})
        step=self.s['PlanStep'](5,'讀回','READ_TEXT_FILE',{'path':'saved.txt'},'工具結果','retry',1)
        result=agent._execute_step(self.ctx,step)
        self.assertTrue(result.ok);self.assertEqual(result.output,'已保存');self.assertEqual(len(calls),2)
    def test_resolved_wrong_type_rejected_before_handler(self):
        handler=Mock();agent=self.agent('WRITE_TEXT_FILE',handler,{'overwrite':{'type':'boolean'}})
        self.ctx.step_results[1]=self.s['ToolResult'](True,output='false')
        step=self.s['PlanStep'](2,'寫入','WRITE_TEXT_FILE',{'overwrite':'{{step:1.output}}'},'工具結果','stop',0)
        self.assertFalse(agent._execute_step(self.ctx,step).ok);handler.assert_not_called()

    def test_full_segment_reference_reaches_actual_write_only_after_all_segments(self):
        content='臺灣🎞️  '*47;source=self.workspace/'來源.txt';source.write_bytes(content.encode('utf8'))
        self.ctx.history=[]
        def observe(id_,offset=0,sha=''):
            result=self.s['tool_read_text_file'](self.ctx,'來源.txt',max_chars=100,offset_chars=offset,expected_sha256=sha)
            self.assertTrue(result.ok)
            self.ctx.step_results[id_]=result
            self.ctx.history.append({'step_id':id_,'tool':'READ_TEXT_FILE','args':{'path':'來源.txt'},'ok':result.ok,'verified':result.verified,'output':result.output,'evidence':result.evidence})
            return result.evidence['read_extent']
        first=observe(1);handler=Mock(side_effect=self.s['tool_write_text_file'])
        agent=self.agent('WRITE_TEXT_FILE',handler,{'path':{'type':'string'},'content':{'type':'string'}})
        step=self.s['PlanStep'](20,'保存全文','WRITE_TEXT_FILE',{'path':'結果.txt','content':'{{step:1.file_text}}'},'寫回','stop',0)
        self.assertFalse(agent._execute_step(self.ctx,step).ok);handler.assert_not_called()
        self.assertFalse((self.workspace/'結果.txt').exists())
        start=first['next_offset_chars'];id_=2
        while start is not None:
            item=observe(id_,start,first['sha256']);start=item['next_offset_chars'];id_+=1
        result=agent._execute_step(self.ctx,step)
        self.assertTrue(result.ok,result.error);self.assertEqual(handler.call_count,1)
        self.assertEqual((self.workspace/'結果.txt').read_bytes(),source.read_bytes())

if __name__=='__main__':unittest.main()
