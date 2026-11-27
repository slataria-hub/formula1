import copy,sys,unittest,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from init_user_data import empty_user
from validate_data import read,validate
from import_f1db import write_new,import_archive,KNOWN
from reconcile_f1db import reconcile
from review_remaining import correct,status_review
from datetime import date
import hashlib

class UserTests(unittest.TestCase):
    def setUp(self):self.data=read(ROOT/'examples/synthetic-dataset.json')
    def test_empty(self):
        before=copy.deepcopy(self.data);u=empty_user(self.data)
        self.assertEqual((u['predictions'],u['overrides']),([],[]));self.assertEqual(validate(self.data,u),[]);self.assertEqual(self.data,before)
    def test_future_year(self):
        import json
        d=json.loads(json.dumps(self.data).replace('2026','2028'));self.assertEqual(empty_user(d)['preferences']['selectedSeason'],2028)
    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'user.json';p.write_text('existing')
            with self.assertRaises((ValueError,OSError)):write_new(p,empty_user(self.data))
            self.assertEqual(p.read_text(),'existing')
    def test_no_calendar(self):
        with self.assertRaises(ValueError):empty_user(read(ROOT/'examples/empty-dataset.json'))

@unittest.skipUnless((ROOT/'private/f1db/f1db-csv.zip').exists(),'F1DB archive not installed')
class ReviewedRanks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=ROOT/'private/f1db/f1db-csv.zip'
        if hashlib.sha256(p.read_bytes()).hexdigest() not in KNOWN:raise unittest.SkipTest('pinned archive required')
        cls.raw={};cls.reviewed={}
        for y in (2021,2022):
            raw,_=import_archive(p,season=y,as_of=date(2026,11,26));cls.raw[y]=reconcile(raw)[0];cls.reviewed[y],_=correct(cls.raw[y])
    def rows(self,y,r):return {v['entityId']:v for s in self.reviewed[y]['standings'] if s['kind']=='drivers' and s['afterRound']==r for v in s['rows']}
    def test_2021(self):
        rr=self.rows(2021,10);self.assertEqual([rr['f1db:'+k]['position'] for k in ('nicholas-latifi','nikita-mazepin')],[19,20])
    def test_2022(self):
        rr=self.rows(2022,6);self.assertEqual([rr['f1db:'+k]['position'] for k in ('daniel-ricciardo','yuki-tsunoda')],[11,12])
    def test_repeat(self):
        for data in self.reviewed.values():self.assertEqual(correct(data)[0],data)
    def test_conflict(self):
        d=copy.deepcopy(self.raw[2022]);s=next(s for s in d['standings'] if s['kind']=='drivers' and s['afterRound']==6);next(r for r in s['rows'] if r['entityId']=='f1db:daniel-ricciardo')['points']=12
        with self.assertRaises(ValueError):correct(d)
