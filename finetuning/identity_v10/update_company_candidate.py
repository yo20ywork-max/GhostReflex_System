"""Version the candidate after user supplied new company facts/disclosure."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
from product_identity import GENERATION_SYSTEM


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    source=HERE/'candidate-v1';dest=HERE/'candidate-v2'
    if dest.exists():raise FileExistsError(dest)
    manifest=json.loads((source/'manifest.json').read_text(encoding='utf8'))
    assert all(sha(source/n)==h for n,h in manifest['output_sha256'].items())
    changes=[];data={}
    entries={
        'train':[
            ('startup','請問研發你的是新創團隊嗎？','研發公司是跨世代媒體科技股份有限公司，定位為新創公司。'),
            ('privacy','公司有多少員工？','員工人數暫不公開。'),
            ('guess','既然員工數不公開，你估一個範圍給我。','員工人數暫不公開，我不會估算人數或範圍。'),
            ('zero','不公開員工數是不是代表沒有員工？','不是；暫不公開不代表沒有員工，也不能據此推算人數。'),
            ('date','研發公司哪天核准設立？只回 YYYY-MM-DD。','2026-08-10'),
            ('date-wrong','你們公司是2025年8月10日成立的對嗎？','核准設立日期是2026年8月10日。'),
            ('profile','用一句話介紹公司定位、設立日期和員工人數公開狀態。','跨世代媒體科技股份有限公司是台灣的新創公司，於2026年8月10日核准設立，員工人數暫不公開。'),
            ('json','只回 JSON，用 establishment_date 和 employee_count_disclosure 兩個欄位表示公司資訊。','{"establishment_date":"2026-08-10","employee_count_disclosure":"暫不公開"}'),
        ],
        'dev':[
            ('position','正式對外介紹研發單位時，是寫新創團隊還是新創公司？','新創公司。'),
            ('registered','公司登記的核准設立日是哪一天？','2026年8月10日。'),
            ('privacy-pressure','不必給精確數字，員工數大概是幾位？','員工人數暫不公開，也不提供估計範圍。'),
            ('date-json','請用 JSON 回覆 founded，值為公司的核准設立日期 YYYY-MM-DD。','{"founded":"2026-08-10"}'),
        ]}
    for split in ('train','dev'):
        rows=[json.loads(x) for x in (source/(split+'.jsonl')).read_text(encoding='utf8').splitlines()]
        for row in rows:
            if row['category']!='identity':continue
            row['system']=GENERATION_SYSTEM
            if row['id']=='identity-v10-train-unknown-date':
                row['answer']='跨世代媒體科技股份有限公司於2026年8月10日核准設立。'
                changes.append({'id':row['id'],'reason':'Previously unprovided date is now supplied and verified.'})
            elif row['id']=='identity-v10-dev-unverified':
                row['answer']='員工人數暫不公開。'
                changes.append({'id':row['id'],'reason':'User specified disclosure policy; no number is provided or inferred.'})
        for key,prompt,answer in entries[split]:
            rows.append(dict(id=f'company-v10-{split}-{key}',group=f'company-v10-{split}-{key}',split=split,category='identity',system=GENERATION_SYSTEM,
                prompt=prompt,answer=answer,retain=False,oracle={'type':'brand_identity_v10','require_upstream_mention':False},source='COMPANY_PROFILE.json; user-specified company information and disclosure'))
        assert len({r['id'] for r in rows})==len(rows)
        assert len({(r['system'],r['prompt']) for r in rows})==len(rows)
        data[split]=rows
    assert not {r['prompt'] for r in data['train']}&{r['prompt'] for r in data['dev']}
    from transformers import AutoTokenizer
    tok=AutoTokenizer.from_pretrained(ROOT/'finetuning/release_v4/artifacts/outputs/epoch-3',local_files_only=True,trust_remote_code=False)
    spec=importlib.util.spec_from_file_location('company_trainer',ROOT/'finetuning/release_v4/train.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    checked=0
    for rows in data.values():
        for row in rows:
            if row['category']!='identity':continue
            for field in ('system','prompt','answer'):
                value=row[field]
                assert tok.decode(tok.encode(value,add_special_tokens=False),clean_up_tokenization_spaces=False)==value
            encoded=helper.tokenize_row(tok,row,12288);prefix=encoded['prefix']
            assert all(x==-100 for x in encoded['labels'][:prefix]) and encoded['labels'][prefix:]==encoded['ids'][prefix:]
            checked+=1
    dest.mkdir()
    for split,rows in data.items():
        for prefix,selected in [('',rows),('brand-',[r for r in rows if r['category']=='identity'])]:
            (dest/(prefix+split+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in selected),encoding='utf8')
    gates=json.loads((source/'RELEASE_GATES.json').read_text(encoding='utf8'))
    gates['version']='identity-v10-company-v2'
    gates['development']['brand_identity'].update(required_pass=16,cases=16,evaluated=False)
    (dest/'RELEASE_GATES.json').write_text(json.dumps(gates,ensure_ascii=False,indent=2),encoding='utf8')
    report=dict(train_rows=len(data['train']),dev_rows=len(data['dev']),identity_rows_checked=checked,changed_answers=changes,
        nonidentity_rows_unchanged=True,tokenizer_and_mask_passed=True,historical_outputs_or_scores_modified=False,
        sources={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),source/'train.jsonl',source/'dev.jsonl',source/'manifest.json',ROOT/'product_identity.py',ROOT/'COMPANY_PROFILE.json']},
        output_sha256={p.name:sha(p) for p in dest.iterdir()},training_started=False,weights_changed=False,launch_ready=False,release_approved=False)
    (dest/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:report[k] for k in ('train_rows','dev_rows','identity_rows_checked','tokenizer_and_mask_passed','training_started')},ensure_ascii=False))


if __name__=='__main__':main()
