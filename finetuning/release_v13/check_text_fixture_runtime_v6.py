"""Verify the extension dispatches text locally and does not prove file success."""
import hashlib
import json
from pathlib import Path
import tempfile
from file_fixture_text import R,ROOT,Fixture,cases,evaluate

def main():
    calls=[]
    class Gateway:
        def chat_text(self,*,prompt,system):
            calls.append({'prompt':prompt,'system':system})
            return '兩段文字相同','authored-local-gateway'
    row=cases()[0]
    with tempfile.TemporaryDirectory(dir=R,prefix='.text-tool-control-') as folder:
        fixture=Fixture(row,folder,'authored-control',Gateway())
        try:
            source=fixture.step('READ_TEXT_FILE',{'path':'訪談記錄.txt','max_chars':500000})
            fixture.step('MODEL_GENERATE',{'prompt':'請判讀：{{step:'+str(source)+'.file_text}}','system':'只判讀提供的文字。'})
            assert calls==[{'prompt':'請判讀：'+row['initial_files']['訪談記錄.txt'],'system':'只判讀提供的文字。'}]
            verdict=evaluate(row,fixture.work,fixture.ctx.history,'completed',row['expected_response'],trace=fixture.trace)
            assert not verdict['passed'] and verdict['false_completion'],'Generated assertion cannot substitute for actual output file'
            report={'real_handler_dispatched':True,'source_reference_preserved':True,'text_assertion_without_file_rejected':True,
                'production_handler_sha256':hashlib.sha256((ROOT/'run_daemon.py').read_bytes()).hexdigest(),
                'fixture_sha256':hashlib.sha256((R/'file_fixture_text.py').read_bytes()).hexdigest(),
                'model_generated':False,'release_approved':False}
        finally:fixture.close()
    with (R/'evaluation-runtime-v6/TEXT_FIXTURE_CONTROLS.json').open('x',encoding='utf8') as f:json.dump(report,f,indent=2)
    print(json.dumps(report))

if __name__=='__main__':main()
