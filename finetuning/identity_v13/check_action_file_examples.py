"""Execute staged file plans through actual handlers with an authored gateway.

This validates training answers, not model generation. No UI or paid inference.
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
sys.path.insert(0, str(R.parent / 'release_v12'))
from file_fixture import Fixture, DEPENDENCIES
from text_reader import completed_file_contents


class AuthoredGateway:
    def __init__(self, plan):
        self.plan = plan
        self.plans = 0

    def chat_json(self, *, messages, schema, models=None):
        if 'complete' in schema['properties']:
            return {'reason': 'authored control; independent artifact checks follow', 'complete': True}, 'authored'
        self.plans += 1
        if self.plans != 1:
            raise AssertionError('Authored plan required unexpected recovery')
        return self.plan, 'authored'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    folder = R / 'action-additions-v1'
    report_path = folder / 'FILE_EXECUTION_CONTROLS.json'
    if report_path.exists():
        raise FileExistsError(report_path)
    data = folder / 'additions.jsonl'
    prep = json.loads((folder / 'PREPARATION.json').read_text(encoding='utf8'))
    assert sha(data) == prep['data_sha256']
    rows = list(map(json.loads, data.read_text(encoding='utf8').splitlines()))
    records = []
    for row in rows:
        if not any(name in row['id'] for name in ('path-copy', 'text-write', 'conditional')):
            continue
        plan = json.loads(row['answer'])
        write = next(s for s in plan['steps'] if s['tool'] in ('COPY_FILE_VERIFIED', 'WRITE_TEXT_FILE'))
        source = next(s['args']['path'] for s in plan['steps'] if s['tool'] == 'READ_TEXT_FILE')
        dest = write['args'].get('destination', write['args'].get('path'))
        conditional = 'conditional' in row['id']
        for exists in ((False, True) if conditional else (False,)):
            initial = {source: '  控制原文𠮷😀\r\n\t中段\r\n字面 {{step:400.output}}\r\n  '}
            if exists:
                initial[dest] = '既有副本，不同於原稿\r\n'
            expected = dict(initial)
            if not exists:
                expected[dest] = initial[source]
            case = {'id': row['id'] + '-' + str(exists), 'user_request': json.loads(row['prompt'])['user_request'],
                    'initial_files': initial, 'write_targets': {} if exists else {dest: ['WRITE_TEXT_FILE']}}
            DEPENDENCIES[case['id']] = {} if exists else {dest: [source]}
            gateway = AuthoredGateway(plan)
            with tempfile.TemporaryDirectory(dir=R, prefix='.action-data-control-') as temp:
                fixture = Fixture(case, temp, 'authored', gateway)
                opens = []
                original_open = Path.open
                source_path = fixture.work / source
                def observed_open(path, mode='r', *args, **kwargs):
                    if path == source_path and ('r' in mode or '+' in mode):
                        opens.append(mode)
                    return original_open(path, mode, *args, **kwargs)
                try:
                    with patch.object(Path, 'open', observed_open):
                        result, _, _ = fixture.run('authored', gateway)
                    actual = {p.relative_to(fixture.work).as_posix(): p.read_bytes()
                              for p in fixture.work.rglob('*') if p.is_file()}
                    assert actual == {n: v.encode('utf8') for n, v in expected.items()}, case['id']
                    assert result.status == 'completed', (case['id'], result.status, result.message)
                    reply = '沿用既有副本' if exists else next(
                        s['args']['message'] for s in plan['steps'] if s['tool'] == 'FINAL_RESPONSE')
                    assert result.message == reply, (case['id'], result.message)
                    assert all(t['dispatched'] for t in fixture.trace), fixture.trace
                    done = [(i, h) for i, h in enumerate(result.history)
                            if h.get('ok') is True and h.get('verified') is True and
                            not (h.get('evidence') or {}).get('condition_skipped')]
                    writes = [(i, h) for i, h in done if h['tool'] in ('COPY_FILE_VERIFIED', 'WRITE_TEXT_FILE')]
                    assert len(writes) == (0 if exists else 1), case['id']
                    if exists:
                        assert not opens, (case['id'], opens)
                    else:
                        i, _ = writes[0]
                        before = completed_file_contents(result.history[:i])
                        after = completed_file_contents(result.history[i + 1:])
                        assert before[str(source_path)]['text'] == initial[source]
                        assert after[str(fixture.work / dest)]['text'] == initial[source]
                    records.append({'id': case['id'], 'passed': True, 'destination_preexisted': exists,
                                    'source_open_count': len(opens), 'successful_writes': len(writes),
                                    'history': result.history})
                finally:
                    fixture.close()
    assert len(records) == 16
    report = {'controls': len(records), 'all_passed': True, 'records': records,
              'data_sha256': sha(data), 'checker_sha256': sha(Path(__file__)),
              'sources': {str(p.relative_to(ROOT)): sha(p) for p in [ROOT / 'run_daemon.py',
                  ROOT / 'explicit_reply.py', ROOT / 'verified_copy.py', ROOT / 'text_reader.py',
                  ROOT / 'step_conditions.py', R.parent / 'release_v12/file_fixture.py']},
              'model_generated': False, 'browser_plans_executed': False,
              'training_ready': False, 'release_approved': False}
    with report_path.open('x', encoding='utf8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k not in ('records', 'sources')}))


if __name__ == '__main__':
    main()
