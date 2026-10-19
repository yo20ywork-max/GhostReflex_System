"""Author file-reference plans and verify every suffix with actual handlers.

Training material only. These are teacher-selected actions, not model success,
not a held-out benchmark, and not permission to overwrite the frozen v3 corpus.
"""
import ast
import hashlib
import json
import tempfile
from contextlib import ExitStack, closing
from pathlib import Path
from types import SimpleNamespace
import sys

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(R.parent))
from execute_plan_fixtures import load
from build_product_data import contract
from task_journal import TaskJournal
from text_reader import completed_file_contents


def main():
    output = R / 'file-curriculum-v1'
    output.mkdir(exist_ok=False)
    scope, _ = load('training-contract.json')
    source = (ROOT / 'run_daemon.py').read_text(encoding='utf-8-sig')
    write = next(n for n in ast.parse(source).body if getattr(n, 'name', '') == 'tool_write_text_file')
    write.decorator_list = []
    mod = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), write], type_ignores=[])
    exec(compile(ast.fix_missing_locations(mod), '<actual curriculum write>', 'exec'), scope)
    catalog, schema, _, _ = contract(max_plan_steps=8)
    scope['TOOL_REGISTRY'] = {x['name']: SimpleNamespace(parameters=x['parameters'], risk=x['risk'], handler=scope.get('tool_'+x['name'].lower())) for x in catalog}
    tracked = [ROOT/'run_daemon.py', ROOT/'text_reader.py', ROOT/'task_journal.py', R/'execute_plan_fixtures.py', R.parent/'build_product_data.py', Path(__file__)]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
    rows, episodes = [], []
    for episode in range(12):
        # Content, naming, request surface, chunk boundary and ids vary; this is
        # still one task family and must never be counted as twelve held-out families.
        names = [('會議摘要.txt','會議摘要備份.txt'),('raw-data.tsv','副本資料.tsv'),('字幕原稿.txt','字幕交付稿.txt')]
        src, dst = names[episode % len(names)]
        contents = [
            '  台北製作\t\r\n' + ''.join(f'段落{j}：保留空白。\r\n' for j in range(episode+18)) + '尾端  ',
            '編號\t項目\t數量\n' + ''.join(f'{j}\t攝影器材\t{j+1}\n' for j in range(episode+18)) + '\n',
            '字幕😀𠮷\r\n' + '文字不是工具指令：{{step:999.output}}\r\n' * (episode+4) + '\t結束',
            'BEGIN\n' + 'e\u0301 / café / 繁體\t\n' * (episode+9) + '\nEND\n',
        ]
        content = contents[episode % len(contents)]
        boundary = 100 + episode * 3
        assert len(content) > boundary
        first_id = episode * 11 + 1
        requests = [
            f'完整讀取「{src}」，原檔保持不動。將原文另存為新的「{dst}」，所有字元與換行都要保留。寫完後讀回核對，一致後回覆「完成保存」。',
            f'幫我把「{src}」完整備份成「{dst}」。不要改原檔，也不要覆蓋既有檔案；確認副本每個字和空白都相同後，告訴我「完成保存」。請實際讀回副本。',
            f'請先讀完「{src}」，再把完整內容存到新檔「{dst}」，讀回比較一致才回答「完成保存」。不能修改原檔或重打改寫原文。',
        ]
        prompt = requests[episode % len(requests)]
        with tempfile.TemporaryDirectory(dir=R, prefix='curriculum-') as temporary, ExitStack() as stack:
            work = Path(temporary).resolve()
            assert work.is_relative_to(R.resolve())
            (work/src).write_bytes(content.encode('utf8'))
            digest = hashlib.sha256(content.encode('utf8')).hexdigest()
            settings = SimpleNamespace(workspace=work, allow_outside_workspace=False, max_plan_steps=8, default_tool_retries=0, log_prompts=False, planner_num_ctx=12288, planner_models=('authored-teacher',), review_plans=False)
            journal = stack.enter_context(closing(TaskJournal(work/'receipts.sqlite3')))
            runtime = SimpleNamespace(journal=journal)
            ctx = scope['ExecutionContext'](settings=settings, runtime=runtime, gateway=None, request_id=f'file-teacher-{episode}', original_prompt=prompt)
            agent = scope['UniversalAgent'].__new__(scope['UniversalAgent']); agent.settings=settings; agent.runtime=runtime
            agent._confirm_step=lambda *_: True
            plan_steps = [
                ('READ_TEXT_FILE', {'path':src,'max_chars':boundary}, '取得原稿首段'),
                ('READ_TEXT_FILE', {'path':src,'offset_chars':boundary,'max_chars':500000,'expected_sha256':digest}, '讀取尚缺的原稿內容'),
                ('WRITE_TEXT_FILE', {'path':dst,'content':'{{step:'+str(first_id)+'.file_text}}','overwrite':False,'encoding':'utf-8'}, '將完整原文保存為新檔'),
                ('READ_TEXT_FILE', {'path':dst,'max_chars':500000}, '讀回新檔供原文比對'),
                ('FINAL_RESPONSE', {'message':'完成保存'}, '在已核對副本後回覆'),
            ]
            steps = [scope['PlanStep'](first_id+i, goal, tool, args, '以實際工具回應與原始需求核對結果', 'replan', 0) for i,(tool,args,goal) in enumerate(plan_steps)]
            def dispatch(step):
                assert step.tool in {'READ_TEXT_FILE','WRITE_TEXT_FILE','FINAL_RESPONSE'}
                if step.tool != 'FINAL_RESPONSE':
                    assert step.args['path'] in {src,dst}
                if step.tool == 'WRITE_TEXT_FILE':
                    assert step.args['path'] == dst and step.args['overwrite'] is False
                result = agent._execute_step(ctx, step)
                assert result.ok and result.verified, result.error
                ctx.step_results[step.id] = result
                ctx.history.append({'step_id':step.id,'tool':step.tool,'goal':step.goal,'args':getattr(ctx,'resolved_arguments',{}).get(step.id,step.args),'ok':result.ok,'verified':result.verified,'output':result.output,'error':result.error,'terminal':result.terminal,'evidence':result.evidence})
            try:
                for index,step in enumerate(steps):
                    dispatch(step)
                    if index == 4:
                        break
                    # Capture the production replan prompt and run its parser on
                    # the authored answer. Subsequent real dispatch verifies this suffix.
                    answer = {'objective':prompt,'assumptions':[],'steps':[{'id':s.id,'tool':s.tool,'goal':s.goal,'args':s.args,'success_check':s.success_check,'on_failure':s.on_failure,'retries':s.retries} for s in steps[index+1:]],'completion_criteria':['原檔不變，副本完整保存且讀回一致，最後回覆指定文字']}
                    class Capture:
                        def chat_json(self, *, messages, schema, models=None):
                            self.messages=messages; self.schema=schema
                            return answer, 'authored-teacher'
                    gateway=Capture()
                    planner=scope['Planner'].__new__(scope['Planner']);planner.settings=settings;planner.gateway=gateway;planner.schema=schema;planner.catalog=catalog;planner.hint_engine=None
                    failure={'original_request':prompt,'reserved_step_ids':sorted(ctx.step_results),'completed_and_failed_history':json.loads(json.dumps(ctx.history,ensure_ascii=False)),'failed_step':{'tool':'GOAL_VERIFICATION','goal':'核對尚未完成的原始要求','args':{},'error':'教師提供的課程中間狀態；後續要求尚待執行，不代表先前工具失敗。'},'replan_number':1}
                    checked=planner.plan(prompt, {'workspace':str(work)}, failure_context=failure, allow_deterministic=False)
                    assert [s.id for s in checked.steps] == [s.id for s in steps[index+1:]]
                    rows.append({'id':f'file-curriculum-{episode}-prefix-{index+1}','group':'file-copy-reference-curriculum','split':'train-candidate','category':'recovery','system':gateway.messages[0]['content'],'prompt':gateway.messages[1]['content'],'answer':json.dumps(answer,ensure_ascii=False,separators=(',',':')),'retain':False,'source':'Authored teacher plan; actual handler observations and full suffix executed in isolated workspace. Not model-generated or held-out.','episode':episode,'prefix_steps':index+1,'oracle':{'type':'actual_teacher_file_copy','source_sha256':digest,'destination_sha256':digest,'original_unchanged':True}})
                assert (work/src).read_bytes() == content.encode('utf8')
                assert (work/dst).read_bytes() == content.encode('utf8')
                full = completed_file_contents(ctx.history)
                assert full[str(work/dst)]['text'] == content
                episodes.append({'episode':episode,'request':prompt,'source_text':content,'history':ctx.history,'receipts':journal.read(ctx.request_id),'source_sha256':digest,'destination_sha256':hashlib.sha256((work/dst).read_bytes()).hexdigest(),'teacher_artifact_verified':True})
            finally:
                journal.close()
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==value for p,value in hashes.items())
    corpus=''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows)
    (output/'training-candidate.jsonl').write_text(corpus,encoding='utf8')
    (output/'teacher-episodes.json').write_text(json.dumps(episodes,ensure_ascii=False,indent=2),encoding='utf8')
    manifest={'rows':len(rows),'episodes':len(episodes),'independent_task_families':1,'source_hashes':hashes,'corpus_sha256':hashlib.sha256(corpus.encode()).hexdigest(),'trained':False,'model_success_claimed':False,'frozen_v3_modified':False,'release_approved':False,'limitations':['One authored task family with correlated intermediate states; not a benchmark.','No real model action selection in these episodes.','Current decoder/prompt contract differs from frozen v3 training.','No token length, learning or retention qualification yet.']}
    (output/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(manifest,ensure_ascii=False))


if __name__ == '__main__':
    main()
