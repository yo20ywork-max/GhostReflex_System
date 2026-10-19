"""Preserve all candidate records; add the legacy scorer's candidate alias."""
import argparse
import hashlib
import json
from pathlib import Path
from evaluate_development import R,inputs


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--results',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if any(Path(x).name!=x for x in [args.results,args.output]):raise ValueError('Use local file names')
    source=R/args.results;target=R/args.output
    receipt=target.with_suffix('.provenance.json')
    if target.exists() or receipt.exists():raise FileExistsError('Preserve prior functional input')
    marker=json.loads(source.with_suffix('.generation-complete.json').read_text(encoding='utf8'))
    if marker['model_and_sources_unchanged'] is not True or marker['results_sha256']!=sha(source):raise ValueError('Unverified generation')
    data,_,_,_=inputs();rows=[json.loads(x) for x in source.read_text(encoding='utf8').splitlines()]
    if len(rows)!=105 or {r['id'] for r in rows}!={r['id'] for r in data} or len({r['model_digest'] for r in rows})!=1:raise ValueError('Incomplete/mixed results')
    output=[]
    for row in rows:
        if 'candidate' in row:raise ValueError('Source already has candidate field')
        output.append({**row,'candidate':row['model']})
    with target.open('x',encoding='utf8') as stream:
        for row in output:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    reread=[json.loads(x) for x in target.read_text(encoding='utf8').splitlines()]
    if any({k:v for k,v in b.items() if k!='candidate'}!=a or b['candidate']!=a['model'] for a,b in zip(rows,reread)) or len(reread)!=len(rows):
        raise ValueError('Functional compatibility transformation changed original fields')
    record={'original_results_sha256':sha(source),'functional_input_sha256':sha(target),'rows':len(rows),
            'transformation':'Add candidate=model; all original keys and values preserved. Same transformation as baseline.',
            'source_sha256':sha(Path(__file__)),'audit_source_sha256':sha(R.parent/'release_v3/code_extended_audit.py')}
    with receipt.open('x',encoding='utf8') as stream:json.dump(record,stream,indent=2)
    print(json.dumps(record))


if __name__=='__main__':main()
