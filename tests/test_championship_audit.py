import copy
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from validate_data import read
from audit_championships import audit, known_delta, dec
from classify_crosswalk import classify, summarize

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.data=read(ROOT/'examples/synthetic-dataset.json')
        e=self.data['events'][0]
        # Fixture explicitly includes a qualifying session for audit coverage.
        if not any(s['kind']=='qualifying' for s in e['sessions']):
            q=copy.deepcopy(e['sessions'][0]);q.update(id=e['id']+'-qualifying',kind='qualifying')
            for r in q['results']:r['points']=None
            e['sessions'].append(q)
        race=next(s for s in e['sessions'] if s['kind']=='race')
        rr=race['results']; self.data['standings']=[dict(season=e['season'],afterRound=e['round'],kind='drivers',sourceIds=e['sourceIds'],rows=[dict(entityId=r['driverId'],position=r['position'],points=r['points'],wins=int(r['position']==1)) for r in rr]),dict(season=e['season'],afterRound=e['round'],kind='constructors',sourceIds=e['sourceIds'],rows=[dict(entityId=rr[0]['constructorId'],position=1,points=sum(r['points'] for r in rr),wins=1)])]
    def test_arithmetic_and_read_only(self):
        original=copy.deepcopy(self.data); r=audit(self.data)
        self.assertEqual(self.data,original);self.assertFalse(r['publicationAuthorized']);self.assertEqual(r['totals']['raceWins'],1)
        self.assertFalse(any(i['code']=='unexplained_points_delta' for i in r['issues']))
    def test_unexpected_points(self):
        s=next(s for s in self.data['standings'] if s['kind']=='drivers');s['rows'][0]['points']+=1
        self.assertTrue(any(i['code']=='unexplained_points_delta' for i in audit(self.data)['issues']))
    def test_missing_snapshot(self):
        self.data['standings']=[s for s in self.data['standings'] if s['kind']!='drivers']
        self.assertTrue(any(i['code']=='missing_standings' for i in audit(self.data)['issues']))
    def test_missing_qualifying(self):
        e=self.data['events'][0];e['sessions']=[s for s in e['sessions'] if s['kind']!='qualifying']
        self.assertTrue(any(i['code']=='missing_session' for i in audit(self.data)['issues']))
    def test_future_no_results(self):
        e=copy.deepcopy(self.data['events'][0]);e.update(id='2027-R01',season=2027,date='2027-03-01',status='scheduled')
        for s in e['sessions']:s.update(id=e['id']+'-'+s['kind'],status='scheduled',results=[])
        self.data['events'].append(e);r=audit(self.data);self.assertEqual(r['seasons']['2027']['notCompleted'],1);self.assertFalse(any(i['season']==2027 for i in r['issues']))
    def test_penalty_exact(self):
        self.assertIsNotNone(known_delta(2020,5,'constructors','f1db:racing-point',dec(42),dec(14),dec(41),[],False))
        self.assertIsNone(known_delta(2020,5,'constructors','f1db:racing-point',dec(42),dec(14),dec(40),[],False))
        self.assertIsNone(known_delta(2020,5,'drivers','f1db:racing-point',dec(42),dec(14),dec(41),[],False))
    def test_exclusion_requires_final_evidence(self):
        args=(2007,1,'constructors','f1db:mclaren',dec(0),dec(14),dec(0))
        self.assertIsNone(known_delta(*args,[],False));self.assertIsNotNone(known_delta(*args,[dict(entityId='f1db:mclaren',position=None,positionText='E',points=0)],False))
    def test_force_india_requires_entrants(self):
        args=(2018,13,'constructors','f1db:force-india',dec(59),dec(18),dec(18),[])
        self.assertIsNone(known_delta(*args,False));self.assertIsNotNone(known_delta(*args,True))

class CrosswalkTests(unittest.TestCase):
    def test_formats(self):
        def c(a,b):return classify(dict(field='qualifyingTimesMs',primary=a,secondary=b))
        self.assertEqual(c([100],[100,None,None]),'single_session_time_format');self.assertEqual(c([100],[None,100,None]),'value_conflict');self.assertEqual(c([100],[101,None,None]),'value_conflict')
    def test_missing_positions(self):self.assertEqual(classify(dict(field='position',primary=None,secondary=15)),'classification_review')
    def test_time_difference(self):
        self.assertEqual(classify(dict(field='timeMs',primary=100,secondary=101)),'one_millisecond_review');self.assertEqual(classify(dict(field='timeMs',primary=100,secondary=None)),'missing_value')
    def test_summary(self):
        x=dict(comparedRows=2,differences=[dict(field='points',primary=1,secondary=2)],unmatchedRows=[{'driver':'x'}]);y=copy.deepcopy(x);r=summarize(x);self.assertEqual(x,y);self.assertEqual(r['categories'],{'value_conflict':1});self.assertFalse(r['publicationAuthorized'])
