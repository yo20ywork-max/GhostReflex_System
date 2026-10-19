"""One bounded, local-only Whisper request. No microphone access or tool execution."""
import argparse
import io
import json
import time
from pathlib import Path


def transcribe(model_dir, audio_path):
    import numpy as np
    from faster_whisper import WhisperModel
    from opencc import OpenCC
    import av
    model_dir = Path(model_dir)
    if isinstance(audio_path, io.BytesIO):
        audio_source, size = audio_path, audio_path.getbuffer().nbytes
    else:
        audio_path = Path(audio_path)
        if not audio_path.is_file():raise ValueError('找不到本機音檔。')
        audio_source, size = str(audio_path), audio_path.stat().st_size
    if not model_dir.is_dir():
        raise ValueError('找不到本機語音模型或音檔。')
    if size > 16_000_000:
        raise ValueError('音檔超過單次辨識的16MB上限；尚未辨識或截斷。')
    began = time.perf_counter()
    samples, count = [], 0
    resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
    with av.open(audio_source) as container:
        for frame in container.decode(audio=0):
            for converted in resampler.resample(frame):
                count += converted.samples
                if count > 120 * 16000:
                    raise ValueError('音訊超過120秒，未送出部分文字。')
                samples.append(converted.to_ndarray().reshape(-1))
        for converted in resampler.resample(None):
            count += converted.samples
            if count > 120 * 16000:
                raise ValueError('音訊超過120秒，未送出部分文字。')
            samples.append(converted.to_ndarray().reshape(-1))
    audio = np.concatenate(samples).astype(np.float32) / 32768.0 if samples else np.empty(0, dtype=np.float32)
    duration = len(audio) / 16000
    if not 0 < duration <= 120 or not np.isfinite(audio).all():
        raise ValueError('需使用120秒以內的有效音訊；尚未辨識或截斷。')
    model = WhisperModel(str(model_dir), device='cpu', compute_type='int8', cpu_threads=4, num_workers=1, local_files_only=True)
    loaded = time.perf_counter()
    segments, info = model.transcribe(audio, language='zh', task='transcribe', beam_size=5, temperature=0,
                                      condition_on_previous_text=False, vad_filter=True,
                                      vad_parameters={'min_silence_duration_ms': 500},
                                      initial_prompt='以下是台灣使用者的語音，請以繁體中文轉錄。')
    records = [{'start': s.start, 'end': s.end, 'text': s.text, 'avg_logprob': s.avg_logprob, 'no_speech_prob': s.no_speech_prob} for s in segments]
    if any(not 0 <= s['start'] <= s['end'] <= duration + 0.25 for s in records):
        raise ValueError('辨識時間範圍異常，不能視為完整轉錄。')
    converter = OpenCC('s2twp')
    for segment in records:
        segment['text'] = converter.convert(segment['text'])
    return {'text': ''.join(s['text'] for s in records).strip(), 'segments': records,
            'audio_seconds': duration, 'speech_seconds': info.duration_after_vad,
            'load_seconds': loaded - began, 'transcribe_seconds': time.perf_counter() - loaded,
            'device': 'cpu', 'compute_type': 'int8', 'cpu_threads': 4,
            'truncated': False, 'completed': True, 'accuracy_verified': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-dir', required=True)
    parser.add_argument('--audio', required=True)
    args = parser.parse_args()
    result = transcribe(args.model_dir, args.audio)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
