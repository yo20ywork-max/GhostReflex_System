"""Read-only full-data audit using the actual assistant-only tokenizer.

Metadata stays in the audit report; only system/prompt/answer become tokens.
This measures composition, not model quality or permission to launch training.
"""
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[2]
R = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    start = time.monotonic()
    candidate = R / 'candidate-v1'
    receipt = candidate / 'FULL_DATA_AUDIT.json'
    if receipt.exists():
        raise FileExistsError(receipt)
    preparation = json.loads((candidate / 'PREPARATION.json').read_text(encoding='utf8'))
    for name, expected in preparation['data_hashes'].items():
        assert sha(candidate / name) == expected, name
    trainer_path = ROOT / 'finetuning/release_v12/train.py'
    spec = importlib.util.spec_from_file_location('locked_v12_tokenizer', trainer_path)
    trainer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trainer)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        str(ROOT / 'finetuning/release_v12/artifacts/outputs/epoch-3'),
        local_files_only=True, trust_remote_code=False)
    sets, statistics, provenance = {}, {}, {}
    issues = []
    for split in ('train', 'dev'):
        path = candidate / (split + '.jsonl')
        rows = list(map(json.loads, path.read_text(encoding='utf8').splitlines()))
        sets[split] = rows
        assert len({r['id'] for r in rows}) == len(rows)
        categories = defaultdict(Counter)
        keyed_answers = defaultdict(set)
        token_rows = []
        for row in rows:
            encoded = trainer.tokenize_row(tokenizer, row, 12288)
            poisoned = trainer.tokenize_row(tokenizer, {
                **row, 'source': 'AUDIT_ONLY_SOURCE', 'attribution': 'NEVER_TOKENIZE',
                'license': 'AUDIT_ONLY_LICENSE', 'oracle': {'answer': 'DO_NOT_USE'},
            }, 12288)
            assert encoded['ids'] == poisoned['ids'] and encoded['labels'] == poisoned['labels'], row['id']
            assert all(t == -100 for t in encoded['labels'][:encoded['prefix']])
            assert encoded['labels'][encoded['prefix']:] == encoded['ids'][encoded['prefix']:]
            total, answer = len(encoded['ids']), len(encoded['ids']) - encoded['prefix']
            values = categories[row['category']]
            values.update(rows=1, total_tokens=total, answer_tokens=answer)
            values['max_tokens'] = max(values['max_tokens'], total)
            keyed_answers[(row['system'], row['prompt'])].add(row['answer'])
            token_rows.append({'id': row['id'], 'category': row['category'],
                               'total_tokens': total, 'answer_tokens': answer})
        conflicts = [hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()
                     for key, answers in keyed_answers.items() if len(answers) > 1]
        if conflicts:
            issues.append({'split': split, 'conflicting_input_hashes': conflicts})
        for category, values in categories.items():
            group = [r for r in rows if r['category'] == category]
            values['unique_prompts'] = len({r['prompt'] for r in group})
            values['unique_conversations'] = len({(r['system'], r['prompt'], r['answer']) for r in group})
        statistics[split] = {name: dict(values) for name, values in categories.items()}
        provenance[split] = token_rows
        print(json.dumps({'split': split, 'rows': len(rows), 'metadata_isolation_verified': True}), flush=True)
    overlap = {r['prompt'].strip() for r in sets['train']} & {r['prompt'].strip() for r in sets['dev']}
    if overlap:
        issues.append({'exact_train_dev_prompt_overlap': len(overlap)})
    identity = [r for r in sets['train'] if r['category'] == 'identity']
    report = {
        'data_hashes': {name: sha(candidate / name) for name in preparation['data_hashes']},
        'trainer_sha256': sha(trainer_path), 'auditor_sha256': sha(Path(__file__)),
        'statistics': statistics, 'row_token_counts': provenance, 'issues': issues,
        'exact_train_dev_prompt_overlap': len(overlap),
        'identity_rows': len(identity), 'identity_unique_questions': len({r['prompt'] for r in identity}),
        'identity_system_without_product_facts': sum('CrossGen-AGI-μ' not in r['system'] for r in identity),
        'all_rows_assistant_only_mask_and_metadata_invariance_verified': True,
        'mechanical_audit_passed': not issues, 'semantic_data_review_complete': False,
        'loss_weighting_note': 'The existing trainer averages loss per example and then per real batch. Token totals describe workload; they are not the category loss weights.',
        'limits': ['Exact prompt separation does not establish semantic independence.',
                   'Template variants do not count as new independent knowledge.',
                   'No model training or release acceptance is implied.'],
        'training_ready': False, 'training_started': False, 'release_approved': False,
        'seconds': time.monotonic() - start,
    }
    with receipt.open('x', encoding='utf8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k not in ('row_token_counts',)}, ensure_ascii=False))
    if issues:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
