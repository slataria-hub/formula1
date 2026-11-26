import copy
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from review_2000 import review, REF
from validate_data import read, validate

class ReferenceTests(unittest.TestCase):
    def test_reference_totals(self):
        r=read(REF)
        self.assertEqual(len(r['drivers']),23)
        self.assertEqual(sum(x['points'] for x in r['drivers']),442)
        self.assertEqual(sum(x['points'] for x in r['constructors']),432)
        self.assertEqual(r['adjustment']['pointsDelta'],-10)
        self.assertEqual(r['adjustment']['afterRound'],10)
        self.assertEqual({x['round'] for x in r['races']},set(range(1,18)))

@unittest.skipUnless((ROOT/'private/candidate-2000.json').is_file(),'Real pilot candidate not available locally')
class PilotReviewTests(unittest.TestCase):
    def setUp(self):
        self.data=read(ROOT/'private/candidate-2000.json'); self.ref=read(REF)
    def test_real_candidate_reconciliation(self):
        original=copy.deepcopy(self.data)
        out,report=review(self.data,self.ref)
        self.assertEqual(original,self.data)
        self.assertEqual(out['datasetStatus'],'draft')
        self.assertFalse(validate(out)); self.assertTrue(validate(out,release=True))
        self.assertEqual(report['mclarenOfficialPoints'],152)
        self.assertEqual(report['raceRows'],373)
        st=next(s for s in out['standings'] if s['kind']=='constructors')
        self.assertEqual(next(r['points'] for r in st['rows'] if r['entityId']=='jolpica:mclaren'),152)
        self.assertEqual(len(out['adjustments']),1)
    def test_no_double_penalty(self):
        out,_=review(self.data,self.ref)
        again,_=review(out,self.ref)
        self.assertEqual(again,out)
    def test_unexpected_points_rejected(self):
        row=next(r for s in self.data['standings'] if s['kind']=='constructors' for r in s['rows'] if r['entityId']=='jolpica:mclaren')
        row['points']=151
        with self.assertRaisesRegex(ValueError,'unexpected standings points'): review(self.data,self.ref)
    def test_missing_qualifying_is_explicit(self):
        out,report=review(self.data,self.ref)
        self.assertEqual(report['missingQualificationRounds'],[2,5,6,7,8,9,10,11,12,13,14,15,17])
        for e in out['events']:
            q=next(s for s in e['sessions'] if s['kind']=='qualifying')
            if e['round'] in report['missingQualificationRounds']:
                self.assertEqual(q['status'],'unavailable'); self.assertFalse(q['results']); self.assertTrue(q['sourceIds'])
    def test_reject_unknown_adjustment(self):
        out,_=review(self.data,self.ref)
        out['adjustments'].append(copy.deepcopy(out['adjustments'][0]))
        with self.assertRaisesRegex(ValueError,'Unknown or duplicate'): review(out,self.ref)

if __name__=='__main__':unittest.main()
