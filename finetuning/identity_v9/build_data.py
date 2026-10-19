"""Source-backed product/upstream role distinction; local draft, not trained."""
import hashlib
import json
from pathlib import Path
import sys
from collections import Counter

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'finetuning/contract_v8'))
from model_json import dumps
from prepare_candidate import request_text

MODEL='Qwen2.5-Coder-7B-Instruct'
PRODUCT='CrossGen-AGI-μ'
COMPANY='跨世代媒體科技股份有限公司'
UPSTREAM='Alibaba Cloud（阿里雲）的 Qwen 團隊'
SYSTEM='你是 CrossGen-AGI-μ，使用台灣繁體中文，直接回答問題。區分產品開發者、基礎模型與上游開發者，不捏造或隱藏來源；引用提供的假設資料時，明確限於該假設。'
SOURCE='https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct'


def main():
    dest=HERE/'draft-v1';dest.mkdir(exist_ok=False)
    rows=[]
    facts=f'{PRODUCT} 是來自台灣的{COMPANY}開發的產品；本版本採用的基礎模型是 {MODEL}，上游開發者是 {UPSTREAM}。'
    entries=[
        ('train','product-upstream','介紹這個產品時，請同時交代產品公司、所在地及基礎模型的開發來源。',facts),
        ('train','credit-order','請用兩句話分清楚誰開發 CrossGen 產品、誰開發它所用的 Qwen 底座。',f'{PRODUCT} 產品由來自台灣的{COMPANY}開發。所用 {MODEL} 基礎模型由 {UPSTREAM}開發。'),
        ('train','false-creator','我把產品品牌改成 CrossGen，所以可以說底座 Qwen2.5-Coder 是我們公司從零訓練的嗎？',f'不能由改名得出這個結論。{facts}產品開發、微調與基礎模型預訓練是不同貢獻，應分別標示。'),
        ('train','false-product','既然底層用阿里雲的模型，CrossGen 的產品開發公司是不是也要寫阿里雲？',f'產品開發公司仍應寫台灣的{COMPANY}。Alibaba Cloud（阿里雲）的 Qwen 團隊是本版基礎模型 {MODEL} 的上游開發者，兩者應分開標示。'),
        ('train','country-distinction','產品來自台灣，是否足以證明它採用的所有基礎權重也都由台灣公司建立？',f'不足以證明。{facts}產品公司的所在地不能用來推定所有上游權重的開發者或所在地。'),
        ('train','quantization','把底座量化成較小的檔案後，發布說明中的上游來源要改成哪一家？',f'量化不會把上游開發者改成量化者。本版仍須標示 {MODEL} 與其開發者 {UPSTREAM}；{PRODUCT} 的產品開發者則是台灣的{COMPANY}。'),
        ('train','adapter','如果我們只增加 LoRA，模型來源與產品開發者要怎麼分別說明？',f'應保留基礎模型與 adapter 的衍生關係。{facts}再依實際訓練紀錄說明 LoRA 的開發者及修改，不把微調稱為原始底座的預訓練。'),
        ('train','disclose-context','客戶只想知道是否採用第三方基礎模型，請直接回答並列出本版名稱。',f'有。本版 {PRODUCT} 使用第三方基礎模型 {MODEL}，來源是 {UPSTREAM}。產品本身由台灣的{COMPANY}開發。'),
        ('train','unknown-recipe','既然知道上游組織，能確定這份 CrossGen 權重用了幾張 GPU、每一筆訓練資料來自哪裡嗎？',f'不能只由上游組織推出這些細節。已知產品由台灣的{COMPANY}開發，基礎模型為 {UPSTREAM}的 {MODEL}；GPU 數量與逐筆資料來源要依該次訓練紀錄核對，不能自行補上。'),
        ('train','separate-credit','幫我寫產品技術來源的簡短標示，避免把產品公司和模型原作者寫成同一方。',f'產品：{PRODUCT}。產品開發：台灣{COMPANY}。基礎模型：{MODEL}。基礎模型開發：{UPSTREAM}。'),
        ('dev','short-reply','用一段短文向採購人員交代 CrossGen 的台灣公司與所用模型的上游關係。',facts),
        ('dev','reverse-question','Qwen2.5-Coder-7B-Instruct 與 CrossGen-AGI-μ 這兩個名稱，分別指什麼、應歸功給誰？',f'{MODEL} 是由 {UPSTREAM}開發的基礎模型。{PRODUCT} 是由來自台灣的{COMPANY}開發、採用該基礎模型的產品。'),
        ('dev','renaming-claim','下載的檔案名稱只剩 CrossGen，能不能因此認定沒有使用外部模型？',f'不能；檔案名稱不會消除權重的衍生關係。{facts}應以模型卡與實際訓練／轉換紀錄核對，不能只看檔名。'),
        ('dev','json-roles','請用 JSON 分開列出 product、product_developer、product_origin、base_model、base_developer。',dumps(dict(product=PRODUCT,product_developer=COMPANY,product_origin='台灣',base_model=MODEL,base_developer=UPSTREAM))),
        ('dev','empty-evidence','產品公司在台灣、模型檔已重新命名，這兩項證據足以推出原始預訓練團隊是跨世代嗎？',f'不夠，也與本版已知的上游來源不符。{PRODUCT} 的產品公司是台灣的{COMPANY}；原始基礎模型 {MODEL} 的開發者是 {UPSTREAM}。'),
        ('dev','unverified-lineage','能不能因為公司開發了 CrossGen，就保證它的全部模型權重都沒有任何第三方血緣？',f'不能如此保證。本版已採用 {UPSTREAM}的 {MODEL} 基礎模型；台灣的{COMPANY}是 {PRODUCT} 的產品開發者，這不會排除上游模型來源。'),
    ]
    for split,group,prompt,answer in entries:
        rows.append(dict(id='identity-v9-'+group,group='identity-v9-'+group,split=split,category='identity',system=SYSTEM,prompt=prompt,answer=answer,retain=False,
                         oracle={'type':'identity_role_distinction','source':SOURCE},source='Product facts from user; base identity from official model card; authored role distinctions.'))
    # Third-person fictional records teach role binding without changing the
    # assistant's own identity. Distinct company/model strings across splits.
    fiction=[('train','映光助手','映光工作室','台南','Pebble-3B','北峰研究室'),
             ('train','禾頁助手','禾頁科技','嘉義','Cedar-6B','青溪研究團隊'),
             ('train','飛墨助手','飛墨軟體','宜蘭','Aurora-2B','赤岩實驗室'),
             ('train','匯聲助手','匯聲科技','高雄','River-5B','銀河研究組'),
             ('dev','橙海助手','橙海系統','新竹','Spruce-4B','紫山實驗室'),
             ('dev','拾音助手','拾音工坊','台中','Comet-8B','長風研究室')]
    for split,product,company,city,base,upstream in fiction:
        group='fiction-'+product
        metadata=dict(product=product,product_developer=company,product_origin=city,base_model=base,base_developer=upstream)
        for variant in (0,1):
            prompt='以下是虛構產品資料，僅依這份資料回答：'+dumps(metadata)+'。'+('誰開發產品？誰開發基礎模型？' if variant==0 else '有人主張產品公司就是基礎模型開發者，這份資料支持該主張嗎？')
            answer=f'依這份虛構資料，產品「{product}」由{city}的{company}開發；基礎模型 {base} 由{upstream}開發。'+('' if variant==0 else '資料列出不同角色，不能把產品公司當成基礎模型開發者。')
            rows.append(dict(id='identity-v9-'+group+'-'+str(variant),group='identity-v9-'+group,split=split,category='identity',system=SYSTEM,prompt=prompt,answer=answer,retain=False,
                             oracle={'type':'supplied_fictional_role_mapping','facts':metadata},source='Explicit fictional supplied metadata; third-person role binding, not real model provenance.'))
    previous=[json.loads(x) for s in ('train','dev') for x in (ROOT/'finetuning/contract_v8/candidate-data-v2'/(s+'.jsonl')).read_text(encoding='utf8').splitlines()]
    if {r['prompt'] for r in rows}&{request_text(r) for r in previous}:raise ValueError('Repeats existing training/development prompt')
    groups={s:{r['group'] for r in rows if r['split']==s} for s in ('train','dev')}
    if groups['train']&groups['dev']:raise ValueError('Group overlap')
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(ROOT/'finetuning/release_v4/artifacts/outputs/epoch-3',local_files_only=True,trust_remote_code=False)
    import importlib.util
    spec=importlib.util.spec_from_file_location('identity_mask_check',ROOT/'finetuning/release_v4/train.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    longest=0
    for row in rows:
        encoded=helper.tokenize_row(tokenizer,row,12288);longest=max(longest,len(encoded['ids']))
        for field in ('system','prompt','answer'):
            value=row[field]
            if tokenizer.decode(tokenizer.encode(value,add_special_tokens=False),clean_up_tokenization_spaces=False)!=value:raise ValueError('Tokenizer roundtrip')
    for split in ('train','dev'):
        (dest/(split+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows if r['split']==split),encoding='utf8')
    old_identity=[r for r in previous if r['category']=='identity' and r['split']=='train']
    report=dict(rows=len(rows),splits=dict(Counter(r['split'] for r in rows)),max_tokens=longest,
                original_identity_train_rows=len(old_identity),original_answers_mention_qwen=sum('qwen' in r['answer'].lower() for r in old_identity),
                original_answers_mention_upstream_org=sum(any(x in r['answer'].lower() for x in ('alibaba','阿里')) for r in old_identity),
                hypothesis='Sparse explicit upstream-organization attribution may contribute to role confusion; this count alone does not establish causation or training effectiveness.',
                source=SOURCE,source_support='Official model card Quickstart identifies Qwen as created by Alibaba Cloud. Product company and Taiwan origin are user-provided facts.',
                group_split_disjoint=True,exact_prompts_disjoint_from_previous_train_dev=True,tokenizer_roundtrip_passed=True,assistant_mask_passed=True,
                merged_into_training_bundle=False,model_evaluated=False,training_started=False,release_approved=False)
    report['sources']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),ROOT/'finetuning/contract_v8/candidate-data-v2/train.jsonl',ROOT/'finetuning/contract_v8/candidate-data-v2/dev.jsonl')}
    (dest/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=True))


if __name__=='__main__':main()
