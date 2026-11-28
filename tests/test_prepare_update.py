import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import prepare_update as mod
from validate_data import read

class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.private=self.root/'private';self.private.mkdir()
        self.output=self.private/'run';self.base=self.private/'base.json';self.cache=self.private/'cache'
        self.old=read(ROOT/'examples/synthetic-dataset.json');self.old['datasetStatus']='draft';self.old['sources'][0]['provider']='F1DB'
        self.old['events'][0]['externalEventId']='f1db:race-1';self.base.write_text(json.dumps(self.old))
        self.new=copy.deepcopy(self.old)
        self.asset=dict(tag='v2034.1.0',sha256='a'*64)
        self.audit=dict(issues=[],countbackReviewCandidates=[],knownPointExceptions=[],totals={})
        for key,value in [('ROOT',self.root),('latest',None)]:
            if key=='ROOT':
                p=patch.object(mod,key,value);p.start();self.addCleanup(p.stop)
        self.patches={}
        for key,ret in [('latest',self.asset),('acquire',(self.private/'archive.zip','CACHE')),('import_archive',(self.new,{'archiveSha256':self.asset['sha256']})),('reconcile',(self.new,{})),('correct',(self.new,[])),('audit',self.audit)]:
            p=patch.object(mod,key,return_value=ret);self.patches[key]=p.start();self.addCleanup(p.stop)
    def run_prepare(self,**kwargs):return mod.prepare(self.base,self.output,self.cache,**kwargs)
    def test_success(self):
        before=self.base.read_bytes();r=self.run_prepare();self.assertEqual(r['status'],'draft_ready');self.assertFalse(r['publicationAuthorized']);self.assertFalse(r['activated']);self.assertEqual(self.base.read_bytes(),before);self.assertEqual(read(self.output/'candidate.json'),self.new)
    def test_future_release_no_max_year(self):
        self.run_prepare();kwargs=self.patches['import_archive'].call_args.kwargs;self.assertEqual(kwargs['from_season'],2026);self.assertNotIn('to_season',kwargs);self.assertEqual(kwargs['revision'],'v2034.1.0')
    def test_existing_output(self):
        self.output.mkdir();(self.output/'keep').write_text('keep')
        with self.assertRaises(FileExistsError):self.run_prepare()
        self.assertEqual((self.output/'keep').read_text(),'keep');self.patches['latest'].assert_not_called()
    def test_output_outside_private(self):
        with self.assertRaises(ValueError):mod.prepare(self.base,self.root/'public',self.cache)
    def test_network_failure(self):
        self.patches['latest'].side_effect=TimeoutError('network')
        with self.assertRaises(TimeoutError):self.run_prepare()
        self.assertEqual(read(self.output/'update-report.json')['stage'],'fetch');self.assertFalse((self.output/'candidate.json').exists())
    def test_digest_changed(self):
        self.patches['import_archive'].return_value=(self.new,{'archiveSha256':'bad'})
        with self.assertRaisesRegex(ValueError,'archive changed'):self.run_prepare()
        self.assertFalse((self.output/'candidate.json').exists())
    def test_removed_event(self):
        self.new['events'][0]['externalEventId']='f1db:race-2'
        with self.assertRaisesRegex(ValueError,'compatibility'):self.run_prepare()
        self.assertFalse((self.output/'candidate.json').exists())
    def test_audit_failure(self):
        self.audit['issues']=[{'code':'unexplained_points_delta'}]
        with self.assertRaisesRegex(ValueError,'audit'):self.run_prepare()
        self.assertFalse((self.output/'candidate.json').exists());self.assertTrue((self.output/'audit-report.json').exists())
    def test_countback_review_draft(self):
        self.audit['countbackReviewCandidates']=[{}];r=self.run_prepare();self.assertEqual(r['audit']['countbackCandidates'],1);self.assertFalse(r['publicationAuthorized'])
    def test_browser_backup_read_only(self):
        user=read(ROOT/'examples/user.example.json');store=dict(version=1,user=user,bindings={'2026-R01-race':dict(kind='race',season=2026,externalEventId='f1db:race-1')})
        p=self.private/'user.json';p.write_text(json.dumps(store));before=p.read_bytes();r=self.run_prepare(user=p);self.assertEqual(p.read_bytes(),before);self.assertIn('passed',r['userCheck']);self.assertFalse((self.output/'user.json').exists())
    def test_browser_import_provenance_compatible(self):
        user=read(ROOT/'examples/user.example.json');store=dict(version=1,user=user,bindings={'2026-R01-race':dict(kind='race',season=2026,externalEventId='f1db:race-1',imported=True)})
        before=copy.deepcopy(store);self.assertEqual(mod.user_payload(store,self.old,self.new),user);self.assertEqual(store,before)
    def test_browser_bad_binding(self):
        user=read(ROOT/'examples/user.example.json');store=dict(version=1,user=user,bindings={'2026-R01-race':dict(kind='race',season=2026,externalEventId='f1db:race-2')})
        with self.assertRaisesRegex(ValueError,'binding mismatch'):mod.user_payload(store,self.old,self.new)
    def test_optional_media_sync_after_candidate(self):
        with patch('sync_media.sync',return_value={'status':'draft_media_ready','present':{},'errors':{}}) as sync,patch.object(sys,'argv',['prepare_update.py','--baseline',str(self.base),'--output',str(self.output),'--cache-dir',str(self.cache),'--media-output',str(self.private/'media')]):
            self.assertEqual(mod.main(),0)
            sync.assert_called_once_with(self.output/'candidate.json',str(self.private/'media'),cache=str(self.cache))
            self.assertTrue((self.output/'candidate.json').exists())
    def test_media_failure_does_not_invalidate_candidate(self):
        with patch('sync_media.sync',side_effect=TimeoutError('offline')),patch.object(sys,'argv',['prepare_update.py','--baseline',str(self.base),'--output',str(self.output),'--cache-dir',str(self.cache),'--media-output',str(self.private/'media')]):
            self.assertEqual(mod.main(),2)
            self.assertEqual(read(self.output/'update-report.json')['status'],'draft_ready')
            self.assertTrue((self.output/'candidate.json').exists())
    def test_blocked_candidate_does_not_trigger_media(self):
        self.audit['issues']=[{'code':'bad'}]
        with patch('sync_media.sync') as sync,patch.object(sys,'argv',['prepare_update.py','--baseline',str(self.base),'--output',str(self.output),'--media-output',str(self.private/'media')]):
            self.assertEqual(mod.main(),1);sync.assert_not_called()
    def test_diff_future_season_and_completed(self):
        old={'events':[{'id':'2026-R01','season':2026,'status':'scheduled','date':'2026-01-01','sessions':[{'id':'s1','status':'scheduled','results':[]}]}]};new=copy.deepcopy(old);new['events'][0]['status']='completed';new['events'][0]['sessions'][0].update(status='final',results=[1]);new['events'].append({'id':'2027-R01','season':2027,'status':'scheduled','date':'2027-01-01','sessions':[]});d=mod.differences(old,new);self.assertEqual(d['newSeasons'],[2027]);self.assertEqual(d['newlyCompleted'],['2026-R01']);self.assertEqual(d['newFinalSessions'],['s1'])

if __name__=='__main__':unittest.main()
