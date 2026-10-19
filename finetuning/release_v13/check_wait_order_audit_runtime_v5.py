"""Positive/counterfactual controls for original waiting-before-reading audit."""
import unittest
from audit_full_loop_requirements_runtime_v5 import wait_order


def wait(by='text', target='載入中', state='hidden', timeout=23000, **extra):
    return {'tool': 'BROWSER_WAIT_FOR', 'args': {'by': by, 'target': target, 'state': state, 'timeout_ms': timeout},
            'ok': True, 'verified': True, **extra}


def read():
    return {'tool': 'BROWSER_GET_TEXT', 'args': {'by': 'css', 'target': '#result'}, 'ok': True, 'verified': True, 'output': '完成'}


class WaitOrderTests(unittest.TestCase):
    def check(self, trace):
        return wait_order(trace, text='載入中', selector='#result', timeout_ms=23000)

    def test_wait_then_read_by_text_or_actual_fixture_css(self):
        self.assertTrue(self.check([wait(), read()])['passed'])
        self.assertTrue(self.check([wait(by='css', target='#busy'), read()])['passed'])

    def test_invented_css_cannot_prove_disappearance(self):
        result = self.check([wait(by='css', target='#載入中'), read()])
        self.assertFalse(result['passed'])
        self.assertEqual(result['premature_read_indices'], [2])

    def test_later_retry_cannot_erase_early_read(self):
        result = self.check([read(), wait(), read()])
        self.assertFalse(result['passed'])
        self.assertEqual(result['premature_read_indices'], [1])

    def test_repair_before_any_result_read_is_allowed(self):
        self.assertTrue(self.check([wait(by='css', target='#載入中'), wait(), read()])['passed'])
        self.assertTrue(self.check([wait(ok=False), wait(), read()])['passed'])

    def test_failed_wait_and_wrong_state_do_not_authorize_read(self):
        for step in (wait(ok=False), wait(verified=False), wait(state='visible'), wait(target='別段文字')):
            with self.subTest(step=step):
                self.assertFalse(self.check([step, read()])['passed'])

    def test_timeout_bound_and_missing_read_remain_required(self):
        self.assertFalse(self.check([wait(timeout=24000), read()])['passed'])
        self.assertFalse(self.check([wait(timeout=True), read()])['passed'])
        self.assertFalse(self.check([wait()])['passed'])
        self.assertTrue(self.check([wait(timeout=12000), read()])['passed'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
