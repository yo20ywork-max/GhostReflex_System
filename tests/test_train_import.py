"""Importing a training module must not start training or require its dataset."""
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TrainImport(unittest.TestCase):
    def test_import_has_no_training_or_filesystem_side_effect(self):
        root=Path(__file__).resolve().parents[1]
        protected=[root/'vocab.json',root/'micro_glr_checkpoint.pt']
        before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
        with tempfile.TemporaryDirectory(dir=root/'finetuning/release_v3',prefix='import-check-') as temporary:
            code=f'import sys; sys.path.insert(0, {str(root)!r}); import train; assert callable(train.main); assert train.CHECKPOINT_PATH == "micro_glr_checkpoint.pt"; print("IMPORT_SAFE")'
            completed=subprocess.run([sys.executable,'-X','utf8','-c',code],cwd=temporary,capture_output=True,text=True,encoding='utf8',timeout=30)
            self.assertEqual(completed.returncode,0,completed.stderr+completed.stdout)
            self.assertEqual(completed.stdout.strip(),'IMPORT_SAFE')
            self.assertEqual(list(Path(temporary).iterdir()),[])
        self.assertEqual({p:hashlib.sha256(p.read_bytes()).hexdigest() for p in protected},before)


if __name__=='__main__':unittest.main()
