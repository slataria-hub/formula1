"""Synthetic regression tests + optional integration against pinned local archive."""
import csv
import io
import json
import sys
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from import_f1db import import_archive, normalize_result, standing_row, write_new, KNOWN
from validate_data import validate

ARCHIVE=ROOT/'private/f1db/f1db-csv.zip'
AS_OF=date(2026,11,26)

def csv_bytes(fields, records):
    s=io.StringIO(); w=csv.DictWriter(s,fieldnames=fields);w.writeheader();w.writerows(records);return s.getvalue()

class CoreTests(unittest.TestCase):
    def test_blank_awarded_points(self):
        r=dict(positionNumber='10',positionText='10',driverId='test-driver',constructorId='test-team',points='',laps='20')
        self.assertEqual(normalize_result(r,'race')['points'],0)
        self.assertIsNone(normalize_result(r,'qualifying')['points'])
    def test_classified_retirement(self):
        r=dict(positionNumber='10',positionText='10',driverId='test-driver',constructorId='test-team',points='1',laps='20',reasonRetired='Engine')
        x=normalize_result(r,'race');self.assertTrue(x['classified']);self.assertTrue(x['started']);self.assertEqual(x['status'],'retired');self.assertEqual(x['points'],1)
    def test_excluded(self):
        r=dict(positionNumber='',positionText='EX',driverId='test-driver',constructorId='test-team',points='',laps='')
        x=normalize_result(r,'race');self.assertIsNone(x['position']);self.assertFalse(x['classified']);self.assertEqual(x['status'],'excluded')
        y=standing_row(dict(positionNumber='',positionText='EX',constructorId='test-team',points='0'),'constructorId',0)
        self.assertEqual((y['position'],y['positionText']),(None,'E'))
    def test_qualifying_time(self):
        r=dict(positionNumber='1',positionText='1',driverId='test-driver',constructorId='test-team',timeMillis='80000')
        self.assertEqual(normalize_result(r,'qualifying')['qualifyingTimesMs'],[80000]);r.update(q1Millis='81000',q2Millis='80500',q3Millis='80000')
        self.assertEqual(normalize_result(r,'qualifying')['qualifyingTimesMs'],[81000,80500,80000])
    def test_write_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.json';write_new(p,{'a':1});self.assertEqual(json.loads(p.read_text()),{'a':1})
            with self.assertRaises(FileExistsError):write_new(p,{'a':2})
            self.assertEqual(json.loads(p.read_text()),{'a':1})
    def test_future_season_without_hardcoded_year(self):
        # Synthetic new year, no results. No dependency on the downloaded archive.
        tables={
          'races':(['id','year','round','date','grandPrixId','circuitId','qualifyingDate','sprintRaceDate','sprintQualifyingDate','sprintQualifyingFormat'],[dict(id='1',year='2027',round='1',date='2027-03-07',grandPrixId='test-gp',circuitId='test-circuit',qualifyingDate='2027-03-06')]),
          'grands-prix':(['id','fullName'],[dict(id='test-gp',fullName='Synthetic Grand Prix')]),
          'drivers':(['id'],[]),'constructors':(['id'],[]),
          'circuits':(['id','name','fullName','countryId','placeName'],[dict(id='test-circuit',name='Test',fullName='Test Circuit',countryId='test-country',placeName='Test')]),
          'countries':(['id','name'],[dict(id='test-country',name='Test Country')]),
        }
        for t in ['race-results','qualifying-results','sprint-race-results','sprint-qualifying-results','driver-standings','constructor-standings','fastest-laps']:
            tables['races-'+t]=(['year','raceId'],[])
        for t in ['driver','constructor']:tables['seasons-'+t+'-standings']=(['year'],[])
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'future.zip'
            with zipfile.ZipFile(p,'w') as z:
                for t,(fields,records) in tables.items():z.writestr('f1db-'+t+'.csv',csv_bytes(fields,records))
            data,report=import_archive(p,from_season=2027,as_of=date(2027,1,1));self.assertEqual(report['selectedSeasons'],[2027]);self.assertEqual(data['events'][0]['status'],'scheduled');self.assertFalse(data['events'][0]['sessions'][0]['results']);self.assertEqual(data['events'][0]['id'],'2027-R01')
            late,_=import_archive(p,from_season=2027,as_of=date(2027,3,8));self.assertEqual(late['events'][0]['status'],'unknown');self.assertEqual(late['events'][0]['sessions'][0]['status'],'pending_results')
            with self.assertRaisesRegex(ValueError,'missing requested'):import_archive(p,season=2026)

@unittest.skipUnless(ARCHIVE.exists(),'F1DB archive not installed')
class ArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import hashlib
        if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() not in KNOWN:raise unittest.SkipTest('pinned v2026.21.0 integration fixture required')
        cls.data,cls.report=import_archive(ARCHIVE,as_of=AS_OF)
        cls.events={e['id']:e for e in cls.data['events']}
    def final(self,year,kind):
        return {r['entityId']:r for r in max((s for s in self.data['standings'] if s['season']==year and s['kind']==kind),key=lambda s:s['afterRound'])['rows']}
    def test_season_2000(self):
        s=self.report['seasons']['2000'];self.assertEqual((s['events'],s['raceRows'],s['qualifyingRows']),(17,374,374));self.assertFalse(s['missingQualifyingRounds']);d=self.final(2000,'drivers');self.assertEqual(d['f1db:michael-schumacher']['points'],108);self.assertEqual(d['f1db:ralf-schumacher']['points'],24);self.assertEqual(self.final(2000,'constructors')['f1db:mclaren']['points'],152);self.assertFalse(self.data['adjustments'])
    def test_season_2007_exclusion(self):
        d=self.final(2007,'drivers'); self.assertEqual([d['f1db:'+x]['points'] for x in ['kimi-raikkonen','lewis-hamilton','fernando-alonso']],[110,109,109]);m=self.final(2007,'constructors')['f1db:mclaren'];self.assertEqual((m['position'],m['positionText'],m['points']),(None,'E',0))
    def test_season_2021_fraction_and_sprints(self):
        d=self.final(2021,'drivers');self.assertEqual(d['f1db:max-verstappen']['points'],395.5);self.assertEqual(d['f1db:lewis-hamilton']['points'],387.5);self.assertEqual(self.report['seasons']['2021']['sprintRows'],60)
    def test_season_2026_future(self):
        s=self.report['seasons']['2026'];self.assertEqual((s['events'],s['completed'],s['pendingRaceRounds']),(23,21,[22,23])); self.assertEqual(self.events['2026-R22']['status'],'scheduled')
    def test_unresolved_records(self):
        self.assertTrue(any(x['season']==2018 and x['kind']=='constructors' for x in self.report['standingConflicts']));q=next(x for x in self.events['2017-R18']['sessions'] if x['kind']=='qualifying');g=next(r for r in q['results'] if r['driverId']=='f1db:pierre-gasly');self.assertEqual((g['position'],g['positionText'],g['classified']),(None,'19',None))
    def test_all_seasons_and_draft(self):
        self.assertEqual(self.report['selectedSeasons'],list(range(2000,2027)));self.assertEqual(len(self.events),526);self.assertEqual(self.data['datasetStatus'],'draft');self.assertTrue(validate(self.data,release=True))
    def test_idempotent_subset(self):
        a,ar=import_archive(ARCHIVE,season=2000,as_of=AS_OF);b,br=import_archive(ARCHIVE,season=2000,as_of=AS_OF);self.assertEqual(a,b);self.assertEqual(ar,br)
