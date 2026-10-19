"""Launch speech workers with a pipe-capable helper in frozen Windows builds."""
import sys
from pathlib import Path


def worker_command(kind, *arguments):
    if kind not in ('voice', 'asr'):
        raise ValueError('Unknown speech worker')
    if getattr(sys, 'frozen', False):
        root = Path(sys.executable).resolve().parent
        helper = root / 'CrossGen-Voice.exe'
        if not helper.is_file():
            raise RuntimeError('語音元件不完整，請重新解壓縮完整展示版。')
        return [str(helper), '--' + kind + '-worker', *arguments], root
    return [sys.executable, '-X', 'utf8', '-m', 'desktop_ui.' + kind + '_worker', *arguments], Path(__file__).resolve().parents[1]
