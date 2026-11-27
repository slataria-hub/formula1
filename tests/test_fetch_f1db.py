import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from fetch_f1db import release_asset, acquire, latest, REQUIRED, BASE, NAME


def make_zip(names=REQUIRED):
    f=io.BytesIO()
    with zipfile.ZipFile(f,'w') as z:
        for name in sorted(names): z.writestr(name,'id\n1\n')
    return f.getvalue()


def metadata(payload, tag='v2028.1.0'):
    return dict(tag_name=tag,draft=False,prerelease=False,assets=[dict(name=NAME,state='uploaded',size=len(payload),digest='sha256:'+hashlib.sha256(payload).hexdigest(),browser_download_url=BASE+tag+'/'+NAME)])


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.payload=make_zip(); self.meta=metadata(self.payload); self.asset=release_asset(self.meta)
        self.source=self.root/'source.zip'; self.source.write_bytes(self.payload);self.cache=self.root/'cache'
    def test_future_release(self):
        self.assertEqual(self.asset['tag'],'v2028.1.0')
        self.assertEqual(release_asset(metadata(self.payload,'v2034.2.1'))['tag'],'v2034.2.1')
    def test_draft_and_prerelease(self):
        for field in ('draft','prerelease'):
            with self.subTest(field=field), self.assertRaises(ValueError): release_asset(dict(self.meta,**{field:True}))
    def test_missing_digest(self):
        self.meta['assets'][0]['digest']=None
        with self.assertRaises(ValueError): release_asset(self.meta)
    def test_bad_url(self):
        self.meta['assets'][0]['browser_download_url']='https://example.org/x.zip'
        with self.assertRaises(ValueError): release_asset(self.meta)
    def test_ambiguous_asset(self):
        self.meta['assets']*=2
        with self.assertRaises(ValueError): release_asset(self.meta)
    def test_invalid_tag(self):
        self.meta['tag_name']='../../x'
        with self.assertRaises(ValueError): release_asset(self.meta)
    def test_local_cache_and_no_overwrite(self):
        p,state=acquire(self.asset,self.cache,local_archive=self.source);self.assertEqual(state,'LOCAL');self.assertEqual(p.read_bytes(),self.payload)
        stamp=p.stat().st_mtime_ns
        with patch('fetch_f1db.request',side_effect=AssertionError('network called')):
            q,state=acquire(self.asset,self.cache)
        self.assertEqual((q,state),(p,'CACHE'));self.assertEqual(p.stat().st_mtime_ns,stamp)
    def test_corrupt_cache_blocks(self):
        p,_=acquire(self.asset,self.cache,local_archive=self.source);p.write_bytes(b'x')
        with self.assertRaises(ValueError):acquire(self.asset,self.cache,local_archive=self.source)
        self.assertEqual(p.read_bytes(),b'x')
    def test_bad_hash_no_file(self):
        self.source.write_bytes(b'x'*len(self.payload))
        with self.assertRaisesRegex(ValueError,'SHA-256'): acquire(self.asset,self.cache,local_archive=self.source)
        self.assertEqual(list(self.cache.rglob('*.zip')),[]);self.assertEqual(list(self.cache.rglob('*.tmp')),[])
    def test_missing_table(self):
        payload=make_zip(REQUIRED-{'f1db-races.csv'});self.source.write_bytes(payload)
        with self.assertRaisesRegex(ValueError,'missing CSV'): acquire(release_asset(metadata(payload)),self.cache,local_archive=self.source)
    def test_network_retry_and_cache(self):
        with patch('fetch_f1db.request',side_effect=[TimeoutError(),io.BytesIO(self.payload)]) as req,patch('fetch_f1db.time.sleep'):
            p,state=acquire(self.asset,self.cache)
        self.assertEqual(req.call_count,2);self.assertEqual(state,'DOWNLOADED');self.assertEqual(p.read_bytes(),self.payload)
    def test_rate_limit_no_retry(self):
        with patch('fetch_f1db.request',side_effect=HTTPError('https://example.org',429,'limit',None,None)) as req:
            with self.assertRaises(HTTPError):acquire(self.asset,self.cache)
        self.assertEqual(req.call_count,1);self.assertEqual(list(self.cache.rglob('*.tmp')),[])
    def test_metadata_discovery(self):
        with patch('fetch_f1db.request',return_value=io.BytesIO(json.dumps(self.meta).encode())) as req:
            self.assertEqual(latest(),self.asset)
        self.assertTrue(req.call_args.kwargs['api'])
    def test_partial_file_cleanup(self):
        with patch('fetch_f1db.request',return_value=io.BytesIO(self.payload[:10])):
            with self.assertRaisesRegex(ValueError,'size mismatch'):acquire(self.asset,self.cache)
        self.assertEqual(list(self.cache.rglob('*.zip')),[]);self.assertEqual(list(self.cache.rglob('*.tmp')),[])

if __name__=='__main__':unittest.main()
