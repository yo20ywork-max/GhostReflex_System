"""Actual teacher controls plus labelled counterfactual oracle rejection checks."""
import hashlib
import json
import tempfile
from pathlib import Path
from file_flow import cases,Fixture,evaluate,R


def main():
    records=[]
    for row in cases():
        with tempfile.TemporaryDirectory(dir=R,prefix='oracle-control-') as temporary:
            fixture=Fixture(row,temporary,'teacher-control',None)
            try:
                initial=evaluate(row,fixture.work,[],'completed',row['expected_response'])
                assert not initial['passed'] and initial['false_completion'],row['id']
                ids={}
                if row['required_existence_checks']:
                    fixture.step('LIST_DIRECTORY',{'path':'.','recursive':False,'max_items':100})
                else:
                    for name in row['initial_files']:
                        ids[name]=fixture.step('READ_TEXT_FILE',{'path':name,'max_chars':500000})
                    for name,allowed in row['write_targets'].items():
                        if 'MAKE_DIRECTORY' in allowed:
                            fixture.step('MAKE_DIRECTORY',{'path':name});continue
                        expected=row['expected_files'][name]
                        if 'APPEND_TEXT_FILE' in allowed:
                            suffix=expected[len(row['initial_files'][name]):]
                            source=next(p for p,text in row['initial_files'].items() if p!=name and text==suffix)
                            fixture.step('APPEND_TEXT_FILE',{'path':name,'content':'{{step:'+str(ids[source])+'.file_text}}'})
                        else:
                            matches=[p for p,text in row['initial_files'].items() if p!=name and text==expected]
                            if matches:content='{{step:'+str(ids[matches[0]])+'.file_text}}'
                            else:
                                assert expected==''.join(row['initial_files'].values())
                                content=''.join('{{step:'+str(ids[p])+'.file_text}}' for p in row['initial_files'])
                            fixture.step('WRITE_TEXT_FILE',{'path':name,'content':content,'overwrite':False})
                    for name in row['required_readback']:
                        fixture.step('READ_TEXT_FILE',{'path':name,'max_chars':500000})
                fixture.step('FINAL_RESPONSE',{'message':row['expected_response']})
                history=fixture.ctx.history
                positive=evaluate(row,fixture.work,history,'completed',row['expected_response'])
                assert positive['passed'],(row['id'],positive)
                wrong_message=evaluate(row,fixture.work,history,'completed','尚未依指定文字回答')
                assert not wrong_message['passed'] and not wrong_message['response_ok']
                if row['required_readback']:
                    target=row['required_readback'][0]
                    stripped=[h for h in history if not(h['tool']=='READ_TEXT_FILE' and h['args']['path']==target)]
                    missing=evaluate(row,fixture.work,stripped,'completed',row['expected_response'])
                    assert not missing['passed'] and missing['false_completion']
                    reads=[h for h in history if h['tool']=='READ_TEXT_FILE' and h['args']['path']==target]
                    reordered=reads+stripped
                    wrong_order=evaluate(row,fixture.work,reordered,'completed',row['expected_response'])
                    assert not wrong_order['passed'] and wrong_order['false_completion']
                    path=fixture.work/target;original=path.read_bytes();path.write_bytes(original+b'CHANGED')
                    corrupted=evaluate(row,fixture.work,history,'completed',row['expected_response'])
                    assert not corrupted['passed'] and corrupted['false_completion']
                    path.write_bytes(original)
                    negatives={'missing_readback_counterfactual':missing,'readback_before_write_counterfactual':wrong_order,'actual_corrupted_artifact':corrupted}
                else:
                    missing=evaluate(row,fixture.work,[h for h in history if h['tool']!='LIST_DIRECTORY'],'completed',row['expected_response'])
                    assert not missing['passed'] and missing['false_completion']
                    negatives={'missing_existence_observation_counterfactual':missing}
                records.append({'id':row['id'],'actual_teacher_positive':positive,'actual_initial_files_only_claim':initial,'wrong_final_response_counterfactual':wrong_message,'negative_controls':negatives,'teacher_history':history,'receipts':fixture.journal.read(fixture.ctx.request_id),'model_generated':False})
            finally:fixture.close()
    report={'cases':len(records),'all_controls_passed':True,'records':records,'model_task_success_claimed':False,'oracle_sha256':hashlib.sha256((R/'file_flow.py').read_bytes()).hexdigest(),'control_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'input_sha256':hashlib.sha256((R/'file-development-v2.jsonl').read_bytes()).hexdigest(),'release_approved':False}
    with (R/'FILE_ORACLE_CONTROLS.json').open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k!='records'}))


if __name__=='__main__':main()
