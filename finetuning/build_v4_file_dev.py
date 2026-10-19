"""Freeze new development inputs/artifact oracles before model generation.

These are additional development cases, not replacements for the original gates
or the unopened final holdout. Oracle file contents are never sent to a model.
"""
import hashlib
import json
from pathlib import Path

F=Path(__file__).resolve().parent
R=F/'release_v4'


def main():
    rows=[]
    def case(id_,family,prompt,files,expected,reads,response,allowed,seed=None):
        rows.append({'id':id_,'group':family,'split':'new-dev','user_request':prompt,
                     'initial_files':files,'expected_files':expected,'required_readback':reads,
                     'expected_response':response,'write_targets':allowed,'seed':seed,
                     'protected_files':[p for p in files if p not in allowed],
                     'oracle_type':'actual_files_history_and_final_response','source':'Authored development input and artifact oracle; no generated plan or model answer.'})
    text='版本：秋季\r\n'+''.join(f'{i:03}\t收音備註𠮷😀\t保留  \r\n' for i in range(57))+'\r\n字面 {{step:800.output}}\r\n  '
    case('v4-file-01','new-single-copy','讀完「訪談記錄.txt」，原樣存成新的「訪談備份.txt」。原檔不要改，空白和換行也不能變。讀回副本確認一樣後回覆「備份完成」。',{'訪談記錄.txt':text},{'訪談記錄.txt':text,'訪談備份.txt':text},['訪談備份.txt'],'備份完成',{'訪談備份.txt':['WRITE_TEXT_FILE']})
    files={'錄影清單.txt':'A機\r\nB機\t\r\n','錄音清單.txt':'左聲道\n右聲道\n'}
    expected={**files,'交付/錄影清單.txt':files['錄影清單.txt'],'交付/錄音清單.txt':files['錄音清單.txt']}
    case('v4-file-02','new-two-copies','建立「交付」資料夾，將「錄影清單.txt」和「錄音清單.txt」各自原樣備份進去，不動原檔、不覆蓋既有檔案。兩份都讀回確認相同後，回覆「兩份已核對」。',files,expected,['交付/錄影清單.txt','交付/錄音清單.txt'],'兩份已核對',{'交付':['MAKE_DIRECTORY'],'交付/錄影清單.txt':['WRITE_TEXT_FILE'],'交付/錄音清單.txt':['WRITE_TEXT_FILE']})
    files={'新增筆記.txt':'\n補充：片尾需留  兩格\t\n','總筆記.txt':'原有內容不可刪\r\n'}
    case('v4-file-03','new-append-source','讀取「新增筆記.txt」，把它的完整原文直接接到「總筆記.txt」末尾，不要自行加換行，不要覆寫原本內容，也不要改新增筆記。讀回總筆記確認後回覆「追加完成」。',files,{**files,'總筆記.txt':files['總筆記.txt']+files['新增筆記.txt']},['總筆記.txt'],'追加完成',{'總筆記.txt':['APPEND_TEXT_FILE']})
    files={'前半.txt':'前半\t\r\n','後半.txt':'後半 e\u0301\n'}
    case('v4-file-04','new-join-sources','先讀「前半.txt」與「後半.txt」，依這個順序直接串接兩份完整原文，不加分隔字元，存成新的「合稿.txt」。保留原始檔，讀回合稿核對後回覆「合稿完成」。',files,{**files,'合稿.txt':files['前半.txt']+files['後半.txt']},['合稿.txt'],'合稿完成',{'合稿.txt':['WRITE_TEXT_FILE']})
    case('v4-file-05','new-empty-copy','把「空白原稿.txt」原樣備份成新檔「空白副本.txt」，空檔也要建立副本。不要改原檔，讀回確認後回覆「空檔已備份」。',{'空白原稿.txt':''},{'空白原稿.txt':'','空白副本.txt':''},['空白副本.txt'],'空檔已備份',{'空白副本.txt':['WRITE_TEXT_FILE']})
    files={'原稿.txt':'新資料\n','既有副本.txt':'這是其他人的版本\n'}
    case('v4-file-06','new-existing-destination','先確認「既有副本.txt」是否存在；若存在，保持所有檔案不變並回覆「副本已存在，保持不變」。只有它不存在時，才讀取「原稿.txt」並原樣建立副本，讀回確認後回覆「新副本完成」。',files,files,['既有副本.txt'],'副本已存在，保持不變',{})
    original='\t已完成第一階段\r\n'+('接續處理來源資料。'*21)
    case('v4-file-07','new-copy-resume-after-write','把「來源稿.txt」完整備份成新的「待核對.txt」，不改原檔。寫入後讀回副本確認一致才回覆「核對完成」。已成功的寫入不要重做。',{'來源稿.txt':original},{'來源稿.txt':original,'待核對.txt':original},['待核對.txt'],'核對完成',{'待核對.txt':['WRITE_TEXT_FILE']},seed={'kind':'actual_read_then_exclusive_copy','source':'來源稿.txt','destination':'待核對.txt'})
    source='標題\r\n'+('保留全部原文與行尾  \t\r\n'*39)
    case('v4-file-08','new-copy-resume-partial','繼續讀完「長原稿.txt」，原檔不要動，把完整內容存成新的「長副本.txt」。寫好要實際讀回，確認相同後回覆「接續完成」。',{'長原稿.txt':source},{'長原稿.txt':source,'長副本.txt':source},['長副本.txt'],'接續完成',{'長副本.txt':['WRITE_TEXT_FILE']},seed={'kind':'actual_partial_read','source':'長原稿.txt','max_chars':137})
    assert len({x['id'] for x in rows})==8
    for row in rows:
        for name in row['initial_files']|row['expected_files']:
            assert not Path(name).is_absolute() and '..' not in Path(name).parts
        assert all(row['expected_files'][p]==row['initial_files'][p] for p in row['protected_files'])
    path=R/'file-development.jsonl'
    with path.open('x',encoding='utf8') as f:
        for row in rows:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    lock={'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'cases':8,'model_answers_generated':False,'training_use':False,'replaces_original_gates':False,'note':'New development set; no claim of complete coverage or statistically independent success rates. Artifact oracle is hidden from model input.'}
    with (R/'FILE_DEV_LOCK.json').open('x',encoding='utf8') as f:json.dump(lock,f,ensure_ascii=False,indent=2)
    print(json.dumps(lock))


if __name__=='__main__':main()
