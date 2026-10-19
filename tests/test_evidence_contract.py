import hashlib,unittest
from evidence_contract import check_contract

class EvidenceContract(unittest.TestCase):
    def setUp(self):
        self.prompt='先讀取 甲.txt，再讀取 乙.txt。不要刪除。最多兩筆。保留原文。'
        self.contract={'request_sha256':hashlib.sha256(self.prompt.encode()).hexdigest(),'requirements':[self.req('a','READ',{'path':'甲.txt'}),self.req('b','READ',{'path':'乙.txt'})],'before':[{'first':'a','then':'b','source_quote':'先讀取 甲.txt，再讀取 乙.txt'}]}
    def req(self,rid,tool,args,**extra):return {'id':rid,'source_quote':self.prompt,'tool':tool,'args':args,'mode':'require','selection':'any',**extra}
    def obs(self,path,**extra):return {'tool':'READ','args':{'path':path},'ok':True,'verified':True,'output':'內容',**extra}
    def run_check(self,history):return check_contract(self.prompt,self.contract,history,{'READ','DELETE','LIST'})
    def test_order_is_checked_from_actual_positions_not_supplied_sequence_numbers(self):
        result=self.run_check([self.obs('乙.txt',sequence_index=99),self.obs('甲.txt',sequence_index=0)])
        self.assertFalse(result['evidence_satisfied'])
    def test_later_verified_retry_satisfies_prior_failure_without_erasing_it(self):
        history=[self.obs('甲.txt',ok=False),self.obs('甲.txt'),self.obs('乙.txt')]
        result=self.run_check(history)
        self.assertTrue(result['evidence_satisfied']);self.assertEqual(result['witness_sequences'],{'a':2,'b':3});self.assertFalse(result['contract_semantics_verified'])
    def test_unverified_dispatch_and_wrong_target_do_not_satisfy(self):
        for item in [self.obs('丙.txt'),self.obs('甲.txt',verified=False)]:self.assertFalse(self.run_check([item,self.obs('乙.txt')])['evidence_satisfied'])
    def test_forbidden_dispatch_is_not_erased_by_failed_response(self):
        self.contract['requirements'].append(self.req('never','DELETE',{},mode='forbid'))
        self.assertFalse(self.run_check([self.obs('甲.txt'),self.obs('乙.txt'),{'tool':'DELETE','args':{'path':'任意.txt'},'ok':False}])['evidence_satisfied'])
    def test_item_limit_counts_actual_list_not_claimed_count(self):
        self.contract['requirements']=[self.req('list','LIST',{},max_output_items=2)];self.contract['before']=[]
        item={'tool':'LIST','args':{},'ok':True,'verified':True,'output':[1,2,3],'output_item_count':2}
        self.assertFalse(self.run_check([item])['evidence_satisfied']);item['output']=[1];self.assertTrue(self.run_check([item])['evidence_satisfied'])
    def test_latest_policy_does_not_accept_stale_correct_value(self):
        self.contract['requirements']=[self.req('a','READ',{'path':'甲.txt'},selection='latest',output_equals='  原文\n')];self.contract['before']=[]
        self.assertFalse(self.run_check([self.obs('甲.txt',output='  原文\n'),self.obs('甲.txt',output='原文')])['evidence_satisfied'])
    def test_any_policy_finds_a_valid_order_among_repeated_reads(self):
        result=self.run_check([self.obs('乙.txt'),self.obs('甲.txt'),self.obs('乙.txt'),self.obs('甲.txt')])
        self.assertTrue(result['evidence_satisfied']);self.assertEqual(result['witness_sequences'],{'a':2,'b':3})
    def test_invalid_quote_request_and_cycle_are_rejected(self):
        self.contract['requirements'][0]['source_quote']='捏造需求'
        with self.assertRaises(ValueError):self.run_check([])
        self.contract['requirements'][0]['source_quote']=self.prompt
        self.contract['before'].append({'first':'b','then':'a','source_quote':self.prompt})
        with self.assertRaisesRegex(ValueError,'Cyclic'):self.run_check([])
    def test_dispatch_count_includes_failed_attempts_with_unknown_outcome(self):
        self.contract['requirements']=[self.req('once','READ',{'path':'甲.txt'},max_dispatches=1)];self.contract['before']=[]
        self.assertFalse(self.run_check([self.obs('甲.txt',ok=False),self.obs('甲.txt')])['evidence_satisfied'])
if __name__=='__main__':unittest.main()
