import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'finetuning/contract_v8'))
from desktop_contract import contract
from copy_fixture import CopyFixture


class DesktopContract(unittest.TestCase):
    def test_exported_schema_and_prompt_match_registered_execution_runtime(self):
        catalog, schema, prompt, _ = contract()
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.desktop-contract-') as folder:
            fixture = CopyFixture({'id': 'catalog', 'user_request': '檢查契約', 'initial_files': {}, 'write_targets': {}}, folder, 'scripted', None)
            try:
                self.assertEqual(catalog, fixture.catalog)
                self.assertEqual(schema, fixture.schema)
                planner = fixture.scope['Planner'].__new__(fixture.scope['Planner'])
                planner.catalog = fixture.catalog
                planner.schema = fixture.schema
                self.assertEqual(prompt(SimpleNamespace(catalog=catalog, schema=schema)), planner._system_prompt())
                self.assertEqual(sum(x['name'] == 'COPY_FILE_VERIFIED' for x in catalog), 1)
            finally:
                fixture.close()

    def test_actual_copy_delivers_exact_binary_and_checker_sees_real_evidence(self):
        content = bytes(range(256)) * 5 + b'\x00\xff'
        class Gateway:
            def chat_json(self, *, messages, schema, models=None):
                if 'complete' in schema['properties']:
                    history = json.loads(messages[-1]['content'])['observed_history']
                    assert history[0]['tool'] == 'COPY_FILE_VERIFIED'
                    assert history[0]['evidence']['destination_readback_verified'] is True
                    return {'complete': True, 'reason': 'scripted'}, 'scripted'
                return {'objective': '複製', 'assumptions': [], 'completion_criteria': ['原樣複製並回覆'], 'steps': [
                    {'id': 1, 'goal': '複製', 'tool': 'COPY_FILE_VERIFIED', 'args': {'source': '原稿.bin', 'destination': '副本.bin', 'if_exists': 'error'}, 'success_check': '核對位元組'},
                    {'id': 2, 'goal': '回覆', 'tool': 'FINAL_RESPONSE', 'args': {'message': '已核對'}, 'success_check': '回覆'}]}, 'scripted'
        gateway = Gateway()
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.desktop-copy-') as folder:
            fixture = CopyFixture({'id': 'copy', 'user_request': '原樣複製原稿.bin到副本.bin，不覆寫，核對後回覆「已核對」。', 'initial_files': {}, 'write_targets': {}}, folder, 'scripted', gateway)
            try:
                (fixture.work/'原稿.bin').write_bytes(content)
                result, receipts, _ = fixture.run('scripted', gateway)
                self.assertEqual(result.status, 'completed')
                self.assertEqual(result.message, '已核對')
                self.assertEqual((fixture.work/'副本.bin').read_bytes(), content)
                self.assertEqual((fixture.work/'原稿.bin').read_bytes(), content)
                self.assertEqual([x['tool'] for x in receipts], ['COPY_FILE_VERIFIED', 'FINAL_RESPONSE'])
            finally:
                fixture.close()


if __name__ == '__main__':
    unittest.main()
