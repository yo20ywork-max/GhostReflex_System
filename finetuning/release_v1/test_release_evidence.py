import copy,hashlib,unittest
from release_gate import ROOT,validate_evidence_identity

class EvidenceTest(unittest.TestCase):
    def setUp(self):
        self.rows=[{'id':'one','system':'system','prompt':'literal path','category':'tools','group':'g'}]
        self.checks={'data_sha256':'data','scorer_sha256':hashlib.sha256((ROOT/'score.py').read_bytes()).hexdigest(),'results':[{'id':'one','candidate':c,'category':'tools','group':'g','prompt_sha256':hashlib.sha256(b'system\nliteral path').hexdigest(),'base_revision':'revision','adapter_sha256':'weights'} for c in ['base','adapter']]}
    def verify(self):return validate_evidence_identity(self.checks,self.rows,'data','revision','weights')
    def test_exact_evidence(self):self.assertEqual(self.verify(),[])
    def test_wrong_checkpoint(self):
        self.checks['results'][1]['adapter_sha256']='other'
        self.assertTrue(any('adapter mismatch' in e for e in self.verify()))
    def test_duplicate_and_missing_candidate(self):
        self.checks['results'][1]=copy.deepcopy(self.checks['results'][0])
        self.assertTrue(any('coverage mismatch' in e for e in self.verify()))
    def test_wrong_data_and_prompt(self):
        self.checks['data_sha256']='dev';self.checks['results'][0]['prompt_sha256']='changed'
        errors=self.verify()
        self.assertIn('Dataset identity mismatch',errors)
        self.assertTrue(any('Prompt identity mismatch' in e for e in errors))
    def test_wrong_foundation(self):
        self.checks['results'][1]['base_revision']='other'
        self.assertTrue(any('Foundation revision mismatch' in e for e in self.verify()))
if __name__=='__main__':unittest.main()
