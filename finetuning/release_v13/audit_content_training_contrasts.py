"""Audit all paired data and the actual pinned tokenizer, without training."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from transformers import AutoTokenizer

R = Path(__file__).resolve().parent
D = R / 'training-candidate/content-contrasts-v3'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    target = D / 'DATA_TOKEN_AUDIT.json'
    assert not target.exists()
    prepared = json.loads((D / 'PREPARATION.json').read_text(encoding='utf8'))
    for name, digest in prepared['files'].items(): assert sha(D / name) == digest
    rows = [json.loads(l) for l in (D / 'rows.jsonl').read_text(encoding='utf8').splitlines()]
    sidecars = [json.loads(l) for l in (D / 'internal-validation.jsonl').read_text(encoding='utf8').splitlines()]
    assert len(rows) == len(sidecars) == 256
    config = json.loads((R / 'config.json').read_text())
    token_root = Path.home() / '.cache/huggingface/hub/models--Qwen--Qwen2.5-Coder-7B-Instruct/snapshots' / config['revision']
    tokenizer_sources = {str(p): sha(p) for p in token_root.iterdir() if p.name in ['tokenizer.json', 'tokenizer_config.json', 'vocab.json', 'merges.txt']}
    tokenizer = AutoTokenizer.from_pretrained(token_root, local_files_only=True, trust_remote_code=False)
    token_records = []
    forbidden_keys = {'correct', 'pair', 'validation', 'source_url', 'license', 'authored_synthetic_data', 'category'}

    def check_keys(value):
        if isinstance(value, dict):
            assert not forbidden_keys.intersection(value)
            for v in value.values(): check_keys(v)
        elif isinstance(value, list):
            for v in value: check_keys(v)

    for row, meta in zip(rows, sidecars):
        assert row['id'] == meta['id']
        assert set(row) == {'id', 'category', 'system', 'prompt', 'answer'}
        context, answer = json.loads(row['prompt']), json.loads(row['answer'])
        check_keys(context)
        artifact = context['semantic_artifacts'][0]
        original = artifact['sources'][0]['full_read']['text']
        output = artifact['output']['text']
        assert hashlib.sha256(original.encode('utf8')).hexdigest() == meta['source_sha256']
        assert hashlib.sha256(output.encode('utf8')).hexdigest() == meta['output_sha256']
        assert (answer['verdict'] == 'satisfied') is meta['correct']
        if row['category'] == 'content-facts':
            expected, actual = meta['validation']['source_facts'], meta['validation']['output_facts']
            assert all(v in original for v in expected.values())
            assert all(v in output for v in actual.values())
            differences = [key for key in expected if expected[key] != actual[key]]
            assert len(differences) == (0 if meta['correct'] else 1)
            if not meta['correct']:
                key = differences[0]
                assert expected[key] in answer['reason'] and actual[key] in answer['reason']
        if row['category'] == 'content-code':
            cases = meta['validation']['tested_integer_pairs']
            assert len(cases) == 20
            assert all(a == b for _, _, a, b in cases) is meta['correct']
        messages = [{'role': 'system', 'content': row['system']}, {'role': 'user', 'content': row['prompt']}]
        prefix = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
        full = tokenizer.apply_chat_template(messages + [{'role': 'assistant', 'content': row['answer']}], tokenize=True, add_generation_prompt=False)
        assert full[:len(prefix)] == prefix and len(prefix) < len(full) <= config['max_length']
        token_records.append({'id': row['id'], 'total_tokens': len(full), 'masked_prefix_tokens': len(prefix), 'answer_tokens': len(full) - len(prefix)})
    for positive, negative in zip(rows[::2], rows[1::2]):
        a, b = json.loads(positive['prompt']), json.loads(negative['prompt'])
        assert a['user_request'] == b['user_request']
        left, right = a['semantic_artifacts'][0], b['semantic_artifacts'][0]
        assert left['sources'] == right['sources'] and left['destination_path'] == right['destination_path']
        assert left['output']['text'] != right['output']['text']
    assert len({r['id'] for r in rows}) == 256
    assert len({(r['prompt'], r['answer']) for r in rows}) == 256
    assert all(sha(Path(p)) == h for p, h in tokenizer_sources.items())
    report = {'audited_utc': datetime.now(timezone.utc).isoformat(), 'rows': 256, 'pairs': 128,
        'tokenizer_revision': config['revision'], 'tokenizer_sources': tokenizer_sources,
        'token_records': token_records, 'max_tokens': max(r['total_tokens'] for r in token_records),
        'answer_only_mask_prefixes_verified': 256, 'no_truncation': True,
        'same_prompt_filenames_source_per_pair': True, 'all_factual_negative_differences_and_reasons_checked': True,
        'all_generated_code_20input_controls_checked': True,
        'metadata_not_in_training_context': True,
        'files': {name: sha(D / name) for name in ['PREPARATION.json', 'rows.jsonl', 'internal-validation.jsonl']},
        'audit_script_sha256': sha(Path(__file__)),
        'pending': ['Linguistic review of status translation pairs', 'Family-disjoint development set and retention/identity mix', 'Formal training and complete release gates'],
        'training_ready': False, 'training_started': False, 'release_approved': False}
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k not in ['token_records', 'tokenizer_sources']}, ensure_ascii=False))
    for row in rows:
        if row['category'] == 'content-literal-status':
            context = json.loads(row['prompt']); artifact = context['semantic_artifacts'][0]
            print(json.dumps({'id': row['id'], 'source': artifact['sources'][0]['full_read']['text'], 'output': artifact['output']['text'], 'answer': json.loads(row['answer'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
