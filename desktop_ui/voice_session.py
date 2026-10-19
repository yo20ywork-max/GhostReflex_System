"""Control only an owned voice process; queued results cannot defeat cancellation."""
import collections
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from desktop_ui.speech import SpeechCancelled
from desktop_ui.worker_command import worker_command


def run_voice(model_dir, stop, cancel, on_state, timeout=210):
    if cancel.is_set():raise SpeechCancelled('已取消語音輸入。')
    command, root = worker_command('voice', '--model-dir', str(Path(model_dir).resolve()))
    environment = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', OMP_NUM_THREADS='4')
    process = subprocess.Popen(command, cwd=root, env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, encoding='utf8', creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    events, errors = queue.Queue(), collections.deque(maxlen=20)
    def read_output():
        for line in process.stdout:events.put(line)
        events.put(None)
    def read_errors():
        for line in process.stderr:errors.append(line[-1000:])
    readers = [threading.Thread(target=read_output, daemon=True), threading.Thread(target=read_errors, daemon=True)]
    for reader in readers:reader.start()
    deadline, stopped, result, eof = time.monotonic()+timeout, False, None, False
    try:
        while True:
            if cancel.is_set():raise SpeechCancelled('已取消語音輸入。')
            if time.monotonic()>deadline:raise TimeoutError('語音工作逾時，未送出部分文字。')
            if stop.is_set() and not stopped:
                stopped=True
                try:process.stdin.write('stop\n');process.stdin.flush()
                except (BrokenPipeError, OSError):pass
            try:line=events.get(timeout=0.1)
            except queue.Empty:line=''
            if line is None:eof=True
            elif line:
                if len(line)>200_000:raise ValueError('語音回應超過上限。')
                event=json.loads(line)
                if event.get('type')=='state' and event.get('state') in ('recording','transcribing'):on_state(event['state'])
                elif event.get('type')=='result':
                    if result is not None:raise ValueError('語音回應重複。')
                    result=event['result']
                else:raise ValueError('語音工作回應格式錯誤。')
            if eof and process.poll() is not None:break
        if cancel.is_set():raise SpeechCancelled('已取消語音輸入。')
        if process.returncode or result is None:raise RuntimeError('語音輸入未完成：'+''.join(errors)[-1000:])
        if result.get('completed') is not True or result.get('truncated') is not False or not isinstance(result.get('text'),str):
            raise ValueError('語音回應不完整。')
        return result
    finally:
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
        process.stdin.close()
        for reader in readers:reader.join(timeout=2)
        process.stdout.close();process.stderr.close()
