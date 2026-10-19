"""Local disk preflight for each model used within an agent task."""
import os
from pathlib import Path
import re
from urllib.parse import urlparse
from model_blob_integrity import ModelIntegrityError, verify_manifest


def manifest_relative_path(name):
    if not isinstance(name, str) or not name or '\\' in name:
        raise ModelIntegrityError('Invalid local model name')
    head, separator, tag = name.rpartition(':')
    if separator and '/' not in tag:
        name = head
    else:
        tag = 'latest'
    parts = name.split('/')
    if len(parts) == 1:
        parts = ['registry.ollama.ai', 'library', *parts]
    elif '.' not in parts[0] and ':' not in parts[0] and parts[0] != 'localhost':
        parts = ['registry.ollama.ai', *parts]
    if len(parts) < 3 or any(p in ('', '.', '..') or not re.fullmatch(r'[A-Za-z0-9._:-]+', p) for p in [*parts, tag]):
        raise ModelIntegrityError('Invalid local model path')
    return Path('manifests', *parts, tag)


def field(value, key, default=None):
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


class OllamaModelIntegrityGuard:
    def __init__(self, client, model_root=None):
        self.client = client
        self.root = Path(model_root) if model_root is not None else Path(os.environ.get('OLLAMA_MODELS') or Path.home() / '.ollama/models')
        self._verified = {}

    def begin_task(self):
        self._verified.clear()

    def ensure(self, name):
        host = urlparse(str(self.client._client.base_url)).hostname
        if host not in ('localhost', '127.0.0.1', '::1'):
            raise ModelIntegrityError('目前無法核對遠端模型檔案；此版本的完整性檢查需要本機 Ollama。')
        listing = self.client.list()
        canonical = name if ':' in name.rsplit('/', 1)[-1] else name + ':latest'
        entry = next((m for m in field(listing, 'models', []) if field(m, 'model', field(m, 'name')) in (name, canonical)), None)
        if entry is None:
            raise ModelIntegrityError(f'找不到已安裝模型：{name}')
        digest = field(entry, 'digest')
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ModelIntegrityError('模型服務未提供有效的檔案清單雜湊。')
        cached = self._verified.get(name)
        if cached is not None and cached['manifest_sha256'] == digest:
            return cached
        try:
            report = verify_manifest(self.root / manifest_relative_path(canonical), self.root / 'blobs', digest)
        except (OSError, ValueError) as exc:
            self._verified.pop(name, None)
            raise ModelIntegrityError(f'模型檔案完整性檢查失敗，尚未送出推論請求：{name}；{exc}') from exc
        self._verified[name] = report
        return report
