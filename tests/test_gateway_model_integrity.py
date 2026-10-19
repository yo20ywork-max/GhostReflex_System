import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import httpx
import ollama
from ollama_model_integrity import manifest_relative_path, OllamaModelIntegrityGuard
from model_blob_integrity import ModelIntegrityError
from test_gateway_completion import Gateway, scope


class GatewayModelIntegrity(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.model = 'test-model:latest'
        self.calls = []
        self.blob = self.root / 'blobs' / ('sha256-' + hashlib.sha256(b'good').hexdigest())
        self.blob.parent.mkdir()
        self.blob.write_bytes(b'good')
        descriptor = {'digest': 'sha256:' + self.blob.name[7:], 'size': 4}
        self.manifest = self.root / manifest_relative_path(self.model)
        self.manifest.parent.mkdir(parents=True)
        self.manifest.write_text(json.dumps({'config': descriptor, 'layers': [descriptor]}))
        self.digest = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        self.clients = []
        def transport(request):
            self.calls.append(request.url.path)
            if request.url.path == '/api/tags':
                return httpx.Response(200, json={'models': [{'model': self.model, 'digest': self.digest}]})
            return httpx.Response(200, json={'model': self.model, 'done': True, 'done_reason': 'stop',
                                           'message': {'role': 'assistant', 'content': '{"ok":true}'}})
        def client(**kwargs):
            c = ollama.Client(host='http://127.0.0.1:11434', transport=httpx.MockTransport(transport), **kwargs)
            self.clients.append(c)
            return c
        scope['ollama'] = SimpleNamespace(Client=client)
        env = patch.dict(os.environ, {'OLLAMA_MODELS': str(self.root)})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(lambda: [c._client.close() for c in self.clients])
        self.gateway = Gateway(SimpleNamespace(planner_models=(self.model,), planner_num_ctx=12288))

    def call(self):
        return self.gateway.chat_json(messages=[{'role': 'user', 'content': 'Return JSON'}], schema={'type': 'object'})

    def test_valid_disk_is_checked_before_real_sdk_chat_and_cached_within_task(self):
        import ollama_model_integrity as module
        with patch.object(module, 'verify_manifest', wraps=module.verify_manifest) as verifier:
            self.call()
            self.call()
            self.assertEqual(verifier.call_count, 1)
            self.gateway.begin_task()
            self.call()
            self.assertEqual(verifier.call_count, 2)
        self.assertEqual(self.calls[:2], ['/api/tags', '/api/chat'])

    def test_corrupt_disk_prevents_any_inference_and_is_not_cached_as_valid(self):
        self.blob.write_bytes(b'BAD!')
        with self.assertRaisesRegex(RuntimeError, '完整性檢查失敗'):
            self.call()
        self.assertNotIn('/api/chat', self.calls)
        self.blob.write_bytes(b'good')
        self.assertEqual(self.call()[0], {'ok': True})

    def test_new_task_detects_corruption_even_when_size_and_mtime_are_unchanged(self):
        self.call()
        stat = self.blob.stat()
        self.blob.write_bytes(b'BAD!')
        os.utime(self.blob, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.gateway.begin_task()
        with self.assertRaisesRegex(RuntimeError, '完整性檢查失敗'):
            self.call()
        self.assertEqual(self.calls.count('/api/chat'), 1)

    def test_server_manifest_change_invalidates_cached_verification(self):
        self.call()
        self.digest = '0' * 64
        with self.assertRaisesRegex(RuntimeError, 'manifest SHA256 mismatch'):
            self.call()
        self.assertEqual(self.calls.count('/api/chat'), 1)

    def test_remote_server_cannot_be_attested_by_local_files(self):
        client = SimpleNamespace(_client=SimpleNamespace(base_url='http://remote.example:11434'))
        with self.assertRaisesRegex(ModelIntegrityError, '遠端'):
            OllamaModelIntegrityGuard(client, self.root).ensure(self.model)

    def test_namespaces_tags_and_invalid_paths(self):
        self.assertEqual(manifest_relative_path('qwen2.5-coder:7b'), Path('manifests/registry.ollama.ai/library/qwen2.5-coder/7b'))
        self.assertEqual(manifest_relative_path('company/model'), Path('manifests/registry.ollama.ai/company/model/latest'))
        self.assertEqual(manifest_relative_path('hf.co/company/model:Q4'), Path('manifests/hf.co/company/model/Q4'))
        for name in ['../escape:latest', '/abs', 'model:', 'dir\\model', 'model:..']:
            with self.assertRaises(ModelIntegrityError):
                manifest_relative_path(name)


if __name__ == '__main__':
    unittest.main()
