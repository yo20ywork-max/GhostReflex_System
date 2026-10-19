"""Explicitly started microphone worker; audio stays in memory and dies with the worker."""
import argparse
import io
import json
import os
import sys
import threading
import time
import traceback
import wave


def record(stop, abandoned, ready, factory=None, limit=120):
    if factory is None:
        import sounddevice
        factory = sounddevice.RawInputStream
    chunks, failures = [], []
    count = 0
    lock = threading.Lock()
    def callback(data, frames, timing, status):
        nonlocal count
        with lock:
            if stop.is_set() or failures:return
            if status:
                failures.append('麥克風資料遺失或裝置異常，未送出部分語音。');return
            count += frames
            if count > limit * 16000:
                failures.append('錄音超過120秒，未送出部分語音。');return
            chunks.append(bytes(data))
    if stop.is_set():raise RuntimeError('錄音已停止，沒有啟動麥克風。')
    with factory(samplerate=16000, channels=1, dtype='int16', blocksize=1600, callback=callback):
        ready()
        began = time.monotonic()
        while not stop.wait(0.05):
            if failures:break
            if time.monotonic()-began >= limit:
                failures.append('錄音超過120秒，未送出部分語音。');break
    if abandoned.is_set():raise RuntimeError('錄音工作已取消。')
    if failures:raise RuntimeError(failures[0])
    if not chunks:raise RuntimeError('沒有錄到音訊，請確認麥克風。')
    result = io.BytesIO()
    with wave.open(result, 'wb') as output:
        output.setnchannels(1);output.setsampwidth(2);output.setframerate(16000);output.writeframes(b''.join(chunks))
    result.seek(0)
    return result


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser();parser.add_argument('--model-dir', required=True);args = parser.parse_args()
    stop, abandoned = threading.Event(), threading.Event()
    def commands():
        pending=b''
        descriptor=sys.stdin.fileno()
        if os.name=='nt':
            import ctypes,msvcrt
            from ctypes import wintypes
            msvcrt.setmode(descriptor,os.O_BINARY)
            handle=msvcrt.get_osfhandle(descriptor)
            peek=ctypes.WinDLL('kernel32',use_last_error=True).PeekNamedPipe
            peek.argtypes=[wintypes.HANDLE,wintypes.LPVOID,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),ctypes.POINTER(wintypes.DWORD),ctypes.POINTER(wintypes.DWORD)]
            peek.restype=wintypes.BOOL
        else:
            import select
        while True:
            if os.name=='nt':
                available=wintypes.DWORD()
                if not peek(handle,None,0,None,ctypes.byref(available),None):break
                if not available.value:time.sleep(0.02);continue
                count=min(1024,available.value)
            else:
                if not select.select([descriptor],[],[],0.05)[0]:continue
                count=1024
            # Never block the Windows CRT descriptor lock while model/audio
            # files are being opened by the inference thread.
            chunk=os.read(descriptor,count)
            if not chunk:break
            pending+=chunk
            if len(pending)>4096:os._exit(2)
            while b'\n' in pending:
                line,pending=pending.split(b'\n',1)
                if line.strip()==b'stop':stop.set()
        abandoned.set();stop.set()
        # The owner closed/crashed. No disk audio or external action exists to
        # recover; end this worker even if a native audio/ASR call is blocked.
        os._exit(2)
    threading.Thread(target=commands, daemon=True).start()
    try:
        audio = record(stop, abandoned, lambda: emit({'type': 'state', 'state': 'recording'}))
        emit({'type': 'state', 'state': 'transcribing'})
        from desktop_ui.asr_worker import transcribe
        result = transcribe(args.model_dir, audio)
        emit({'type': 'result', 'result': result})
    except BaseException:
        traceback.print_exc();sys.stderr.flush();os._exit(1)
    # All recording resources have closed and the result was flushed. Avoid
    # interpreter shutdown waiting for the still-open control pipe reader.
    os._exit(0)


if __name__ == '__main__':
    main()
