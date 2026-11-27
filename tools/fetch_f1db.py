"""Fetch latest stable F1DB CSV release into immutable local cache. No publication."""
import argparse
import hashlib
import json
import os
import re
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API = 'https://api.github.com/repos/f1db/f1db/releases/latest'
BASE = 'https://github.com/f1db/f1db/releases/download/'
NAME = 'f1db-csv.zip'
MAX_BYTES = 128 * 1024 * 1024
MAX_UNPACKED = 512 * 1024 * 1024
REQUIRED = {'f1db-'+x+'.csv' for x in ('races','races-race-results','races-qualifying-results',
    'races-sprint-race-results','races-sprint-qualifying-results','races-fastest-laps',
    'races-driver-standings','races-constructor-standings','drivers','constructors','circuits',
    'countries','grands-prix','seasons-driver-standings','seasons-constructor-standings')}


def release_asset(release):
    if release.get('draft') is not False or release.get('prerelease') is not False:
        raise ValueError('not a stable published release')
    tag = release.get('tag_name','')
    if not isinstance(tag,str) or not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+',tag):
        raise ValueError('unexpected stable release tag')
    assets = [a for a in release.get('assets',[]) if a.get('name') == NAME]
    if len(assets) != 1: raise ValueError('missing or ambiguous CSV asset')
    asset = assets[0]
    url = BASE + tag + '/' + NAME
    if asset.get('browser_download_url') != url or asset.get('state') != 'uploaded':
        raise ValueError('unexpected asset URL/state')
    digest = asset.get('digest')
    if not isinstance(digest,str) or not re.fullmatch(r'sha256:[a-fA-F0-9]{64}',digest):
        raise ValueError('published SHA-256 missing or invalid; refusing unverified download')
    size = asset.get('size')
    if type(size) is not int or not 0 < size <= MAX_BYTES:
        raise ValueError('unexpected asset size')
    return dict(tag=tag,url=url,sha256=digest[7:].lower(),size=size,publishedAt=release.get('published_at'))


def request(url, timeout, api=False):
    headers={'User-Agent':'F1Analytics-release-fetch/1.0','Accept':'application/vnd.github+json' if api else 'application/octet-stream'}
    if api: headers['X-GitHub-Api-Version']='2022-11-28'
    return urlopen(Request(url,headers=headers),timeout=timeout)


def retry(operation, attempts=3):
    for i in range(attempts):
        try: return operation()
        except HTTPError as e:
            # Rate limits require a subsequent run, not an aggressive retry loop.
            if e.code not in (500,502,503,504) or i+1==attempts: raise
        except (URLError,TimeoutError,ConnectionError):
            if i+1==attempts: raise
        time.sleep(2**i)


def latest(timeout=30):
    def load():
        with request(API,timeout,api=True) as response:
            raw=response.read(4*1024*1024+1)
        if len(raw)>4*1024*1024: raise ValueError('release metadata too large')
        return release_asset(json.loads(raw))
    return retry(load)


def verify_archive(path, asset):
    path=Path(path)
    if path.stat().st_size != asset['size']: raise ValueError('asset size mismatch')
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    if h.hexdigest()!=asset['sha256']: raise ValueError('asset SHA-256 mismatch')
    with zipfile.ZipFile(path) as z:
        info=z.infolist(); names=[x.filename for x in info]
        if len(names)!=len(set(names)) or not REQUIRED <= set(names):
            raise ValueError('duplicate or missing CSV tables')
        if sum(x.file_size for x in info)>MAX_UNPACKED or len(info)>1024:
            raise ValueError('archive exceeds safety limits')
        if any('/' in n or '\\' in n or not n.endswith('.csv') for n in names):
            raise ValueError('unexpected ZIP entry')
        bad=z.testzip()
        if bad: raise ValueError('CRC mismatch: '+bad)
    return path


def acquire(asset, cache_dir, timeout=30, local_archive=None):
    # Tag and digest validated by release_asset; never replace a cached archive.
    dest=Path(cache_dir)/asset['tag']/asset['sha256']/NAME
    if dest.exists(): return verify_archive(dest,asset), 'CACHE'
    dest.parent.mkdir(parents=True,exist_ok=True)
    def download():
        fd,tmp=tempfile.mkstemp(dir=dest.parent,prefix='.download-',suffix='.tmp')
        try:
            with os.fdopen(fd,'wb') as out:
                stream=Path(local_archive).open('rb') if local_archive is not None else request(asset['url'],timeout)
                with stream:
                    count=0
                    while True:
                        chunk=stream.read(1024*1024)
                        if not chunk: break
                        count+=len(chunk)
                        if count>asset['size']: raise ValueError('download larger than published size')
                        out.write(chunk)
                out.flush();os.fsync(out.fileno())
            verify_archive(tmp,asset)
            try: os.link(tmp,dest)
            except FileExistsError: return verify_archive(dest,asset),'CACHE'
            return dest,'LOCAL' if local_archive is not None else 'DOWNLOADED'
        finally: Path(tmp).unlink(missing_ok=True)
    return download() if local_archive is not None else retry(download)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache-dir',default='private/f1db/releases')
    p.add_argument('--timeout',type=int,default=30)
    p.add_argument('--metadata-only',action='store_true')
    p.add_argument('--release-json',help='Offline test: saved release metadata (not live verification)')
    p.add_argument('--local-archive',help='Offline test: archive matching saved release metadata')
    a=p.parse_args()
    if not 1<=a.timeout<=300: p.error('--timeout must be 1..300')
    if bool(a.release_json)!=bool(a.local_archive) and not (a.release_json and a.metadata_only):
        p.error('offline mode requires --release-json and --local-archive (unless metadata-only)')
    try:
        asset=release_asset(json.loads(Path(a.release_json).read_text(encoding='utf-8-sig'))) if a.release_json else latest(a.timeout)
        print('RELEASE',asset['tag'],'SHA256',asset['sha256'],'BYTES',asset['size'],flush=True)
        if a.metadata_only: return 0
        path,state=acquire(asset,a.cache_dir,a.timeout,a.local_archive)
        print(state, path,flush=True)
        print('PASS archive integrity only; no import or publication authorized')
        print(json.dumps(dict(asset,archive=str(path),result=state,publicationAuthorized=False)))
        return 0
    except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile,RuntimeError) as e:
        print('FETCH FAILED:',e);return 1
    except KeyboardInterrupt:
        print('FETCH CANCELLED');return 130

if __name__=='__main__': raise SystemExit(main())
