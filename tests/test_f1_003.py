import copy,sys,unittest
from pathlib import Path
from datetime import date
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from import_f1db import import_archive,KNOWN
from reconcile_f1db import reconcile,OLD,NEW
from compare_sources import compare
from check_update import check_update
from validate_data import read,validate

class GateTests(unittest.TestCase):
    def setUp(self):self.old=read(ROOT/'examples/synthetic-dataset.json');self.new=copy.deepcopy(self.old)
    def test_same(self):self.assertEqual(check_update(self.old,self.new),[])
    def test_reordered_calendar(self):
        self.new['events'][0]['name']='Different GP';self.assertTrue(any('identity changed' in e for e in check_update(self.old,self.new)))
    def test_date_update(self):
        self.new['events'][0]['date']='2026-05-04';self.assertEqual(check_update(self.old,self.new),[])
    def test_stable_provider_id(self):
        self.old['events'][0]['externalEventId']='f1db:race-1';self.new['events'][0]['externalEventId']='f1db:race-2';self.assertTrue(any('identity changed' in e for e in check_update(self.old,self.new)))
    def test_result_revision(self):
        self.new['events'][0]['sessions'][0]['results'][0]['points']=12;self.assertEqual(check_update(self.old,self.new),[])
    def test_participant_removed(self):
        self.new['events'][0]['sessions'][0]['results'].pop();self.assertTrue(any('participants removed' in e for e in check_update(self.old,self.new)))
    def test_user_unchanged(self):
        user=read(ROOT/'examples/user.example.json');before=copy.deepcopy(user);self.assertEqual(check_update(self.old,self.new,user),[]);self.assertEqual(user,before)
    def test_crosswalk_no_surname_only(self):
        for d in (self.old,self.new):
            for r in d['drivers']:r.update(givenName='A',familyName='Same',birthDate='1970-01-01')
        self.assertEqual(compare(self.old,self.new)['driverCrosswalk'],{})

@unittest.skipUnless((ROOT/'private/f1db/f1db-csv.zip').exists(),'F1DB archive not installed')
class HistoricalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import hashlib
        p=ROOT/'private/f1db/f1db-csv.zip'
        if hashlib.sha256(p.read_bytes()).hexdigest() not in KNOWN:raise unittest.SkipTest('pinned archive required')
        # Existing ArchiveTests separately cover the full range.
        years=(2000,2007,2017,2018,2021)
        cls.raw,_=import_archive(p,season=2000,as_of=date(2026,11,26))
        for year in years[1:]:
            part,_=import_archive(p,season=year,as_of=date(2026,11,26))
            for key in ('drivers','constructors','circuits'):
                known={r['id'] for r in cls.raw[key]};cls.raw[key].extend(r for r in part[key] if r['id'] not in known)
            for key in ('events','standings','fastestLaps','stints','adjustments'):cls.raw[key].extend(part[key])
        cls.data,cls.report=reconcile(cls.raw)
    def final(self,y,k):return max((s for s in self.data['standings'] if s['season']==y and s['kind']==k),key=lambda s:s['afterRound'])['rows']
    def test_2000(self):
        r={x['entityId']:x for x in self.final(2000,'drivers')};self.assertEqual(r['f1db:pedro-diniz']['position'],17);self.assertEqual(r['f1db:johnny-herbert']['position'],18);self.assertEqual(next(x['points'] for x in self.final(2000,'constructors') if x['entityId']=='f1db:mclaren'),152)
    def test_2017(self):
        e=next(e for e in self.data['events'] if e['id']=='2017-R18');q=next(s for s in e['sessions'] if s['kind']=='qualifying');g=next(r for r in q['results'] if r['driverId']=='f1db:pierre-gasly');self.assertEqual((g['position'],g['positionText'],g['classified']),(None,'19',False))
    def test_2018(self):
        rr={r['entrantId']:r for r in self.final(2018,'constructors') if 'entrantId' in r};self.assertEqual((rr[OLD]['points'],rr[OLD]['positionText'],rr[NEW]['points']),(0,'E',52))
        self.assertEqual(len(self.data['entrants']),2);self.assertEqual(validate(self.data),[])
    def test_entrant_wrong_period(self):
        d=copy.deepcopy(self.data);e=next(e for e in d['events'] if e['id']=='2018-R01');r=next(r for s in e['sessions'] for r in s['results'] if r.get('entrantId')==OLD);r['entrantId']=NEW;self.assertTrue(any('invalid entrant assignment' in x for x in validate(d)))
    def test_idempotent(self):self.assertEqual(reconcile(self.data)[0],self.data)
    def test_raw_unchanged(self):self.assertNotIn('entrants',self.raw);self.assertEqual(len(self.raw['events']),len(self.data['events']))
    def test_draft(self):self.assertTrue(validate(self.data,release=True))
    def test_provider_event_ids(self):self.assertEqual(len({e['externalEventId'] for e in self.data['events']}),len(self.data['events']))
    def test_no_duplicate_deduction(self):self.assertFalse(self.data['adjustments'])
