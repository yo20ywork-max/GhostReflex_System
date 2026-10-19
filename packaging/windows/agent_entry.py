"""Frozen entry point, including explicit offline diagnostic commands."""
import json
import os
from pathlib import Path
import sys


def main():
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace', line_buffering=True)
    import run_daemon as agent
    if '--self-check' in sys.argv:
        required = ['np', 'sd', 'ollama', 'opencc', 'torch', 'pynput_keyboard', 'AutoModel', 'MicroGLRNet']
        missing = [name for name in required if getattr(agent, name) is None]
        if missing:
            raise RuntimeError('Missing runtime dependencies: ' + ', '.join(missing))
        from playwright.sync_api import sync_playwright
        print(json.dumps({'dependencies': 'ok', 'torch': agent.torch.__version__, 'tools': len(agent.TOOL_REGISTRY)}), flush=True)
        return agent.self_test(agent.Settings.from_env())
    if '--asr-check' in sys.argv:
        import soundfile as sf
        import numpy as np
        from scipy.signal import resample_poly
        from math import gcd
        wav = Path(sys.argv[sys.argv.index('--asr-check') + 1])
        output = Path(sys.argv[sys.argv.index('--result') + 1])
        audio, rate = sf.read(wav, dtype='float32')
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if rate != 16000:
            factor = gcd(rate, 16000)
            audio = resample_poly(audio, 16000 // factor, rate // factor)
        model = agent.AutoModel(model=os.environ['GHOST_ASR_MODEL'], hub='ms', device='cpu', disable_update=True)
        raw = model.generate(input=np.asarray(audio, dtype=np.float32), hotword=agent.VoiceEngine.HOTWORDS)[0]['text']
        normalized = agent.opencc.OpenCC('s2twp').convert(raw)
        result = {'raw': raw, 'normalized': normalized, 'microphone_used': False, 'frozen': bool(getattr(sys, 'frozen', False))}
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0
    return agent.main()


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
