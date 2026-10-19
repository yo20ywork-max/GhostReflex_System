"""Supplemental defect audit; never edits locked prompts, tests, or gate scores."""
import ast,hashlib,json,random,re,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent
def main():
    output=R/'INTERSECTION_ORACLE_AUDIT.json'
    if output.exists():raise FileExistsError(output)
    rid='v2-oci-56dfe2003494e8568b12868885a6b347'
    row=next(x for x in map(json.loads,(R/'dev.jsonl').read_text(encoding='utf8').splitlines()) if x['id']==rid)
    rng=random.Random(20260906)
    pairs=[([1,2,2,3,4],[2,3,5]),([1,1,2,2],[2,2,3,3]),([],[])]
    pairs.extend(([rng.randrange(-30,31) for _ in range(rng.randrange(30))],[rng.randrange(-30,31) for _ in range(rng.randrange(30))]) for _ in range(100))
    tests=[{'args':[left,right],'expected':[True,sorted(set(left)&set(right)),len(set(left)&set(right))]} for left,right in pairs]
    sources={'locked_reference':row['answer']}
    for name in ('local-base-dev.jsonl','local-base-repeat1-dev.jsonl','local-epoch1-dev.jsonl','local-epoch1-repeat1-dev.jsonl','local-epoch2-dev.jsonl'):
        sources[name]=next(x['text'] for x in map(json.loads,(R/name).read_text(encoding='utf8').splitlines()) if x['id']==rid)
    records=[]
    for name,raw in sources.items():
        code=raw.strip();match=re.fullmatch(r'```(?:python)?\s*\n(.*?)\n```',code,re.S)
        if match:code=match.group(1)
        try:
            tree=ast.parse(code);definitions=[x for x in tree.body if isinstance(x,(ast.FunctionDef,ast.Import,ast.ImportFrom))]
            functions=[x.name for x in definitions if isinstance(x,ast.FunctionDef)];function=row['oracle']['function']
            if function not in functions and len(functions)==1:function=functions[0]
            clean=ast.unparse(ast.Module(body=definitions,type_ignores=[]))
            wrapped=clean+'\n\ndef verify_intersection(left, right):\n    value = '+function+'(left, right)\n    return [isinstance(value, list), sorted(value), len(value)]\n'
            payload={'code':wrapped,'function':'verify_intersection','tests':tests}
            proc=subprocess.run([sys.executable,'-I',str(R/'code_extended_audit.py'),'--worker'],input=json.dumps(payload),text=True,encoding='utf8',capture_output=True,timeout=3)
            result=json.loads(proc.stdout)
        except Exception as exc:result={'passed':False,'error':str(exc)}
        records.append({'source':name,'text_sha256':hashlib.sha256(raw.encode()).hexdigest(),**result})
    report={'row_id':rid,'prompt_sha256':hashlib.sha256(row['prompt'].encode()).hexdigest(),'locked_oracle':row['oracle'],'supplemental_tests':tests,'results':records,'scope':'Known-development oracle defect audit. Prompt sample deduplicates intersection and explicitly permits any order; locked reference retains duplicates and locked comparator imposes order. Original data and original gate scores retained. Not unseen generalization or release qualification.','original_gate_scores_unchanged':True,'product_release_approved':False}
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(records))
if __name__=='__main__':main()
