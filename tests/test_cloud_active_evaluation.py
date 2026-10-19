"""Execute the real remote-inventory program against mocked process observations."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cloud_inventory_check', ROOT / 'finetuning/release_v4/fetch_artifacts.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CloudActiveEvaluation(unittest.TestCase):
    def execute_inventory(self, root, argv):
        proc = MagicMock()
        proc.name = '999999999'
        proc.__truediv__.side_effect = lambda key: SimpleNamespace(resolve=lambda: root) if key == 'cwd' else SimpleNamespace(read_bytes=lambda: b'\0'.join(argv))
        proc_directory = SimpleNamespace(iterdir=lambda: [proc])
        actual_path = Path
        def paths(value):
            return proc_directory if value == '/proc' else actual_path(value)
        code = module.remote_inventory(None).replace('/workspace/crossgen-release-v4', root.as_posix())
        output = io.StringIO()
        with patch('pathlib.Path', side_effect=paths), contextlib.redirect_stdout(output):
            exec(compile(code, '<actual remote inventory>', 'exec'), {})
        return json.loads(output.getvalue())

    def test_live_native_evaluation_prevents_final_transfer(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'finetuning/release_v4') as directory:
            root = Path(directory).resolve()
            (root / 'DATA_LOCK.json').write_text('{"sha256":{}}')
            for script in (b'evaluate_native_adapter.py', b'/workspace/crossgen-release-v4/evaluate_native_adapter.py', b'train.py'):
                with self.subTest(script=script), self.assertRaisesRegex(RuntimeError, 'still active'):
                    self.execute_inventory(root, [b'python', script])

    def test_unrelated_process_does_not_block_terminal_inventory(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'finetuning/release_v4') as directory:
            root = Path(directory).resolve()
            (root / 'DATA_LOCK.json').write_text('{"sha256":{}}')
            result = self.execute_inventory(root, [b'python', b'-c', b'print(1)'])
            self.assertTrue(result['terminal_run'])
            self.assertEqual([row['path'] for row in result['files']], ['DATA_LOCK.json'])
