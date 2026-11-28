import copy, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from activate_update import json_bytes
from build_preview import build
from persist_draft import manifest, SEED
from media_catalog import make_manifest
from release_store import ReleaseStore,verify_release
from static_build import sha
from validate_data import read

class StorageTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'private').mkdir(exist_ok=True);self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'private');self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        d=read(ROOT/'examples/synthetic-dataset.json');d['datasetStatus']='draft';sid='f1db:archive-'+SEED['sha256']
        def walk(x):
            if isinstance(x,dict):
                for k,v in list(x.items()):
                    if k=='sourceIds':x[k]=[sid if t=='test:sample' else t for t in v]
                    else:walk(v)
            elif isinstance(x,list):
                for v in x:walk(v)
        walk(d);d['sources'][0].update(id=sid,provider='F1DB',revision=SEED['tag'],sha256=SEED['sha256'])
        e=d['events'][0];e.update(externalEventId='f1db:race-1',grandPrixKey='f1db:gp-1')
        self.raw=json_bytes(d);self.data=self.base/'official.json';self.data.write_bytes(self.raw)
        self.meta=self.base/'data-manifest.json';self.meta.write_bytes(json_bytes(manifest(self.raw,SEED,None)))
        self.media=self.base/'visual-media.json';self.media.write_bytes(json_bytes(dict(version=1,photos={d['drivers'][0]['id']:dict(src='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1ZkAAAAASUVORK5CYII=',source='https://example.invalid',author='fixture',license='CC BY 4.0')},logos={},circuits={})))
        self.flags=(ROOT/'web/preview/media.mjs').read_bytes();self.mm,self.reg,b=make_manifest(self.raw,self.media.read_bytes(),self.flags);self.binding=self.base/'binding.json';self.binding.write_bytes(json_bytes(b));self.store=ReleaseStore(self.base/'store');self.site=self.base/'site';build(self.data,self.site,self.media,media_manifest=self.binding,manifest=True)
    def retain(self,commit='1'*40):return self.store.retain(self.site,self.meta,commit)
    def test_idempotent_restore_rollback(self):
        a=self.retain();self.assertEqual(a,self.retain());b=self.retain('2'*40);self.assertNotEqual(a['releaseId'],b['releaseId']);p=self.store.pointers();self.assertEqual(p['previous_valid_draft'],a['releaseId']);self.assertEqual(p['last_valid_draft'],b['releaseId']);self.assertIsNone(p['current_published']);self.store.restore(a['releaseId'],self.base/'restored');self.assertEqual((self.base/'restored'/'official.json').read_bytes(),self.raw);self.assertEqual((self.base/'restored'/'visual-media.json').read_bytes(),self.media.read_bytes());self.store.rollback_draft(a['releaseId']);self.assertEqual(self.store.pointers()['last_valid_draft'],a['releaseId']);self.assertEqual(self.store.pointers()['latest_checked'],b['releaseId'])
    def test_corrupt_file_blocked(self):
        a=self.retain();(self.store.versions/a['releaseId']/'official.json').write_bytes(b'{}');before=self.store.pointers();self.assertRaises(ValueError,self.store.restore,a['releaseId'],self.base/'bad');self.assertEqual(before,self.store.pointers());self.assertFalse((self.base/'bad').exists())
    def test_incompatible_source_blocked(self):
        m=read(self.meta);m['release']['tag']='v2027.1.0';self.meta.write_bytes(json_bytes(m));self.assertRaises(ValueError,self.retain);self.assertIsNone(self.store.pointers()['last_valid_draft'])
    def test_publication_flag_rejected(self):
        a=self.retain();f=self.store.versions/a['releaseId']/'release-manifest.json';r=read(f);r['publicationAuthorized']=True;f.write_bytes(json_bytes(r));self.assertRaises(ValueError,self.store.get,a['releaseId'])
    def test_private_file_rejected(self):
        (self.site/'user.json').write_text('{}');self.assertRaises(ValueError,self.retain)
    def test_rehearsal_and_registry(self):
        self.assertEqual(self.mm['rightsStatus'],'pending');self.assertFalse(self.mm['publicationAuthorized']);self.assertIn(b'publicAllowed',self.reg);self.assertEqual(self.mm['counts']['photos'],1);self.assertEqual(self.mm['counts']['flags'],0 if __import__('os').environ.get('F1_PUBLIC_PROFILE')=='circuits-only' else 42)
    def test_sync_binding(self):
        r=dict(packSha256=self.mm['mediaSha256'],sourceTag=SEED['tag'],archiveSha256=SEED['sha256'],publicationAuthorized=False,status='draft_media_ready')
        a,_,_=make_manifest(self.raw,self.media.read_bytes(),self.flags,sync_report=json_bytes(r));self.assertEqual(a['syncReportSha256'],sha(json_bytes(r)));r['packSha256']='0'*64;self.assertRaises(ValueError,make_manifest,self.raw,self.media.read_bytes(),self.flags,sync_report=json_bytes(r))
    def test_rollback_corrupt_previous_leaves_pointers(self):
        a=self.retain();self.retain('2'*40);p=self.store.pointers();(self.store.versions/a['releaseId']/'media.mjs').write_text('broken');self.assertRaises(ValueError,self.store.rollback_draft,a['releaseId']);self.assertEqual(self.store.pointers(),p)
    def test_no_overwrite_restore(self):
        a=self.retain();dest=self.base/'existing';dest.mkdir();self.assertRaises(FileExistsError,self.store.restore,a['releaseId'],dest)

if __name__=='__main__':unittest.main()
