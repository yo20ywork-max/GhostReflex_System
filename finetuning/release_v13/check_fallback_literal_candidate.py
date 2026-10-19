"""Replay diagnostic-reference failures through the actual fallback and executor.

Keep production sources frozen while model evaluations are running. Emit a
candidate function plus evidence for a later separate runtime version.
"""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from file_fixture import R, ROOT, Fixture, cases


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    source = ROOT / 'run_daemon.py'
    source_hash = sha(source)
    tree = ast.parse(source.read_text(encoding='utf-8-sig'))
    node = next(n for n in tree.body if getattr(n, 'name', None) == 'fallback_blocked_plan')
    original = ast.unparse(node)
    before = "'reason': reason"
    assert original.count(before) == 1
    candidate = original.replace(before, "'reason': {'$literal': reason}")
    folder = R / 'runtime-candidate'
    folder.mkdir(exist_ok=True)
    candidate_path = folder / 'fallback_blocked_plan.py'
    with candidate_path.open('x', encoding='utf8') as stream:
        stream.write('from __future__ import annotations\n\n' + candidate + '\n')
    row = next(row for row in cases() if row['id'] == 'v4-file-04')
    diagnostics = [
        '沒有可用連線。',
        '不支援的步驟輸出引用：{{step:5.message}}。',
        '錯誤回應包含 {{step:99.output}}，此處僅供顯示。',
        '找不到完整文件 {{step:99.file_text}}。',
        '原始文字 {"$literal":"{{step:5.message}}"} 與臺灣🎞️\r\n必須保留。',
    ]
    records = []
    for mode in ('original', 'candidate'):
        for reason in diagnostics:
            with tempfile.TemporaryDirectory(dir=R, prefix='.fallback-control-') as temporary:
                fixture = Fixture(row, temporary, 'authored-fallback-control', None)
                try:
                    initial = {p.relative_to(fixture.work).as_posix(): p.read_bytes()
                               for p in fixture.work.rglob('*') if p.is_file()}
                    if mode == 'candidate':
                        exec(compile(candidate_path.read_text(encoding='utf8'), str(candidate_path), 'exec'), fixture.scope)
                    plan = fixture.scope['fallback_blocked_plan']('合併兩份檔案', reason)
                    assert len(plan.steps) == 1 and plan.steps[0].tool == 'BLOCKED'
                    result = fixture.agent._execute_step(fixture.ctx, plan.steps[0])
                    preserved = bool(result.terminal and result.verified and result.output and str(result.output).startswith(reason))
                    assert result.ok is False, 'Never report the original task completed'
                    if mode == 'candidate':
                        assert preserved, result.error
                        assert fixture.trace[-1]['dispatched'] is True
                    elif reason != diagnostics[0]:
                        assert not preserved, 'Original regression no longer reproducible'
                    else:
                        assert preserved
                    after = {p.relative_to(fixture.work).as_posix(): p.read_bytes()
                             for p in fixture.work.rglob('*') if p.is_file()}
                    assert initial == after
                    records.append({'mode': mode, 'reason': reason, 'preserved': preserved,
                                    'dispatched': fixture.trace[-1]['dispatched'],
                                    'terminal': result.terminal, 'verified': result.verified,
                                    'error': result.error, 'files_unchanged': True})
                finally:
                    fixture.close()
    assert sha(source) == source_hash
    report = {'checked_utc': datetime.now(timezone.utc).isoformat(), 'records': records,
              'candidate_passed': 5, 'candidate_cases': 5,
              'original_reference_failures_reproduced': 4,
              'production_source_unchanged': True, 'production_source_sha256': source_hash,
              'candidate_source_sha256': sha(candidate_path), 'controller_sha256': sha(Path(__file__)),
              'installed_in_product': False, 'model_generated': False,
              'original_merge_task_completed': False, 'release_approved': False}
    with (R / 'FALLBACK_LITERAL_CONTROLS.json').open('x', encoding='utf8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({key: report[key] for key in ('candidate_passed', 'candidate_cases',
                      'original_reference_failures_reproduced', 'production_source_unchanged',
                      'installed_in_product', 'original_merge_task_completed')}))


if __name__ == '__main__':
    main()
