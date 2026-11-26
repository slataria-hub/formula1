import copy
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from validate_data import read, validate, verify_backup
class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.data=read(ROOT/'examples/synthetic-dataset.json')
        self.user=read(ROOT/'examples/user.example.json')
        self.results=self.data['events'][0]['sessions'][0]['results']
    @unittest.skipUnless((ROOT/'legacy/SHA256SUMS.txt').exists(), 'local backup not installed')
    def test_backup(self): self.assertEqual(verify_backup(),[])
    def test_fixture(self): self.assertEqual(validate(self.data,self.user),[])
    def test_empty_draft(self): self.assertEqual(validate(read(ROOT/'examples/empty-dataset.json')),[])
    def test_release_rejects_fixture(self): self.assertTrue(validate(self.data,release=True))
    def test_release_rejects_empty(self): self.assertTrue(validate(read(ROOT/'examples/empty-dataset.json'),release=True))
    def test_duplicate_driver(self):
        self.results.append(copy.deepcopy(self.results[0])); self.assertTrue(any('duplicate driver' in x for x in validate(self.data)))
    def test_missing_points(self):
        self.results[0]['points']=None; self.assertTrue(any('missing official points' in x for x in validate(self.data)))
    def test_unknown_constructor(self):
        self.results[0]['constructorId']='test:missing'; self.assertTrue(any('unknown constructor' in x for x in validate(self.data)))
    def test_unknown_source(self):
        self.data['events'][0]['sourceIds']=['test:missing']; self.assertTrue(any('unknown source' in x for x in validate(self.data)))
    def test_duplicate_classification(self):
        self.results[1]['position']=1; self.assertTrue(any('duplicate classified position' in x for x in validate(self.data)))
    def test_dns(self):
        self.results[0]['status']='dns'; self.assertTrue(any('DNS marked started' in x for x in validate(self.data)))
    def test_invalid_prediction(self):
        self.user['predictions'][0]['driverIds']=['test:missing']; self.assertTrue(any('prediction: unknown driver' in x for x in validate(self.data,self.user)))
    def test_wrong_round(self):
        self.data['events'][0]['round']=2; self.assertTrue(any('season/round mismatch' in x for x in validate(self.data)))
    def test_classified_retirement(self):
        self.results[0]['status']='retired'; self.assertEqual(validate(self.data),[])
if __name__=='__main__': unittest.main()
