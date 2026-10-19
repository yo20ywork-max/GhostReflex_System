"""Read-only verification of an Ollama manifest and every referenced local blob.

The manifest digest alone does not attest its files. No timestamp-based cache is
used: memory-mapped changes can retain a file's size and apparent modification time.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re


class ModelIntegrityError(ValueError):
    pass


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(manifest_path, blob_directory, expected_manifest_sha256=None):
    """Verify current on-disk bytes; no claim about already-loaded GPU memory."""
    manifest_path, blob_directory = Path(manifest_path), Path(blob_directory)
    original = manifest_path.read_bytes()
    manifest_hash = hashlib.sha256(original).hexdigest()
    if expected_manifest_sha256 is not None and manifest_hash != expected_manifest_sha256:
        raise ModelIntegrityError('Model manifest SHA256 mismatch')
    manifest = json.loads(original)
    config, layers = manifest.get('config'), manifest.get('layers')
    if not isinstance(config, dict) or not isinstance(layers, list) or not layers:
        raise ModelIntegrityError('Missing model config or layers')
    descriptors = {}
    for entry in [config, *layers]:
        if not isinstance(entry, dict):
            raise ModelIntegrityError('Invalid model blob descriptor')
        digest, size = entry.get('digest'), entry.get('size')
        if not isinstance(digest, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
            raise ModelIntegrityError('Invalid content-addressed blob digest')
        if type(size) is not int or size < 0:
            raise ModelIntegrityError('Invalid model blob size')
        if digest in descriptors and descriptors[digest] != size:
            raise ModelIntegrityError('Conflicting sizes for the same blob')
        descriptors[digest] = size
    records = []
    for digest, size in descriptors.items():
        path = blob_directory / digest.replace(':', '-')
        try:
            before = path.stat()
            if before.st_size != size:
                raise ModelIntegrityError(f'Model blob size mismatch: {path.name}')
            actual = file_sha256(path)
            after = path.stat()
        except OSError as exc:
            raise ModelIntegrityError(f'Model blob unavailable: {path.name}') from exc
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise ModelIntegrityError(f'Model blob changed during verification: {path.name}')
        if actual != digest.removeprefix('sha256:'):
            raise ModelIntegrityError(f'Model blob SHA256 mismatch: {path.name}; observed {actual}')
        records.append({'digest': digest, 'size': size, 'verified': True})
    if manifest_path.read_bytes() != original:
        raise ModelIntegrityError('Model manifest changed during verification')
    return {'manifest': str(manifest_path.resolve()), 'manifest_sha256': manifest_hash,
            'blobs': records, 'verified_bytes': sum(v for v in descriptors.values()),
            'all_blobs_verified': True,
            'scope': 'Current disk content integrity only; not loaded-memory integrity, model quality or release acceptance.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--blobs', type=Path, required=True)
    parser.add_argument('--expected-manifest-sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(verify_manifest(args.manifest, args.blobs, args.expected_manifest_sha256), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
