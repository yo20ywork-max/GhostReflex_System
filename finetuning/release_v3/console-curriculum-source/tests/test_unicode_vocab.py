import ast
import json
from pathlib import Path
import unittest
from typing import Any, Optional
from types import SimpleNamespace

import torch
import torch.nn as nn
from torch.utils.data import Dataset

from core_model import MicroGLRNet
from tokenizer import UnicodeTokenizer, extend_vocab
from lora_layer import inject_lora_to_model


ROOT = Path(__file__).resolve().parents[1]


class UnicodeVocabularyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)
        cls.tokenizer = UnicodeTokenizer.load(ROOT / "vocab.json")

    def test_all_unicode_scalar_values_round_trip(self):
        # Includes rare/unassigned code points, combining marks and controls.
        for start in range(0, 0x110000, 4096):
            text = "".join(chr(i) for i in range(start, min(start + 4096, 0x110000))
                           if not 0xD800 <= i <= 0xDFFF)
            ids = self.tokenizer.encode(text)
            self.assertNotIn(1, ids)
            self.assertEqual(self.tokenizer.decode(ids), text)

    def test_mixed_text_and_literal_special_tokens(self):
        text = '臺灣台灣简体𠮷𰻞 café e\u0301 日本語 한국어 العربية 👩🏽‍💻 <UNK> <0xFF>\n\t'
        self.assertEqual(self.tokenizer.decode(self.tokenizer.encode(text)), text)
        with self.assertRaises(ValueError):
            self.tokenizer.encode('\ud800')

    def test_extension_is_idempotent_and_preserves_ids(self):
        vocab = self.tokenizer.vocab
        self.assertEqual(extend_vocab(vocab), vocab)
        legacy_size = torch.load(ROOT / "micro_glr_checkpoint.pt", weights_only=True,
                                 map_location="cpu")["vocab_migration"]["original_size"]
        legacy = {t: i for t, i in vocab.items() if i < legacy_size}
        self.assertEqual(extend_vocab(legacy), vocab)
        text = ''.join(t for t in legacy if len(t) == 1)
        self.assertEqual(self.tokenizer.encode(text), [legacy[c] for c in text])

    def test_character_boundary_truncation(self):
        self.assertEqual(self.tokenizer.encode_prefix('𠮷', 3), [])
        ids = self.tokenizer.encode_prefix('𠮷abc', 4)
        self.assertEqual(self.tokenizer.decode(ids), '𠮷')

    def test_checkpoint_forward_and_backward(self):
        checkpoint = torch.load(ROOT / "micro_glr_checkpoint.pt", weights_only=True, map_location="cpu")
        self.assertEqual(checkpoint['vocab'], self.tokenizer.vocab)
        model = MicroGLRNet(len(self.tokenizer.vocab))
        model.load_state_dict(checkpoint['model_state_dict'], strict=True)
        self.assertIs(model.embedding.weight, model.lm_head.weight)
        ids = torch.tensor([self.tokenizer.encode('𠮷👩🏽‍💻中文')])
        output = model(ids)
        self.assertEqual(output.shape, (1, ids.shape[1], len(self.tokenizer.vocab)))
        loss = nn.functional.cross_entropy(output[:, :-1].reshape(-1, output.shape[-1]),
                                          ids[:, 1:].reshape(-1))
        self.assertTrue(torch.isfinite(loss))
        loss.backward()
        self.assertTrue(torch.isfinite(model.embedding.weight.grad).all())

    def test_training_dataset_uses_shared_tokenizer(self):
        # Load only dataset definitions; never execute the training entrypoint.
        tree = ast.parse((ROOT / 'train.py').read_text(encoding='utf-8-sig'))
        definitions = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))]
        ns = dict(torch=torch, nn=nn, Dataset=Dataset, UnicodeTokenizer=UnicodeTokenizer)
        exec(compile(ast.Module(body=definitions, type_ignores=[]), 'train_definitions', 'exec'), ns)
        seq = '[FRAG:𠮷👩🏽‍💻] [SEP] [TARGET:臺灣]'
        dataset = ns['TrainDataset']([seq], self.tokenizer.vocab)
        x, y = dataset[0]
        self.assertNotIn(1, x.tolist())
        self.assertEqual(self.tokenizer.decode(x.tolist()), seq)
        prefix = self.tokenizer.encode('[FRAG:𠮷👩🏽‍💻] [SEP] ')
        self.assertTrue((y[:len(prefix)-1] == -100).all())
        self.assertNotEqual(y[len(prefix)-1], -100)
        with self.assertRaises(ValueError):
            ns['TrainDataset']([seq], self.tokenizer.vocab, max_len=4)

    def test_actual_hint_engine_load_and_inference(self):
        # Use the real engine class without importing desktop/audio side effects.
        tree = ast.parse((ROOT / 'run_daemon.py').read_text(encoding='utf-8-sig'))
        engine = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MicroGLRHintEngine')
        console = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'console_print')
        ns = dict(torch=torch, MicroGLRNet=MicroGLRNet, UnicodeTokenizer=UnicodeTokenizer,
                  Optional=Optional, Any=Any, Settings=object, BASE_DIR=ROOT, json=json,
                  active_window_title=lambda: '測試𠮷👩🏽‍💻')
        import re
        ns['re'] = re
        exec(compile(ast.Module(body=[console, engine], type_ignores=[]), 'hint_engine', 'exec'), ns)
        disabled = ns['MicroGLRHintEngine'](SimpleNamespace())
        self.assertIsNone(disabled.model)
        self.assertIsNone(disabled.hint('任意文字'))
        hint = ns['MicroGLRHintEngine'](SimpleNamespace(use_micro_hint=True))
        self.assertIsNotNone(hint.model)
        result = hint.hint('幫我輸入𠮷👩🏽‍💻')
        self.assertIsNotNone(result)
        self.assertIn('action_hint', result)

    def test_actual_lora_merge_can_reload_plain_model(self):
        model = inject_lora_to_model(MicroGLRNet(len(self.tokenizer.vocab)), r=4).eval()
        with torch.no_grad():
            for name, parameter in model.named_parameters():
                if name.endswith('lora_B'):
                    parameter.fill_(0.001)
        x = torch.tensor([self.tokenizer.encode('臺灣𠮷')])
        with torch.no_grad():
            before = model(x)
        tree = ast.parse((ROOT / 'auto_evolver.py').read_text(encoding='utf-8-sig'))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run_lora_evolution')
        merge = next(n for n in fn.body if isinstance(n, ast.With)
                     and isinstance(n.items[0].context_expr, ast.Call)
                     and isinstance(n.items[0].context_expr.func, ast.Attribute)
                     and n.items[0].context_expr.func.attr == 'no_grad')
        exec(compile(ast.Module(body=[merge], type_ignores=[]), 'actual_merge', 'exec'),
             dict(torch=torch, model=model))
        restored = MicroGLRNet(len(self.tokenizer.vocab)).eval()
        restored.load_state_dict(model.state_dict(), strict=True)
        with torch.no_grad():
            torch.testing.assert_close(restored(x), before, rtol=1e-4, atol=1e-5)


if __name__ == '__main__':
    unittest.main()
