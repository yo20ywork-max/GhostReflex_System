import threading
import unittest
from desktop_ui.dialogs import DialogBroker


class DialogCancellation(unittest.TestCase):
    def test_cancel_before_queued_ui_delivery_does_not_reopen_question(self):
        broker = DialogBroker()
        request = broker.request('確認', '是否執行？', True)
        broker.cancel()
        self.assertTrue(request.ready.is_set())
        self.assertIsNone(request.answer)
        self.assertFalse(broker.is_pending(request.token))
        self.assertIsNone(broker.request('晚到的提問', '不應顯示', False))

    def test_stale_answer_cannot_authorize_a_new_task(self):
        broker = DialogBroker()
        old = broker.request('確認', '先前任務', True)
        broker.cancel()
        broker.begin_task()
        current = broker.request('確認', '新任務', True)
        self.assertFalse(broker.resolve(old.token, 'yes'))
        self.assertFalse(current.ready.is_set())
        self.assertTrue(broker.resolve(current.token, 'yes'))
        self.assertEqual(current.answer, 'yes')

    def test_cancel_releases_waiting_worker(self):
        broker = DialogBroker()
        request = broker.request('輸入', '路徑', False)
        finished = threading.Event()
        worker = threading.Thread(target=lambda: (request.ready.wait(), finished.set()))
        worker.start()
        broker.cancel()
        worker.join(timeout=1)
        self.assertTrue(finished.is_set())
        self.assertIsNone(request.answer)

    def test_answer_preserves_literal_whitespace(self):
        broker = DialogBroker()
        request = broker.request('輸入', '原文', False)
        broker.resolve(request.token, '  原文\n\t')
        self.assertEqual(request.answer, '  原文\n\t')
