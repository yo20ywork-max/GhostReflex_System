import copy
import unittest

from completion_requirements import request_clauses, audit_schema, validate_audit


class CompletionRequirements(unittest.TestCase):
    def test_partition_preserves_every_character_and_quoted_punctuation(self):
        prompt='讀取「路徑，原稿；甲.txt」，不要修改。\n保存「a\nb」；核對後回覆。'
        clauses=request_clauses(prompt)
        self.assertEqual(''.join(c['text'] for c in clauses),prompt)
        self.assertEqual(clauses[0]['text'],'讀取「路徑，原稿；甲.txt」，')
        self.assertTrue(any('「a\nb」' in c['text'] for c in clauses))
        for c in clauses:self.assertEqual(prompt[c['start']:c['end']],c['text'])

    def test_oversized_request_fails_instead_of_discarding_tail(self):
        with self.assertRaisesRegex(ValueError,'不能略去'):request_clauses('讀取。'*65)

    def sample(self):
        clauses=request_clauses('先讀取，再写入。')
        history=[{'tool':'READ_TEXT_FILE','ok':True,'verified':True}]
        check={'reason':'已讀取','required_successful_tools':['READ_TEXT_FILE'],'witnesses':[{'sequence_index':1,'tool':'READ_TEXT_FILE'}],'satisfied':True}
        return clauses,history,{'before':[],'checks':{c['id']:copy.deepcopy(check) for c in clauses}}

    def test_omitted_later_requirement_is_rejected(self):
        clauses,history,value=self.sample();value['checks'].pop(clauses[-1]['id'])
        with self.assertRaisesRegex(ValueError,'遺漏'):validate_audit(value,clauses,history)

    def test_claimed_write_cannot_use_read_witness(self):
        clauses,history,value=self.sample()
        value['checks']['c2']['required_successful_tools']=['WRITE_TEXT_FILE']
        complete,reason=validate_audit(value,clauses,history)
        self.assertFalse(complete);self.assertIn('WRITE_TEXT_FILE',reason)

    def test_invented_tool_or_observation_is_rejected(self):
        clauses,history,value=self.sample()
        for witness in [{'sequence_index':2,'tool':'READ_TEXT_FILE'},{'sequence_index':True,'tool':'READ_TEXT_FILE'},{'sequence_index':1,'tool':'WRITE_TEXT_FILE'}]:
            changed=copy.deepcopy(value);changed['checks']['c1']['witnesses']=[witness]
            with self.assertRaises(ValueError):validate_audit(changed,clauses,history)

    def test_unverified_success_and_failed_result_do_not_prove_required_action(self):
        clauses,history,value=self.sample()
        for flag in ('verified','ok'):
            changed=copy.deepcopy(history);changed[0][flag]=False
            complete,_=validate_audit(value,clauses,changed)
            self.assertFalse(complete)

    def test_schema_requires_all_clauses_and_reason_before_decision(self):
        clauses=request_clauses('讀取；儲存。');schema=audit_schema(clauses,['READ_TEXT_FILE','WRITE_TEXT_FILE'])
        checks=schema['properties']['checks']
        self.assertEqual(checks['required'],['c1','c2'])
        self.assertEqual(list(checks['properties']['c1']['properties'])[-1],'satisfied')

    def test_all_actions_present_but_reversed_order_cannot_pass(self):
        clauses,history,value=self.sample()
        history.append({'tool':'WRITE_TEXT_FILE','ok':True,'verified':True})
        value['checks']['c2'].update(required_successful_tools=['WRITE_TEXT_FILE'],witnesses=[{'sequence_index':2,'tool':'WRITE_TEXT_FILE'}])
        value['before']=[{'source_quote':''.join(c['text'] for c in clauses),'earlier':'c1','later':'c2'}]
        self.assertTrue(validate_audit(value,clauses,history)[0])
        history.reverse()
        value['checks']['c1']['witnesses'][0]['sequence_index']=2
        value['checks']['c2']['witnesses'][0]['sequence_index']=1
        complete,reason=validate_audit(value,clauses,history)
        self.assertFalse(complete);self.assertIn('時間順序不符',reason)

    def test_order_edges_need_source_and_cannot_cycle(self):
        clauses,history,value=self.sample()
        edge={'source_quote':'捏造的要求','earlier':'c1','later':'c2'};value['before']=[edge]
        with self.assertRaisesRegex(ValueError,'逐字'):validate_audit(value,clauses,history)
        edge['source_quote']='先讀取'
        value['before'].append({'source_quote':'再写入','earlier':'c2','later':'c1'})
        with self.assertRaisesRegex(ValueError,'循環'):validate_audit(value,clauses,history)


if __name__=='__main__':unittest.main()
