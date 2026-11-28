"""Local immutable DRAFT release storage. No network, Git writes, or public promotion.
The owner must keep the directory access-controlled and backed up independently.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from activate_update import private_path, draft, json_bytes
from persist_draft import verify as verify_data
from static_build import ASSETS, parse_json, sha, build_manifest, media_info, data_bytes
from media_catalog import catalog_for_verified_data
from repository_audit import inspect_bytes

HEX=re.compile(r'[0-9a-f]{64}')
COMMIT=re.compile(r'[0-9a-f]{40}')
SITE=set(ASSETS)|{'official.json','build-manifest.json'}
FILES=SITE|{'data-manifest.json','media-manifest.json','rights-register.csv','release-manifest.json'}
POINTERS={'latest_checked':None,'last_valid_draft':None,'previous_valid_draft':None,'current_published':None,'previous_published':None}

def canon(obj):return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def record(raw):return {'sha256':sha(raw),'bytes':len(raw)}
def require_id(value):
    if not isinstance(value,str) or not HEX.fullmatch(value):raise ValueError('invalid release ID')
    return value

def load_files(root,names):
    root=Path(root)
    if root.is_symlink() or not root.is_dir() or {p.name for p in root.iterdir()}!=names:raise ValueError('unexpected release files')
    result={}
    for name in names:
        p=root/name
        if p.is_symlink() or not p.is_file():raise ValueError('nonregular release file')
        result[name]=p.read_bytes()
    return result

def checked_material(files,data_commit, *, populate=False):
    if not isinstance(data_commit,str) or not COMMIT.fullmatch(data_commit):raise ValueError('invalid data commit')
    raw=files['official.json'];meta=parse_json(files['data-manifest.json']);data=verify_data(raw,meta)
    media=files['visual-media.json']; flags=files['media.mjs']; mm,register,binding=catalog_for_verified_data(raw,media,flags,data)
    if populate:
        files['media-manifest.json']=json_bytes(mm);files['rights-register.csv']=register
    # Store only independently derived pending review metadata; never trust caller claims.
    if meta['release']['tag']!=mm['sourceTag'] or meta['release']['sha256']!=mm['archiveSha256']:
        raise ValueError('data manifest release differs from media source')
    if parse_json(files['media-manifest.json'])!=mm or files['rights-register.csv']!=register:raise ValueError('media manifest or register mismatch')
    b=parse_json(files['build-manifest.json']);prov=b.get('provenance')
    if not isinstance(prov,dict) or not isinstance(prov.get('sourceFiles'),dict) or prov.get('sourceSha256')!=sha(canon(prov['sourceFiles'])):
        raise ValueError('invalid source provenance')
    code=b.get('codeCommit')
    if code is not None and (not isinstance(code,str) or not COMMIT.fullmatch(code)):raise ValueError('invalid code commit')
    if prov.get('codeCommit')!=code:raise ValueError('inconsistent code provenance')
    for name in set(ASSETS)-{'visual-media.json'}:
        if prov['sourceFiles'].get('web/preview/'+name)!=sha(files[name]):raise ValueError('source hash mismatch')
    if b.get('mode') not in ('local-draft','pages-private-rehearsal'):raise ValueError('only local pending-rights builds can be retained here')
    if not isinstance(b.get('builtAt'),str) or not b['builtAt']:raise ValueError('missing build timestamp')
    info=media_info(media,data,binding,rehearsal=True,official_sha=sha(raw))
    expected=build_manifest({n:files[n] for n in SITE-{'build-manifest.json'}},data,info,code_commit=code,mode=b['mode'],input_sha=sha(raw),timestamp=b['builtAt'],provenance=prov)
    if b!=expected:raise ValueError('build manifest mismatch')
    if any(inspect_bytes(n,files[n]) for n in SITE):raise ValueError('security screening blocked release')
    return dict(contractVersion=1,codeCommit=code,codeSourceSha256=prov['sourceSha256'],dataCommit=data_commit,dataCommitBinding='caller-supplied; compare against trusted Git object before cloud use',mediaVersion=mm['mediaVersion'],sourceTag=meta['release']['tag'],schemaVersion=data['schemaVersion'],officialSha256=sha(raw),mediaSha256=sha(media),formedAt=b['builtAt'],verificationStatus='structural_pass_independent_pending',rightsStatus='pending',publicationAuthorized=False,storageScope='local-only; not a privacy guarantee',files={n:record(v) for n,v in sorted(files.items())})

def manifest(files,data_commit):
    body=checked_material(files,data_commit,populate=True)
    # build timestamp is part of the exact build-manifest bytes; idempotence means exact same bundle.
    return dict(body,releaseId=sha(canon(body)),createdAt=datetime.now(timezone.utc).isoformat())

def verify_release(directory):
    f=load_files(directory,FILES); r=parse_json(f.pop('release-manifest.json'))
    created=r.pop('createdAt',None); rid=r.pop('releaseId',None)
    if not isinstance(created,str):raise ValueError('missing release timestamp')
    datetime.fromisoformat(created)
    if require_id(rid)!=Path(directory).name or rid!=sha(canon(r)):raise ValueError('release ID mismatch')
    if r!=checked_material(f,r['dataCommit']):raise ValueError('release integrity or authorization mismatch')
    return dict(r,releaseId=rid,createdAt=created)

class ReleaseStore:
    def __init__(self,root):
        self.root=private_path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.versions=self.root/'versions'; self.versions.mkdir(exist_ok=True)
        if self.versions.is_symlink():raise ValueError('unsafe versions directory')
        self.pointer=self.root/'pointers.json'
    @contextmanager
    def lock(self):
        p=self.root/'.write.lock';fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        try:yield
        finally:os.close(fd);p.unlink()
    def pointers(self):
        if self.pointer.is_symlink():raise ValueError('unsafe pointer file')
        r=parse_json(self.pointer.read_bytes()) if self.pointer.exists() else POINTERS.copy()
        if set(r)!=set(POINTERS) or r['current_published'] is not None or r['previous_published'] is not None:raise ValueError('publication not supported in F1-012.3')
        for v in r.values():
            if v is not None:require_id(v)
        return r
    def write_pointers(self,p):
        fd,tmp=tempfile.mkstemp(prefix='.pointers-',dir=self.root);os.close(fd)
        try:
            with open(tmp,'wb') as f:f.write(json_bytes(p));f.flush();os.fsync(f.fileno())
            os.replace(tmp,self.pointer)
        finally:Path(tmp).unlink(missing_ok=True)
    def get(self,rid):return verify_release(self.versions/require_id(rid))
    def retain(self,site,data_manifest,data_commit):
        files=load_files(site,SITE);files['data-manifest.json']=Path(data_manifest).read_bytes()
        r=manifest(files,data_commit);rid=r['releaseId'];target=self.versions/rid
        with self.lock():
            p=self.pointers()
            if target.exists():
                existing=self.get(rid)
                if {k:v for k,v in existing.items() if k!='createdAt'}!={k:v for k,v in r.items() if k!='createdAt'}:raise ValueError('immutable release collision')
                # A retry of an older release must not move the current pointer backward.
                return existing
            tmp=Path(tempfile.mkdtemp(prefix='.release-',dir=self.root))
            try:
                staging=tmp/rid;staging.mkdir()
                for n,v in files.items():(staging/n).write_bytes(v)
                (staging/'release-manifest.json').write_bytes(json_bytes(r))
                # Re-read exact staged bytes, already semantically checked above.
                if load_files(staging,FILES)!={**files,'release-manifest.json':json_bytes(r)}:raise ValueError('staged bytes changed')
                staging.rename(target)
                if p['last_valid_draft']!=rid:p['previous_valid_draft']=p['last_valid_draft']
                p.update(latest_checked=rid,last_valid_draft=rid);self.write_pointers(p)
            finally:shutil.rmtree(tmp)
        return r
    def restore(self,rid,destination):
        dest=private_path(destination);rid=require_id(rid)
        if dest.exists():raise FileExistsError('restore destination exists')
        r=self.get(rid);dest.parent.mkdir(parents=True,exist_ok=True)
        tmp=Path(tempfile.mkdtemp(prefix='.restore-',dir=dest.parent))
        try:
            copy=tmp/rid;shutil.copytree(self.versions/rid,copy)
            copied=load_files(copy,FILES);meta=parse_json(copied.pop('release-manifest.json'))
            if meta!=r or {n:record(v) for n,v in copied.items()}!=r['files']:raise ValueError('restored bytes differ')
            # Exact copy to new local directory; pointers unchanged. No deployment.
            if dest.exists():raise FileExistsError('restore destination exists')
            copy.rename(dest)
        finally:shutil.rmtree(tmp)
    def rollback_draft(self,rid):
        with self.lock():
            p=self.pointers();rid=require_id(rid)
            if rid!=p['previous_valid_draft']:raise ValueError('only previous valid draft may be restored as pointer')
            self.get(rid)
            p['previous_valid_draft'],p['last_valid_draft']=p['last_valid_draft'],rid
            # latest_checked is diagnostic, not the active draft.
            self.write_pointers(p);return p

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--store',required=True);s=p.add_subparsers(dest='cmd',required=True)
    b=s.add_parser('retain');b.add_argument('--site',required=True);b.add_argument('--data-manifest',required=True);b.add_argument('--data-commit',required=True)
    b=s.add_parser('verify');b.add_argument('--release-id',required=True)
    b=s.add_parser('restore');b.add_argument('--release-id',required=True);b.add_argument('--output',required=True)
    b=s.add_parser('rollback-draft');b.add_argument('--release-id',required=True)
    s.add_parser('pointers');a=p.parse_args()
    try:
        store=ReleaseStore(a.store)
        if a.cmd=='retain':r=store.retain(a.site,a.data_manifest,a.data_commit)
        elif a.cmd=='verify':r=store.get(a.release_id)
        elif a.cmd=='restore':store.restore(a.release_id,a.output);r={'restored':a.release_id}
        elif a.cmd=='rollback-draft':r=store.rollback_draft(a.release_id)
        else:r=store.pointers()
        print(json.dumps(r,ensure_ascii=False,indent=2));return 0
    except Exception as e:print('RELEASE_BLOCKED:',type(e).__name__);return 1
if __name__=='__main__':raise SystemExit(main())
