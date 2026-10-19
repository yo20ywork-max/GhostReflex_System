"""Exercise actual console boundary with strict legacy streams and no console."""
import ast
import io
import unittest
from pathlib import Path
from unittest.mock import patch


source = (Path(__file__).resolve().parents[1] / 'run_daemon.py').read_text(encoding='utf-8-sig')
node = next(n for n in ast.parse(source).body if getattr(n, 'name', '') == 'console_print')
module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), node], type_ignores=[])
scope = {}
exec(compile(ast.fix_missing_locations(module), '<actual console output>', 'exec'), scope)
console_print = scope['console_print']


class ConsoleOutput(unittest.TestCase):
    def test_cp950_display_does_not_corrupt_input_or_raise(self):
        original = '台灣 🎞️ 😀 𠮷 {{step:999.output}}\r\n'
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding='cp950', errors='strict', newline='')
        with patch('sys.stdout', stream):
            console_print(original, end='', flush=True)
        expected = original.encode('cp950', errors='backslashreplace')
        self.assertEqual(raw.getvalue(), expected)
        self.assertIn('😀', original)

    def test_utf8_keeps_exact_text_separator_and_end(self):
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding='utf8', newline='')
        console_print('台灣😀', '原文', sep='\t', end='\r\n', file=stream, flush=True)
        self.assertEqual(raw.getvalue(), '台灣😀\t原文\r\n'.encode('utf8'))

    def test_windowed_and_closed_console_are_nonfatal(self):
        with patch('sys.stdout', None):
            console_print('任務結果😀')
        stream = io.StringIO()
        stream.close()
        console_print('已經執行，不應重試', file=stream)

    def test_broken_pipe_does_not_interrupt_worker(self):
        class Broken:
            encoding = 'utf8'
            def write(self, value):
                raise BrokenPipeError('viewer closed')
        console_print('已完成的工具回應', file=Broken())


if __name__ == '__main__':
    unittest.main()
