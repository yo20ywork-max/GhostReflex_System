import json
from pathlib import Path
import tempfile
import unittest
import torch
from safetensors.torch import load_file, save_file
from export_counter import export


class CounterExportTests(unittest.TestCase):
    def test_saved_adapter_scaling_matches_signed_operator(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            a,b=root/'chosen',root/'error'
            a.mkdir(); b.mkdir()
            config={'peft_type':'LORA','base_model_name_or_path':'test-base', 'r':2,
                    'lora_alpha':4,'target_modules':['q_proj','v_proj'],'task_type':'CAUSAL_LM'}
            for path in (a,b):
                (path/'adapter_config.json').write_text(json.dumps(config))
            config['target_modules'].reverse()
            (b/'adapter_config.json').write_text(json.dumps(config))
            torch.manual_seed(42)
            prefix='base_model.model.layers.0.self_attn.q_proj'
            ak,bk=prefix+'.lora_A.weight',prefix+'.lora_B.weight'
            left={ak:torch.randn(2,4),bk:torch.randn(3,2)}
            right={ak:torch.randn(2,4),bk:torch.randn(3,2)}
            save_file(left,a/'adapter_model.safetensors')
            save_file(right,b/'adapter_model.safetensors')
            export(a,b,root/'result',0.1)
            weights=load_file(root/'result/adapter_model.safetensors')
            saved=json.loads((root/'result/adapter_config.json').read_text())
            actual=(saved['lora_alpha']/saved['r'])*weights[bk]@weights[ak]
            expected=2*left[bk]@left[ak]-0.2*right[bk]@right[ak]
            torch.testing.assert_close(actual,expected)
            self.assertEqual(saved['r'],4)


if __name__=='__main__':
    unittest.main()
