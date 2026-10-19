import copy
import unittest

from evidence_contract import check_contract
from source_contract import SourceContractError, compile_source_contract


CATALOG = [
    {'name': 'LIST_DIRECTORY', 'parameters': {'properties': {'path': {'type': 'string'}, 'recursive': {'type': 'boolean', 'default': False}, 'max_items': {'type': 'integer', 'minimum': 1, 'maximum': 5000, 'default': 300}}}},
    {'name': 'BROWSER_CLICK', 'parameters': {'properties': {'target': {'type': 'string'}, 'exact': {'type': 'boolean', 'default': False}}}},
    {'name': 'WRITE_TEXT_FILE', 'parameters': {'properties': {'path': {'type': 'string'}, 'content': {'type': 'string'}}}},
    {'name': 'BROWSER_WAIT_FOR', 'parameters': {'properties': {'by': {'type': 'string', 'enum': ['text', 'css']}, 'target': {'type': 'string'}, 'state': {'type': 'string', 'enum': ['visible', 'hidden']}}}},
]


def extraction(tool, quote, arguments, constraints=()):
    return {'requirements': [{'id': 'r1', 'source_quote': quote, 'tool': tool, 'mode': 'require',
                              'arguments': [{'name': name, 'quote': source} for name, source in arguments.items()],
                              'constraints': list(constraints)}], 'before': [], 'unresolved': []}


