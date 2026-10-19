"""Cancel and timeout stop only the owned speech worker, never returning partial text."""
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch
from desktop_ui.speech import SpeechCancelled, transcribe_file


class SpeechProcess(unittest.TestCase):
    def test_cancel_before_start_creates_no_child(self):
        event = threading.Event()
        event.set()
        with patch('desktop_ui.speech.subprocess.Popen') as spawn:
            with self.assertRaises(SpeechCancelled):
                transcribe_file('unused.wav', 'unused-model', event)
            spawn.assert_not_called()

    def child_factory(self, body):
        original = subprocess.Popen
        children = []
        def create(command, **kwargs):
            child = original([sys.executable, '-c', body], **kwargs)
            children.append(child)
            return child
        return create, children

    def test_cancelling_live_worker_reaps_owned_process(self):
        create, children = self.child_factory('import time;time.sleep(20)')
        event = threading.Event()
        timer = threading.Timer(0.1, event.set)
        timer.start()
        try:
            with patch('desktop_ui.speech.subprocess.Popen', side_effect=create):
                with self.assertRaises(SpeechCancelled):
                    transcribe_file('unused.wav', 'unused-model', event)
        finally:
            timer.cancel()
            timer.join()
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())

    def test_timeout_does_not_return_an_early_partial_json(self):
        create, children = self.child_factory('import time;print("{\\\"text\\\":\\\"partial\\\"",flush=True);time.sleep(20)')
        with patch('desktop_ui.speech.subprocess.Popen', side_effect=create):
            with self.assertRaises(TimeoutError):
                transcribe_file('unused.wav', 'unused-model', timeout=0.1)
        self.assertIsNotNone(children[0].poll())

    def test_successful_worker_response_requires_explicit_completion(self):
        create, children = self.child_factory('print(\'{"text":"partial","completed":false,"truncated":true}\')')
        with patch('desktop_ui.speech.subprocess.Popen', side_effect=create):
            with self.assertRaises(ValueError):
                transcribe_file('unused.wav', 'unused-model')
        self.assertIsNotNone(children[0].poll())


if __name__ == '__main__':
    unittest.main()
