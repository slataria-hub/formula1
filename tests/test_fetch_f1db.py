import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from fetch_f1db import release_asset, acquire, latest, REQUIRED, BASE, NAME, API, request


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
    def test_authenticated_api_only(self):
        with patch.dict(os.environ, {'F1DB_GITHUB_TOKEN':'fake-test-token'}), patch('fetch_f1db.urlopen') as opened:
            request(API,30,api=True)
            req=opened.call_args.args[0]
            self.assertEqual(req.get_header('Authorization'),'Bearer fake-test-token')
            self.assertEqual(req.get_header('X-github-api-version'),'2022-11-28')
            request(self.asset['url'],30)
            self.assertIsNone(opened.call_args.args[0].get_header('Authorization'))
            with self.assertRaisesRegex(ValueError,'unexpected release API URL'):
                request('https://example.org/metadata',30,api=True)
            self.assertEqual(opened.call_count,2)
    def test_token_not_forwarded_on_redirect(self):
        with patch.dict(os.environ, {'F1DB_GITHUB_TOKEN':'fake-test-token'}), patch('fetch_f1db.urlopen') as opened:
            request(API,30,api=True)
            req=opened.call_args.args[0]
            redirected=HTTPRedirectHandler().redirect_request(req,None,302,'Found',{},'https://example.org/redirect')
            self.assertIsNone(redirected.get_header('Authorization'))
    def test_unauthenticated_local_api(self):
        with patch.dict(os.environ, {'F1DB_GITHUB_TOKEN':''}), patch('fetch_f1db.urlopen') as opened:
            request(API,30,api=True)
            self.assertIsNone(opened.call_args.args[0].get_header('Authorization'))
    def test_authenticated_rate_limit_still_blocks(self):
        with patch.dict(os.environ, {'F1DB_GITHUB_TOKEN':'fake-test-token'}), patch('fetch_f1db.urlopen',side_effect=HTTPError(API,403,'rate limit exceeded',None,None)) as opened:
            with self.assertRaises(HTTPError): latest()
            self.assertEqual(opened.call_count,1)
    def test_partial_file_cleanup(self):
        with patch('fetch_f1db.request',return_value=io.BytesIO(self.payload[:10])):
            with self.assertRaisesRegex(ValueError,'size mismatch'):acquire(self.asset,self.cache)
        self.assertEqual(list(self.cache.rglob('*.zip')),[]);self.assertEqual(list(self.cache.rglob('*.tmp')),[])

if __name__=='__main__':unittest.main()
