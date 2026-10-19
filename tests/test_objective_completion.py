"""Actual agent state transitions, without desktop hooks or model downloads."""
import ast,json,re,unittest,uuid,threading,time,queue,traceback
from dataclasses import dataclass,field
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

def load():
    tree=ast.parse((Path(__file__).resolve().parents[1]/'run_daemon.py').read_text(encoding='utf-8-sig'))
    wanted={'console_print','ToolResult','PlanStep','TaskPlan','ExecutionContext','AgentRunResult','UniversalAgent','Planner','tool_model_generate','normalize_prompt','AgentRequest','AgentService','tool_wait'}
    nodes=[n for n in tree.body if getattr(n,'name',None) in wanted]
    for n in nodes:
        if isinstance(n,ast.FunctionDef):n.decorator_list=[]
    s={'dataclass':dataclass,'field':field,'json':json,'re':re,'uuid':uuid,'threading':threading,'time':time,'queue':queue,'traceback':traceback,'normalize_prompt':lambda x:x,'request_fingerprint':lambda x:'test','safe_log_value':lambda x:x,'compact_json':lambda x,*_:json.dumps(x),'write_event':Mock()}
    mod=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*nodes],type_ignores=[])
    exec(compile(ast.fix_missing_locations(mod),'<actual objective loop>','exec'),s);return s

