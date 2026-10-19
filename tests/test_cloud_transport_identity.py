"""Wrong-pod rejection and fresh identity checks without any cloud mutation."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('v4_transport_test',ROOT/'finetuning/release_v4/remote.py')
transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)


class CloudTransportIdentity(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'finetuning/release_v4',prefix='transport-check-')
        self.root=Path(self.temp.name);(self.root/'DATA_LOCK.json').write_bytes(b'locked')
        self.state={'status':'created','pod':{'id':'expected-pod'}}
        (self.root/'CLOUD_RUN.json').write_text(json.dumps(self.state),encoding='utf8')
        self.identity={'pod_id':'expected-pod','data_lock_sha256':hashlib.sha256(b'locked').hexdigest()}
        self.patcher=patch.object(transport,'R',self.root);self.patcher.start()
    def tearDown(self):self.patcher.stop();self.temp.cleanup()

    def test_reject_wrong_pod_and_changed_lock(self):
        for value in [dict(self.identity,pod_id='other'),dict(self.identity,data_lock_sha256='0'*64),dict(self.identity,data_lock_sha256=None)]:
            with self.assertRaises(ValueError):transport.verify_identity(value,self.state)
        transport.verify_identity(self.identity,self.state)

    def test_fallback_requires_fresh_probe_not_only_cached_receipt(self):
        cached={'pod_id':'expected-pod','endpoint':{'ip':'127.0.0.1','port':22,'ssh_key':{'path':'unused'}}}
        (self.root/'SSH_ENDPOINT_VERIFIED.json').write_text(json.dumps(cached),encoding='utf8')
        with patch.object(transport.subprocess,'check_output',return_value='{"error":"pod not ready"}'),patch.object(transport,'probe',return_value=(('host','22',[]),self.identity)) as probe:
            self.assertEqual(transport.connection(),('host','22',[]))
            probe.assert_called_once_with(cached['endpoint'],self.state)
        self.assertTrue((self.root/'SSH_FALLBACK_OBSERVATION.json').exists())

    def test_wrong_cached_pod_is_rejected_without_ssh(self):
        (self.root/'SSH_ENDPOINT_VERIFIED.json').write_text(json.dumps({'pod_id':'other'}),encoding='utf8')
        with patch.object(transport.subprocess,'check_output',return_value='{"error":"pod not ready"}'),patch.object(transport,'probe') as probe:
            with self.assertRaises(ValueError):transport.connection()
            probe.assert_not_called()

    def test_deleted_pod_never_reuses_cached_endpoint(self):
        (self.root/'CLOUD_RUN.json').write_text(json.dumps(dict(self.state,status='deleted')),encoding='utf8')
        with patch.object(transport.subprocess,'check_output') as command:
            with self.assertRaises(RuntimeError):transport.connection()
            command.assert_not_called()


if __name__=='__main__':unittest.main()
