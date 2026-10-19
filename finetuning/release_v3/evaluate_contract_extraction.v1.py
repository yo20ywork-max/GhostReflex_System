"""Known completion diagnostic: extract requirements before exposing observations."""
import argparse,hashlib,json,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R.parents[1]))
from evidence_contract import check_contract
from evaluate_local import request

def main():
    p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    output=R/a.output
    if output.exists():raise FileExistsError(output)
    catalog=json.loads((R/'training-contract.json').read_text(encoding='utf8'))['catalog']
    names=[x['name'] for x in catalog]
    # Input remains the request alone. No reference answer, oracle or observed
    # result enters the extraction prompt. All generated contracts are saved.
    requirement={'type':'object','properties':{'id':{'type':'string'},'source_quote':{'type':'string'},'tool':{'type':'string','enum':names},'args':{'type':'object'},'mode':{'type':'string','enum':['require','forbid']},'selection':{'type':'string','enum':['any','latest']},'max_output_items':{'type':'integer','minimum':0},'max_dispatches':{'type':'integer','minimum':0},'output_equals':{'type':'string'}},'required':['id','source_quote','tool','args','mode','selection'],'additionalProperties':False}
    edge={'type':'object','properties':{'first':{'type':'string'},'then':{'type':'string'},'source_quote':{'type':'string'}},'required':['first','then','source_quote'],'additionalProperties':False}
    schema={'type':'object','properties':{'requirements':{'type':'array','items':requirement,'minItems':1,'maxItems':128},'before':{'type':'array','items':edge,'maxItems':512}},'required':['requirements','before'],'additionalProperties':False}
    system=('將原始任務轉成可由工具紀錄核對的條件，不要執行。每項source_quote必須逐字引用使用者原文。'
            'require代表要有成功且verified的觀察；forbid代表禁止派發該工具。args只放使用者要求的精確參數，空物件表示該工具所有對象。'
            '不要把工具選用習慣當作額外需求。selection=any允許成功重試；latest用於核對最新結果。'
            'before列出使用者明確要求的先後關係，first與then引用requirement id。'
            'max_output_items只限制回傳清單筆數，max_dispatches限制實際派發次數；沒有要求的限制不要新增。'
            'output_equals只用於明確指定原文，保留空白；沒有指定內容時不要猜測檔案內容。'
            '空清單可以是正確的列出結果。只讀且不要改動時，列出讀取要求與禁止的寫入/追加/刪除工具。'
            '只輸出schema JSON。工具目錄：'+json.dumps(catalog,ensure_ascii=False))
    rows=[x for x in map(json.loads,(R/'dev.jsonl').read_text(encoding='utf8').splitlines()) if x['category']=='completion']
    model=next(x for x in request('/api/tags')['models'] if x['name']==a.model);cache={};records=[]
    with output.open('x',encoding='utf8') as f:
        for row in rows:
            payload=json.loads(row['prompt']);original=payload['user_request'];started=time.monotonic()
            try:
                if original not in cache:
                    messages=[{'role':'system','content':system},{'role':'user','content':original}]
                    response=request('/api/chat',{'model':a.model,'messages':messages,'format':schema,'stream':False,'truncate':False,'shift':False,'options':{'temperature':0,'num_ctx':12288,'num_predict':2048,'repeat_penalty':1.0}})
                    if response.get('done_reason')!='stop':raise ValueError('Incomplete extraction')
                    contract=json.loads(response['message']['content']);contract['request_sha256']=hashlib.sha256(original.encode()).hexdigest()
                    cache[original]={'contract':contract,'response':response,'prompt_sha256':hashlib.sha256(json.dumps(messages,ensure_ascii=False).encode()).hexdigest()}
                extracted=cache[original];check=check_contract(original,extracted['contract'],payload['observed_history'],names)
                record={'id':row['id'],'extraction':extracted,'check':check,'expected':row['oracle']['complete'],'classification_correct':check['evidence_satisfied']==row['oracle']['complete'],'false_completion':check['evidence_satisfied'] and not row['oracle']['complete']}
            except Exception as exc:record={'id':row['id'],'error':str(exc),'classification_correct':False,'false_completion':False}
            record.update(seconds=time.monotonic()-started,model_digest=model['digest'],product_release_approved=False)
            records.append(record);f.write(json.dumps(record,ensure_ascii=False)+'\n');f.flush();print(json.dumps({k:v for k,v in record.items() if k not in ('extraction','check')}),flush=True)
    summary={'classified_correctly':sum(x['classification_correct'] for x in records),'total':len(records),'false_positive_classifications':sum(x['false_completion'] for x in records),'extraction_errors':sum('error' in x for x in records),'unique_requests':len(cache),'source_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'scope':'Known synthetic observations, not actual actions. Mechanical classification depends on unverified model extraction; complete semantic coverage and end-to-end behavior remain unvalidated.','product_release_approved':False}
    output.with_suffix('.summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))
if __name__=='__main__':main()
