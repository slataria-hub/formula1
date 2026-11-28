"""F1-007.6: no internet required; future archive and local pack migration."""
import copy, json, sys, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import sync_media as mod
import collect_media as media
from fetch_f1db import REQUIRED
from validate_data import read, validate


def pic(name='Test.jpg'):
    return dict(src=media.uri(b'\xff\xd8\xffabc','jpeg'),source='https://commons.wikimedia.org/wiki/File:'+name,author='Test Author',license='CC BY 4.0',file=name)

class SyncTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'private').mkdir(exist_ok=True);tmp=tempfile.TemporaryDirectory(dir=ROOT/'private');self.addCleanup(tmp.cleanup);self.root=Path(tmp.name);self.out=self.root/'media';self.out.mkdir()
        self.archive=self.root/'future.zip';self.source=self.root/'source.zip';self.base=self.root/'candidate.json';self.file=self.out/'visual-media.json'
        self.tables={'races':'id,year,round,date,circuitId,circuitLayoutId\n1,2034,1,2034-01-01,track,track-2\n',
                     'circuits-layouts':'id,circuitId\ntrack-2,track\n',
                     'countries':'id,alpha2Code,name,demonym\nexample,GB,Example Country,Example National\n',
                     'drivers':'id,name,dateOfBirth\na,Test a,1980-01-01\nb,Test b,1981-01-01\nrookie,New Rookie,2010-01-01\n',
                     'constructors':'id,name\nteam,Test Team\nnew-team,New Team\n',
                     'seasons-entrants-drivers':'year,driverId,testDriver\n2034,rookie,false\n2034,ignored,true\n',
                     'seasons-entrants-constructors':'year,constructorId\n2034,new-team\n'}
        self.data=json.loads(json.dumps(read(ROOT/'examples/synthetic-dataset.json')).replace('2026-R','2034-R').replace('2026-01-01','2034-01-01').replace('test:','f1db:'))
        self.data['datasetStatus']='draft';self.data['events'][0].update(season=2034,externalEventId='f1db:race-1')
        self.make_archive();self.old=dict(version=1,photos={'f1db:a':pic('Existing.jpg')},logos={'f1db:team@2026':dict(pic('ExistingLogo.jpg'),years=[2026],periodStatus='manufacturer_brand')},circuits={'track-1':dict(pic('ExistingTrack.jpg'))});self.file.write_bytes(mod.json_bytes(self.old))
        with zipfile.ZipFile(self.source,'w') as z:
            z.writestr('f1db-2034.1.0/src/assets/circuits/black/track-2.svg','<svg><path d="M0 0L10 10"/></svg>')
            z.writestr('f1db-2034.1.0/LICENSE','Creative Commons Attribution 4.0 International Public License')
            z.writestr('f1db-2034.1.0/README.md','Jules Roy — Circuit SVG assets')
        self.photo=patch.object(media,'find_photo',return_value=pic('New.jpg')).start();self.addCleanup(patch.stopall)
        self.discovery=patch.object(media,'discover_logo_files',return_value=['Team Logo.svg']).start()
        self.download=patch.object(media,'read_url',side_effect=AssertionError('unexpected network')).start()
    def make_archive(self):
        old=self.data['sources'][0]['id']
        with zipfile.ZipFile(self.archive,'w') as z:
            for n in REQUIRED|{'f1db-'+k+'.csv' for k in self.tables}:z.writestr(n,self.tables.get(n.removeprefix('f1db-').removesuffix('.csv'),'id\n'))
        h=mod.sha(self.archive);sid='f1db:archive-'+h;self.data=json.loads(json.dumps(self.data).replace(old,sid));self.data['sources'][0].update(id=sid,sha256=h,revision='v2034.1.0',provider='F1DB');self.base.write_bytes(mod.json_bytes(self.data));self.assertFalse(validate(self.data))
    def run_sync(self,**kwargs):return mod.sync(self.base,self.out,archive=self.archive,source=self.source,**kwargs)
    def test_plan_is_read_only(self):
        before=self.file.read_bytes();r=self.run_sync(plan_only=True);self.assertEqual(r['target'],dict(photos=2,layouts=1,teamSeasons=1,events=1));self.assertEqual(r['coverageMissing'],dict(photos=['f1db:b'],layouts=['track-2'],teamSeasons=['f1db:team@2034']));self.assertEqual(before,self.file.read_bytes());self.photo.assert_not_called();self.discovery.assert_not_called();self.download.assert_not_called();self.assertTrue((self.out/'media-sync-plan.json').exists());self.assertFalse((self.out/'media-sync-report.json').exists())
    def test_future_sync_preserves_every_old_item_and_backup(self):
        before=self.file.read_bytes();official=self.base.read_bytes();r=self.run_sync();p=read(self.file)
        self.assertEqual(r['status'],'draft_media_review_required');self.assertEqual(r['added'],dict(photos=['f1db:b'],circuits=['track-2'],logos=[]));self.assertEqual(p['eventLayouts']['f1db:race-1'],[2034,'f1db:track','track-2',self.data['sources'][0]['id']]);self.assertIn('v2034.1.0',p['circuits']['track-2']['source']);self.assertEqual(p['countryCodes']['Example National'],'gb');self.assertEqual((self.out/r['backup']).read_bytes(),before);self.assertEqual(self.base.read_bytes(),official)
        for k in ('photos','logos','circuits'):
            for key,v in self.old[k].items():self.assertEqual(p[k][key],v)
        self.assertFalse(r['logoCandidates']['f1db:team']['approved']);self.assertFalse(r['publicationAuthorized']);self.assertNotIn('f1db:team@2034',p['logos']);self.assertEqual(r['coverageMissing']['teamSeasons'],['f1db:team@2034'])
    def test_idempotent_no_new_requests(self):
        self.run_sync();h=mod.sha(self.file);self.photo.reset_mock();self.discovery.reset_mock();r=self.run_sync();self.assertFalse(r['packChanged']);self.assertEqual(mod.sha(self.file),h);self.photo.assert_not_called();self.discovery.assert_not_called();self.download.assert_not_called()
    def test_exact_year_review_only(self):
        p=self.root/'approved.json';p.write_bytes(mod.json_bytes([dict(id='f1db:team',file='Team Logo.svg',years=[2034],periodStatus='dated_source')]))
        with patch.object(media,'image_item',return_value=pic('Team Logo.svg')) as loader:r=self.run_sync(approvals=p)
        self.assertEqual(r['status'],'draft_media_ready');self.assertEqual(r['coverageMissing']['teamSeasons'],[]);self.assertEqual(read(self.file)['logos']['f1db:team@2034']['years'],[2034]);loader.assert_called_once();self.discovery.assert_not_called()
    def test_wrong_year_approval_rejected_before_network(self):
        p=self.root/'approved.json';p.write_bytes(mod.json_bytes([dict(id='f1db:team',file='Team Logo.svg',years=[2035])]))
        h=mod.sha(self.file)
        with self.assertRaisesRegex(ValueError,'invalid explicit approval'):self.run_sync(approvals=p)
        self.assertEqual(mod.sha(self.file),h);self.photo.assert_not_called()
    def test_mismatched_archive_rejected(self):
        h=mod.sha(self.file);self.archive.write_bytes(b'not archive')
        with self.assertRaisesRegex(ValueError,'matching verified'):self.run_sync()
        self.assertEqual(mod.sha(self.file),h);self.photo.assert_not_called()
    def test_mismatched_event_rejected(self):
        self.data['events'][0]['date']='2034-02-01';self.base.write_bytes(mod.json_bytes(self.data))
        with self.assertRaisesRegex(ValueError,'identity mismatch'):self.run_sync()
        self.photo.assert_not_called()
    def test_new_layout_missing_does_not_reuse_old_layout(self):
        self.tables['races']=self.tables['races'].replace('track-2','track-99');self.make_archive();r=self.run_sync();self.assertEqual(r['unmappedEvents'],['2034-R01']);self.assertEqual(read(self.file)['eventLayouts'],{});self.assertEqual(r['status'],'draft_media_review_required')
    def test_wrong_source_tag_blocks_only_new_track(self):
        with zipfile.ZipFile(self.source,'w') as z:z.writestr('f1db-2026.21.0/src/assets/circuits/black/track-2.svg','<svg/>')
        r=self.run_sync();self.assertIn('circuitSource',r['errors']);self.assertIn('track-2',r['coverageMissing']['layouts']);self.assertEqual(read(self.file)['circuits'],self.old['circuits']);self.assertEqual(r['added']['photos'],['f1db:b'])
    def test_network_failure_retains_old_and_retries(self):
        self.photo.side_effect=TimeoutError('offline');r=self.run_sync();self.assertIn('photos:f1db:b',r['errors']);self.assertEqual(read(self.file)['photos'],self.old['photos']);self.photo.side_effect=None;r=self.run_sync();self.assertEqual(r['added']['photos'],['f1db:b'])
    def test_calendar_only_roster(self):
        e=self.data['events'][0];e['status']='scheduled';e['sessions'][0].update(status='scheduled',results=[]);self.data['drivers']=[];self.data['constructors']=[];self.base.write_bytes(mod.json_bytes(self.data));r=self.run_sync(plan_only=True)
        self.assertEqual(r['coverageMissing']['photos'],['f1db:rookie']);self.assertEqual(r['coverageMissing']['teamSeasons'],['f1db:new-team@2034'])
    def test_lock_no_concurrent_writer(self):
        p=self.out/'.media-sync.lock';p.write_text('123');h=mod.sha(self.file)
        with self.assertRaises(FileExistsError):self.run_sync()
        self.assertEqual(mod.sha(self.file),h);self.assertTrue(p.exists())
    def test_bad_layout_binding_rejected(self):
        p=copy.deepcopy(self.old);p['eventLayouts']={'f1db:race-1':[2034,'f1db:track','../evil',self.data['sources'][0]['id']]}
        with self.assertRaises(ValueError):media.validate_pack(p)
    def test_source_license_change_rejected(self):
        with zipfile.ZipFile(self.source,'w') as z:
            z.writestr('f1db-2034.1.0/LICENSE','All rights reserved')
            z.writestr('f1db-2034.1.0/README.md','Jules Roy')
            z.writestr('f1db-2034.1.0/src/assets/circuits/black/track-2.svg','<svg/>')
        r=self.run_sync();self.assertIn('source license/attribution',r['errors']['circuitSource']);self.assertNotIn('track-2',read(self.file)['circuits'])
    def test_cache_selects_exact_revision(self):
        s=mod.exact_source(self.data);p=self.root/'cache'/s['revision']/s['sha256']/'f1db-csv.zip';p.parent.mkdir(parents=True);p.write_bytes(self.archive.read_bytes());self.assertEqual(mod.resolve_archive(s,cache=self.root/'cache'),p)

if __name__=='__main__':unittest.main()
