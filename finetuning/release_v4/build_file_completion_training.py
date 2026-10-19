"""Balanced completion labels from pre-existing actual teacher episodes.

Uses only training-side teacher histories, never new development model answers.
Negative prefixes are earlier recorded states of the same execution, not claims
that the final on-disk artifact remained absent after the whole episode finished.
"""
import hashlib
import json
from types import SimpleNamespace
from file_flow import runtime,R,V3


def main():
    source=V3/'file-curriculum-v1/teacher-episodes.json'
    episodes=json.loads(source.read_text(encoding='utf8'))
    scope,_,_=runtime();rows=[]
    for episode in episodes:
        assert episode['teacher_artifact_verified']
        assert episode['source_sha256']==episode['destination_sha256']
        for complete in (False,True):
            # Alternate missing write and missing readback negatives. Pair each
            # with the complete actual episode; no repeated positive oversampling.
            prefix=len(episode['history']) if complete else 2+episode['episode']%2
            history=episode['history'][:prefix]
            reason='原稿已讀齊，副本原樣寫入並讀回一致，最後回覆了指定文字。' if complete else ('目前只有原稿讀取，尚未保存或讀回副本。' if prefix==2 else '副本已寫入，但還沒有寫入後的讀回核對與指定回覆。')
            answer={'reason':reason,'complete':complete}
            class Capture:
                def chat_json(self,*,messages,schema,models=None):
                    self.messages=messages;self.schema=schema
                    return answer,'authored-actual-teacher'
            checker=scope['Planner'].__new__(scope['Planner']);checker.settings=SimpleNamespace(planner_num_ctx=12288);checker.gateway=Capture()
            result,_=checker.assess_completion(episode['request'],history)
            assert hasattr(checker.gateway,'messages') and result==complete
            rows.append({'id':f'v4-file-completion-{episode["episode"]}-{int(complete)}','group':'file-copy-reference-curriculum','split':'train','category':'completion','system':checker.gateway.messages[0]['content'],'prompt':checker.gateway.messages[1]['content'],'answer':json.dumps(answer,ensure_ascii=False,separators=(',',':')),'retain':False,'oracle':{'type':'completion','complete':complete},'source':'Actual training-side teacher episode / recorded prefix; no development results used.','source_episode':episode['episode'],'observed_prefix_steps':prefix})
    assert len(rows)==24 and sum(row['oracle']['complete'] for row in rows)==12
    target=R/'completion-file-training.jsonl'
    with target.open('x',encoding='utf8') as f:
        for row in rows:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    original=[json.loads(x) for x in (R/'train-draft.jsonl').read_text(encoding='utf8').splitlines()]
    with (R/'train-draft-v2.jsonl').open('x',encoding='utf8') as f:
        for row in original+rows:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    manifest={'rows_added':24,'positive':12,'negative':12,'total_training_rows':len(original)+len(rows),'teacher_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'new_rows_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'new_development_data_used':False,'model_answers_used':False,'training_started':False,'release_approved':False}
    with (R/'FILE_COMPLETION_TRAINING.json').open('x',encoding='utf8') as f:json.dump(manifest,f,ensure_ascii=False,indent=2)
    print(json.dumps(manifest))


if __name__=='__main__':main()
