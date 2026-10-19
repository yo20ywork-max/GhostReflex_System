"""Execute positive controls and reject missing/forged evidence and bad bytes."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from file_fixture import R,Fixture,cases,evaluate,DEPENDENCIES

def main():
    records=[]
    for row in cases():
        for mode in ('text','copy'):
            with tempfile.TemporaryDirectory(dir=R,prefix='.file8-control-') as folder:
                fixture=Fixture(row,folder,'authored-control',None)
                try:
                    score=lambda h=None,msg=None: evaluate(row,fixture.work,fixture.ctx.history if h is None else h,'completed',row['expected_response'] if msg is None else msg)
                    assert not score([])['passed']
                    if row['id']=='v4-file-06':
                        fixture.step('PATH_INFO' if mode=='text' else 'COPY_FILE_VERIFIED',
                            {'path':'既有副本.txt'} if mode=='text' else {'source':'原稿.txt','destination':'既有副本.txt','if_exists':'skip'})
                    else:
                        fixture.seed();ids={}
                        if mode=='text':
                            for name in row['initial_files']:ids[name]=fixture.step('READ_TEXT_FILE',{'path':name,'max_chars':500000})
                        for name,allowed in row['write_targets'].items():
                            if 'MAKE_DIRECTORY' in allowed:fixture.step('MAKE_DIRECTORY',{'path':name});continue
                            if row['seed'] and row['seed']['kind']=='actual_read_then_exclusive_copy':continue
                            sources=DEPENDENCIES[row['id']][name]
                            if mode=='copy' and len(sources)==1 and 'WRITE_TEXT_FILE' in allowed:
                                fixture.step('COPY_FILE_VERIFIED',{'source':sources[0],'destination':name,'if_exists':'error'})
                            else:
                                for source in sources:
                                    if source not in ids:ids[source]=fixture.step('READ_TEXT_FILE',{'path':source,'max_chars':500000})
                                content=''.join('{{step:'+str(ids[s])+'.file_text}}' for s in sources)
                                tool='APPEND_TEXT_FILE' if 'APPEND_TEXT_FILE' in allowed else 'WRITE_TEXT_FILE'
                                args={'path':name,'content':content}
                                if tool=='WRITE_TEXT_FILE':args['overwrite']=False
                                fixture.step(tool,args)
                        for name in row['required_readback']:fixture.step('READ_TEXT_FILE',{'path':name,'max_chars':500000})
                    fixture.step('FINAL_RESPONSE',{'message':row['expected_response']})
                    positive=score();assert positive['passed'],(row['id'],mode,positive)
                    assert not score(msg='錯誤交付文字')['passed']
                    history=copy.deepcopy(fixture.ctx.history)
                    # Remove all actual observation/readback evidence, keeping
                    # files correct. An assertion of completion must still fail.
                    without=[h for h in history if h['tool'] not in ('READ_TEXT_FILE','PATH_INFO','LIST_DIRECTORY','COPY_FILE_VERIFIED')]
                    assert not score(without)['passed']
                    copies=[h for h in history if h['tool']=='COPY_FILE_VERIFIED' and h['evidence'].get('copied')]
                    if copies:
                        forged=copy.deepcopy(history)
                        for h in forged:
                            if h['tool']=='COPY_FILE_VERIFIED':h['evidence']['sha256']='0'*64
                        assert not score(forged)['passed']
                    path=fixture.work/next(iter(row['expected_files']));original=path.read_bytes();path.write_bytes(original+b'WRONG')
                    assert not score()['passed'];path.write_bytes(original)
                    if row['id']=='v4-file-06':
                        forbidden=evaluate(row,fixture.work,history,'completed',row['expected_response'],source_opens=[{'path':'原稿.txt','mode':'rb'}])
                        assert not forbidden['passed']
                    records.append({'id':row['id'],'mode':mode,'positive':positive,'teacher_history':history,
                        'negative_controls_rejected':True,'model_generated':False})
                finally:fixture.close()
    sources=[Path(__file__),R/'file_fixture.py',R.parent/'release_v4/file_flow.py',R.parent/'release_v4/file-development-v2.jsonl']
    report={'cases':8,'positive_controls':len(records),'all_controls_passed':True,'records':records,
        'sources':{str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},'release_approved':False}
    with (R/'evaluation-runtime-v2/FILE_FIXTURE_CONTROLS.json').open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k not in ('records','sources')}))

if __name__=='__main__':main()
