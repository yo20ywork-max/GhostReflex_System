"""Paired supplied/missing/stale facts; fictional records, no guessed facts."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
from product_identity import GENERATION_SYSTEM


def main():
    dest=HERE/'evidence-draft-v1'
    if dest.exists():raise FileExistsError(dest)
    rows=[]
    # Every entity stays in one split. Counts and strings are authored fictional
    # input evidence, not purported company facts or closed-book gold knowledge.
    entities={'train':[('晴禾',17,23),('柳泉',42,38),('川墨',9,14),('嶼星',63,57),('藤原工坊',28,31),('松音',81,75)],
              'dev':[('露嶺',34,41),('澄頁',56,49),('霧桐',12,19)]}
    for split, records in entities.items():
        for name,older,newer in records:
            base=f'以下是虛構組織「{name}」的任務資料；只依提供的證據回答，缺少的資料不要自行補上。'
            cases=[
                ('present',f'本次已確認員工數為 {newer} 人。問題：已確認的員工數是多少？只回數字。',str(newer),'provided'),
                ('missing','本次只提供組織名稱，未提供員工數。問題：有幾位員工？','資料未提供員工人數，無法確定。','missing'),
                ('stale',f'三年前的紀錄有 {older} 位員工，沒有近期紀錄。問題：目前有幾位員工？',f'三年前的紀錄是 {older} 人；目前人數缺少近期資料，無法確定。','stale'),
                ('correct',f'先前紀錄為 {older} 人；本次已核實更新為 {newer} 人。有人仍說本次有 {older} 人，正確嗎？請依更新資料回答。',f'不正確；本次已核實為 {newer} 人，{older} 人是先前紀錄。','updated'),
            ]
            for kind,prompt,answer,mode in cases:
                rows.append(dict(id=f'evidence-v10-{split}-{name}-{kind}',group=f'evidence-v10-{name}',split=split,category='grounded',
                    system=GENERATION_SYSTEM,prompt=base+prompt,answer=answer,retain=False,
                    oracle={'type':'supplied_evidence_boundary','mode':mode,'fictional':True},source='Authored fictional supplied facts; no real company facts'))
    previous=[json.loads(x) for split in ('train','dev') for x in (HERE/'candidate-v1'/(split+'.jsonl')).read_text(encoding='utf8').splitlines()]
    assert not {r['prompt'] for r in previous}&{r['prompt'] for r in rows}
    assert not {r['group'] for r in rows if r['split']=='train'}&{r['group'] for r in rows if r['split']=='dev'}
    from transformers import AutoTokenizer
    tok=AutoTokenizer.from_pretrained(ROOT/'finetuning/release_v4/artifacts/outputs/epoch-3',local_files_only=True,trust_remote_code=False)
    spec=importlib.util.spec_from_file_location('evidence_trainer',ROOT/'finetuning/release_v4/train.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    maximum=0
    for row in rows:
        encoded=helper.tokenize_row(tok,row,12288);maximum=max(maximum,len(encoded['ids']))
        prefix=encoded['prefix']
        assert all(v==-100 for v in encoded['labels'][:prefix]) and encoded['labels'][prefix:]==encoded['ids'][prefix:]
        for field in ('system','prompt','answer'):
            value=row[field]
            assert tok.decode(tok.encode(value,add_special_tokens=False),clean_up_tokenization_spaces=False)==value
    dest.mkdir()
    for split in ('train','dev'):
        (dest/(split+'.jsonl')).write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows if row['split']==split),encoding='utf8')
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    report=dict(train_rows=24,dev_rows=12,max_tokens=maximum,tokenizer_and_mask_passed=True,
        entity_split_disjoint=True,known_template_family_not_blind=True,
        purpose='Teach evidence availability, freshness and correction without memorizing a fixed employee-count answer. All organizations are fictional.',
        scope_limit='One count field and four evidence patterns; not broad factual or political validation.',
        sources={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'product_identity.py']},
        outputs={p.name:sha(p) for p in dest.iterdir()},merged=False,trained=False,release_approved=False)
    (dest/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
