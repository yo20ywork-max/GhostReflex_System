"""Recording uses fake devices; process lifecycle checks use real owned child processes."""
import subprocess
import sys
import threading
import unittest
import wave
from unittest.mock import patch
from desktop_ui.voice_session import run_voice
from desktop_ui.voice_worker import record
from desktop_ui.speech import SpeechCancelled


class VoiceSession(unittest.TestCase):
    def device(self, overflow=False):
        status = {'closed': False}
        def factory(**kwargs):
            class Device:
                def __enter__(self):
                    kwargs['callback'](b'\x01\x00' * 1600, 1600, None, overflow)
                    return self
                def __exit__(self, *_):status['closed'] = True
            return Device()
        return factory, status

    def test_recording_stops_and_keeps_pcm_in_memory(self):
        stop, abandoned = threading.Event(), threading.Event()
        factory, state = self.device()
        audio = record(stop, abandoned, stop.set, factory=factory)
        self.assertTrue(state['closed'])
        with wave.open(audio) as stream:
            self.assertEqual((stream.getframerate(), stream.getnchannels(), stream.getnframes()), (16000, 1, 1600))
            self.assertEqual(stream.readframes(1600), b'\x01\x00' * 1600)

    def test_overflow_is_not_treated_as_complete_audio(self):
        stop, abandoned = threading.Event(), threading.Event()
        factory, state = self.device(overflow=True)
        with self.assertRaisesRegex(RuntimeError, '資料遺失'):
            record(stop, abandoned, stop.set, factory=factory)
        self.assertTrue(state['closed'])

    def process_factory(self, script):
        original, children = subprocess.Popen, []
        def create(command, **kwargs):
            child = original([sys.executable, '-X', 'utf8', '-c', script], **kwargs)
            children.append(child)
            return child
        return create, children

    def test_stop_command_reaches_worker_and_complete_result_returns(self):
        script = '''import json,sys
print(json.dumps({'type':'state','state':'recording'}),flush=True)
assert sys.stdin.readline().strip()=='stop'
print(json.dumps({'type':'state','state':'transcribing'}),flush=True)
print(json.dumps({'type':'result','result':{'completed':True,'truncated':False,'text':'不要刪除'}}),flush=True)
'''
        create, children = self.process_factory(script)
        stop, cancel = threading.Event(), threading.Event()
        states = []
        def observed(state):
            states.append(state)
            if state == 'recording':stop.set()
        with patch('desktop_ui.voice_session.subprocess.Popen', side_effect=create):
            result = run_voice('unused-model', stop, cancel, observed, timeout=3)
        self.assertEqual(result['text'], '不要刪除')
        self.assertEqual(states, ['recording', 'transcribing'])
        self.assertEqual(children[0].poll(), 0)

    def test_cancel_after_ready_reaps_child_without_a_transcript(self):
        create, children = self.process_factory('import json,time;print(json.dumps({"type":"state","state":"recording"}),flush=True);time.sleep(20)')
        stop, cancel = threading.Event(), threading.Event()
        with patch('desktop_ui.voice_session.subprocess.Popen', side_effect=create):
            with self.assertRaises(SpeechCancelled):
                run_voice('unused-model', stop, cancel, lambda _: cancel.set(), timeout=3)
        self.assertIsNotNone(children[0].poll())

    def test_owner_eof_exits_worker_even_when_recorder_is_blocked(self):
        # Replace the device path before main runs. This checks the actual EOF
        # thread without ever importing/opening a microphone driver.
        script = '''import sys,time
import desktop_ui.voice_worker as worker
def fake_record(stop,abandoned,ready):
 ready()
 time.sleep(20)
worker.record=fake_record
sys.argv=['voice-worker','--model-dir','unused-model']
worker.main()
'''
        original = subprocess.Popen
        children = []
        # Close a real owner pipe after recording becomes ready, instead of
        # supplying an invalid/non-pipe stdin descriptor from the outset.
        def launch(command, **kwargs):
            child = original([sys.executable, '-c', script], **kwargs)
            children.append(child)
            return child
        def close_owner(state):
            if state == 'recording': children[0].stdin.close()
        with patch('desktop_ui.voice_session.subprocess.Popen', side_effect=launch):
            with self.assertRaises(RuntimeError):
                run_voice('unused-model', threading.Event(), threading.Event(), close_owner, timeout=3)
        self.assertEqual(children[0].poll(), 2)

    def test_worker_exits_after_result_with_control_pipe_still_open(self):
        script = '''import io,sys
import desktop_ui.voice_worker as worker
import desktop_ui.asr_worker as asr
def fake_record(stop,abandoned,ready):
 ready()
 assert stop.wait(2)
 with open(worker.__file__,encoding='utf8') as source:assert source.read()
 return io.BytesIO()
worker.record=fake_record
asr.transcribe=lambda *args:{'completed':True,'truncated':False,'text':'已辨識'}
sys.argv=['voice-worker','--model-dir','unused-model']
worker.main()
'''
        create, children = self.process_factory(script)
        stop, cancel = threading.Event(), threading.Event()
        with patch('desktop_ui.voice_session.subprocess.Popen', side_effect=create):
            result = run_voice('unused-model', stop, cancel, lambda state: stop.set() if state=='recording' else None, timeout=3)
        self.assertEqual(result['text'], '已辨識')
        self.assertEqual(children[0].poll(), 0)


if __name__ == '__main__':
    unittest.main()
