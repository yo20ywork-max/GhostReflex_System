"""Install the verified one-line recovery change after fixed-profile evaluation."""
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
    profile = R / 'evaluation-runtime-v2'
    bindings = {}
    for epoch in (1, 2, 3):
        generation = profile / f'epoch{epoch}-gateway-v1.jsonl'
        receipt = read(generation.with_suffix('.generation-complete.json'))
        assert receipt['complete_generations'] == 176 and receipt['model_and_sources_unchanged']
        assert receipt['results_sha256'] == sha(generation)
        loop = generation.with_suffix('.full-loop') / 'result.json'
        result = read(loop)
        assert result['source_files_unchanged'] and result['model_digest_unchanged']
        audit = read(loop.parent / 'order-audit-v1.json')
        assert audit['total'] == 12 and audit['original_result_sha256'] == sha(loop)
        file8 = profile / f'epoch{epoch}-file8-v1.jsonl'
        summary = read(file8.with_suffix('.summary.json'))
        assert summary['total'] == 8 and summary['sources_and_model_unchanged']
        assert summary['results_sha256'] == sha(file8)
        bindings[str(epoch)] = {'generation_sha256': sha(generation),
                                'loop_sha256': sha(loop), 'file8_sha256': sha(file8)}
    controls_path = R / 'CONDITION_RECOVERY_CANDIDATE.json'
    controls = read(controls_path)
    assert controls['candidate_controls_passed'] == controls['candidate_controls_total'] == 5
    source = ROOT / 'run_daemon.py'
    assert sha(source) == controls['production_source_sha256']
    candidate = R / 'runtime-candidate/execute_step_condition_recovery.py'
    assert sha(candidate) == controls['candidate_sha256']
    before = source.read_bytes()
    old = 'return ToolResult(False, error=f"條件無法判定，未派發動作：{exc}", terminal=True)'.encode()
    new = 'return ToolResult(False, error=f"條件無法判定，未派發動作：{exc}", terminal=step.on_failure not in ("replan", "retry"))'.encode()
    assert before.count(old) == 1
    after = before.replace(old, new)
    compile(after, str(source), 'exec')
    tree = ast.parse(after.decode('utf-8-sig'))
    agent = next(n for n in tree.body if getattr(n, 'name', '') == 'UniversalAgent')
    method = next(n for n in agent.body if getattr(n, 'name', '') == '_execute_step')
    proposed = next(n for n in ast.parse(candidate.read_text(encoding='utf8')).body
                    if getattr(n, 'name', '') == '_execute_step')
    assert ast.dump(method) == ast.dump(proposed)
    snapshot = R / 'runtime-v3-sources'
    snapshot.mkdir(exist_ok=False)
    (snapshot / 'runtime_before.py').write_bytes(before)
    (snapshot / 'runtime_after.py').write_bytes(after)
    source.write_bytes(after)
    assert sha(source) == sha(snapshot / 'runtime_after.py')
    receipt = {'installed_utc': datetime.now(timezone.utc).isoformat(),
               'before_sha256': sha(snapshot / 'runtime_before.py'), 'after_sha256': sha(source),
               'controls_sha256': sha(controls_path), 'completed_baselines': bindings,
               'candidate_ast_matches_product': True, 'installed_in_product': True,
               'production_tests_pending': True, 'model_repair_success_measured': False,
               'new_runtime_profile_required': True, 'release_approved': False}
    with (R / 'CONDITION_RECOVERY_INSTALL.json').open('x', encoding='utf8') as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2)
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
