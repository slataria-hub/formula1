"""Locally retain exact approved releases; pointer changes require successful HTTP smoke.
No remote mutation, no deploy. Existing ReleaseStore remains DRAFT-only.
"""
import argparse, os, tempfile, shutil
from pathlib import Path
from pages_release import resolve, authorize, SITE, sha, commit_id
from release_store import ReleaseStore, canon, require_id, load_files, record
from static_build import parse_json, write_assets
from post_deploy_smoke import check

class PublishedStore:
    def __init__(self,root):
        self.storage=ReleaseStore(root)
        self.versions=self.storage.versions
        self.pointer=self.storage.root/'published-pointers.json'
    def pointers(self):
        if self.pointer.is_symlink():raise ValueError('unsafe pointer')
        p=parse_json(self.pointer.read_bytes()) if self.pointer.exists() else {'current_published':None,'previous_published':None}
        if set(p)!={'current_published','previous_published'}:raise ValueError('bad pointer contract')
        for v in p.values():
            if v is not None:
                if set(v)!={'releaseId','releaseCommit','approvalSha256'}:raise ValueError('bad pointer entry')
                require_id(v['releaseId']);commit_id(v['releaseCommit']);require_id(v['approvalSha256'])
        return p
    def read(self,rid,pin):
        require_id(rid);files=load_files(self.versions/rid,SITE)
        d=parse_json(files['release-manifest.json']);a=d.pop('approvalRecord');stored_pin=d.pop('approvalSha256');commit=commit_id(d.pop('releaseCommit'))
        if stored_pin!=pin or d['releaseId']!=rid:raise ValueError('retained approval mismatch')
        authorize(d,canon(a),pin)
        if {n:record(b) for n,b in files.items() if n!='release-manifest.json'}!=d['fileManifest']:raise ValueError('retained content damaged')
        return files,dict(releaseId=rid,releaseCommit=commit,approvalSha256=pin)
    def retain(self,repo,commit,pin):
        files,d=resolve(repo,commit,pin);rid=d['releaseId'];entry=dict(releaseId=rid,releaseCommit=commit,approvalSha256=pin)
        with self.storage.lock():
            target=self.versions/rid
            if target.exists():
                if self.read(rid,pin)!=(files,entry):raise ValueError('immutable version collision')
            else:
                t=Path(tempfile.mkdtemp(prefix='.retain-',dir=self.storage.root))
                try:
                    write_assets(t,files,SITE)
                    if load_files(t,SITE)!=files:raise ValueError('staged bytes differ')
                    t.rename(target)
                finally:
                    if t.exists():shutil.rmtree(t)
        return entry
    def restore(self,rid,pin,output):
        from activate_update import private_path
        files,_=self.read(rid,pin);out=private_path(output)
        if out.exists():raise FileExistsError('restore destination exists')
        out.parent.mkdir(parents=True,exist_ok=True);t=Path(tempfile.mkdtemp(prefix='.restore-',dir=out.parent))
        try:
            write_assets(t,files,SITE)
            if load_files(t,SITE)!=files:raise ValueError('restore verification failed')
            if out.exists():raise FileExistsError('restore destination exists')
            t.rename(out)
        finally:
            if t.exists():shutil.rmtree(t)
    def confirm(self,rid,pin):
        # Lock covers smoke and pointer update. No user data accessed. Only exact bytes over HTTPS.
        with self.storage.lock():
            files,entry=self.read(rid,pin);p=self.pointers()
            if p['current_published'] is not None:
                old=p['current_published'];self.read(old['releaseId'],old['approvalSha256'])
            check(files) # raises on mismatch, no pointer update
            if p['current_published']==entry:return p
            p['previous_published']=p['current_published'];p['current_published']=entry
            fd,n=tempfile.mkstemp(prefix='.published-',dir=self.storage.root)
            try:
                with os.fdopen(fd,'wb') as f:f.write(canon(p));f.flush();os.fsync(f.fileno())
                os.replace(n,self.pointer)
            finally:Path(n).unlink(missing_ok=True)
            return p

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--store',required=True);s=p.add_subparsers(dest='command',required=True)
    q=s.add_parser('retain');q.add_argument('--release-commit',required=True)
    for n in ('confirm','restore'):
        q=s.add_parser(n);q.add_argument('--release-id',required=True)
        if n=='restore':q.add_argument('--output',required=True)
    s.add_parser('pointers');a=p.parse_args();pin=os.environ.get('F1_APPROVAL_SHA256','')
    try:
        st=PublishedStore(a.store)
        if a.command=='retain':r=st.retain(Path(__file__).resolve().parents[1],a.release_commit,pin)
        elif a.command=='confirm':r=st.confirm(a.release_id,pin)
        elif a.command=='restore':st.restore(a.release_id,pin,a.output);r={'restored':a.release_id}
        else:r=st.pointers()
        print(canon(r).decode());return 0
    except Exception as e:print('PUBLISHED_STORE_BLOCKED:',type(e).__name__);return 1
if __name__=='__main__':raise SystemExit(main())
