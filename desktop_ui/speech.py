"""Cancelable CPU speech subprocess; canceling can never submit a partial transcript."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from desktop_ui.worker_command import worker_command


class SpeechCancelled(Exception):
    pass


def transcribe_file(audio, model_dir, cancel_event=None, timeout=75):
    if timeout <= 0:
        raise ValueError('Timeout must be positive')
    if cancel_event is not None and cancel_event.is_set():
        raise SpeechCancelled('已取消語音辨識。')
    environment = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', OMP_NUM_THREADS='4')
    command, root = worker_command('asr', '--audio', str(Path(audio).resolve()), '--model-dir', str(Path(model_dir).resolve()))
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    process = subprocess.Popen(command, cwd=root, env=environment, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf8', creationflags=flags)
    deadline = time.monotonic() + timeout
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise SpeechCancelled('已取消語音辨識。')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('語音辨識逾時，未送出部分文字。')
            try:
                output, error = process.communicate(timeout=min(0.2, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
        if cancel_event is not None and cancel_event.is_set():
            raise SpeechCancelled('已取消語音辨識。')
        if process.returncode:
            raise RuntimeError('語音辨識未完成：' + error[-1000:])
        result = json.loads(output)
        if result.get('completed') is not True or result.get('truncated') is not False or not isinstance(result.get('text'), str):
            raise ValueError('語音結果不完整，尚未送出。')
        return result
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()
