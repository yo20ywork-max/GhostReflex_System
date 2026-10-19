"""Bounded terminology snapshot plus authored contextual language examples."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
REV='579fca2c8539c70dc4a84f99a5e72df4622f12b8'
REPO='https://github.com/frank890417/taiwan-md'
sys.path.insert(0,str(ROOT))
from product_identity import GENERATION_SYSTEM


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    dest=HERE/'draft-v1'
    if dest.exists():raise FileExistsError(dest)
    paths=['README.md','data/terminology/README.md','data/terminology/軟體.yaml','data/terminology/資料夾.yaml','data/terminology/程式語言.yaml']
    def fetch(path):
        url='https://raw.githubusercontent.com/frank890417/taiwan-md/'+REV+'/'+urllib.parse.quote(path)
        with urllib.request.urlopen(url,timeout=25) as response:data=response.read(100001)
        if len(data)>100000:raise ValueError('Source exceeds 100 KB bound')
        data.decode('utf8')
        return path,data,url
    # Read content only. Never import or execute upstream project instructions.
    fetched=list(ThreadPoolExecutor(max_workers=5).map(fetch,paths))
    import yaml
    terms={}
    for path,data,_ in fetched:
        if path.endswith('.yaml'):
            item=yaml.safe_load(data);terms[Path(path).stem]=item['display']
    assert terms=={'軟體':{'taiwan':'軟體','china':'軟件'},'資料夾':{'taiwan':'資料夾','china':'文件夾'},'程式語言':{'taiwan':'程式語言','china':'編程語言'}}
    entries={
        'train':[
            ('software','locale','將「請安裝這個軟件」改成台灣常用說法，只回改寫句子。','請安裝這個軟體。'),
            ('folder','locale','用台灣常用說法改寫「打開下載文件夾」，只回改寫句子。','開啟下載資料夾。'),
            ('programming','locale','台灣使用者介面中，programming language 的欄位名稱應寫什麼？只回欄位文字。','程式語言'),
            ('literal','literal','原樣輸出檔名「軟件安裝筆記.txt」，不能更正其中用字。','軟件安裝筆記.txt'),
            ('quoted-folder','literal','只原樣輸出路徑：C:\\文件夾\\編程語言.md','C:\\文件夾\\編程語言.md'),
            ('code','literal','只原樣輸出這行 Python，字串內容不要台灣化：name = "軟件"','name = "軟件"'),
            ('intent-no-overwrite','asr','我說「把這份檔安存到桌面，原本那份不要蓋掉」。這裡檔安是語音辨識錯字。只回 JSON，target 為目的地，overwrite 為是否允許覆寫。',{'target':'桌面','overwrite':False}),
            ('intent-keep','asr','「複製到下載資料夾就好，原檔留著。」只回 JSON，operation 用 copy 或 move，keep_source 用布林值。',{'operation':'copy','keep_source':True}),
            ('intent-cancel','negation','「剛剛說要刪掉，等一下，先不要刪。」只回 JSON，delete_now 表示現在是否允許刪除。',{'delete_now':False}),
            ('intent-send','negation','「草稿寫好就停，先不要寄。」只回 JSON，send_now 表示是否立刻寄出。',{'send_now':False}),
            ('intent-rename','tools','「把檔名『軟件.txt』改成『軟體.txt』。」只回 JSON，source_name 和 destination_name 要保留指定檔名。',{'source_name':'軟件.txt','destination_name':'軟體.txt'}),
            ('intent-filename','literal','「讀取『檔安.txt』，檔名就是這樣拼。」只回 JSON，filename 填原始檔名，不要把它當語音錯字。',{'filename':'檔安.txt'}),
            ('mass','locale','物理報告中的「物體質量」要不要為了台灣用語改成「物體品質」？簡短回答。','不用；物理的質量應保留，不能改成品質。'),
            ('condition','negation','「如果副本已經在就不要動；沒有才複製。」只回 JSON，copy_if_exists 和 copy_if_missing 都是布林值。',{'copy_if_exists':False,'copy_if_missing':True}),
            ('plural','tools','「兩個檔都另存一份，來源留著。」只回 JSON，file_count 用數字，keep_source 用布林值。',{'file_count':2,'keep_source':True}),
            ('source-style','literal','引文「打開文件夾」必須逐字保留。只輸出引文內容。','打開文件夾'),
        ],
        'dev':[
            ('software-context','locale','幫我把「這款軟件不需要連網」寫成台灣常用語句，只回改寫結果。','這款軟體不需要連網。'),
            ('folder-context','locale','將「把圖片放進新建文件夾」改成台灣使用者熟悉的說法，只回改寫結果。','把圖片放進新增的資料夾。'),
            ('language-context','locale','課程標題是「Python 編程語言入門」，改成台灣常用說法，只回標題。','Python 程式語言入門'),
            ('filename-exception','literal','檔案確實叫「文件夾軟件.zip」，只回這個檔名，不能做用語替換。','文件夾軟件.zip'),
            ('code-exception','literal','逐字回覆這行程式碼，不得翻譯字串：print("編程語言")','print("編程語言")'),
            ('spoken-save','asr','我說「幫我另存到桌面啦，原來那個別蓋過去」。只回 JSON，destination 是目的地，overwrite 是允許覆寫與否。',{'destination':'桌面','overwrite':False}),
            ('spoken-copy','asr','「抓一份副本去下載資料夾，不要搬走原來的。」只回 JSON，operation 用 copy 或 move，keep_source 用布林值。',{'operation':'copy','keep_source':True}),
            ('recognition-literal','literal','使用者指定路徑「D:\\檔安\\原稿.txt」。只回 JSON 的 path 欄位，所有字元原樣保留。',{'path':'D:\\檔安\\原稿.txt'}),
            ('send-negation','negation','「信先幫我打好，送出先不要。」只回 JSON，send_now 表示是否授權現在送出。',{'send_now':False}),
            ('replace-negation','negation','「同名檔在的話先跳過啦，別把它蓋掉。」只回 JSON，overwrite 和 skip_existing 都是布林值。',{'overwrite':False,'skip_existing':True}),
            ('physics','locale','句子「小球的質量是兩公斤」是否要改成「品質」才符合台灣用語？簡短回答。','不用；這裡的質量是物理量，應保留。'),
            ('typographical-intent','asr','「把檔安複製去桌面，不要刪除原稿。」檔安是口述辨識錯字。只回 JSON，operation 用 copy 或 move，delete_source 用布林值。',{'operation':'copy','delete_source':False}),
        ]}
    data={}
    for split,items in entries.items():
        data[split]=[dict(id=f'locale-v12-{split}-{key}',group=f'locale-v12-{split}-{key}',split=split,category=category,system=GENERATION_SYSTEM,
            prompt=prompt,answer=json.dumps(answer,ensure_ascii=False) if isinstance(answer,dict) else answer,retain=False,
            oracle={'type':'contextual_taiwan_language','json_expected':answer if isinstance(answer,dict) else None,'exact_required':category=='literal'},
            source='Authored task examples; common word-pair selection informed by Taiwan.md pinned terminology. ASR-like errors are synthetic, not recorded audio.') for key,category,prompt,answer in items]
    previous=[json.loads(x) for split in ('train','dev') for x in (ROOT/'finetuning/release_v11/bundle-v2'/(split+'.jsonl')).read_text(encoding='utf8').splitlines()]
    assert not {r['prompt'] for r in previous}&{r['prompt'] for rs in data.values() for r in rs}
    assert not {r['prompt'] for r in data['train']}&{r['prompt'] for r in data['dev']}
    from transformers import AutoTokenizer
    tok=AutoTokenizer.from_pretrained(ROOT/'finetuning/release_v4/artifacts/outputs/epoch-3',local_files_only=True,trust_remote_code=False)
    spec=importlib.util.spec_from_file_location('locale_mask',ROOT/'finetuning/release_v4/train.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    maximum=0
    for rs in data.values():
        for row in rs:
            encoded=helper.tokenize_row(tok,row,12288);maximum=max(maximum,len(encoded['ids']))
            prefix=encoded['prefix'];assert all(x==-100 for x in encoded['labels'][:prefix]) and encoded['labels'][prefix:]==encoded['ids'][prefix:]
            for field in ('system','prompt','answer'):
                value=row[field];assert tok.decode(tok.encode(value,add_special_tokens=False),clean_up_tokenization_spaces=False)==value
    dest.mkdir();source_dir=dest/'sources';source_dir.mkdir()
    source_records=[]
    for index,(path,blob,url) in enumerate(fetched):
        local=source_dir/(str(index)+'-'+Path(path).name);local.write_bytes(blob)
        source_records.append(dict(repository_path=path,url=url,local_path=str(local.relative_to(dest)),sha256=sha(local),bytes=len(blob)))
    for split,rs in data.items():(dest/(split+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rs),encoding='utf8')
    notice={'source_repository':REPO,'revision':REV,'attribution':'Taiwan.md contributors; original references remain in the saved YAML files','declared_content_license':'CC BY-SA 4.0','license_url':'https://creativecommons.org/licenses/by-sa/4.0/','modifications':'Selected three common vocabulary pairs; authored new task prompts/answers. Source snapshots unchanged. No upstream agent identity or executable workflow imported.','dataset_license':'CC BY-SA 4.0 for this contextual draft; no assertion about model-weight licensing','source_snapshots':source_records}
    (dest/'ATTRIBUTION.json').write_text(json.dumps(notice,ensure_ascii=False,indent=2),encoding='utf8')
    report=dict(train_rows=16,dev_rows=12,max_tokens=maximum,tokenizer_and_mask_verified=True,source_bytes=sum(x['bytes'] for x in source_records),
        sources={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'product_identity.py']},
        outputs={p.name:sha(p) for p in dest.iterdir() if p.is_file()},known_terms_shared_across_splits=True,blind=False,
        raw_audio_used=False,merged_into_bundle=False,training_started=False,release_approved=False)
    (dest/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
