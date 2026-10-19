"""Bind cloud/local outputs to identical known prompts; differences are not scores."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    output=R/'DEPLOYMENT_COMPARISON.json'
    if output.exists():raise FileExistsError(output)
    verification=json.loads((R/'ARTIFACT_VERIFIED.json').read_text())
    if not verification['verified']:raise ValueError('Cloud artifact verification required')
    prefixes={'base':'local-base-repeat1','epoch-1':'local-epoch1-repeat1','epoch-2':'local-epoch2','epoch-3':'local-epoch3'}
    models=[];hashes={}
    for name,prefix in prefixes.items():
        cloud=R/'artifacts/outputs'/('known-nf4-'+name+'.jsonl')
        expected=next(x['sha256'] for x in verification['files'] if x['path']==cloud.relative_to(R/'artifacts').as_posix())
        if sha(cloud)!=expected:raise ValueError('Cloud diagnostic changed')
        hf=list(map(json.loads,cloud.read_text(encoding='utf8').splitlines()));local={}
        for suffix in ('dev.jsonl','regression.jsonl'):
            p=R/(prefix+'-'+suffix);hashes[p.name]=sha(p)
            local.update({x['id']:x for x in map(json.loads,p.read_text(encoding='utf8').splitlines())})
        if len(hf)!=26 or len({x['id'] for x in hf})!=26:raise ValueError('Incomplete known cloud questions')
        pairs=[]
        for h in hf:
            q=local[h['id']]
            if h['prompt_sha256']!=q['prompt_sha256']:raise ValueError('Mismatched prompts')
            if q['inference_overrides'].get('repeat_penalty')!=1.0:raise ValueError('Mismatched repetition penalty')
            pairs.append({'id':h['id'],'category':h['category'],'nf4_text':h['text'],'local_text':q['text'],'exact_text_equal':h['text']==q['text'],'prompt_tokens_equal':h['prompt_tokens']==q['prompt_eval_count'],'nf4_completed':h['completed'],'local_completed':q['completed']})
        hashes[cloud.relative_to(R).as_posix()]=sha(cloud)
        models.append({'candidate':name,'local_model_digest':local[hf[0]['id']]['model_digest'],'total':26,'exact_text_matches':sum(x['exact_text_equal'] for x in pairs),'prompt_token_count_matches':sum(x['prompt_tokens_equal'] for x in pairs),'both_generation_complete':sum(x['nf4_completed'] and x['local_completed'] for x in pairs),'rows':pairs})
    report={'models':models,'sources_sha256':hashes,'scope':'Known questions, matching prompts and greedy/repetition parameters. Compares entire HF NF4 and Ollama Q4_K_M deployments, not an isolated quantization experiment. Matching text is not a correctness score. Different frameworks, quantization and unresolved Q4 upstream tensor provenance remain confounds. No frozen final used.','product_release_approved':False}
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps([{k:v for k,v in x.items() if k!='rows'} for x in models]))
if __name__=='__main__':main()
