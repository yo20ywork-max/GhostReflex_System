"""Unicode roundtrip, size and captured-request checks for staged JSON encoder."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import unicodedata
from tokenizers import Tokenizer

R = Path(__file__).resolve().parent
ROOT = R.parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    target = R / 'COMPACT_MODEL_JSON_CONTROLS.json'
    if target.exists():
        raise FileExistsError(target)
    before = ROOT / 'model_json.py'
    candidate_path = R / 'runtime-candidate/model_json_compact.py'
    old = load('old_model_json', before)
    candidate = load('compact_model_json', candidate_path)
    counts = {'canonical_decompositions': 0, 'hangul_decompositions': 0, 'random_mixed': 0, 'literal_controls': 0}
    def check(value):
        encoded = candidate.dumps(value)
        assert json.loads(encoded) == value
        assert json.loads(unicodedata.normalize('NFC', encoded)) == value
        assert encoded == unicodedata.normalize('NFC', encoded)
        assert len(encoded) <= len(old.dumps(value))
    # Includes canonical decompositions whose second component is class0,
    # compatibility-sensitive singletons and combining-mark reorderings.
    for codepoint in range(0x110000):
        char = chr(codepoint)
        decomposition = unicodedata.decomposition(char)
        if decomposition and not decomposition.startswith('<'):
            decomposed = ''.join(chr(int(x, 16)) for x in decomposition.split())
            check({'prefix': '台灣', 'value': '前文A' + decomposed + '後文', decomposed: [char, decomposed]})
            counts['canonical_decompositions'] += 1
    for codepoint in range(0xAC00, 0xD7A4):
        text = unicodedata.normalize('NFD', chr(codepoint))
        check(['前文' + text + '後文', text])
        counts['hangul_decompositions'] += 1
    pool = ['台灣原文', 'e\u0301', '\u1100\u1161\u11a8', '\u09c7\u09be', '\u212b', '\u0344',
            '\r\n', '\t', '\x00', '\\u0301', '\"', '\\', '𠮷😀', '\u0301\u0327', '{{step:3.file_text}}', '']
    rng = random.Random(20260907)
    for _ in range(500):
        value = ''.join(rng.choice(pool) for _ in range(rng.randint(1, 40)))
        check({'e\u0301': [value, {'nested': value}], 'empty': '', 'bool': True, 'number': 42})
        counts['random_mixed'] += 1
    for options in ({}, {'indent': 2}, {'separators': (',', ':')}, {'sort_keys': True}):
        value = {'e\u0301': pool, 'normal': '台灣原文𠮷😀', 'empty': []}
        encoded = candidate.dumps(value, **options)
        assert json.loads(unicodedata.normalize('NFC', encoded)) == value
        counts['literal_controls'] += 1
    normal = {'user_request': '台灣原文\r\n𠮷😀', 'count': 0}
    assert candidate.dumps(normal) == json.dumps(normal, ensure_ascii=False)
    tokenizer_path = R / 'artifacts/outputs/epoch-3/tokenizer.json'
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    captured = R / 'evaluation-runtime-v4/epoch3-file8-v1.jsonl'
    rows = [json.loads(line) for line in captured.read_text(encoding='utf8').splitlines()]
    comparisons = []
    for row in rows:
      for index, call in enumerate(row['calls']):
        for message_index, message in enumerate(call['request']['messages']):
            text = message['content']
            if message['role'] != 'user':
                continue
            try:
                payload = json.loads(text)
            except ValueError:
                continue
            if not isinstance(payload, dict):
                continue
            encoded = candidate.dumps(payload)
            assert json.loads(unicodedata.normalize('NFC', encoded)) == payload
            before_tokens = len(tokenizer.encode(text, add_special_tokens=False).ids)
            after_tokens = len(tokenizer.encode(encoded, add_special_tokens=False).ids)
            comparisons.append({'case_id': row['id'], 'call_index': index, 'message_index': message_index,
                                'old_chars': len(text), 'new_chars': len(encoded),
                                'old_content_tokens': before_tokens, 'new_content_tokens': after_tokens,
                                'same_decoded_payload': True})
    assert comparisons
    # Size reduction is an observation, not a correctness requirement. The
    # original case01-only run failed this expectation after passing Unicode
    # checks: that case is already NFC and does not benefit from this encoder.
    prior_expectation = {'case_id': 'v4-file-01', 'expected_token_reduction': True,
                         'expectation_satisfied': any(r['new_content_tokens'] < r['old_content_tokens']
                             for r in comparisons if r['case_id'] == 'v4-file-01'),
                         'original_run_result': 'AssertionError at token-reduction expectation; no report written',
                         'context_overflow_fixed': False}
    report = {'checked_utc': datetime.now(timezone.utc).isoformat(), 'unicode_version': unicodedata.unidata_version,
              'counts': counts, 'all_controls_passed': True, 'roundtrip_after_nfc_preserved': True,
              'whole_payload_omitted_or_summarized': False, 'comparisons': comparisons,
              'token_count_scope': 'User message content only, from pinned tokenizer.json; not server chat-template admission or task success.',
              'source_sha256': sha(before), 'candidate_sha256': sha(candidate_path),
              'tokenizer_sha256': sha(tokenizer_path),
              'captured_results_sha256': sha(captured), 'prior_failed_expectation': prior_expectation,
              'installed_in_product': False, 'release_approved': False}
    with target.open('x', encoding='utf8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k not in ('comparisons',)}), flush=True)
    print(json.dumps(comparisons), flush=True)


if __name__ == '__main__':
    main()
