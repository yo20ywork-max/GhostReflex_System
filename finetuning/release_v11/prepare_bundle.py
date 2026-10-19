"""Audited local-only integration of desktop, brand, history and evidence data."""
import collections
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'finetuning/contract_v8'))
from desktop_contract import contract
from product_identity import GENERATION_SYSTEM, generation_system
from jsonschema import Draft202012Validator


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf8'))
def rows(path):return [json.loads(x) for x in path.read_text(encoding='utf8').splitlines()]
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')


def main():
    dest=HERE/'bundle-v3'
    if dest.exists():raise FileExistsError(dest)
    brand=ROOT/'finetuning/identity_v10/candidate-v2'
    hist=ROOT/'finetuning/history_v9/draft-v1'
    evidence=ROOT/'finetuning/identity_v10/evidence-draft-v1'
    locale=ROOT/'finetuning/locale_v12/candidate-v2'
    old=ROOT/'finetuning/contract_v8/training-bundle-v1'
    source_paths=[Path(__file__),HERE/'launch_guard.py',ROOT/'COMPANY_PROFILE.json',ROOT/'PROJECT_GOALS.md',ROOT/'product_identity.py']
    company=read(ROOT/'COMPANY_PROFILE.json')
    if company['employee_count_accepted_wordings']!=['暫不公開','尚未核定']:raise ValueError('Company wording policy changed; review required')
    if company['establishment_approval_date']!='2026-08-10' or company['employee_count'] is not None:raise ValueError('Company fact change needs explicit data revision')
    historical_profile_changes=[]
    for folder in (brand,):
        m=read(folder/'manifest.json')
        for name,digest in m['output_sha256'].items():
            if sha(folder/name)!=digest:raise ValueError('Candidate changed: '+name)
        for name,digest in m['sources'].items():
            if sha(ROOT/name)!=digest:
                # Only this user-authorized policy amendment may differ from
                # the previous company's source snapshot. Data stays locked.
                if Path(name).as_posix()!='COMPANY_PROFILE.json':raise ValueError('Candidate source changed: '+name)
                historical_profile_changes.append(dict(path=name,old_sha256=digest,new_sha256=sha(ROOT/name),reason='User accepts 尚未核定 in addition to 暫不公開'))
    for folder in (ROOT/'finetuning/release_v4',old):
        lock=read(folder/'DATA_LOCK.json')
        for name,digest in lock['sha256'].items():
            if sha(folder/name)!=digest:raise ValueError('Historical lock changed: '+str(folder/name))
    # Explicit snapshot revalidation: evidence's system predates new company
    # facts and will be migrated, but its original prompts/answers are retained.
    em=read(evidence/'manifest.json')
    for name,digest in em['outputs'].items():
        if sha(evidence/name)!=digest:raise ValueError('Evidence rows changed')
    lm=read(locale/'manifest.json')
    for name,digest in lm['outputs'].items():
        if sha(locale/name)!=digest:raise ValueError('Locale candidate changed: '+name)
    for name,digest in lm['sources'].items():
        if sha(ROOT/name)!=digest:raise ValueError('Locale source changed: '+name)
    if not lm['actual_tokenizer_metadata_invariance_verified']:raise ValueError('Locale metadata isolation not verified')
    for folder in (brand,hist,evidence,locale):
        source_paths.extend(folder/name for name in ('train.jsonl','dev.jsonl','manifest.json'))
    source_paths.extend([locale/'INTERNAL_METADATA.json',locale/'CHANGES.json',locale.parent/'draft-v1/ATTRIBUTION.json'])
    source_paths.extend([hist/'sources.json',old/'train.py',old/'answer_loss.py',old/'DATA_LOCK.json',brand/'RELEASE_GATES.json'])
    datasets={};changes=[];retention={};internal_metadata={}
    for split in ('train','dev'):
        base=rows(brand/(split+'.jsonl'))
        added=[]
        for folder in (hist,evidence):
            for original in rows(folder/(split+'.jsonl')):
                row=copy.deepcopy(original)
                row['system']=generation_system(original['system']) if folder==hist else GENERATION_SYSTEM
                changes.append({'id':row['id'],'change':'system aligned with current product facts; question and answer retained'})
                added.append(row)
        datasets[split]=base+added+rows(locale/(split+'.jsonl'))
        for row in datasets[split]:
            metadata={key:row.pop(key) for key in ('source','attribution','license') if key in row}
            if metadata:internal_metadata[row['id']]=metadata
        retention[split]=dict(collections.Counter(r['category'] for r in base if r['category'] in ('code','literal')))
    for split,data in datasets.items():
        for key in ('id',):
            if len({r[key] for r in data})!=len(data):raise ValueError('Duplicate '+key)
        if len({(r['system'],r['prompt']) for r in data})!=len(data):raise ValueError('Duplicate input')
    for key in ('id','prompt','group'):
        if {r[key] for r in datasets['train']}&{r[key] for r in datasets['dev']}:raise ValueError('Split overlap: '+key)
    catalog,schema,planner_prompt,contract_sources=contract(max_plan_steps=24)
    validator=Draft202012Validator(schema)
    expected_planner=planner_prompt(SimpleNamespace(catalog=catalog,schema=schema))
    from transformers import AutoTokenizer
    tokdir=ROOT/'finetuning/release_v4/artifacts/outputs/epoch-3'
    tokenizer=AutoTokenizer.from_pretrained(tokdir,local_files_only=True,trust_remote_code=False)
    spec=importlib.util.spec_from_file_location('v11_trainer',old/'train.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    stats={}
    for split,data in datasets.items():
        lengths=[];structured=[]
        for row in data:
            if type(row.get('retain')) is not bool:raise ValueError('retain must be boolean')
            for field in ('system','prompt','answer'):
                value=row[field]
                if tokenizer.decode(tokenizer.encode(value,add_special_tokens=False),clean_up_tokenization_spaces=False)!=value:raise ValueError('Unicode changed: '+row['id'])
            kind=row['oracle']['type']
            if kind in ('plan','actual_teacher_file_copy'):
                validator.validate(json.loads(row['answer']))
                if row['system']!=expected_planner:raise ValueError('Planner system mismatch: '+row['id'])
            if kind in ('plan','actual_teacher_file_copy','completion'):
                count=len(tokenizer.encode(row['answer'],add_special_tokens=False))+2
                if count>2048:raise ValueError('Structured output too long')
                structured.append(count)
            if row['category']=='identity':
                if row['system']!=GENERATION_SYSTEM:raise ValueError('Identity system mismatch')
                if any(t in (row['system']+row['prompt']+row['answer']).lower() for t in ('qwen','alibaba','阿里雲','底座','上游')):raise ValueError('Withdrawn identity reinforcement')
            encoded=helper.tokenize_row(tokenizer,row,12288);prefix=encoded['prefix']
            # Exercise the actual training tokenizer with changed metadata.
            # Task evidence already inside prompt/answer remains untouched.
            probe=dict(row,source='SOURCE_METADATA_NOT_MODEL_INPUT',attribution='EXTERNAL_IDENTITY_NOT_MODEL_INPUT',license='LICENSE_METADATA_NOT_MODEL_INPUT')
            probe_encoded=helper.tokenize_row(tokenizer,probe,12288)
            if any(encoded[k]!=probe_encoded[k] for k in ('ids','labels','prefix')):raise ValueError('Source metadata reached model tokens')
            if any(v!=-100 for v in encoded['labels'][:prefix]) or encoded['labels'][prefix:]!=encoded['ids'][prefix:]:raise ValueError('Assistant mask mismatch')
            lengths.append(len(encoded['ids']))
        stats[split]=dict(rows=len(data),categories=dict(collections.Counter(r['category'] for r in data)),max_tokens=max(lengths),total_tokens=sum(lengths),structured_max_tokens=max(structured),text_fields_verified=len(data)*3)
    runtime_files=('run_daemon.py','product_identity.py','model_json.py','product_tools.py','verified_copy.py','desktop_session.py','explicit_reply.py')
    source_paths.extend(ROOT/name for name in runtime_files)
    source_paths.extend([tokdir/'tokenizer.json',tokdir/'tokenizer_config.json',ROOT/'finetuning/release_v4/requirements-cloud.txt'])
    source_hashes={str(p.relative_to(ROOT)):sha(p) for p in source_paths}
    dest.mkdir()
    for split,data in datasets.items():
        (dest/(split+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in data),encoding='utf8')
    write(dest/'INTERNAL_METADATA.json',dict(use='Internal build/audit only; never include as training conversations or routine model answers',rows=internal_metadata,locale=read(locale/'INTERNAL_METADATA.json')))
    write(dest/'locale-internal-notice.json',read(locale.parent/'draft-v1/ATTRIBUTION.json'))
    for name in runtime_files:
        (dest/('runtime_source.py' if name=='run_daemon.py' else name)).write_bytes((ROOT/name).read_bytes())
    trainer=(old/'train.py').read_text(encoding='utf8')
    needle='    lock=verify_lock(args.lock)'
    if trainer.count(needle)!=1:raise ValueError('Unexpected trainer source')
    trainer=trainer.replace(needle,needle+"\n    from launch_guard import require_launch\n    require_launch(ROOT, lock, mode='preflight' if args.preflight_only else 'train')")
    (dest/'train.py').write_text(trainer,encoding='utf8')
    (dest/'answer_loss.py').write_bytes((old/'answer_loss.py').read_bytes())
    (dest/'launch_guard.py').write_bytes((HERE/'launch_guard.py').read_bytes())
    (dest/'requirements-cloud.txt').write_bytes((ROOT/'finetuning/release_v4/requirements-cloud.txt').read_bytes())
    (dest/'COMPANY_PROFILE.json').write_bytes((ROOT/'COMPANY_PROFILE.json').read_bytes())
    (dest/'history-sources.json').write_bytes((hist/'sources.json').read_bytes())
    for name in ('brand-train.jsonl','brand-dev.jsonl'):(dest/name).write_bytes((brand/name).read_bytes())
    write(dest/'training-contract.json',dict(catalog=catalog,schema=schema))
    gates=read(brand/'RELEASE_GATES.json');gates['version']='release-v11-bundle-v3'
    gates['development']['brand_identity']['employee_disclosure']={'preferred':'暫不公開','accepted':['暫不公開','尚未核定'],'guessed_counts_or_ranges_allowed':False}
    gates['supplemental_development']={'history_event_binding':{'cases':12,'required_pass':12},'evidence_availability':{'cases':12,'required_pass':12},'previous_condition_reference_copy_regressions':'Retained; see existing release evidence. No replacement with authored teacher scores.'}
    gates['supplemental_development']['contextual_taiwan_language']={'cases':24,'required_pass':24,'candidate':'locale_v12/candidate-v2','known_task_families_not_blind':True,'replaces_original_locale_or_asr_gates':False}
    write(dest/'RELEASE_GATES.json',gates)
    cfg=read(old/'config.json')
    cfg['draft_notes']['data']='Current desktop contract; user-corrected brand/company facts; historical binding; evidence-availability pairs; contextual Taiwan language/literal contrasts; previous code/literal rows preserved. Source identity/license metadata is separate from model tokens.'
    cfg['draft_notes']['limitations']='Local data audit only; no v11 GPU preflight, trained adapter or release evidence. New cloud storage permission is pending.'
    cfg['release_status']='prepared_not_trained'
    write(dest/'config.json',cfg)
    # Explicit launch block prevents this local package from being mistaken for
    # permission to allocate or train. Resolve in a newly versioned launch bundle.
    write(dest/'LAUNCH_STATUS.json',dict(launch_allowed=False,reason='Cloud temporary-storage clearance and bounded provider plan/preflight pending',training_started=False))
    write(dest/'DATA_AUDIT.json',dict(stats=stats,retention_counts=retention,source_hashes=source_hashes,system_changes=changes,historical_profile_changes=historical_profile_changes,
        current_desktop_contract_sources=contract_sources,catalog_tools=len(catalog),planner_system_aligned=True,
        identity_system_aligned=True,tokenizer_and_mask_verified=True,history_topics_overlap_known_development=True,
        evidence_patterns_known_not_blind=True,locale_patterns_known_not_blind=True,metadata_token_invariance_verified=True,
        external_source_metadata_stored_separately=True,final_holdout_read=False,training_started=False,release_approved=False))
    compile((dest/'train.py').read_text(encoding='utf8'),'train.py','exec')
    lock=dict(sha256={p.name:sha(p) for p in dest.iterdir() if p.is_file()},release_approved=False)
    write(dest/'DATA_LOCK.json',lock)
    if not all(sha(ROOT/n)==h for n,h in source_hashes.items()):raise RuntimeError('Sources changed during build')
    receipt=dict(bundle='bundle-v3',stats=stats,bytes=sum(p.stat().st_size for p in dest.iterdir()),
        planned_optimizer_steps=math.ceil(len(datasets['train'])/cfg['gradient_accumulation'])*cfg['epochs'],
        lock_sha256=sha(dest/'DATA_LOCK.json'),lock_verified=all(sha(dest/n)==h for n,h in lock['sha256'].items()),
        launch_allowed=False,gpu_preflight_passed=False,training_started=False,release_approved=False)
    write(HERE/'PREPARATION_RECEIPT_V3.json',receipt)
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':main()
