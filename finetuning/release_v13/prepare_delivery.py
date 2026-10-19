"""Prepare version-specific delivery/evaluation helpers without cloud actions."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent
OLD = R.parent / 'release_v12'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    unchanged = (
        'verify_epoch_binding.py', 'finish_cloud.py', 'file_fixture.py',
        'file_fixture_text.py', 'check_file_fixture.py', 'check_text_fixture.py',
        'evaluate_file_tasks_text.py', 'audit_full_loop_requirements.py',
        'check_wait_order_audit.py',
    )
    replaced = {
        'convert_candidate.py': [('verified v12 checkpoint', 'verified v13 checkpoint')],
        'verify_local_adapter.py': [('V12 only verifies', 'V13 only verifies')],
        'install_candidate.py': [('verified v12 adapter', 'verified v13 adapter'),
                                 ('v12-e{args.epoch}-eval-20260906', 'v13-e{args.epoch}-eval-20260907')],
        'package_preview.py': [('v12-e{args.epoch}-package-preview', 'v13-e{args.epoch}-package-preview')],
        'run_full_loop.py': [('v12_original_full_loop', 'v13_original_full_loop'),
                             ('v12_original_full_review', 'v13_original_full_review')],
    }
    planned = []
    for name in (*unchanged, *replaced):
        source, destination = OLD / name, R / name
        raw = source.read_bytes()
        substitutions = replaced.get(name, [])
        for before, after in substitutions:
            assert raw.count(before.encode()) == 1, (name, before)
            raw = raw.replace(before.encode(), after.encode())
        compile(raw, str(destination), 'exec')
        assert not destination.exists(), destination
        planned.append((name, raw, substitutions))
    record = {'prepared_utc': datetime.now(timezone.utc).isoformat(), 'files': [],
              'training_restarted': False, 'weights_downloaded': False,
              'model_installed': False, 'cloud_resource_changed': False,
              'original_evaluation_requests_and_oracles_preserved': True,
              'release_approved': False}
    for name, raw, substitutions in planned:
        with (R / name).open('xb') as stream:
            stream.write(raw)
        record['files'].append({'name': name, 'source': str(OLD / name),
                                'source_sha256': sha(OLD / name),
                                'prepared_sha256': sha(R / name),
                                'substitutions': substitutions,
                                'byte_identical': not substitutions})
    with (R / 'DELIVERY_PREPARATION.json').open('x', encoding='utf8') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'prepared_files': len(planned), 'cloud_actions': False,
                      'model_inference': False, 'release_approved': False}))


if __name__ == '__main__':
    main()
