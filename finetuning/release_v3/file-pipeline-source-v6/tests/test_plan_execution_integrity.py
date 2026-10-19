"""Run actual parser and planner methods without importing desktop hooks."""
import ast,json,re,unittest,tempfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

def load():
    tree=ast.parse((Path(__file__).resolve().parents[1]/'run_daemon.py').read_text(encoding='utf-8-sig'))
    names={'PlanStep','TaskPlan','validate_plan','validate_tool_arguments','resolve_references','fallback_blocked_plan','Planner'}
    body=[n for n in tree.body if getattr(n,'name',None) in names or (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='REFERENCE_RE' for t in n.targets))]
    scope={'dataclass':dataclass,'json':json,'re':re,'REFERENCE_RE':re.compile(r'\{\{step:(\d+)\.output\}\}'),'compact_json':json.dumps,'TOOL_REGISTRY':{'READ_TEXT_FILE':SimpleNamespace(parameters={'properties':{'path':{}},'required':['path']})}}
    mod=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*body],type_ignores=[])
    exec(compile(ast.fix_missing_locations(mod),'<actual planner>','exec'),scope)
    return scope

class Integrity(unittest.TestCase):
    def setUp(self):
        self.s=load();self.settings=SimpleNamespace(max_plan_steps=2,default_tool_retries=0,planner_models=['test'])
    def value(self,ids):
        return {'objective':'讀取','assumptions':[],'steps':[{'id':i,'tool':'READ_TEXT_FILE','args':{'path':'原稿.txt'},'goal':'讀取','success_check':'讀取成功'} for i in ids],'completion_criteria':['取得內容']}
    def test_tail_is_never_silently_discarded(self):
        with self.assertRaisesRegex(ValueError,'不可截斷'):self.s['validate_plan'](self.value([1,2,3]),self.settings,'test')
    def test_ids_are_preserved_and_old_reference_stays_valid(self):
        p=self.s['validate_plan'](self.value([7,8]),self.settings,'test',{1,2,3})
        self.assertEqual([x.id for x in p.steps],[7,8])
        outputs={1:SimpleNamespace(output='舊內容'),7:SimpleNamespace(output='新內容')}
        self.assertEqual(self.s['resolve_references']('{{step:1.output}}',outputs),'舊內容')
    def test_duplicate_history_and_boolean_ids_rejected(self):
        for ids,reserved in [([2,2],set()),([1],{1}),([True],set())]:
            with self.assertRaises(ValueError):self.s['validate_plan'](self.value(ids),self.settings,'test',reserved)
    def test_unknown_arguments_are_not_silently_removed(self):
        raw=self.value([1]);raw['steps'][0]['args']['overwrite']=True
        with self.assertRaisesRegex(ValueError,'未知參數'):self.s['validate_plan'](raw,self.settings,'test')
    def test_future_and_self_references_rejected_before_execution(self):
        for target in (1,9):
            raw=self.value([1,2]);raw['steps'][0]['args']['path']='{{step:'+str(target)+'.output}}'
            with self.assertRaisesRegex(ValueError,'尚未取得'):self.s['validate_plan'](raw,self.settings,'test')
        raw=self.value([4]);raw['steps'][0]['args']['path']='{{step:2.output}}'
        self.assertEqual(self.s['validate_plan'](raw,self.settings,'test',{2}).steps[0].id,4)
    def test_failed_output_cannot_feed_a_later_action(self):
        for value in ('{{step:1.output}}','prefix {{step:1.output}}'):
            with self.assertRaisesRegex(ValueError,'執行失敗'):
                self.s['resolve_references'](value,{1:SimpleNamespace(ok=False,output='unreliable')})

    def test_partial_read_cannot_be_passed_as_a_complete_document(self):
        result=SimpleNamespace(ok=True,output='前段',evidence={'read_extent':{'start':0,'end':2,'total_chars':200}})
        for value in ('{{step:1.output}}','prefix {{step:1.output}}'):
            with self.assertRaisesRegex(ValueError,'片段'):self.s['resolve_references'](value,{1:result})

    def test_full_file_reference_preserves_actual_text_and_rejects_missing_or_changed_version(self):
        from text_reader import read_text_segment
        root=Path(__file__).resolve().parents[1]/'finetuning/release_v3'
        with tempfile.TemporaryDirectory(dir=root,prefix='file-ref-test-') as folder:
            path=Path(folder)/'原稿.txt';text=' 臺灣🎞️\r\n'*31;path.write_bytes(text.encode('utf8'))
            history=[];results={}
            def observe(id_,start=0,sha=''):
                output,evidence=read_text_segment(path,100,start,sha)
                row={'step_id':id_,'tool':'READ_TEXT_FILE','args':{'path':str(path)},'ok':True,'verified':True,'output':output,'evidence':evidence}
                history.append(row);results[id_]=SimpleNamespace(ok=True,verified=True,output=output,evidence=evidence)
                return evidence['read_extent']
            first=observe(1)
            with self.assertRaisesRegex(ValueError,'尚未取得'):self.s['resolve_references']('{{step:1.file_text}}',results,history)
            start=first['next_offset_chars'];id_=2
            while start is not None:
                extent=observe(id_,start,first['sha256']);start=extent['next_offset_chars'];id_+=1
            value={'body':['{{step:1.file_text}}','prefix {{step:1.file_text}} suffix']}
            self.assertEqual(self.s['resolve_references'](value,results,history),{'body':[text,'prefix '+text+' suffix']})
            # Ordinary output remains exactly the original fragment, not implicitly upgraded.
            with self.assertRaisesRegex(ValueError,r'已核對齊全.*\{\{step:1.file_text\}\}'):
                self.s['resolve_references']('{{step:1.output}}',results,history)
            with self.assertRaisesRegex(ValueError,'唯一'):self.s['resolve_references']('{{step:1.file_text}}',results,[])
            path.write_text('新版本',encoding='utf8');observe(id_)
            with self.assertRaisesRegex(ValueError,'版本'):self.s['resolve_references']('{{step:1.file_text}}',results,history)

    def test_full_file_reference_cannot_point_forward(self):
        raw=self.value([1]);raw['steps'][0]['args']['path']='{{step:2.file_text}}'
        with self.assertRaisesRegex(ValueError,'尚未取得'):self.s['validate_plan'](raw,self.settings,'test')
    def test_invalid_plan_receives_bounded_repair(self):
        planner=self.s['Planner'].__new__(self.s['Planner']);planner.settings=self.settings;planner.schema={}
        planner.gateway=Mock();planner.gateway.chat_json.side_effect=[(self.value([1]),'test'),(self.value([4]),'test')]
        p=planner._request_valid_plan([{'role':'user','content':'讀取'}],reserved_ids={1,2,3})
        self.assertEqual(p.steps[0].id,4);self.assertEqual(planner.gateway.chat_json.call_count,2)
        self.assertIn('歷史已使用',planner.gateway.chat_json.call_args.kwargs['messages'][-1]['content'])
    def test_false_string_cannot_enable_overwrite(self):
        validate=self.s['validate_tool_arguments'];schema={'type':'boolean'}
        validate(False,schema)
        with self.assertRaises(ValueError):validate('false',schema)
        validate('{{step:1.output}}',schema,True)
        with self.assertRaises(ValueError):validate('{{step:1.output}}',schema)

    def test_replan_decoder_reserves_history_ids_without_changing_shared_schema(self):
        planner=self.s['Planner'].__new__(self.s['Planner']);planner.settings=self.settings
        branch={'properties':{'id':{'type':'integer','minimum':1}}}
        for items in (branch,{'oneOf':[branch,branch]}):
            planner.schema={'properties':{'steps':{'items':items}}}
            original=json.dumps(planner.schema)
            planner.gateway=Mock();planner.gateway.chat_json.return_value=(self.value([20]),'test')
            result=planner._request_valid_plan([{'role':'user','content':'繼續'}],reserved_ids={1,2,19})
            sent=planner.gateway.chat_json.call_args.kwargs['schema']['properties']['steps']['items']
            self.assertTrue(all(x['properties']['id']['minimum']==20 for x in sent.get('oneOf',[sent])))
            self.assertEqual(result.steps[0].id,20)
            self.assertEqual(json.dumps(planner.schema),original)
    def test_numeric_bounds_and_array_items(self):
        validate=self.s['validate_tool_arguments']
        for value in [True,-1,float('nan'),float('inf')]:
            with self.assertRaises(ValueError):validate(value,{'type':'number','minimum':0})
        with self.assertRaises(ValueError):validate(['ctrl',12],{'type':'array','items':{'type':'string'}})
    def test_replanning_does_not_restart_deterministic_action(self):
        planner=self.s['Planner'].__new__(self.s['Planner']);planner.settings=self.settings;planner.hint_engine=None
        self.settings.review_plans=False
        self.s['deterministic_plan']=Mock(side_effect=AssertionError('must not restart'))
        planner._system_prompt=lambda:'s';planner._request_valid_plan=Mock(side_effect=RuntimeError('failed'))
        result=planner.plan('讀取',{},failure_context={'completed_and_failed_history':[{'step_id':2}],'reserved_step_ids':[1,2,19]})
        self.assertEqual(result.steps[0].tool,'BLOCKED');self.assertEqual(result.steps[0].id,20)

if __name__=='__main__':unittest.main()
