"""Freeze the complete next training bundle; no GPU allocation or model download."""
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
OLD = R.parent / 'release_v12'
DEST = R.parent / 'release_v13/bundle-v1'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    return json.loads(p.read_text(encoding='utf8'))


def rows(p):
    return list(map(json.loads, p.read_text(encoding='utf8').splitlines()))


def write(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def main():
    if DEST.exists():
        raise FileExistsError(DEST)
    old_lock = read(OLD / 'DATA_LOCK.json')
    assert all(sha(OLD / n) == digest for n, digest in old_lock['sha256'].items())
    original = rows(OLD / 'train.jsonl')
    candidate = R / 'candidate-v1'
    for name, digest in read(candidate / 'PREPARATION.json')['data_hashes'].items():
        assert sha(candidate / name) == digest
    previous_audit = read(candidate / 'FULL_DATA_AUDIT.json')
    assert previous_audit['mechanical_audit_passed']
    assert previous_audit['data_hashes']['train.jsonl'] == sha(candidate / 'train.jsonl')
    train = rows(candidate / 'train.jsonl')
    assert train[:len(original)] == original
    additions = []
    source_paths = [Path(__file__), candidate / 'train.jsonl', candidate / 'PREPARATION.json',
                    candidate / 'FULL_DATA_AUDIT.json', OLD / 'DATA_LOCK.json']
    for kind in ('action', 'history'):
        folder = R / (kind + '-additions-v1')
        prep = read(folder / 'PREPARATION.json')
        assert sha(folder / 'additions.jsonl') == prep['data_sha256']
        extra = rows(folder / 'additions.jsonl')
        additions.extend(extra)
        source_paths += [folder / 'additions.jsonl', folder / 'PREPARATION.json']
        if kind == 'action':
            for name in ('FILE_EXECUTION_CONTROLS.json', 'BROWSER_EXECUTION_CONTROLS.json', 'TOKENIZATION.json'):
                report = read(folder / name)
                assert report['data_sha256'] == prep['data_sha256']
                if 'CONTROLS' in name:
                    assert report['all_passed']
                source_paths.append(folder / name)
    train += additions
    dev = rows(candidate / 'dev.jsonl')
    assert dev == rows(OLD / 'dev.jsonl')
    assert len(train) == 1799 and len(dev) == 385
    for key in ('id', 'prompt', 'group'):
        assert not {r[key] for r in train} & {r[key] for r in dev}, key
    assert len({r['id'] for r in train}) == len(train)
    assert len({(r['system'], r['prompt']) for r in train}) == len(train)
    # Rebuild the active desktop contract, rather than trusting old prose.
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(R.parent / 'contract_v8'))
    from desktop_contract import contract
    catalog, schema, planner_prompt, contract_sources = contract(max_plan_steps=24)
    assert {'catalog': catalog, 'schema': schema} == read(OLD / 'training-contract.json')
    planner_system = planner_prompt(SimpleNamespace(catalog=catalog, schema=schema))
    from jsonschema import Draft202012Validator
    validator = Draft202012Validator(schema)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(OLD / 'artifacts/outputs/epoch-3'), local_files_only=True, trust_remote_code=False)
    spec = importlib.util.spec_from_file_location('release_tokenizer', OLD / 'train.py')
    trainer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trainer)
    stats = {}
    for split, data in [('train', train), ('dev', dev)]:
        total = answer_total = maximum = plan_count = 0
        for row in data:
            value = None
            try:
                value = json.loads(row['answer'])
            except ValueError:
                pass
            if isinstance(value, dict) and set(value) == {'objective', 'assumptions', 'steps', 'completion_criteria'}:
                validator.validate(value)
                assert row['system'] == planner_system, row['id']
                plan_count += 1
            encoded = trainer.tokenize_row(tokenizer, row, 12288)
            changed = trainer.tokenize_row(tokenizer, {**row, 'source': 'NOT_A_MESSAGE', 'license': 'NOT_A_MESSAGE', 'attribution': 'NOT_A_MESSAGE'}, 12288)
            assert encoded['ids'] == changed['ids'] and encoded['labels'] == changed['labels'], row['id']
            prefix = encoded['prefix']
            assert all(v == -100 for v in encoded['labels'][:prefix])
            assert encoded['labels'][prefix:] == encoded['ids'][prefix:]
            for field in ('system', 'prompt', 'answer'):
                assert tokenizer.decode(tokenizer.encode(row[field], add_special_tokens=False), clean_up_tokenization_spaces=False) == row[field]
            total += len(encoded['ids'])
            answer_total += len(encoded['ids']) - prefix
            maximum = max(maximum, len(encoded['ids']))
        stats[split] = {'rows': len(data), 'categories': dict(Counter(r['category'] for r in data)),
                        'total_tokens': total, 'answer_tokens': answer_total, 'max_tokens': maximum,
                        'plans_checked_against_actual_contract': plan_count}
        print(json.dumps({'split': split, **stats[split]}), flush=True)
    # All previously validated production engine files remain byte-identical.
    trainer_names = ['train.py', 'train_distributed.py', 'distributed_engine.py', 'distributed_update.py',
                     'answer_loss.py', 'cloud_entry.py', 'launch_guard.py', 'requirements-cloud.txt']
    runtime_names = ['run_daemon.py', 'product_identity.py', 'model_json.py', 'product_tools.py',
                     'verified_copy.py', 'desktop_session.py', 'explicit_reply.py', 'PROJECT_GOALS.md', 'COMPANY_PROFILE.json']
    source_paths += [OLD / n for n in trainer_names] + [ROOT / n for n in runtime_names]
    source_paths += [OLD / 'RELEASE_GATES.json', OLD / 'RUN_AUTHORIZATION.json']
    source_hashes = {str(p.relative_to(ROOT)): sha(p) for p in source_paths}
    DEST.mkdir(parents=True)
    for split, data in [('train', train), ('dev', dev)]:
        (DEST / (split + '.jsonl')).write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in data), encoding='utf8')
    for name in trainer_names:
        (DEST / name).write_bytes((OLD / name).read_bytes())
    for name in runtime_names:
        (DEST / ('runtime_source.py' if name == 'run_daemon.py' else name)).write_bytes((ROOT / name).read_bytes())
    for name in ['RELEASE_GATES.json', 'RUN_AUTHORIZATION.json', 'brand-dev.jsonl',
                 'locale-internal-notice.json', 'INTERNAL_METADATA.json',
                 'DISTRIBUTED_ENGINE_VERIFIED_V2.json', 'PEFT_DISTRIBUTED_VERIFIED.json']:
        (DEST / name).write_bytes((OLD / name).read_bytes())
    (DEST / 'brand-train.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in train if r['category'] == 'identity'), encoding='utf8')
    write(DEST / 'training-contract.json', {'catalog': catalog, 'schema': schema})
    write(DEST / 'history-sources.json', read(R / 'history-additions-v1/PREPARATION.json'))
    write(DEST / 'ADDITIONAL_RELEASE_REQUIREMENTS.json', {
        'source': 'PROJECT_GOALS.md persistent user requirements; original RELEASE_GATES.json unchanged',
        'neutral_weight_identity': {'cases': 16, 'required_pass': 16, 'system_excludes_product_facts': True,
            'package_default_is_separate': True, 'require_upstream_mention': False},
        'full_request_wait_order': 'Check observed order against original requests; final result alone cannot erase premature reads.',
        'missing_or_untested_is_not_pass': True, 'release_approved': False})
    cfg = read(OLD / 'config.json')
    cfg['draft_notes'] = {
        'initialization': 'Fresh rank32 adapter on the same pinned original base; no reuse of failed adapters.',
        'data': 'All original1633 training rows preserved; 88 uncued identity,28 action contrasts,50 history/quotation contrasts added.',
        'optimizer_choice': 'Same learning rate2e-5, rank32, global batch8 and3 full epochs as prior run, to measure this data revision without simultaneous optimizer changes.',
        'limitations': 'Local data readiness only. New full-size GPU preflight, trained artifacts and all release gates remain unproven.'}
    cfg['release_status'] = 'prepared_not_trained'
    write(DEST / 'config.json', cfg)
    write(DEST / 'LAUNCH_STATUS.json', {'launch_allowed': False, 'temporary_storage_user_approved': True,
        'reason': 'Awaiting binding to an available pod, current quote, deadline and exact launch lock; existing user authorization persists.', 'training_started': False})
    write(DEST / 'DATA_AUDIT.json', {'stats': stats, 'source_hashes': source_hashes,
        'original_1633_rows_preserved_exactly': True, 'original_dev_preserved_exactly': True,
        'original_release_gates_preserved_exactly': sha(DEST / 'RELEASE_GATES.json') == sha(OLD / 'RELEASE_GATES.json'),
        'tokenizer_and_mask_verified': True, 'metadata_token_invariance_verified': True,
        'exact_train_dev_id_prompt_group_separation': True, 'planner_contract_aligned': True,
        'contract_sources': contract_sources, 'source_metadata_separate': True,
        'data_review_scope': 'All new authored questions/answers reviewed; original data retained under previous lock, not newly independently relabeled. Topic overlap with known development disclosed.',
        'new_history_quote_rows_intentionally_not_fact_corrections': 4,
        'final_holdout_read': False, 'training_started': False, 'release_approved': False})
    assert all(sha(ROOT / n) == digest for n, digest in source_hashes.items())
    write(DEST / 'DATA_LOCK.json', {'sha256': {p.name: sha(p) for p in DEST.iterdir() if p.is_file()}, 'release_approved': False})
    script = "import runpy,sys;sys.path.insert(0,'.');sys.modules['torch']=None;sys.modules['transformers']=None;sys.argv=['train_distributed.py','--preflight-only'];runpy.run_path('train_distributed.py',run_name='__main__')"
    check = subprocess.run([sys.executable, '-X', 'utf8', '-c', script], cwd=DEST, capture_output=True, text=True, encoding='utf8', timeout=20)
    assert check.returncode == 1 and 'Training launch disabled' in check.stderr, check.stderr
    assert not (DEST / 'outputs').exists()
    assert all(sha(DEST / n) == digest for n, digest in read(DEST / 'DATA_LOCK.json')['sha256'].items())
    receipt = {'bundle': str(DEST.relative_to(ROOT)), 'lock_sha256': sha(DEST / 'DATA_LOCK.json'),
        'lock_verified': True, 'local_bytes': sum(p.stat().st_size for p in DEST.iterdir() if p.is_file()),
        'planned_optimizer_steps': math.ceil(len(train) / cfg['gradient_accumulation']) * cfg['epochs'],
        'stats': stats, 'launch_blocked_before_model_imports': True, 'cloud_storage_already_authorized': True,
        'gpu_preflight_passed': False, 'training_started': False, 'release_approved': False}
    write(DEST.parent / 'PREPARATION_RECEIPT.json', receipt)
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
