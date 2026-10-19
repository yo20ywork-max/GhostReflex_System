"""Launch rejection is before model loading, not a status-only convention."""
import importlib.util
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('v11_launch',ROOT/'finetuning/release_v11/launch_guard.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class TrainingLaunchGuard(unittest.TestCase):
    def test_pending_expired_unbounded_and_wrong_mode_are_blocked(self):
        now=datetime.now(timezone.utc)
        valid=dict(launch_allowed=True,temporary_storage_user_approved=True,allowed_modes=['preflight'],max_temporary_gib=30,max_charge_usd=5,max_run_seconds=1800,pod_id='test-only-pod',deadline_utc=(now+timedelta(minutes=10)).isoformat())
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);lock={'sha256':{'LAUNCH_STATUS.json':'already-verified-by-caller'}}
            for change in ({'launch_allowed':False},{'launch_allowed':'true'},{'temporary_storage_user_approved':False},{'max_charge_usd':0},{'max_temporary_gib':float('nan')},{'max_run_seconds':True},{'pod_id':''},{'deadline_utc':now.isoformat()},{'allowed_modes':['train']}):
                (root/'LAUNCH_STATUS.json').write_text(json.dumps(dict(valid,**change)),encoding='utf8')
                with self.assertRaises(RuntimeError):module.require_launch(root,lock,mode='preflight',now=now)
            (root/'LAUNCH_STATUS.json').write_text(json.dumps(valid),encoding='utf8')
            self.assertEqual(module.require_launch(root,lock,mode='preflight',now=now)['pod_id'],'test-only-pod')
            with self.assertRaises(RuntimeError):module.require_launch(root,{'sha256':{}},mode='preflight',now=now)


if __name__=='__main__':unittest.main()
