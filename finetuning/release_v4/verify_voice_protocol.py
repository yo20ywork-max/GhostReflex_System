"""Actual owned voice worker + local ASR, substituting existing audio for capture."""
import hashlib
import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from desktop_ui.voice_session import run_voice


def main():
    audio = ROOT / 'mic_test.wav'
    model = ROOT / 'models/asr/faster-whisper-small'
    original, children = subprocess.Popen, []
    script = '''import io,sys
from pathlib import Path
import desktop_ui.voice_worker as worker
def fixture_record(stop,abandoned,ready,**kwargs):
 ready()
 assert stop.wait(5)
 return io.BytesIO(Path(AUDIO).read_bytes())
worker.record=fixture_record
sys.argv=['voice-worker','--model-dir',MODEL]
worker.main()
'''.replace('AUDIO', repr(str(audio))).replace('MODEL', repr(str(model)))
    def launch(command, **kwargs):
        child = original([sys.executable, '-X', 'utf8', '-c', script], **kwargs)
        children.append(child)
        return child
    stop, cancel, states = threading.Event(), threading.Event(), []
    began = time.monotonic()
    def status(state):
        states.append({'state': state, 'seconds': time.monotonic()-began})
        print(json.dumps(states[-1]), flush=True)
        if state == 'recording': stop.set()
    receipt = {'utc': datetime.now(timezone.utc).isoformat(),
               'capture_simulated_from_existing_file': True,
               'actual_whisper_inference': True, 'microphone_opened': False,
               'task_dispatched': False, 'accuracy_verified': False,
               'release_approved': False, 'audio_sha256': hashlib.sha256(audio.read_bytes()).hexdigest(),
               'sources': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                           ['desktop_ui/voice_worker.py', 'desktop_ui/voice_session.py',
                            'desktop_ui/asr_worker.py', 'finetuning/release_v4/verify_voice_protocol.py']}}
    try:
        with patch('desktop_ui.voice_session.subprocess.Popen', side_effect=launch):
            receipt['result'] = run_voice(model, stop, cancel, status, timeout=30)
        receipt['passed'] = True
    except Exception as exc:
        receipt.update(passed=False, error=f'{type(exc).__name__}: {exc}')
    receipt.update(states=states, seconds=time.monotonic()-began,
                   child_exit_codes=[child.poll() for child in children])
    destination = Path(__file__).parent / 'speech/voice-protocol-real-asr.json'
    destination.write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps(receipt, ensure_ascii=False), flush=True)
    return 0 if receipt['passed'] and receipt['child_exit_codes'] == [0] else 1


if __name__ == '__main__':
    raise SystemExit(main())
