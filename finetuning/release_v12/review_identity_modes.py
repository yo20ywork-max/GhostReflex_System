"""Bind manually reviewed identity outcomes to exact local/native probe files."""
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    common = {'identity-v10-dev-task-code', 'identity-v10-dev-task-ui'}
    profiles = [
        ('base-neutral', 'evaluation-v1/base-identity-neutral-v1.jsonl',
         '78128b473870d04b0d179b03913f86bb7c2813fe8ca5691bbd56fe46acf96a2e',
         None, common | {'company-v10-dev-position'}),
        ('epoch1-neutral', 'evaluation-v1/epoch1-identity-neutral-v1.jsonl',
         '21234470cb7531cd22d04d5c111694fa5671879d0675c616b2aeeb7e3c824289',
         None, common | {'identity-v10-dev-region-label', 'identity-v10-dev-literal'}),
        ('epoch2-neutral', 'evaluation-v1/epoch2-identity-neutral-v1.jsonl',
         '4b7cc201b74cc8f38cb0715281b61a4d20e7c43c6cd2467ea4489358129c4be6',
         None, common | {'identity-v10-dev-region-label'}),
        ('epoch1-package-default', 'evaluation-v1/epoch1-identity-package-v1.jsonl',
         '407bf4fced23021b452529ca00fb0313506f11dd2852d6672497652194c05f56',
         None, 'all-except-literal'),
        ('epoch3-native-neutral', 'cloud-observations/outputs/identity-backend-e3/results.jsonl',
         '025bd7422a0f222460a0ef9f093e9aeaabea1e28f28fd3f2949df90dc1b70169',
         'neutral', common | {'identity-v10-dev-region-label', 'identity-v10-dev-literal'}),
        ('epoch3-native-branded', 'cloud-observations/outputs/identity-backend-e3/results.jsonl',
         '025bd7422a0f222460a0ef9f093e9aeaabea1e28f28fd3f2949df90dc1b70169',
         'branded', 'all-except-format-three'),
    ]
    reports = []
    for profile, filename, digest, mode, passing in profiles:
        path = R / filename
        assert sha(path) == digest
        rows = list(map(json.loads, path.read_text(encoding='utf8').splitlines()))
        if mode:
            rows = [r for r in rows if r['mode'] == mode]
        assert len(rows) == 16
        records = []
        for row in rows:
            id_ = row.get('original_id', row['id'])
            if passing == 'all-except-literal':
                passed = id_ != 'identity-v10-dev-literal'
            elif passing == 'all-except-format-three':
                passed = id_ not in {'identity-v10-dev-literal', 'identity-v10-dev-unicode', 'company-v10-dev-date-json'}
            else:
                passed = id_ in passing
            records.append({'id': id_, 'passed': passed, 'text_sha256': hashlib.sha256(row['text'].encode()).hexdigest()})
        reports.append({'profile': profile, 'source': filename, 'results_sha256': digest,
                        'passed': sum(r['passed'] for r in records), 'total': 16, 'records': records})
    report = {'profiles': reports, 'reviewer': 'Codex whole-answer review of each exact result; known development',
              'interpretation': 'Neutral profile contains no company facts. Correct region alone is not identity learning. Refusing a number without stating the approved disclosure status is not a company-profile pass. Ordinary tasks and exact quotes are still required.',
              'sampling_caveat': 'Local probes use fixed-seed temperature0.2; native probes are greedy NF4. Backend scores are not a controlled quantization comparison.',
              'verified_finding': 'The final native checkpoint still gives the prior identity under a neutral system. GGUF conversion alone cannot explain the identity requirement failure.',
              'weight_identity_requirement_passed': False, 'complete_latent_memory_erasure_proven': False,
              'script_sha256': sha(Path(__file__)), 'release_approved': False}
    with (R / 'IDENTITY_MODE_REVIEW.json').open('x', encoding='utf8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({p['profile']: p['passed'] for p in reports}))


if __name__ == '__main__':
    main()
