"""Retention checks run without cloud credentials or mutation tools."""
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

R = Path(__file__).resolve().parents[1]/'finetuning/release_v4'
sys.path.insert(0, str(R))
spec = importlib.util.spec_from_file_location('v4_cleanup_gate', R/'finish_cloud.py')
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)
sys.path.pop(0)


class CleanupGate(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='cleanup-verification-', dir=R)
        self.root = Path(self.directory.name).resolve()
        self.assertTrue(self.root.is_relative_to(R.resolve()))
        (self.root/'artifacts').mkdir()
        data = {'config.json': b'{"training":"fixture"}'}
        lock = {'sha256': {name: hashlib.sha256(value).hexdigest() for name,value in data.items()}}
        data['DATA_LOCK.json'] = json.dumps(lock).encode()
        for name,value in data.items():
            (self.root/name).write_bytes(value)
            (self.root/'artifacts'/name).write_bytes(value)
        self.receipt = {'epoch': None, 'terminal_run': True, 'transfer_verified': True,
                        'training_completed_and_reload_verified': False,
                        'files': [{'path': name, 'bytes':len(value), 'sha256':hashlib.sha256(value).hexdigest()} for name,value in data.items()],
                        'total_bytes':sum(map(len,data.values()))}
        self.save()

    def save(self):
        (self.root/'FINAL_TRANSFER_VERIFIED.json').write_text(json.dumps(self.receipt), encoding='utf8')

    def tearDown(self):
        self.assertTrue(self.root.is_relative_to(R.resolve()))
        self.directory.cleanup()

    def test_complete_transfer_of_failed_training_is_retainable(self):
        result = cleanup.local_receipt(self.root)
        self.assertFalse(result['training_completed_and_reload_verified'])

    def test_modified_local_artifact_blocks_cleanup(self):
        (self.root/'artifacts/config.json').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Retained artifact changed'):
            cleanup.local_receipt(self.root)

    def test_epoch_only_receipt_cannot_authorize_cleanup(self):
        self.receipt.update(epoch=1, terminal_run=False);self.save()
        with self.assertRaisesRegex(ValueError,'terminal transfer'):
            cleanup.local_receipt(self.root)


if __name__ == '__main__': unittest.main()