class SourceContract(unittest.TestCase):
    def test_implicit_tool_defaults_do_not_become_user_requirements(self):
        prompt = '列出「素材庫」。'
        raw = extraction('LIST_DIRECTORY', prompt, {'path': '素材庫'})
        compiled = compile_source_contract(prompt, raw, CATALOG)
        self.assertEqual(compiled['contract']['requirements'][0]['args'], {'path': '素材庫'})
        history = [{'tool': 'LIST_DIRECTORY', 'args': {'path': '素材庫'}, 'output': [], 'ok': True, 'verified': True}]
        self.assertTrue(check_contract(prompt, compiled['contract'], history, ['LIST_DIRECTORY'])['evidence_satisfied'])
        self.assertFalse(compiled['contract_semantics_verified'])

    def test_invented_defaults_are_rejected_instead_of_silently_stripped(self):
        prompt = '列出「素材庫」。'
        raw = extraction('LIST_DIRECTORY', prompt, {'path': '素材庫', 'max_items': '300'})
        with self.assertRaisesRegex(SourceContractError, 'source quote'):
            compile_source_contract(prompt, raw, CATALOG)

    def test_click_count_cannot_become_result_count(self):
        prompt = '點「預覽」一次。'
        raw = extraction('BROWSER_CLICK', prompt, {'target': '預覽'}, [{'kind': 'max_dispatches', 'quote': '一次'}])
        compiled = compile_source_contract(prompt, raw, CATALOG)
        self.assertEqual(compiled['contract']['requirements'][0]['max_dispatches'], 1)
        raw['requirements'][0]['constraints'][0]['kind'] = 'max_output_items'
        with self.assertRaisesRegex(SourceContractError, 'list result'):
            compile_source_contract(prompt, raw, CATALOG)
        # Even on a list-returning tool, the wrong unit remains invalid.
        raw['requirements'][0]['tool'] = 'LIST_DIRECTORY'
        raw['requirements'][0]['arguments'] = []
        with self.assertRaisesRegex(SourceContractError, 'correct unit'):
            compile_source_contract(prompt, raw, CATALOG)

    def test_chinese_count_is_applied_to_actual_list_length(self):
        prompt = '列出「音軌」，最多七十二筆。'
        raw = extraction('LIST_DIRECTORY', prompt, {'path': '音軌'}, [{'kind': 'max_output_items', 'quote': '最多七十二筆'}])
        compiled = compile_source_contract(prompt, raw, CATALOG)
        item = {'tool': 'LIST_DIRECTORY', 'args': {'path': '音軌'}, 'output': list(range(81)), 'output_item_count': 72, 'ok': True, 'verified': True}
        self.assertFalse(check_contract(prompt, compiled['contract'], [item], ['LIST_DIRECTORY'])['evidence_satisfied'])

    def test_ambiguous_colloquial_count_is_not_silently_changed(self):
        prompt = '列出音軌，最多一百二筆。'
        raw = extraction('LIST_DIRECTORY', prompt, {'path': '音軌'}, [{'kind': 'max_output_items', 'quote': '最多一百二筆'}])
        with self.assertRaisesRegex(SourceContractError, 'Ambiguous'):
            compile_source_contract(prompt, raw, CATALOG)
        for numeral, expected in [('一百零二', 102), ('一百二十', 120), ('兩百', 200), ('三千零六', 3006)]:
            prompt = '列出音軌，最多' + numeral + '筆。'
            raw = extraction('LIST_DIRECTORY', prompt, {'path': '音軌'}, [{'kind': 'max_output_items', 'quote': '最多' + numeral + '筆'}])
            compiled = compile_source_contract(prompt, raw, CATALOG)
            self.assertEqual(compiled['contract']['requirements'][0]['max_output_items'], expected)

    def test_cited_literal_preserves_whitespace_and_cannot_supply_a_separate_value(self):
        literal = ' \t繁體中文\r\n  '
        prompt = '將【' + literal + '】寫入「片尾.txt」。'
        raw = extraction('WRITE_TEXT_FILE', prompt, {'path': '片尾.txt', 'content': literal})
        compiled = compile_source_contract(prompt, raw, CATALOG)
        self.assertEqual(compiled['contract']['requirements'][0]['args']['content'], literal)
        raw['requirements'][0]['arguments'][1]['value'] = '被替換'
        with self.assertRaisesRegex(SourceContractError, 'fields'):
            compile_source_contract(prompt, raw, CATALOG)

    def test_locator_and_state_are_derived_from_cited_words(self):
        prompt = '等文字「處理中」消失。'
        raw = extraction('BROWSER_WAIT_FOR', prompt, {'by': '文字', 'target': '處理中', 'state': '消失'})
        compiled = compile_source_contract(prompt, raw, CATALOG)
        self.assertEqual(compiled['contract']['requirements'][0]['args'], {'by': 'text', 'target': '處理中', 'state': 'hidden'})
        raw['requirements'][0]['arguments'][0]['quote'] = '處理中'
        with self.assertRaisesRegex(SourceContractError, 'enum'):
            compile_source_contract(prompt, raw, CATALOG)

    def test_explicit_unrepresentable_condition_prevents_partial_contract_acceptance(self):
        prompt = '列出素材庫，遇到同名檔案時詢問我。'
        raw = extraction('LIST_DIRECTORY', '列出素材庫', {'path': '素材庫'})
        raw['unresolved'] = [{'source_quote': '遇到同名檔案時詢問我', 'reason': 'Conditional policy needs another representation.'}]
        with self.assertRaisesRegex(SourceContractError, 'cannot be represented'):
            compile_source_contract(prompt, raw, CATALOG)

    def test_duplicate_constraints_and_dangling_order_are_rejected(self):
        prompt = '點「預覽」一次。'
        raw = extraction('BROWSER_CLICK', prompt, {'target': '預覽'}, [{'kind': 'max_dispatches', 'quote': '一次'}])
        bad = copy.deepcopy(raw)
        bad['requirements'][0]['constraints'] *= 2
        with self.assertRaisesRegex(SourceContractError, 'duplicate'):
            compile_source_contract(prompt, bad, CATALOG)
        raw['before'] = [{'first': 'r1', 'then': 'invented', 'source_quote': prompt}]
        with self.assertRaisesRegex(SourceContractError, 'Order edges'):
            compile_source_contract(prompt, raw, CATALOG)


if __name__ == '__main__':
    unittest.main()
