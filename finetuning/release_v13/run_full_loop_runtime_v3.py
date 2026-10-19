"""Run the unchanged original 12 file/DOM oracles with the desktop catalog.

All case bodies and outcome predicates remain in the original v4 evaluator.
Only its catalog loader is extended to match the product's registered tools.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

R=Path(__file__).resolve().parent
ROOT=R.parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(R.parent/'contract_v8'))
from desktop_contract import contract,extend_scope
from desktop_session import install as install_desktop_guard
from explicit_reply import install_reply_completion_guard
from types import SimpleNamespace


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf8'))
def rows(p):return [json.loads(x) for x in p.read_text(encoding='utf8').splitlines()]
def dump(p,v):
    with p.open('x',encoding='utf8') as f:json.dump(v,f,ensure_ascii=False,indent=2)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--results',required=True);parser.add_argument('--validate-only',action='store_true');args=parser.parse_args()
    if Path(args.results).name!=args.results:raise ValueError('Local result filename required')
    folder=R/'evaluation-runtime-v3';source=folder/args.results
    generation=read(source.with_suffix('.generation-complete.json'));manifest=read(source.with_suffix('.manifest.json'))
    assert generation['model_and_sources_unchanged'] and generation['results_sha256']==sha(source)
    assert all(sha(ROOT/n)==h for n,h in manifest['sources'].items())
    cases=rows(folder/'cases.jsonl');results=rows(source)
    assert [r['id'] for r in cases]==[r['id'] for r in results]
    selected=[r for r in cases if r['suite']=='core' and r['category'] in ('recovery','negation')]
    assert len(selected)==12
    ids={r['id'] for r in selected};seeds=[r for r in results if r['id'] in ids]
    assert len({r['model_digest'] for r in seeds})==1
    for row in selected:
        assert row['system']==row['gateway_system']
    catalog,schema,_,_=contract(max_plan_steps=24)
    locked=read(R/'training-contract.json')
    assert catalog==locked['catalog'] and schema==locked['schema'],'Desktop contract drift'
    original=R.parent/'release_v4/execute_full_plan_fixtures.py'
    spec=importlib.util.spec_from_file_location('v13_original_full_loop',original)
    legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
    old_load=legacy.load
    def desktop_load(path):
        scope,digest=old_load(path)
        # The AST core loader cannot supply plugin handlers; register those
        # through product_tools instead of retaining a placeholder None.
        extend_scope(scope,[item for item in catalog if item['name']!='COPY_FILE_VERIFIED'])
        install_desktop_guard(SimpleNamespace(**scope))
        install_reply_completion_guard(scope['Planner'])
        return scope,digest
    legacy.load=desktop_load
    # The legacy closed_loop imports this function lazily. desktop_contract
    # already holds the original core implementation, so there is no recursion.
    import build_product_data
    original_contract=build_product_data.contract
    build_product_data.contract=contract
    extra=[Path(__file__),R/'training-contract.json',R.parent/'contract_v8/desktop_contract.py',
        ROOT/'product_tools.py',ROOT/'verified_copy.py',ROOT/'explicit_reply.py',ROOT/'desktop_session.py',
        ROOT/'step_conditions.py',ROOT/'argument_references.py',ROOT/'completion_verification.py',ROOT/'path_metadata.py']
    hashes={str(p.relative_to(ROOT)):sha(p) for p in extra}
    if args.validate_only:
        scope,_=desktop_load(str((R/'training-contract.json').resolve()))
        assert len(scope['TOOL_REGISTRY'])==len(catalog)==48
        assert all(callable(scope['TOOL_REGISTRY'][n].handler) for n in legacy.ALLOWED|{'FINAL_RESPONSE','BLOCKED','COPY_FILE_VERIFIED'})
        print(json.dumps({'cases':12,'catalog_tools':48,'unchanged_oracle_sha256':sha(original),'fixture_executed':False}))
        return
    dest=folder/(source.stem+'.full-loop')
    dest.mkdir(exist_ok=False)
    data=dest/'cases.jsonl';seed=dest/'seed-results.jsonl';contract_path=dest/'contract.json';output=dest/'result.json'
    data.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in selected),encoding='utf8')
    seed.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in seeds),encoding='utf8')
    dump(contract_path,{'catalog':catalog,'schema':schema})
    model=seeds[0]['candidate']
    dump(dest/'protocol.json',{'original_evaluator_sha256':sha(original),'generation_sha256':sha(source),
        'extra_sources':hashes,'original_case_oracles_unchanged':True,'catalog_tools':48,
        'native_desktop_test':False,'release_approved':False})
    old_argv=sys.argv
    try:
        sys.argv=[str(original),'--results',str(seed.resolve()),'--data',str(data.resolve()),'--contract',str(contract_path.resolve()),
            '--output',str(output.resolve()),'--full-loop','--model',model,'--stress-list-limit']
        legacy.main()
    finally:
        sys.argv=old_argv;build_product_data.contract=original_contract
    assert all(sha(ROOT/n)==h for n,h in hashes.items()),'Mixed desktop source run'
    review_path=R.parent/'release_v4/review_full_loop.py'
    spec=importlib.util.spec_from_file_location('v13_original_full_review',review_path)
    review=importlib.util.module_from_spec(spec);spec.loader.exec_module(review)
    report=review.summarize(read(output));report.update(result_sha256=sha(output),extra_sources_unchanged=True)
    dump(dest/'joint-review.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='records'},ensure_ascii=False))


if __name__=='__main__':main()
