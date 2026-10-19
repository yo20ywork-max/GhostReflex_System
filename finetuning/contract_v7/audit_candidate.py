"""Supplemental, fail-closed local data audit; no inference or cloud calls."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import unicodedata

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = HERE.parent / 'release_v4'


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    args = argparse.ArgumentParser()
    args.add_argument('--candidate', required=True)
    args.add_argument('--output', required=True)
    args = args.parse_args()
    if any(Path(x).name != x for x in (args.candidate, args.output)):
        raise ValueError('Use local names only')
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(OLD/'artifacts/outputs/epoch-3', local_files_only=True, trust_remote_code=False)
    candidate = HERE / args.candidate
    manifest = json.loads((candidate/'manifest.json').read_text(encoding='utf8'))
    failures = []
    stats = {}
    system_updates = []
    for split in ('train', 'dev'):
        originals = {r['id']: r for r in rows(OLD/(split+'.jsonl'))}
        maximum = Counter()
        retention = Counter()
        checked = 0
        for row in rows(candidate/(split+'.jsonl')):
            for field in ('system', 'prompt', 'answer'):
                value = row[field]
                decoded = tokenizer.decode(tokenizer.encode(value, add_special_tokens=False), skip_special_tokens=False, clean_up_tokenization_spaces=False)
                checked += 1
                if decoded != value:
                    failures.append({'id': row['id'], 'field': field, 'issue': 'tokenizer_roundtrip'})
            kind = row.get('oracle', {}).get('type')
            if kind in ('plan', 'actual_teacher_file_copy', 'completion'):
                length = len(tokenizer.encode(row['answer'], add_special_tokens=False)) + 2
                maximum[kind] = max(maximum[kind], length)
                if length > 2048:
                    failures.append({'id': row['id'], 'issue': 'output_budget'})
            original = originals.get(row['id'])
            if original and row['category'] in ('code', 'literal'):
                retention[row['category']] += 1
                fields = ('system', 'prompt', 'answer') if row['category'] == 'code' else ('prompt', 'answer')
                if any(row[k] != original[k] for k in fields):
                    failures.append({'id': row['id'], 'issue': 'retention_changed'})
                if row['category'] == 'literal' and row['system'] != original['system']:
                    if kind != 'plan':
                        failures.append({'id': row['id'], 'issue': 'unexpected_literal_system_change'})
                    system_updates.append(row['id'])
        stats[split] = {'text_fields_checked': checked, 'retention_counts': dict(retention), 'structured_answer_max_with_two_end_tokens': dict(maximum)}
    for name, digest in manifest['sources'].items():
        if sha(ROOT/name) != digest:
            failures.append({'source': name, 'issue': 'source_changed'})
    for name, digest in manifest['output_sha256'].items():
        if sha(candidate/name) != digest:
            failures.append({'source': name, 'issue': 'export_changed'})
    original_failures = []
    for split in ('train', 'dev'):
        for row in rows(HERE/'candidate-data-v1'/(split+'.jsonl')):
            for field in ('system', 'prompt', 'answer'):
                value = row[field]
                decoded = tokenizer.decode(tokenizer.encode(value, add_special_tokens=False), skip_special_tokens=False, clean_up_tokenization_spaces=False)
                if decoded != value:
                    original_failures.append({'id': row['id'], 'field': field, 'difference_exactly_nfc': decoded == unicodedata.normalize('NFC', value)})
    catalog = json.loads((candidate/'training-contract.json').read_text(encoding='utf8'))['catalog']
    report = {
        'candidate': args.candidate, 'stats': stats, 'failures': failures,
        'literal_plan_system_updates': system_updates,
        'prior_candidate_tokenizer_failures': original_failures,
        'tokenizer_normalizer': str(tokenizer.backend_tokenizer.normalizer),
        'data_audit_passed': not failures,
        'core_catalog_has_verified_copy': any(x['name'] == 'COPY_FILE_VERIFIED' for x in catalog),
        'full_qt_product_catalog_aligned': False,
        'remaining_before_paid_training': [
            'Align actual Qt COPY_FILE_VERIFIED catalog and validate representative real copy episodes.',
            'Complete training configuration, GPU/context/memory preflight and bounded cloud cost plan.',
            'Review dataset quality beyond the five authored filesystem families; retain original identity, history, ASR and code gates.'
        ],
        'actual_model_quality_measured': False, 'training_started': False, 'release_approved': False,
        'sources': {'audit_candidate.py': sha(Path(__file__)), 'candidate_manifest': sha(candidate/'manifest.json')},
    }
    with (HERE/args.output).open('x', encoding='utf8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: report[k] for k in ('candidate', 'stats', 'failures', 'data_audit_passed', 'training_started', 'release_approved')}, ensure_ascii=True))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
