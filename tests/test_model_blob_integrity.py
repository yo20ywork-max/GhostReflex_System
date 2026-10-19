import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import model_blob_integrity as integrity


class BlobIntegrity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / 'model'
        self.blobs = self.root / 'blobs'
        self.blobs.mkdir()
        self.config = self.add_blob(b'{}')
        self.weights = self.add_blob(b'correct weights')
        self.data = {'config': self.config, 'layers': [self.weights]}
        self.save()

    def add_blob(self, content):
        digest = hashlib.sha256(content).hexdigest()
        (self.blobs / ('sha256-' + digest)).write_bytes(content)
        return {'digest': 'sha256:' + digest, 'size': len(content)}

    def save(self):
        self.manifest.write_text(json.dumps(self.data))
        self.manifest_hash = integrity.file_sha256(self.manifest)

    def verify(self):
        return integrity.verify_manifest(self.manifest, self.blobs, self.manifest_hash)

    def test_valid_manifest_deduplicates_and_handles_empty_blob(self):
        self.data['layers'] += [self.weights, self.add_blob(b'')]
        self.save()
        report = self.verify()
        self.assertTrue(report['all_blobs_verified'])
        self.assertEqual(len(report['blobs']), 3)
        self.assertEqual(report['verified_bytes'], len(b'{}correct weights'))

    def test_same_size_same_timestamp_corruption_is_detected(self):
        self.verify()
        path = self.blobs / self.weights['digest'].replace(':', '-')
        stat = path.stat()
        path.write_bytes(b'corrupt weights')
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.assertEqual(path.stat().st_size, stat.st_size)
        self.assertEqual(path.stat().st_mtime_ns, stat.st_mtime_ns)
        with self.assertRaisesRegex(integrity.ModelIntegrityError, 'SHA256 mismatch'):
            self.verify()

    def test_changed_manifest_is_rejected(self):
        self.manifest.write_text(json.dumps(self.data) + '\n')
        with self.assertRaisesRegex(integrity.ModelIntegrityError, 'manifest SHA256 mismatch'):
            self.verify()

    def test_missing_and_truncated_blobs_are_rejected(self):
        path = self.blobs / self.weights['digest'].replace(':', '-')
        path.write_bytes(b'short')
        with self.assertRaisesRegex(integrity.ModelIntegrityError, 'size mismatch'):
            self.verify()
        path.unlink()
        with self.assertRaisesRegex(integrity.ModelIntegrityError, 'unavailable'):
            self.verify()

    def test_invalid_digest_cannot_escape_blob_directory(self):
        for value in ['../private', 'sha256:../private', 'sha256:' + 'z' * 64]:
            self.data['layers'][0]['digest'] = value
            self.save()
            with self.assertRaisesRegex(integrity.ModelIntegrityError, 'digest'):
                self.verify()

    def test_missing_layers_and_invalid_sizes_are_rejected(self):
        for size in [-1, True, '15']:
            self.data['layers'][0]['size'] = size
            self.save()
            with self.assertRaisesRegex(integrity.ModelIntegrityError, 'size'):
                self.verify()
        self.data['layers'] = []
        self.save()
        with self.assertRaisesRegex(integrity.ModelIntegrityError, 'Missing'):
            self.verify()

    def test_conflicting_duplicate_sizes_are_rejected(self):
        self.data['layers'].append({**self.weights, 'size': 999})
        self.save()
        with self.assertRaisesRegex(integrity.ModelIntegrityError, 'Conflicting'):
            self.verify()

    def test_mid_read_manifest_mutation_is_rejected(self):
        real = integrity.file_sha256
        def changed(path):
            value = real(path)
            self.manifest.write_text(json.dumps(self.data) + '\n')
            return value
        with patch.object(integrity, 'file_sha256', side_effect=changed):
            with self.assertRaisesRegex(integrity.ModelIntegrityError, 'manifest changed'):
                self.verify()


if __name__ == '__main__':
    unittest.main()
