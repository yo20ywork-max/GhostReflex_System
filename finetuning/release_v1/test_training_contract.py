import json
from pathlib import Path
import unittest
from train import tokenize_row
from code_sandbox import validate_code,run
from score import score,validate_result_identity
import hashlib

class FakeTokenizer:
    def apply_chat_template(self,messages,tokenize,add_generation_prompt):
        # Deterministic fake boundary checks, without external downloads.
        prefix=[1,2,3]
        return prefix if add_generation_prompt else prefix+[4,5,6]

class Contracts(unittest.TestCase):
    def test_prompt_is_masked(self):
        s=tokenize_row(FakeTokenizer(),{'id':'x','system':'s','prompt':'p','answer':'a'},10)
        self.assertEqual(s['labels'],[-100,-100,-100,4,5,6])
    def test_overlength_rejected(self):
        with self.assertRaises(ValueError):tokenize_row(FakeTokenizer(),{'id':'x','system':'s','prompt':'p','answer':'a'},4)
    def test_sandbox_blocks_side_effects(self):
        for code in ['import os\ndef f(x): return x','def f(x): return open("secret")','def f(x): return x.__class__','def f(x): return eval(x)']:
            with self.assertRaises(ValueError):validate_code(code,'f')
    def test_sandbox_checks_actual_behavior(self):
        oracle={'function':'f','tests':[{'args':[[1,2]],'expected':3},{'args':[[]],'expected':0}]}
        self.assertTrue(run({**oracle,'code':'def f(x):\n    return sum(x)'})['passed'])
        self.assertFalse(run({**oracle,'code':'def f(x):\n    return 3'})['passed'])
    def test_no_split_leak(self):
        seen={};prompts=set();sources={}
        for split in ['train','dev','test']:
            for line in (Path(__file__).parent/(split+'.jsonl')).read_text(encoding='utf8').splitlines():
                r=json.loads(line)
                self.assertEqual(seen.setdefault(r['group'],split),split)
                self.assertNotIn((r['system'],r['prompt']),prompts);prompts.add((r['system'],r['prompt']))
                if r['source']:self.assertEqual(sources.setdefault(r['source'],split),split)
    def test_numeric_dictionary_keys_survive_json(self):
        p={'code':'def f(xs):\n    return {x:xs.count(x) for x in xs}','function':'f','tests':[{'args':[[1,1,2]],'expected':{'1':2,'2':1}}]}
        self.assertTrue(run(p)['passed'])
    def test_safe_standard_library_solution(self):
        p={'code':'from collections import Counter\ndef f(xs):\n    return dict(Counter(xs))','function':'f','tests':[{'args':[[1,1,2]],'expected':{'1':2,'2':1}}]}
        self.assertTrue(run(p)['passed'])
    def test_plan_defaults_and_contradictions(self):
        rows=[json.loads(l) for l in (Path(__file__).parent/'dev.jsonl').read_text(encoding='utf8').splitlines()]
        row=next(r for r in rows if r['id']=='wait-read-9-0')
        answer=json.loads(row['answer']);del answer['steps'][1]['args']['state']
        self.assertTrue(score(row,{'text':json.dumps(answer),'completed':True})['passed'])
        answer['steps'][1]['args']['state']='hidden'
        self.assertFalse(score(row,{'text':json.dumps(answer),'completed':True})['passed'])
    def test_blocked_prose_requires_review(self):
        rows=[json.loads(l) for l in (Path(__file__).parent/'dev.jsonl').read_text(encoding='utf8').splitlines()]
        row=next(r for r in rows if r['id']=='blocked-9-0')
        answer=json.loads(row['answer']);answer['steps'][0]['args']['reason']='付款結果尚未確認。'
        self.assertIsNone(score(row,{'text':json.dumps(answer),'completed':True})['passed'])
    def test_results_cannot_be_assigned_to_different_prompts(self):
        row={'id':'r','system':'s','prompt':'p','category':'code','group':'g'}
        result={'prompt_sha256':hashlib.sha256(b's\np').hexdigest(),'category':'code','group':'g','candidate':'adapter','completed':True,'text':'answer'}
        validate_result_identity(row,result)
        with self.assertRaises(ValueError):validate_result_identity({**row,'prompt':'different'},result)
        with self.assertRaises(ValueError):validate_result_identity(row,{**result,'completed':None})
    def test_equivalent_screen_prose_requires_review(self):
        rows=[json.loads(l) for l in (Path(__file__).parent/'dev.jsonl').read_text(encoding='utf8').splitlines()]
        row=next(r for r in rows if r['id']=='tool-24-slot-10-0');answer=json.loads(row['answer'])
        answer['steps'][0]['args']['question']='報告10 欄位在何處？'
        self.assertIsNone(score(row,{'text':json.dumps(answer),'completed':True})['passed'])
    def test_extra_step_needs_review_and_invalid_tools_still_fail(self):
        rows=[json.loads(l) for l in (Path(__file__).parent/'dev.jsonl').read_text(encoding='utf8').splitlines()]
        row=next(r for r in rows if r['id']=='write-read-10-0');answer=json.loads(row['answer'])
        answer['steps'].insert(0,{**answer['steps'][0],'args':{'path':'工作區/專案10'}})
        for i,step in enumerate(answer['steps']):step['id']=i+1
        self.assertIsNone(score(row,{'text':json.dumps(answer),'completed':True})['passed'])
        answer['steps'][0]['tool']='INVENTED_TOOL'
        self.assertFalse(score(row,{'text':json.dumps(answer),'completed':True})['passed'])

if __name__=='__main__':unittest.main()
