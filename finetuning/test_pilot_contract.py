import copy
import json
from pathlib import Path
import unittest

from build_product_data import check, contract
from train_pilot import validate


class PilotContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog, cls.schema, _, _ = contract()
        cls.tools = {entry['name']:entry for entry in cls.catalog}
        cls.data = json.loads(Path(__file__).with_name('product_pilot_data.json').read_text(encoding='utf-8'))

    def test_all_chosen_plans_fit_real_tool_arguments(self):
        validate(self.data)
        plans = [r for r in self.data['records'] if r['id'].startswith('format-') and r['split']=='train']
        self.assertEqual(len(plans), 4)
        for row in plans:
            plan = json.loads(row['chosen'])
            check(plan, self.schema)
            for step in plan['steps']:
                check(step['args'], self.tools[step['tool']]['parameters'])

    def test_unknown_tool_rejected(self):
        row = next(r for r in self.data['records'] if r['id']=='format-screen')
        plan = json.loads(row['chosen'])
        plan['steps'][0]['tool'] = 'MADE_UP_TOOL'
        with self.assertRaises(ValueError):
            check(plan, self.schema)

    def test_unexpected_tool_argument_rejected(self):
        with self.assertRaises(ValueError):
            check({'shell_command':'anything'}, self.tools['CAPTURE_SCREEN']['parameters'])

    def test_missing_required_tool_argument_rejected(self):
        with self.assertRaises(ValueError):
            check({}, self.tools['FINAL_RESPONSE']['parameters'])

    def test_event_and_source_leakage_rejected(self):
        for field in ('group', 'source_id'):
            data = copy.deepcopy(self.data)
            origin = next(r for r in data['records'] if r['id']=='history-tw-1987')
            other = next(r for r in data['records'] if r['id']=='history-dev-election')
            other[field] = origin[field]
            with self.assertRaises(ValueError):
                validate(data)


if __name__ == '__main__':
    unittest.main()
