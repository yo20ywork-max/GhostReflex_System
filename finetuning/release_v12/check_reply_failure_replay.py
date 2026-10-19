"""Replay the observed file07 failure against frozen and corrected reply guards.

The recovery response is authored, so this isolates the veto/recovery mechanism;
the separate file8 generation run supplies current model acceptance evidence.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
import file_fixture
import explicit_reply


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    output = R / 'REPLY_FAILURE_REPLAY.json'
    if output.exists():
        raise FileExistsError(output)
    baseline = R / 'evaluation-v1/epoch1-file8-text-v2.jsonl'
    assert sha(baseline) == '4b96c7beefdb0421900ac45f38ba9c36d45af92072214025549b726b5fdda75b'
    failed = next(r for r in map(json.loads, baseline.read_text(encoding='utf8').splitlines()) if r['id'] == 'v4-file-07')
    first_plan, checker = [json.loads(c['response']['message']['content']) for c in failed['calls']]
    assert checker['complete'] is True and failed['false_completion'] is True
    spec = importlib.util.spec_from_file_location('frozen_reply_guard', R / 'explicit_reply.py')
    frozen = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = frozen
    spec.loader.exec_module(frozen)
    row = next(r for r in file_fixture.cases() if r['id'] == 'v4-file-07')
    records = []
    for label, module in [('frozen', frozen), ('corrected', explicit_reply)]:
        class Gateway:
            plans = 0
            def chat_json(self, *, messages, schema, models=None):
                if 'complete' in schema['properties']:
                    return checker, 'replayed-checker'
                self.plans += 1
                if self.plans == 1:
                    return first_plan, 'replayed-plan'
                assert self.plans == 2
                assert '尚未提供原始需求指定的最後回覆' in messages[-1]['content']
                return {'objective': row['user_request'], 'assumptions': [], 'steps': [
                    {'id': 4, 'tool': 'FINAL_RESPONSE', 'args': {'message': '核對完成'},
                     'goal': '補上指定回覆', 'success_check': '核對實際回覆', 'on_failure': 'stop', 'retries': 0}],
                    'completion_criteria': ['原工作不重做，補上指定回覆']}, 'authored-recovery'
        gateway = Gateway()
        with tempfile.TemporaryDirectory(dir=R, prefix='.reply-failure-replay-') as temp:
            with patch.object(file_fixture, 'install_reply_completion_guard', module.install_reply_completion_guard):
                fixture = file_fixture.Fixture(row, temp, 'replay', gateway)
            try:
                result, _, _ = fixture.run('replay', gateway)
                verdict = file_fixture.evaluate(row, fixture.work, result.history, result.status, result.message, trace=fixture.trace)
                writes = [h for h in result.history if h['tool'] == 'WRITE_TEXT_FILE' and h['ok'] and h['verified']]
                assert len(writes) == 1
                assert gateway.plans == (1 if label == 'frozen' else 2)
                assert verdict['false_completion'] is (label == 'frozen')
                assert verdict['passed'] is (label == 'corrected')
                records.append({'guard': label, 'guard_sha256': sha(Path(module.__file__)),
                                'plans': gateway.plans, 'successful_writes': len(writes),
                                'history': result.history, 'message': result.message, **verdict})
            finally:
                fixture.close()
    report = {'controls': 2, 'all_passed': True, 'records': records,
              'observed_failure_sha256': sha(baseline), 'checker_sha256': sha(Path(__file__)),
              'same_initial_plan_and_overconfident_checker': True,
              'authored_recovery_not_model_generation': True, 'release_approved': False}
    with output.open('x', encoding='utf8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != 'records'}))


if __name__ == '__main__':
    main()
