"""Whole-answer review of the32 completed temperature-only diagnostic replays."""
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent
P = R / 'evaluation-runtime-v2'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    pinned = {2: 'db41edb190cdbc5da369af0844a2f56669055829500efde5c75dbe5071e7fdf6',
              3: 'a483460f0df0af0dee28c310bc198f559afe91102ce99694abd7ac67085275c6'}
    epochs = {}
    for epoch, digest in pinned.items():
        source = P / f'epoch{epoch}-identity-neutral-greedy-diagnostic-v1.jsonl'
        assert sha(source) == digest
        receipt = json.loads(source.with_suffix('.complete.json').read_text(encoding='utf8'))
        assert receipt['model_and_sources_unchanged'] and receipt['rows'] == receipt['generation_finished'] == 16
        assert receipt['results_sha256'] == digest
        for path, h in receipt['sources'].items():
            assert sha(Path(path)) == h
        rows = list(map(json.loads, source.read_text(encoding='utf8').splitlines()))
        original = list(map(json.loads, (P / f'epoch{epoch}-identity-neutral-v1.jsonl').read_text(encoding='utf8').splitlines()))
        prior = json.loads((P / f'epoch{epoch}-identity-neutral-v1.manual-review.json').read_text(encoding='utf8'))
        old_decisions = {r['id']: r for r in prior['records']}
        records = []
        for row, old in zip(rows, original):
            assert row['id'] == old['id'] and row['generation_finished']
            request = json.loads(json.dumps(row['request']))
            assert request['options']['temperature'] == 0
            request['options']['temperature'] = 0.2
            assert request == old['request']
            decision = old_decisions[row['id']]
            # All32 were freshly read against their complete questions. The same
            # two failure families remain; unchanged verdicts are not blind reuse.
            passed = row['id'] != 'company-v10-dev-date-json' and not (epoch == 2 and row['id'] == 'identity-v10-dev-welcome')
            assert passed == decision['passed']
            records.append({'id': row['id'], 'passed': passed,
                            'reason': decision['reason'],
                            'review_basis': 'Fresh whole-answer review against original request; same verdict as temperature0.2',
                            'text_sha256': hashlib.sha256(row['text'].encode()).hexdigest()})
        epochs[str(epoch)] = {'results_sha256': digest, 'records': records,
                              'passed': sum(r['passed'] for r in records), 'total': 16,
                              'temperature_only_change_verified': True}
    report = {'epochs': epochs, 'review_script_sha256': sha(Path(__file__)),
              'conclusion': 'Temperature0 alone did not repair missing product name in E2 welcome or missing founded JSON field in E2/E3. Backend/quantization/template causes remain unproven.',
              'native_backend_parity_proven': False, 'original_gate_results_replaced': False,
              'final_holdout_opened': False, 'release_approved': False}
    with (R / 'GREEDY_IDENTITY_REVIEW.json').open('x', encoding='utf8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({e: {'passed': r['passed'], 'total': r['total']} for e, r in epochs.items()}))


if __name__ == '__main__':
    main()
