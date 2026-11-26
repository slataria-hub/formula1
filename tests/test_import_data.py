import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from import_data import Client, NetworkReadError, dump, flags, import_season, milliseconds
from validate_data import validate

DRIVERS=[{'driverId':'michael_schumacher','givenName':'Michael','familyName':'Schumacher'}, {'driverId':'ralf_schumacher','givenName':'Ralf','familyName':'Schumacher'}]
TEAMS=[{'constructorId':'ferrari','name':'Ferrari'},{'constructorId':'williams','name':'Williams'}]
RACE={'season':'2000','round':'1','raceName':'Synthetic race','Circuit':{'circuitId':'test_circuit','circuitName':'Test Circuit'},'date':'2000-03-12'}

class FakeClient(Client):
    def __init__(self):
        super().__init__(Path('unused'))
    def get(self,route,offset,limit=100):
        kind=route.split('/')[-1]; rows=[]
        if kind=='races': table,collection,nested='RaceTable','Races',None; rows=[RACE]
        elif kind in ('results','qualifying'):
            table,collection,nested='RaceTable','Races','Results' if kind=='results' else 'QualifyingResults'
            rows=[{'Driver':d,'Constructor':t,'position':str(i+1),'positionText':str(i+1),'points':str(10 if i==0 else 4.5),'status':'Finished','laps':'58','grid':str(i+1),'Q1':'1:29.123'} for i,(d,t) in enumerate(zip(DRIVERS,TEAMS))]
        else:
            table,collection='StandingsTable','StandingsLists'; nested='DriverStandings' if kind=='driverstandings' else 'ConstructorStandings'
            rows=[{('Driver' if kind=='driverstandings' else 'Constructor'):d,'position':str(i+1),'points':str(10 if i==0 else 4.5),'wins':str(1-i)} for i,d in enumerate(DRIVERS if kind=='driverstandings' else TEAMS)]
        # Deliberately split a single race or standings snapshot across API pages.
        page=rows[offset:offset+1]
        groups=([dict(RACE,**{nested:page})] if page else []) if nested else page
        sid=f'jolpica:{kind}-{offset}'
        self.sources[sid]={'id':sid,'provider':'synthetic importer test','url':'https://example.invalid/'+kind,'retrievedAt':'2026-11-26T00:00:00Z','sha256':None,'revision':None}
        return {'total':str(len(rows)),'offset':str(offset),'limit':'1',table:{collection:groups}},sid

