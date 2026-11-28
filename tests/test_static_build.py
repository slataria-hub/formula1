import json, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_preview import build
from static_build import sha, media_info
from validate_data import read
class StaticBuildTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'private').mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'private'); self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name); self.src=self.base/'data.json'; self.data=read(ROOT/'examples/synthetic-dataset.json');self.data['datasetStatus']='draft'; self.src.write_text(json.dumps(self.data))
    def test_explicit_synthetic_and_reproducible(self):
        a,b=self.base/'a',self.base/'b'
        build(self.src,a,mode='pages',synthetic=True);build(self.src,b,mode='pages',synthetic=True)
        x,y=[read(p/'build-manifest.json') for p in (a,b)]
        self.assertEqual(x['files'],y['files']);self.assertFalse(x['publicationAuthorized']);self.assertEqual(x['mode'],'synthetic-draft');self.assertTrue(x['syntheticMediaOnly']);self.assertEqual(x['sportingDataStatus'],'draft');self.assertIn('not imply private',x['visibility'])
        self.assertEqual(set(x['files']),{p.name for p in a.iterdir()}-{'build-manifest.json'})
    def test_missing_media_fails_closed(self):
        with self.assertRaises(ValueError):build(self.src,self.base/'bad',mode='pages')
        self.assertFalse((self.base/'bad').exists())
    def test_reviewed_media_and_hash(self):
        import base64
        item=dict(src='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1ZkAAAAASUVORK5CYII=',source='https://example.invalid',author='synthetic',license='CC BY 4.0')
        pack=dict(version=1,photos={'test:a':item,'test:b':item},logos={},circuits={})
        f=self.base/'media.json'; f.write_text(json.dumps(pack)); manifest=self.base/'review.json'; manifest.write_text(json.dumps(dict(version=1,mediaSha256=sha(f.read_bytes()),officialSha256=sha(self.src.read_bytes()),rightsReviewed=True,reviewReference="synthetic fixture only")))
        out=self.base/'good';build(self.src,out,f,mode='pages',media_manifest=manifest)
        self.assertEqual((out/'visual-media.json').read_bytes(),f.read_bytes());info=read(out/'build-manifest.json')['media'];self.assertEqual(info['objects'],2);self.assertEqual(info['uniqueObjects'],1);self.assertGreater(info['duplicateBytes'],0)
        f.write_text('{}');with_error=self.base/'bad'
        with self.assertRaises(ValueError):build(self.src,with_error,f,mode='pages',media_manifest=manifest)
        self.assertFalse(with_error.exists());self.assertTrue(out.exists())

    def test_pending_rights_private_rehearsal_only(self):
        item=dict(src='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1ZkAAAAASUVORK5CYII=',source='https://example.invalid',author='synthetic',license='CC BY 4.0')
        pack=dict(version=1,photos={self.data['drivers'][0]['id']:item},logos={},circuits={})
        f=self.base/'media.json'; f.write_text(json.dumps(pack)); r=self.base/'review.json'; meta=dict(version=1,mediaSha256=sha(f.read_bytes()),officialSha256=sha(self.src.read_bytes()),rightsReviewed=False,reviewReference='pending fixture');r.write_text(json.dumps(meta))
        out=self.base/'rehearsal';build(self.src,out,f,mode='pages',media_manifest=r,rehearsal=True)
        self.assertEqual(read(out/'build-manifest.json')['mode'],'pages-private-rehearsal')
        with self.assertRaises(ValueError):build(self.src,self.base/'blocked',f,mode='pages',media_manifest=r)
        meta['officialSha256']='0'*64;r.write_text(json.dumps(meta))
        with self.assertRaises(ValueError):build(self.src,self.base/'bad',f,mode='pages',media_manifest=r,rehearsal=True)
        self.assertTrue(out.exists())
