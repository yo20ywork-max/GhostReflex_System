"""Finite local inference protocol check; no generated desktop action."""
import hashlib,json,urllib.error
from pathlib import Path
from transformers import AutoTokenizer
from evaluate_local import request
R=Path(__file__).resolve().parent

def main():
    output=R/'CONTEXT_TRANSPORT_VERIFIED.json'
    if output.exists():raise FileExistsError(output)
    tokenizer=AutoTokenizer.from_pretrained(str(R.parent/'release_v2/tokenizer'),local_files_only=True,trust_remote_code=False)
    model='qwen2.5-coder:7b';records=[]
    for name,content in [('short','Reply OK.'),('oversize',' context-check'*14000)]:
        messages=[{'role':'user','content':content}]
        tokens=len(tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True))
        payload={'model':model,'messages':messages,'stream':False,'truncate':False,'shift':False,'options':{'num_ctx':12288,'num_predict':8,'temperature':0}}
        record={'case':name,'input_tokens':tokens,'payload_sha256':hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()}
        try:
            response=request('/api/chat',payload,timeout=90)
            record.update(http_status=200,response=response,passed=name=='short' and response.get('done') is True)
        except urllib.error.HTTPError as exc:
            body=exc.read().decode('utf8',errors='replace')
            record.update(http_status=exc.code,error=body,passed=name=='oversize' and exc.code==400 and ('context' in body.lower() or 'length' in body.lower()))
        records.append(record)
    report={'version':request('/api/version'),'passed':all(x['passed'] for x in records),'records':records,'scope':'Observed local server protocol only; not long-task success or target hardware verification.'}
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
