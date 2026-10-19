"""Apply the verified diagnostic fix after the prior file baseline terminates."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent
ROOT = R.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def main():
    output = R / 'evaluation-v1/base-file8-current-v1.jsonl'
    summary = read(output.with_suffix('.summary.json'))
    run = read(output.with_suffix('.manifest.json'))
    assert summary['total'] == 8 and summary['sources_and_model_unchanged']
    assert summary['results_sha256'] == sha(output)
    assert all(sha(ROOT / name) == digest for name, digest in run['sources'].items())
    controls = read(R / 'FALLBACK_LITERAL_CONTROLS.json')
    source = ROOT / 'run_daemon.py'
    assert sha(source) == controls['production_source_sha256']
    assert controls['candidate_passed'] == controls['candidate_cases'] == 5
    candidate = R / 'runtime-candidate/fallback_blocked_plan.py'
    assert sha(candidate) == controls['candidate_source_sha256']
    before = source.read_bytes()
    search = b'                    "reason": reason,'
    replacement = b'                    "reason": {"$literal": reason},'
    assert before.count(search) == 1
    after = before.replace(search, replacement)
    compile(after, str(source), 'exec')
    changed_tree = ast.parse(after.decode('utf-8-sig'))
    node = next(node for node in changed_tree.body if getattr(node, 'name', None) == 'fallback_blocked_plan')
    proposed = next(node for node in ast.parse(candidate.read_text(encoding='utf8')).body
                    if getattr(node, 'name', None) == 'fallback_blocked_plan')
    assert ast.dump(node) == ast.dump(proposed), 'Product patch differs from executor-tested candidate'
    snapshot = R / 'runtime-v2-sources'
    snapshot.mkdir(exist_ok=False)
    (snapshot / 'runtime_before.py').write_bytes(before)
    (snapshot / 'runtime_after.py').write_bytes(after)
    source.write_bytes(after)
    assert sha(source) == sha(snapshot / 'runtime_after.py')
    receipt = {'installed_utc': datetime.now(timezone.utc).isoformat(),
               'before_sha256': sha(snapshot / 'runtime_before.py'), 'after_sha256': sha(source),
               'candidate_controls_sha256': sha(R / 'FALLBACK_LITERAL_CONTROLS.json'),
               'baseline_results_sha256': sha(output), 'baseline_summary': summary,
               'candidate_ast_matches_product': True, 'installed_in_product': True,
               'production_tests_pending': True, 'training_bundle_changed': False,
               'generation_profile_refresh_required': True, 'release_approved': False}
    with (R / 'FALLBACK_LITERAL_INSTALL.json').open('x', encoding='utf8') as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main()
