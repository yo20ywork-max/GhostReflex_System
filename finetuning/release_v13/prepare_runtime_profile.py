"""Create a separate current-runtime evaluation profile after the fallback fix.

Original prompts, answers, schemas, oracles and historical outputs remain intact.
The only runner substitutions are output/control paths for this new profile.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
PROFILE = 'evaluation-runtime-v2'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def main():
    installed = read(R / 'FALLBACK_LITERAL_INSTALL.json')
    assert installed['installed_in_product'] and installed['candidate_ast_matches_product']
    assert sha(ROOT / 'run_daemon.py') == installed['after_sha256']
    assert sha(R / 'runtime_source.py') == installed['before_sha256']
    locked = read(R / 'DATA_LOCK.json')
    assert all(sha(R / name) == digest for name, digest in locked['sha256'].items())
    original = read(R / 'evaluation-v1/manifest.json')
    for name, digest in original['source_hashes'].items():
        if name == 'run_daemon.py':
            assert digest == installed['before_sha256']
        else:
            assert sha(ROOT / name) == digest
    for name, digest in original['outputs'].items():
        assert sha(R / 'evaluation-v1' / name) == digest
    sources = ('evaluate_gateway.py', 'score_generation.py', 'evaluate_identity_independent.py',
               'run_full_loop.py', 'evaluate_file_tasks_text.py', 'check_file_fixture.py', 'check_text_fixture.py')
    planned = []
    for name in sources:
        target = R / (Path(name).stem + '_runtime_v2.py')
        assert not target.exists()
        raw = (R / name).read_bytes()
        replacements = [(b'evaluation-v1', PROFILE.encode())]
        if name in ('evaluate_file_tasks_text.py', 'check_file_fixture.py', 'check_text_fixture.py'):
            replacements += [(label.encode(), (PROFILE + '/' + label).encode()) for label in
                             ('FILE_FIXTURE_CONTROLS.json', 'TEXT_FIXTURE_CONTROLS.json')]
        applied = []
        for before, after in replacements:
            count = raw.count(before)
            if count:
                raw = raw.replace(before, after)
                applied.append({'before': before.decode(), 'after': after.decode(), 'count': count})
        compile(raw, str(target), 'exec')
        planned.append((name, target, raw, applied))
    destination = R / PROFILE
    destination.mkdir(exist_ok=False)
    for name in ('cases.jsonl', 'schemas.json'):
        (destination / name).write_bytes((R / 'evaluation-v1' / name).read_bytes())
    runner_records = []
    for name, target, raw, applied in planned:
        with target.open('xb') as stream:
            stream.write(raw)
        runner_records.append({'original': name, 'original_sha256': sha(R / name),
                               'current': target.name, 'current_sha256': sha(target),
                               'path_substitutions': applied})
    manifest = dict(original)
    manifest['source_hashes'] = dict(original['source_hashes'])
    manifest['source_hashes']['run_daemon.py'] = installed['after_sha256']
    for path in (Path(__file__), R / 'FALLBACK_LITERAL_INSTALL.json', R / 'runtime-v2-sources/runtime_after.py'):
        manifest['source_hashes'][str(path.relative_to(ROOT))] = sha(path)
    manifest['profile_created_utc'] = datetime.now(timezone.utc).isoformat()
    manifest['profile_name'] = PROFILE
    manifest['predecessor_manifest_sha256'] = sha(R / 'evaluation-v1/manifest.json')
    manifest['training_runtime_snapshot_unchanged'] = True
    manifest['runtime_change'] = 'Only fallback diagnostic reason is protected by $literal; current runtime reevaluated separately.'
    manifest['outputs'] = {name: sha(destination / name) for name in ('cases.jsonl', 'schemas.json')}
    assert manifest['outputs'] == original['outputs'], 'Evaluation data or schemas changed'
    with (destination / 'manifest.json').open('x', encoding='utf8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    with (destination / 'PROFILE_PREPARATION.json').open('x', encoding='utf8') as stream:
        json.dump({'prepared_utc': manifest['profile_created_utc'], 'runners': runner_records,
                   'original_cases_answers_oracles_schemas_byte_identical': True,
                   'training_locked_inputs_unchanged': True, 'model_inference_started': False,
                   'prior_results_rewritten': False, 'release_approved': False}, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'profile': PROFILE, 'cases': manifest['total'], 'runners': len(runner_records),
                      'evaluation_data_unchanged': True, 'training_inputs_unchanged': True,
                      'inference_started': False, 'release_approved': False}))


if __name__ == '__main__':
    main()
