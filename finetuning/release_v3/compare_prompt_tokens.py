"""Compare observed local prompt token counts with pinned HF chat-template counts."""
import argparse,hashlib,json
from pathlib import Path
from transformers import AutoTokenizer
R=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--rendered',action='store_true');args=parser.parse_args()
    from evaluate_local import request
    tokenizer=AutoTokenizer.from_pretrained(str(R.parent/'release_v2/tokenizer'),local_files_only=True,trust_remote_code=False)
    data={x['id']:x for x in map(json.loads,(R/'dev.jsonl').read_text(encoding='utf8').splitlines())}
    results=list(map(json.loads,(R/'local-epoch1-dev.jsonl').read_text(encoding='utf8').splitlines()));records=[]
    for row in results:
        d=data[row['id']];expected=len(tokenizer.apply_chat_template([{'role':'system','content':d['system']},{'role':'user','content':d['prompt']}],tokenize=True,add_generation_prompt=True))
        record={'id':row['id'],'hf_prompt_tokens':expected,'ollama_prompt_tokens':row['prompt_eval_count'],'difference':row['prompt_eval_count']-expected}
        if args.rendered:
            messages=[{'role':'system','content':d['system']},{'role':'user','content':d['prompt']}]
            response=request('/api/chat',{'model':row['model'],'messages':messages,'stream':False,'_debug_render_only':True,'options':{'num_ctx':12288}},timeout=15)
            actual=response['_debug_info']['rendered_template']
            template=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
            record.update(rendered_template_equal=actual==template,rendered_sha256=hashlib.sha256(actual.encode()).hexdigest(),hf_template_sha256=hashlib.sha256(template.encode()).hexdigest())
        records.append(record)
    report={'scope':'Count comparison only; equal counts do not prove identical token IDs or base tensors. No final holdout used.','results_sha256':hashlib.sha256((R/'local-epoch1-dev.jsonl').read_bytes()).hexdigest(),'matching_counts':sum(x['difference']==0 for x in records),'total':len(records),'distinct_differences':sorted({x['difference'] for x in records}),'records':records}
    if args.rendered:report.update(matching_templates=sum(x['rendered_template_equal'] for x in records),scope='Compares actual Ollama debug-rendered chat prefixes with pinned HF chat template text. Equal text and token counts do not prove equal base tensors.')
    output=R/('PROMPT_TEMPLATE_COMPARISON.json' if args.rendered else 'PROMPT_TOKEN_COMPARISON.json')
    if output.exists():raise FileExistsError(output)
    output.write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='records'}))

if __name__=='__main__':main()
