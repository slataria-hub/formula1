"""Local read-only security screening. Findings report rules/locations, never matched values.
Heuristics are not proof of absence. History mode scans all reachable local Git refs.
"""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile

FORBIDDEN_DIRS={'private','.venv','.git','node_modules','backups','backup','__pycache__'}
FORBIDDEN_SUFFIXES=('.zip','.7z','.tar','.tar.gz','.pem','.key','.pfx','.p12','.bak','.backup','.local.json')
PATTERNS={
 'github_token': rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b',
 'aws_access_key': rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
 'private_key': rb'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----',
 'url_credentials': rb'https?://[^\s/@:]+:[^\s/@]+@[^\s/]+',
 'literal_secret': rb'(?i)\b(?:password|passwd|api[_-]?key|access[_-]?token|client[_-]?secret)\s*[=:]\s*[\"\'][^\"\'\r\n]{12,}[\"\']',
}
MAX_BLOB=100*1024*1024

def forbidden(name):
    p=PurePosixPath(name.replace('\\','/')); parts=[x.lower() for x in p.parts]; leaf=parts[-1] if parts else ''
    return (p.is_absolute() or '..' in parts or bool(FORBIDDEN_DIRS.intersection(parts)) or leaf.startswith('.env') or leaf.endswith(FORBIDDEN_SUFFIXES) or leaf=='user.json' or leaf.startswith(('user-state','predictions')) and leaf.endswith('.json'))

def inspect_bytes(name,raw):
    found=[]
    if forbidden(name):found.append('forbidden_path')
    # Avoid false positives within literal embedded data URIs; actual media must be separately reviewed.
    cleaned=re.sub(rb'data:image/[a-zA-Z0-9+.-]+;base64,[A-Za-z0-9+/=]+',b'<embedded-image>',raw)
    for rule,pattern in PATTERNS.items():
        if re.search(pattern,cleaned):found.append(rule)
    if name.lower().endswith('.json'):
        try:
            obj=json.loads(raw)
            # User-state shape is prohibited except the exact checked-in example.
            if isinstance(obj,dict) and 'predictions' in obj and ('settings' in obj or 'schemaVersion' in obj) and name not in ('examples/user.example.json','schemas/user.schema.json'):
                found.append('possible_user_state')
        except (ValueError,UnicodeError):found.append('invalid_json')
    return found

def git(root,*args):
    r=subprocess.run(['git','-C',str(root),*args],capture_output=True,check=False)
    if r.returncode:raise ValueError('git '+args[0]+' failed; no output logged')
    return r.stdout

def scan_tracked(root):
    paths=sorted(set(git(root,'ls-files','-z','--cached','--others','--exclude-standard').decode('utf-8').split('\0'))-{''})
    findings=[]; count=0; blocked=[]
    for name in paths:
        p=Path(root)/name
        if p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(Path(root).resolve()):blocked.append(name);continue
        if p.stat().st_size>MAX_BLOB:blocked.append(name);continue
        count+=1
        for rule in inspect_bytes(name,p.read_bytes()):findings.append({'path':name,'rule':rule})
    return dict(scanned=count,findings=findings,blocked=blocked)

def scan_index(root):
    # Read staged Git blobs, not the potentially different working tree.
    findings=[]; blocked=[]; count=0
    for row in git(root,'ls-files','--stage','-z').split(b'\0'):
        if not row:continue
        meta,path=row.split(b'\t',1)
        mode,oid,stage=meta.decode('ascii').split()
        name=path.decode('utf-8','strict')
        if stage!='0' or mode not in ('100644','100755') or set(oid)=={'0'}:
            blocked.append({'path':name,'reason':'unsupported_or_unmerged_index_entry'});continue
        if int(git(root,'cat-file','-s',oid))>MAX_BLOB:
            blocked.append({'path':name,'reason':'blob_too_large'});continue
        raw=git(root,'cat-file','blob',oid)
        count+=1
        for rule in inspect_bytes(name,raw):findings.append({'path':name,'rule':rule})
    return dict(scanned=count,findings=findings,blocked=blocked)

def scan_history(root):
    # Enumerate EVERY reachable commit tree, including paths reused for the same blob.
    commits=git(root,'rev-list','--all').decode().splitlines(); seen={}; findings=[]; blocked=[]; paths=set()
    for c in commits:
        for row in git(root,'ls-tree','-rz',c).split(b'\0'):
            if not row:continue
            meta,path=row.split(b'\t',1); mode,typ,oid=meta.decode().split(); name=path.decode('utf-8','replace')
            if typ!='blob':blocked.append({'commit':c,'path':name});continue
            key=(oid,name)
            if key in paths:continue
            paths.add(key)
            if oid not in seen:
                size=int(git(root,'cat-file','-s',oid))
                if size>MAX_BLOB:seen[oid]=None
                else:seen[oid]=git(root,'cat-file','blob',oid)
            raw=seen[oid]
            if raw is None:blocked.append({'commit':c,'path':name});continue
            if mode!='100644' and mode!='100755':findings.append({'commit':c,'path':name,'rule':'unexpected_blob_mode'})
            for rule in inspect_bytes(name,raw):findings.append({'commit':c,'path':name,'rule':rule})
    return dict(commits=len(commits),uniqueBlobs=len(seen),pathBlobPairs=len(paths),findings=findings,blocked=blocked)

def scan_zip(path):
    findings=[]; blocked=[]; count=0
    with zipfile.ZipFile(path) as z:
        names=set()
        for info in z.infolist():
            if info.is_dir():continue
            name=info.filename
            if name in names or info.file_size>MAX_BLOB or (info.external_attr>>16)&0o170000==0o120000:
                blocked.append(name);continue
            names.add(name);count+=1
            for rule in inspect_bytes(name,z.read(info)):findings.append({'path':name,'rule':rule})
    return dict(scanned=count,findings=findings,blocked=blocked)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['tracked','history','artifact','index']);p.add_argument('--project',default=str(Path(__file__).resolve().parents[1]));p.add_argument('--zip');a=p.parse_args()
    try:r=scan_zip(a.zip) if a.mode=='artifact' else (scan_history(a.project) if a.mode=='history' else (scan_index(a.project) if a.mode=='index' else scan_tracked(a.project)))
    except Exception as e:print(json.dumps({'status':'BLOCKED','errorType':type(e).__name__}));return 2
    print(json.dumps(r,ensure_ascii=True,indent=2));return 1 if r['findings'] or r['blocked'] else 0
if __name__=='__main__':raise SystemExit(main())