class ImportTests(unittest.TestCase):
    def test_timeout_retry_reports_endpoint(self):
        with TemporaryDirectory() as tmp:
            c=Client(tmp,timeout=120)
            with patch('import_data.urlopen',side_effect=TimeoutError('read timeout')) as request, patch('import_data.time.sleep'), patch('builtins.print') as log:
                with self.assertRaisesRegex(RuntimeError,'2000/races/.*TimeoutError'):
                    c.get('2000/races',0)
            self.assertEqual(request.call_count,5)
            self.assertTrue(all(call.kwargs['timeout']==120 for call in request.call_args_list))
            self.assertTrue(any('NETWORK' in str(call) for call in log.call_args_list))
            self.assertEqual(list(Path(tmp).iterdir()),[])
    def test_import_uses_round_endpoints(self):
        client=FakeClient()
        with patch.object(client,'get',wraps=client.get) as get:
            data,_=import_season(client,2000)
        routes={call.args[0] for call in get.call_args_list}
        self.assertIn('2000/1/results',routes)
        self.assertIn('2000/1/qualifying',routes)
        self.assertNotIn('2000/results',routes)
        self.assertNotIn('2000/qualifying',routes)
        self.assertFalse(validate(data))

    def test_adaptive_pages_preserve_offsets(self):
        client=Client('unused',page_size=4)
        rows=list(range(9))
        def get(route,offset,limit):
            if offset==4 and limit>2: raise NetworkReadError('timeout')
            page=rows[offset:offset+limit]
            return {'total':'9','offset':str(offset),'limit':str(limit),'RaceTable':{'Races':[{'Results':page}]}},'source'
        with patch.object(client,'get',side_effect=get) as request:
            got=[x for group,_ in client.pages('2000/1/results','RaceTable','Races','Results') for x in group['Results']]
        self.assertEqual(got,rows)
        self.assertEqual([(c.args[1],c.args[2]) for c in request.call_args_list],[(0,4),(4,4),(4,2),(6,2),(8,2)])

    def test_minimum_page_failure_is_not_ignored(self):
        client=Client('unused',page_size=2)
        with patch.object(client,'get',side_effect=NetworkReadError('timeout')) as get:
            with self.assertRaises(NetworkReadError):
                list(client.pages('2000/1/results','RaceTable','Races','Results'))
        self.assertEqual([c.args[2] for c in get.call_args_list],[2,1])

    def test_empty_qualifying_recorded_with_provenance(self):
        client=FakeClient(); original=client.get
        def get(route,offset,limit):
            data,sid=original(route,offset,limit)
            if route.endswith('/qualifying'):
                data['total']='0'; data['RaceTable']['Races']=[]
            return data,sid
        with patch.object(client,'get',side_effect=get):
            data,notes=import_season(client,2000)
        q=next(s for s in data['events'][0]['sessions'] if s['kind']=='qualifying')
        self.assertEqual(q['status'],'unavailable')
        self.assertEqual(q['results'],[])
        self.assertEqual(q['sourceIds'],['jolpica:qualifying-0'])
        self.assertTrue(any('qualifying: no published result' in n for n in notes))
        self.assertFalse(validate(data))

    def test_wrong_round_rejected(self):
        client=FakeClient()
        original=client.get
        def get(route,offset,limit):
            data,sid=original(route,offset,limit)
            if route=='2000/1/results':
                data['RaceTable']['Races'][0]['round']='2'
            return data,sid
        with patch.object(client,'get',side_effect=get):
            with self.assertRaisesRegex(ValueError,'Unexpected result round'):
                import_season(client,2000)

    def test_same_surname_distinct_ids_and_teams(self):
        data,notes=import_season(FakeClient(),2000)
        self.assertEqual({d['id'] for d in data['drivers']},{'jolpica:michael_schumacher','jolpica:ralf_schumacher'})
        race=data['events'][0]['sessions'][0]
        self.assertEqual([r['constructorId'] for r in race['results']],['jolpica:ferrari','jolpica:williams'])
        self.assertEqual([r['points'] for r in race['results']],[10,4.5]); self.assertFalse(validate(data))
    def test_qualification_and_standings_pagination(self):
        data,_=import_season(FakeClient(),2000)
        q=next(s for s in data['events'][0]['sessions'] if s['kind']=='qualifying')
        self.assertEqual(len(q['results']),2); self.assertIsNone(q['results'][0]['points'])
        self.assertEqual(q['results'][0]['qualifyingTimesMs'],[89123,None,None]); self.assertEqual(len(data['standings']),2)
        self.assertEqual(len(data['standings'][0]['rows']),2)
    def test_unranked_standings_preserved(self):
        client=FakeClient(); original=client.get
        def get(route,offset,limit):
            data,sid=original(route,offset,limit)
            if route.endswith(('driverstandings','constructorstandings')) and offset==1:
                key='DriverStandings' if route.endswith('driverstandings') else 'ConstructorStandings'
                row=data['StandingsTable']['StandingsLists'][0][key][0]
                del row['position']; row['positionText']='-'; row['points']='0'
            return data,sid
        with patch.object(client,'get',side_effect=get):
            data,_=import_season(client,2000)
        for st in data['standings']:
            self.assertIsNone(st['rows'][1]['position'])
            self.assertEqual(st['rows'][1]['positionText'],'-')
            self.assertEqual(st['rows'][1]['points'],0)
        self.assertFalse(validate(data))
        del data['standings'][0]['rows'][1]['positionText']
        self.assertTrue(validate(data))

    def test_excluded_or_disqualified_standings_preserved(self):
        for marker in ('E','D'):
            client=FakeClient(); original=client.get
            def get(route,offset,limit):
                data,sid=original(route,offset,limit)
                if route.endswith('driverstandings') and offset==1:
                    row=data['StandingsTable']['StandingsLists'][0]['DriverStandings'][0]
                    del row['position']; row['positionText']=marker
                return data,sid
            with patch.object(client,'get',side_effect=get):
                data,_=import_season(client,2000)
            self.assertIsNone(data['standings'][0]['rows'][1]['position'])
            self.assertEqual(data['standings'][0]['rows'][1]['positionText'],marker)
            self.assertFalse(validate(data))

    def test_unexplained_missing_standings_position_rejected(self):
        client=FakeClient(); original=client.get
        def get(route,offset,limit):
            data,sid=original(route,offset,limit)
            if route.endswith('driverstandings') and offset==1:
                del data['StandingsTable']['StandingsLists'][0]['DriverStandings'][0]['position']
            return data,sid
        with patch.object(client,'get',side_effect=get):
            with self.assertRaisesRegex(ValueError,'driverstandings.*missing or invalid position'):
                import_season(client,2000)

    def test_qualification_missing_position_preserved(self):
        client=FakeClient(); original=client.get
        def get(route,offset,limit):
            data,sid=original(route,offset,limit)
            if route.endswith('qualifying') and offset==1:
                row=data['RaceTable']['Races'][0]['QualifyingResults'][0]
                del row['position']; del row['positionText']
            return data,sid
        with patch.object(client,'get',side_effect=get):
            data,_=import_season(client,2000)
        q=next(s for s in data['events'][0]['sessions'] if s['kind']=='qualifying')
        self.assertIsNone(q['results'][1]['position']); self.assertIsNone(q['results'][1]['positionText'])
        self.assertFalse(validate(data))

    def test_repeat_identical_fixture(self):
        self.assertEqual(import_season(FakeClient(),2000),import_season(FakeClient(),2000))
    def test_classified_retirement(self):
        self.assertEqual(flags({'positionText':'7','status':'Engine','laps':'50'})[2],True)
        self.assertEqual(flags({'positionText':'R','status':'Engine','laps':'0'})[1],None)
    def test_dns_and_dsq(self):
        self.assertEqual(flags({'positionText':'W','status':'Withdrawn'}),('withdrawn',None,False))
        self.assertEqual(flags({'status':'Did not start'}),('dns',False,False)); self.assertEqual(flags({'positionText':'D'}),('dsq',None,False))
    def test_invalid_pagination_rejected(self):
        c=FakeClient()
        with patch.object(c,'get',return_value=({'total':'2','offset':'0','limit':'1','RaceTable':{'Races':[]}},'x')):
            with self.assertRaisesRegex(ValueError,'unexpected page length'): list(c.pages('2000/races','RaceTable','Races'))
    def test_no_overwrite(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/'candidate.json'; dump(p,{'original':True},exclusive=True)
            with self.assertRaises(FileExistsError): dump(p,{'original':False},exclusive=True)
            self.assertEqual(json.loads(p.read_text()),{'original':True})
    def test_times(self):
        self.assertEqual(milliseconds('1:30.123'),90123); self.assertIsNone(milliseconds(''))
    def test_draft_not_releasable(self):
        data,_=import_season(FakeClient(),2000); self.assertEqual(data['datasetStatus'],'draft'); self.assertTrue(validate(data,release=True))

if __name__=='__main__': unittest.main()
