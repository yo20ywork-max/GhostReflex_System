"""Reuse unchanged, complete base generations as seeds for new runtime checks."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
OLD = R.parent / 'release_v12'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def main():
    parity = read(R / 'BASELINE_GENERATION_PARITY.json')
    source = ROOT / parity['historical_base_output']
    assert sha(source) == parity['historical_base_output_sha256']
    original_manifest = read(source.with_suffix('.manifest.json'))
    completed = read(source.with_suffix('.generation-complete.json'))
    assert completed['model_and_sources_unchanged'] and completed['rows'] == completed['complete_generations'] == 176
    assert completed['results_sha256'] == sha(source)
    assert original_manifest['model']['digest'] == parity['original_base_model_digest']
    assert all(sha(ROOT / name) == digest for name, digest in original_manifest['sources'].items())
    assert (OLD / 'evaluation-v1/cases.jsonl').read_bytes() == (R / 'evaluation-v1/cases.jsonl').read_bytes()
    for name in ('evaluate_gateway.py', 'score_generation.py'):
        assert (OLD / name).read_bytes() == (R / name).read_bytes()
    current = read(R / 'evaluation-v1/manifest.json')
    assert all(sha(ROOT / name) == digest for name, digest in current['source_hashes'].items())
    destination = R / 'evaluation-v1/base-gateway-reused-v1.jsonl'
    copies = [(source, destination)] + [(source.with_suffix(suffix), destination.with_suffix(suffix))
                                       for suffix in ('.manifest.json', '.generation-complete.json')]
    assert all(not target.exists() for _, target in copies)
    for origin, target in copies:
        with target.open('xb') as stream:
            stream.write(origin.read_bytes())
        assert sha(target) == sha(origin)
    record = {'staged_utc': datetime.now(timezone.utc).isoformat(),
              'files': [{'original': str(origin.relative_to(ROOT)),
                         'staged': str(target.relative_to(ROOT)), 'sha256': sha(target)}
                        for origin, target in copies],
              'current_cases_and_generation_sources_verified': True,
              'original_generation_metadata_preserved': True,
              'new_generation_performed': False, 'new_runtime_actions_performed': False,
              'purpose': 'Only reuse initial generation seeds; current full-loop actions must execute separately.',
              'release_approved': False}
    with (R / 'BASELINE_STAGING.json').open('x', encoding='utf8') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
    print(json.dumps({key: record[key] for key in ('current_cases_and_generation_sources_verified',
                      'original_generation_metadata_preserved', 'new_generation_performed',
                      'new_runtime_actions_performed', 'release_approved')}))


if __name__ == '__main__':
    main()
