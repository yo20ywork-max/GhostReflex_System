"""Separate known-file development variant: additional explicit-reply veto.

Reuse the original file oracles and bounded execution. Never overwrite original
candidate comparison results, modify the frozen runtime, or claim a release.
"""
import hashlib
import json
from pathlib import Path
import sys

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
sys.path.insert(0, str(ROOT))
import evaluate_file_development as driver
from explicit_reply import install_reply_completion_guard


def main():
    args = sys.argv[1:]
    if '--output' not in args:
        raise ValueError('Explicit separate output required')
    name = args[args.index('--output') + 1]
    if Path(name).name != name or 'reply-guard' not in name:
        raise ValueError('Output must be a file name containing reply-guard')
    output = R / name
    receipt = output.with_suffix('.guard-provenance.json')
    if output.exists() or receipt.exists():
        raise FileExistsError('Refuse overwrite of existing evaluation')
    paths = [Path(__file__), ROOT / 'explicit_reply.py', ROOT / 'completion_requirements.py',
             ROOT / 'tests/test_explicit_reply.py', Path(driver.__file__)]
    hashes = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    state = {'source_hashes': hashes, 'argv': args, 'status': 'running',
             'scope': 'Separate explicit reply veto; unchanged original file8 oracles. Known development, not final or native UI.',
             'release_approved': False}
    with receipt.open('x', encoding='utf8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    original_fixture = driver.Fixture

    class GuardFixture(original_fixture):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if not install_reply_completion_guard(self.scope['Planner']):
                raise RuntimeError('Unexpected prior guard installation')

    driver.Fixture = GuardFixture
    try:
        driver.main()
        state['status'] = 'terminal'
        state['result_sha256'] = hashlib.sha256(output.read_bytes()).hexdigest()
    except BaseException as exc:
        state.update(status='failed', error=repr(exc))
        raise
    finally:
        driver.Fixture = original_fixture
        state['guard_sources_unchanged'] = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in hashes.items())
        receipt.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf8')
    if not state['guard_sources_unchanged']:
        raise RuntimeError('Guard sources changed during comparison')


if __name__ == '__main__':
    main()
