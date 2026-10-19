"""Exercise the pending reply fix without modifying the frozen product source."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
sys.path.insert(0, str(ROOT))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


candidate = load('explicit_reply', R / 'runtime-candidate/explicit_reply.py')
old_tests = load('reply_existing_tests', ROOT / 'tests/test_explicit_reply.py')


class ReplyTrailingConstraintTests(unittest.TestCase):
    def test_original_failed_file_task_seven(self):
        rows = list(map(json.loads, (R.parent / 'release_v4/file-development-v2.jsonl').read_text(encoding='utf8').splitlines()))
        # Read the original request verbatim; do not author an easier fixture.
        row = next(r for r in rows if r['id'] == 'v4-file-07')
        prompt = row['user_request']
        required = candidate.explicit_reply_requirement(prompt)
        self.assertIsNotNone(required)
        self.assertEqual(required.text, '核對完成')
        self.assertEqual(prompt[required.start:required.end], required.text)
        self.assertIsNotNone(candidate.reply_completion_veto(prompt, [
            {'tool': 'FINAL_RESPONSE', 'ok': True, 'verified': True, 'output': '備份完成'}]))
        self.assertIsNone(candidate.reply_completion_veto(prompt, [
            {'tool': 'FINAL_RESPONSE', 'ok': True, 'verified': True, 'output': '核對完成'}]))

    def test_additive_constraints_keep_unique_reply_and_exact_offsets(self):
        for tail in ('不要改動原稿。', '已成功的寫入不要重做。', '保留「取消.txt」。', '請保留中間檔案。'):
            text = '  μ𠮷\n\t{{step:19.output}}  '
            prompt = '核對完成後只回覆「' + text + '」。' + tail
            with self.subTest(tail=tail):
                found = candidate.explicit_reply_requirement(prompt)
                self.assertIsNotNone(found)
                self.assertEqual(found.text, text)
                self.assertEqual(prompt[found.start:found.end], text)

    def test_later_cancellation_example_and_conflict_not_enforced(self):
        for tail in ('上述作廢。', '這只是示範。', '取消上述指令。', '不要回覆。',
                     '改為保持沉默。', '最後回覆「失敗」。', '如果內容不同就停止。'):
            with self.subTest(tail=tail):
                self.assertIsNone(candidate.explicit_reply_requirement('完成後回覆「成功」。' + tail))


if __name__ == '__main__':
    before = sha(ROOT / 'explicit_reply.py')
    suite = unittest.TestSuite([
        unittest.defaultTestLoader.loadTestsFromModule(old_tests),
        unittest.defaultTestLoader.loadTestsFromTestCase(ReplyTrailingConstraintTests),
    ])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'tests': result.testsRun, 'passed': result.wasSuccessful(),
              'candidate_sha256': sha(R / 'runtime-candidate/explicit_reply.py'),
              'original_source_unchanged': before == sha(ROOT / 'explicit_reply.py'),
              'test_script_sha256': sha(Path(__file__)),
              'product_installed': False, 'actual_model_rerun_required': True, 'release_approved': False}
    (R / 'REPLY_CANDIDATE_CONTROLS.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    if not result.wasSuccessful():
        raise SystemExit(1)
