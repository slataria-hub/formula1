import csv,io,json,os,sys,tempfile,unittest,subprocess
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import pages_release as p
from published_store import PublishedStore
from release_store import canon
from static_build import sha
import test_pages_release as fixtures

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'private').mkdir(exist_ok=True);self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'private');self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.repo=self.root/'repo';self.repo.mkdir();self.git('init');self.git('config','user.name','fixture');self.git('config','user.email','fixture@example.invalid')
        f=fixtures.GateTests();f.setUp();self.f=f
        self.code=self.commit({'web/preview/'+k:v for k,v in f.code.items()},'main')
        self.draft=self.commit({'official.json':f.rawdraft,'manifest.json':canon(f.md)},'f1-data')
        f.meta=canon(dict(json.loads(f.meta),sourceDataCommit=self.draft,independentReviewSha256='a'*64))
        self.approved=self.commit({'official.json':f.raw,'manifest.json':f.meta},'f1-approved-data')
        self.media_files={'visual-media.json':f.media,'rights-register.csv':f.reg,'manifest.json':canon(p.media_manifest(f.media,f.reg,f.code['media.mjs'],f.raw,f.body['sourceTag'],f.d['schemaVersion']))}
        self.media=self.commit(self.media_files,'f1-media')
    def git(self,*args,input=None):return subprocess.check_output(['git','-C',str(self.repo),*args],input=input,stderr=subprocess.DEVNULL).decode().strip()
    def tree(self,files):
        groups={};entries=[]
        for name,data in sorted(files.items()):
            if '/' in name:
                first,rest=name.split('/',1);groups.setdefault(first,{})[rest]=data
            else:
                oid=self.git('hash-object','-w','--stdin',input=data);entries.append(f'100644 blob {oid}\t{name}\n')
        for n,items in groups.items():entries.append(f'040000 tree {self.tree(items)}\t{n}\n')
        return self.git('mktree',input=''.join(entries).encode())
    def commit(self,files,branch,parent=None):
        tree=self.tree(files);c=self.git('commit-tree',tree,*(['-p',parent] if parent else []),input=b'fixture\n');self.git('update-ref','refs/remotes/origin/'+branch,c);return c
    def candidate(self,formed='2026-11-28T00:00:00+00:00',media=None,approved=None):
        return p.describe(self.repo,code_commit=self.code,data_commit=approved or self.approved,source_data_commit=self.draft,media_commit=media or self.media,formed_at=formed)
    def release(self,formed='2026-11-28T00:00:00+00:00',parent=None):
        cand=self.candidate(formed);self.assertFalse(cand['publicationAuthorized']);d,a=p.finalize(cand,cand['releaseId'],'fixture owner','fixture architect','test-only record','2026-11-28T01:00:00+00:00');c=self.commit({'release.json':canon(d),'approval.json':a},'f1-releases',parent);return c,sha(a),d
    def test_actual_commit_resolution_and_deterministic_build(self):
        c,pin,d=self.release();a=self.root/'a';b=self.root/'b';p.build(self.repo,c,pin,a);p.build(self.repo,c,pin,b)
        self.assertEqual(p.load_files(a,p.SITE),p.load_files(b,p.SITE));self.assertEqual(p.resolve(self.repo,c,pin)[1],d);self.assertEqual((a/'official.json').read_bytes(),self.f.raw)
    def test_corrupted_media_manifest(self):
        bad=self.commit({**self.media_files,'manifest.json':b'{}'},'f1-media',self.media)
        with self.assertRaisesRegex(ValueError,'manifest incompatibility'):self.candidate(media=bad)
    def test_projection_mismatch(self):
        d=dict(self.f.d);d['drivers']=[dict(x) for x in d['drivers']];d['drivers'][0]['name']='Different';raw=canon(d)
        bad=self.commit({'official.json':raw,'manifest.json':self.f.meta},'f1-approved-data',self.approved)
        with self.assertRaisesRegex(ValueError,'differs from source'):self.candidate(approved=bad)
    def test_finalize_wrong_review_id(self):
        d=self.candidate()
        with self.assertRaises(ValueError):p.finalize(d,'0'*64,'a','b','test','2026-11-28T01:00:00+00:00')
    def test_previous_exact_restore_and_failed_smoke(self):
        c1,pin1,d1=self.release();c2,pin2,d2=self.release('2026-11-28T00:15:00+00:00',c1);s=PublishedStore(self.root/'store');e1=s.retain(self.repo,c1,pin1);self.assertEqual(s.retain(self.repo,c1,pin1),e1);e2=s.retain(self.repo,c2,pin2);self.assertIsNone(s.pointers()['current_published'])
        with patch('published_store.check',return_value=None):s.confirm(d1['releaseId'],pin1);s.confirm(d2['releaseId'],pin2)
        self.assertEqual(s.pointers(),{'current_published':e2,'previous_published':e1});dest=self.root/'restore';s.restore(d1['releaseId'],pin1,dest);self.assertEqual(p.load_files(dest,p.SITE),p.resolve(self.repo,c1,pin1)[0]);old=s.pointers()
        with patch('published_store.check',side_effect=ValueError('synthetic HTTP failure')):
            with self.assertRaises(ValueError):s.confirm(d1['releaseId'],pin1)
        self.assertEqual(s.pointers(),old)
        with patch('published_store.check',return_value=None):s.confirm(d1['releaseId'],pin1)
        self.assertEqual(s.pointers()['current_published'],e1)
    def test_corrupt_store_no_restore(self):
        c,pin,d=self.release();s=PublishedStore(self.root/'store');s.retain(self.repo,c,pin);(s.versions/d['releaseId']/'style.css').write_bytes(b'broken')
        with self.assertRaises(ValueError):s.restore(d['releaseId'],pin,self.root/'bad')
        self.assertFalse((self.root/'bad').exists())
    def test_wrong_pin_no_artifact(self):
        c,pin,d=self.release();dest=self.root/'bad'
        with self.assertRaises(ValueError):p.build(self.repo,c,'0'*64,dest)
        self.assertFalse(dest.exists())
    def test_workflow_code_binding_and_explicit_rollback(self):
        c,pin,d=self.release()
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true','GITHUB_SHA':'a'*40,'F1_DEPLOY_MODE':'publish'}):
            with self.assertRaisesRegex(ValueError,'revision differ'):p.resolve(self.repo,c,pin)
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true','GITHUB_SHA':'a'*40,'F1_DEPLOY_MODE':'rollback'}):self.assertEqual(p.resolve(self.repo,c,pin)[1],d)
if __name__=='__main__':unittest.main()
