"""Context/literal contrasts, with metadata kept separate from model text."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from product_identity import GENERATION_SYSTEM


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_text(encoding='utf8'))
def rows(path): return [json.loads(x) for x in path.read_text(encoding='utf8').splitlines()]
def write(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf8')


def main():
    dest = HERE/'candidate-v2'
    if dest.exists(): raise FileExistsError(dest)
    draft = HERE/'draft-v1'
    manifest = read(draft/'manifest.json')
    for name, digest in manifest['outputs'].items():
        assert sha(draft/name) == digest, name
    # These are new authored task contexts, not copies of failed development answers.
    train = [
        ('course-ui', 'locale', '把介面標籤「編程語言選擇」改為台灣繁體中文，只回標籤。', '程式語言選擇'),
        ('course-java', 'locale', '請將課名「Java 编程基础」改寫為台灣繁體中文，只回課名。', 'Java 程式設計基礎'),
        ('course-js', 'locale', '將「JavaScript 編程語言課程」改成台灣常用說法，只回改寫文字。', 'JavaScript 程式語言課程'),
        ('course-literal', 'literal', '課程資料表的原始 key 就是「编程课程」，逐字回覆這個 key，不能改字。', '编程课程'),
        ('save-downloads', 'asr', '另存一份去下載資料夾啦，同名的不要蓋掉。只回 JSON 物件，destination 填目的資料夾名稱、overwrite 填布林值。', {'destination':'下載資料夾','overwrite':False}),
        ('save-documents', 'asr', '存到文件資料夾就好，裡面原本有的先別動。只回 JSON 物件，destination 填目的資料夾名稱、overwrite 填布林值。', {'destination':'文件資料夾','overwrite':False}),
        ('copy-folder', 'asr', '把檔安複製一份到圖片資料夾，原稿留著。只回 JSON 物件，operation 用 copy 或 move，destination 填目的資料夾名稱，keep_source 用布林值。', {'operation':'copy','destination':'圖片資料夾','keep_source':True}),
        ('save-explicit-file', 'tools', '另存到桌面上的「提案副本.md」，只回 JSON 物件，destination_folder 填資料夾名稱，destination_name 填指定檔名。', {'destination_folder':'桌面','destination_name':'提案副本.md'}),
        ('typo-literal-path', 'literal', '回覆 JSON 物件，唯一欄位 path 的字串值必須逐字等於這個路徑：E:\\檔安\\報表.csv。句末句號不是路徑的一部分。', {'path':'E:\\檔安\\報表.csv'}),
        ('typo-intent', 'asr', '幫我把這個檔安拷貝到下載資料夾，不要移走原檔。只回 JSON 物件，operation 用 copy 或 move，keep_source 填布林值。', {'operation':'copy','keep_source':True}),
        ('literal-china-path', 'literal', '只回 JSON 物件，path 值是下面整行原始路徑，不做用語校正：\nF:\\軟件\\文件夾\\課程.txt', {'path':'F:\\軟件\\文件夾\\課程.txt'}),
        ('literal-relative', 'literal', '只回 JSON 物件，把以下路徑原樣放進 path 字串；JSON 解碼後必須和原文完全一致：\n.\\編程語言\\範例.py', {'path':'.\\編程語言\\範例.py'}),
        ('literal-unc', 'literal', '只回 JSON 物件，path 是以下原始路徑，不能增減反斜線：\n\\\\nas\\team\\軟件.zip', {'path':'\\\\nas\\team\\軟件.zip'}),
        ('literal-ui-name', 'tools', '畫面按鈕實際寫「打开文件夹」。要按這顆按鈕，回 JSON 物件，label 必須和畫面文字完全相同。', {'label':'打开文件夹'}),
        ('help-ui-name', 'locale', '將說明文字「点一下打开文件夹」改成台灣繁體中文，只回說明文字。', '點一下開啟資料夾。'),
        ('rename-explicit', 'tools', '把檔案從「编程.txt」改名為「程式設計.txt」。只回 JSON 物件，old_name 和 new_name 分別填使用者指定的檔名。', {'old_name':'编程.txt','new_name':'程式設計.txt'}),
        ('ambiguous-name', 'asr', '語音轉文字是「開啟台北報表」，畫面同時有「台北報表.xlsx」和「臺北報表.xlsx」。沒有其他線索，不可猜檔名。只回 JSON 物件，needs_clarification 用布林值，selected_name 不確定時用 null。', {'needs_clarification':True,'selected_name':None}),
        ('resolved-name', 'asr', '畫面有「台北報表.xlsx」和「臺北報表.xlsx」。我要開的是檔名用「臺」的那份。只回 JSON 物件，needs_clarification 用布林值，selected_name 填完整檔名。', {'needs_clarification':False,'selected_name':'臺北報表.xlsx'}),
        ('negation-revision', 'negation', '剛說要覆蓋，改一下：同名的先跳過，不要蓋。只回 JSON 物件，overwrite 和 skip_existing 都用布林值。', {'overwrite':False,'skip_existing':True}),
        ('positive-revision', 'negation', '原先說不要寄，現在確認內容正確，請寄給指定收件人。只判斷目前授權，回 JSON 物件，send_now 用布林值。', {'send_now':True}),
        ('positive-copy', 'tools', '同名的是我不要的舊副本，現在允許覆寫目的檔，但來源保留。只回 JSON 物件，overwrite 和 keep_source 用布林值。', {'overwrite':True,'keep_source':True}),
        ('conditional-send', 'negation', '等我點頭才寄，現在還沒確認。只回 JSON 物件，send_now 用布林值。', {'send_now':False}),
        ('mass-science', 'locale', '將「这个物体的质量是五公斤」寫成台灣繁體中文，保留物理量的意思，只回句子。', '這個物體的質量是五公斤。'),
        ('quality-product', 'locale', '將「这款软件的质量很好」寫成台灣繁體中文，只回句子。', '這款軟體的品質很好。'),
    ]
    dev = [
        ('course-new', 'locale', '課程廣告寫「Go 编程进阶」，改成台灣繁體中文，只回標題。', 'Go 程式設計進階'),
        ('course-preserve', 'literal', '資料庫的課程代碼是「编程进阶」。只回這個代碼，不要翻譯或校正。', '编程进阶'),
        ('save-music', 'asr', '幫我另外存一份到音樂資料夾，同名的先留著嘿。只回 JSON 物件，destination 填目的資料夾名稱，overwrite 用布林值。', {'destination':'音樂資料夾','overwrite':False}),
        ('literal-g-path', 'literal', '只回 JSON 物件，唯一的 path 欄位須逐字保留下一行的路徑；不要更正疑似錯字：\nG:\\檔安\\文件夾\\提案.md', {'path':'G:\\檔安\\文件夾\\提案.md'}),
        ('literal-second-unc', 'literal', '把下面路徑放入 JSON 物件的 path 字串，只回 JSON；解碼後須和原文一致：\n\\\\office\\public\\编程.txt', {'path':'\\\\office\\public\\编程.txt'}),
        ('ui-exact-label', 'tools', '要點選畫面上標示「下载软件」的按鈕。只回 JSON 物件，label 填按鈕實際文字。', {'label':'下载软件'}),
        ('asr-no-hint', 'asr', '這份檔安先複製去文件資料夾就好，別移掉原來那份。只回 JSON 物件，operation 用 copy 或 move，keep_source 用布林值。', {'operation':'copy','keep_source':True}),
        ('ambiguous-file', 'asr', '我要開「七月報表」，資料夾同時有「7月報表.xlsx」和「七月報表.xlsx」，語音沒說實際檔名用數字還是國字，也沒有其他線索。只回 JSON 物件，needs_clarification 用布林值，selected_name 不確定時用 null。', {'needs_clarification':True,'selected_name':None}),
        ('resolved-file', 'asr', '請開「七月報表.xlsx」，不要開「7月報表.xlsx」；我指定檔名用國字七。只回 JSON 物件，needs_clarification 用布林值，selected_name 填檔名。', {'needs_clarification':False,'selected_name':'七月報表.xlsx'}),
        ('send-now-positive', 'negation', '剛才叫你先別送，現在我確認好了，送出吧。只判斷當前授權，回 JSON 物件，send_now 用布林值。', {'send_now':True}),
        ('overwrite-now-positive', 'negation', '同名的目的檔是舊版，可以蓋過去，來源不要刪。只回 JSON 物件，overwrite 和 keep_source 用布林值。', {'overwrite':True,'keep_source':True}),
        ('two-meanings', 'locale', '把「产品质量与物体质量是不同概念」改成台灣繁體中文，保留兩個意思，只回句子。', '產品品質與物體質量是不同概念。'),
    ]
    datasets={}; internal={}; changes=[]
    for split, items in (('train',train),('dev',dev)):
        data=rows(draft/(split+'.jsonl'))
        for row in data:
            internal[row['id']]={'source':row.pop('source')}
            if row['id']=='locale-v12-dev-recognition-literal':
                original=copy.deepcopy(row)
                row['prompt']='只回 JSON 物件，唯一的 path 欄位必須原樣保留以下整行路徑，不能增減字元：\nD:\\檔安\\原稿.txt'
                changes.append({'id':row['id'],'original_prompt':original['prompt'],'new_prompt':row['prompt'],'reason':'Clarify JSON object shape; original v1 result remains unchanged.'})
        for key,category,prompt,answer in items:
            row=dict(id=f'locale-v12-{split}-v2-{key}',group=f'locale-v12-{split}-v2-{key}',split=split,category=category,
                system=GENERATION_SYSTEM,prompt=prompt,answer=json.dumps(answer,ensure_ascii=False) if isinstance(answer,dict) else answer,retain=False,
                oracle={'type':'contextual_taiwan_language','json_expected':answer if isinstance(answer,dict) else None,'exact_required':category=='literal'})
            data.append(row);internal[row['id']]={'source':'Authored contextual task; text-only synthetic speech variants where applicable.'}
        datasets[split]=data
    for key in ('id','prompt','group'):
        assert not {r[key] for r in datasets['train']} & {r[key] for r in datasets['dev']}, key
        for data in datasets.values():assert len({r[key] for r in data})==len(data),key
    old=[r for split in ('train','dev') for r in rows(ROOT/'finetuning/release_v11/bundle-v2'/(split+'.jsonl'))]
    assert not {r['prompt'] for r in old} & {r['prompt'] for data in datasets.values() for r in data}
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(ROOT/'finetuning/release_v4/artifacts/outputs/epoch-3',local_files_only=True,trust_remote_code=False)
    trainer=ROOT/'finetuning/release_v11/bundle-v2/train.py'
    spec=importlib.util.spec_from_file_location('locale_v2_trainer',trainer)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    stats={}
    for split,data in datasets.items():
        lengths=[]
        for row in data:
            assert row['system']==GENERATION_SYSTEM
            assert 'source' not in row and 'attribution' not in row
            for field in ('system','prompt','answer'):
                value=row[field]
                assert tokenizer.decode(tokenizer.encode(value,add_special_tokens=False),clean_up_tokenization_spaces=False)==value
                assert not any(marker in value for marker in ('Taiwan.md','taiwan-md','CC BY-SA','ATTRIBUTION'))
            encoded=helper.tokenize_row(tokenizer,row,12288)
            poisoned=copy.deepcopy(row)
            poisoned.update(source='METADATA_SENTINEL_DO_NOT_TOKENIZE',attribution='UNRELATED_DATASET_IDENTITY',license='LICENSE_METADATA_ONLY')
            alternate=helper.tokenize_row(tokenizer,poisoned,12288)
            for field in ('ids','labels','prefix'):assert encoded[field]==alternate[field], 'Metadata reached tokens'
            p=encoded['prefix'];assert encoded['labels'][:p]==[-100]*p and encoded['labels'][p:]==encoded['ids'][p:]
            lengths.append(len(encoded['ids']))
        stats[split]={'rows':len(data),'max_tokens':max(lengths),'total_tokens':sum(lengths)}
    dest.mkdir()
    for split,data in datasets.items():
        (dest/(split+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in data),encoding='utf8')
    write(dest/'INTERNAL_METADATA.json',{'rows':internal,'parent_notice_path':'../draft-v1/ATTRIBUTION.json','use':'Internal build records only; never input as model conversations.'})
    write(dest/'CHANGES.json',changes)
    sources=[Path(__file__),trainer,ROOT/'product_identity.py',ROOT/'PROJECT_GOALS.md',draft/'manifest.json',draft/'train.jsonl',draft/'dev.jsonl',draft/'ATTRIBUTION.json']
    report={'stats':stats,'sources':{str(p.relative_to(ROOT)):sha(p) for p in sources},'outputs':{p.name:sha(p) for p in dest.iterdir() if p.is_file()},
        'actual_tokenizer_metadata_invariance_verified':True,'tokenizer_and_assistant_mask_verified':True,
        'source_identity_in_model_fields':False,'shared_task_families_not_blind':True,'original_v1_outputs_retained':True,
        'raw_audio_used':False,'merged_into_bundle':False,'training_started':False,'release_approved':False}
    write(dest/'manifest.json',report)
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