class ObjectiveCompletion(unittest.TestCase):
    def setUp(self):self.s=load()
    def agent(self,replans=1):
        s=self.s;agent=s['UniversalAgent'].__new__(s['UniversalAgent']);agent.settings=SimpleNamespace(log_prompts=False,max_replans=replans);agent.runtime=SimpleNamespace();agent.gateway=Mock();agent.runtime_context=lambda:{};agent.print_plan=lambda p:None
        agent.planner=Mock();agent.planner.plan.side_effect=[s['TaskPlan']('讀取',[],[s['PlanStep'](i,'觀察','BROWSER_GET_TEXT',{'target':'#result'},'讀取結果')],['讀到結果'],model='candidate') for i in [1,2]]
        agent._execute_step=Mock(return_value=s['ToolResult'](True,output='觀察',verified=True));return agent
    def test_successful_tool_does_not_skip_goal_verification(self):
        agent=self.agent();agent.planner.assess_completion.side_effect=[(False,'缺少最後讀回'),(True,'已讀回')]
        result=agent.run('等載入完成再讀回')
        self.assertEqual(result.status,'completed');self.assertEqual(agent._execute_step.call_count,2)
        self.assertEqual(agent.planner.plan.call_args.kwargs['failure_context']['failed_step']['tool'],'GOAL_VERIFICATION')
        self.assertEqual(agent.planner.plan.call_args.kwargs['failure_context']['reserved_step_ids'],[1])
        self.assertEqual(result.history[0]['args'],{'target':'#result'})
    def test_unverified_goal_never_reports_completion(self):
        agent=self.agent(0);agent.planner.assess_completion.return_value=(False,'缺少完成證據')
        result=agent.run('完成工作');self.assertNotEqual(result.status,'completed');self.assertIn('缺少完成證據',result.message)
    def test_checker_cannot_promote_unverified_command(self):
        checker=self.s['Planner'].__new__(self.s['Planner']);checker.settings=SimpleNamespace(planner_num_ctx=12288);checker.gateway=Mock();checker.gateway.chat_json.return_value=({'complete':True,'reason':'看來完成'},'candidate')
        complete,_=checker.assess_completion('開啟文件',[{'ok':True,'verified':False,'output':'命令已送出'}]);self.assertFalse(complete)

    def test_checker_cannot_promote_partial_file_even_if_model_would_agree(self):
        checker=self.s['Planner'].__new__(self.s['Planner']);checker.settings=SimpleNamespace(planner_num_ctx=12288);checker.gateway=Mock()
        checker.gateway.chat_json.return_value=({'complete':True,'reason':'完成'},'candidate')
        def item(start,end):return {'tool':'READ_TEXT_FILE','args':{'path':'a.txt'},'ok':True,'verified':True,'output':'甲'*(end-start),'evidence':{'path':'a.txt','read_extent':{'version':1,'kind':'whole_file_segment','sha256':'a'*64,'total_chars':200,'start':start,'end':end}}}
        complete,_=checker.assess_completion('讀取全文',[item(0,100)])
        self.assertFalse(complete);checker.gateway.chat_json.assert_not_called()
        complete,_=checker.assess_completion('讀取全文',[item(0,100),item(100,200)])
        self.assertTrue(complete);checker.gateway.chat_json.assert_called_once()
        payload=json.loads(checker.gateway.chat_json.call_args.kwargs['messages'][-1]['content'])
        self.assertEqual(payload['verified_file_coverage']['a.txt'],{'sha256':'a'*64,'total_chars':200,'whole_file_observed':True})
    def test_generation_limit_never_silently_truncates(self):
        ctx=SimpleNamespace(gateway=Mock());ctx.gateway.chat_text.return_value=('字'*101,'candidate')
        result=self.s['tool_model_generate'](ctx,'原文',max_chars=100)
        self.assertFalse(result.ok);self.assertIn('未截斷',result.error)

    def test_literal_whitespace_survives_request_and_evidence(self):
        literal='  原文\t\t全形　空格\r\n'+('甲'*2000)+'\n'
        self.assertEqual(self.s['normalize_prompt'](literal),literal)
        agent=self.agent(0);agent.planner.assess_completion.return_value=(True,'符合')
        agent._execute_step.return_value=self.s['ToolResult'](True,output={'text':literal},verified=True)
        result=agent.run(literal)
        self.assertEqual(result.history[0]['output'],{'text':literal})
        self.assertEqual(agent.planner.assess_completion.call_args.args[0],literal)

    def test_replan_retains_early_steps_of_long_history(self):
        agent=self.agent();items=[{'step_id':i,'tool':'READ_TEXT_FILE','goal':'讀回','args':{},'ok':True,'verified':True,'output':str(i),'error':None} for i in range(1,31)]
        self.assertEqual(agent._history_for_replan(SimpleNamespace(history=items)),items)

    def test_tool_extent_and_uncertainty_survive_completion_and_replanning(self):
        agent=self.agent(0);agent.planner.assess_completion.return_value=(False,'只收到前段內容')
        metadata={'truncated':True,'chars':98765,'path':'原文.txt','source':{'encoding':'utf-8'}}
        agent._execute_step.return_value=self.s['ToolResult'](True,output='前段',verified=True,evidence=metadata)
        result=agent.run('讀取完整原文')
        self.assertEqual(result.history[0]['evidence'],metadata)
        self.assertEqual(agent.planner.assess_completion.call_args.args[1][0]['evidence'],metadata)
        copied=agent._history_for_replan(SimpleNamespace(history=result.history))
        copied[0]['evidence']['source']['encoding']='modified'
        self.assertEqual(result.history[0]['evidence']['source']['encoding'],'utf-8')

    def test_replan_does_not_replay_successful_click(self):
        agent=self.s['UniversalAgent'].__new__(self.s['UniversalAgent'])
        handler=Mock();self.s['TOOL_REGISTRY']={'BROWSER_CLICK':SimpleNamespace(handler=handler,parameters={})}
        self.s['resolve_references']=lambda a,r,h=None:a;self.s['validate_tool_arguments']=lambda *a:None
        step=self.s['PlanStep'](4,'預覽','BROWSER_CLICK',{'by':'text','target':'預覽'},'點選')
        ctx=SimpleNamespace(replan_number=1,step_results={},history=[{'tool':'BROWSER_CLICK','args':dict(step.args),'ok':True}])
        result=agent._execute_step(ctx,step)
        self.assertFalse(result.ok);self.assertTrue(result.terminal);handler.assert_not_called()

    def test_cancellation_during_planning_prevents_first_action(self):
        agent=self.agent();event=threading.Event();plan=agent.planner.plan.side_effect[0] if isinstance(agent.planner.plan.side_effect,list) else self.s['TaskPlan']('工作',[],[self.s['PlanStep'](1,'讀取','READ_TEXT_FILE',{'path':'a'},'讀回')],[])
        def planning(*a,**kw):event.set();return plan
        agent.planner.plan.side_effect=planning
        result=agent.run('工作',cancel_event=event)
        self.assertEqual(result.status,'cancelled');agent._execute_step.assert_not_called()

    def test_cancellation_after_first_action_prevents_second(self):
        agent=self.agent();event=threading.Event();s=self.s
        agent.planner.plan.side_effect=None;agent.planner.plan.return_value=s['TaskPlan']('工作',[],[s['PlanStep'](i,'步驟','READ_TEXT_FILE',{'path':str(i)},'讀回') for i in [1,2]],[])
        def first(*a):event.set();return s['ToolResult'](True,output='已讀取',verified=True)
        agent._execute_step.side_effect=first
        result=agent.run('工作',cancel_event=event)
        self.assertEqual(result.status,'cancelled');self.assertEqual(agent._execute_step.call_count,1);agent.planner.assess_completion.assert_not_called()

    def test_wait_interrupts_without_waiting_full_timeout(self):
        event=threading.Event();event.set();began=time.monotonic()
        result=self.s['tool_wait'](SimpleNamespace(cancel_event=event),120)
        self.assertFalse(result.ok);self.assertTrue(result.terminal);self.assertLess(time.monotonic()-began,0.5)

    def test_service_cancels_current_and_queued_requests(self):
        s=self.s;started=threading.Event();release=threading.Event();done=threading.Event();seen=[];answers=[]
        runtime=SimpleNamespace(browser=SimpleNamespace(close=Mock()))
        s['AgentRuntime']=lambda _:runtime;s['OllamaGateway']=lambda _:None;s['MicroGLRHintEngine']=lambda _:None;s['Planner']=lambda *a:None
        class Worker:
            def run(self,prompt,cancel_event=None,request_id=None):
                seen.append(prompt);started.set();release.wait(2)
                return s['AgentRunResult']('test','cancelled' if cancel_event.is_set() else 'completed','結果','none',[])
        s['UniversalAgent']=lambda *a:Worker()
        service=s['AgentService'](SimpleNamespace(copy_result_to_clipboard=False))
        try:
            service.submit('第一個',lambda r:(answers.append(r),done.set()))
            self.assertTrue(started.wait(1));service.submit('第二個',answers.append)
            service.cancel_all();release.set();self.assertTrue(done.wait(1))
            self.assertEqual(seen,['第一個']);self.assertEqual(len(answers),2);self.assertTrue(all(r.status=='cancelled' for r in answers))
        finally:release.set();service.stop();service.thread.join(2)
        self.assertFalse(service.thread.is_alive());runtime.browser.close.assert_called_once()

    def test_bootstrap_failure_returns_result_instead_of_leaving_queue_stuck(self):
        s=self.s;done=threading.Event();answers=[]
        def broken(_):raise RuntimeError('初始化失敗')
        s['AgentRuntime']=broken;service=s['AgentService'](SimpleNamespace(copy_result_to_clipboard=False))
        service.submit('讀取',lambda r:(answers.append(r),done.set()))
        self.assertTrue(done.wait(1));service.thread.join(1)
        self.assertTrue(service.ready_event.is_set());self.assertEqual(service.startup_error,'初始化失敗')
        self.assertEqual(answers[0].status,'failed');self.assertIn('初始化失敗',answers[0].message);self.assertFalse(service.thread.is_alive())
        with self.assertRaises(RuntimeError):service.submit('下一個')

if __name__=='__main__':unittest.main()
