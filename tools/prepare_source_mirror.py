"""Prepare a separate, explicitly allowlisted source overlay. No Git operations.
Only after owner approval may this overlay be staged in a fresh public clone.
Never copy the original flag raster module into that clone.
"""
import argparse, json, shutil, tempfile
from pathlib import Path
from static_build import sha
from activate_update import private_path
from public_profile import strip_flags
from validate_data import ROOT
from repository_audit import inspect_bytes

ALLOWLIST=ROOT/'references/F1-012.4_public_source_allowlist.json'
def prepare(output):
    out=private_path(output)
    if out.exists():raise FileExistsError('fresh output required')
    names=json.loads(ALLOWLIST.read_bytes()); files={}
    if len(names)!=len(set(names)):raise ValueError('duplicate allowlist')
    for n in names:
        rel=Path(n);p=ROOT/rel
        if rel.is_absolute() or '..' in rel.parts or any(x in ('private','.git','__pycache__','.venv') for x in rel.parts) or not p.is_file() or p.is_symlink() or any(x.is_symlink() for x in p.parents if x.is_relative_to(ROOT)):
            raise ValueError('unsafe source path')
        b=p.read_bytes()
        if n=='web/preview/media.mjs':b=strip_flags(b)
        if n=='web/preview/visual-media.json' and any(json.loads(b).get(k) for k in ('photos','logos','circuits')):raise ValueError('unexpected real media in template')
        if n.startswith('web/preview/') and n.endswith(('.mjs','.html','.css')) and b'data:image/' in b and n=='web/preview/media.mjs':raise ValueError('embedded images')
        if inspect_bytes(n,b):raise ValueError('security scan rejected '+n)
        files[n]=b
    out.parent.mkdir(parents=True,exist_ok=True);temp=Path(tempfile.mkdtemp(prefix='.source-',dir=out.parent))
    try:
        for n,b in files.items():p=temp/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
        if out.exists():raise FileExistsError('output exists')
        temp.rename(out)
    finally:
        if temp.exists():shutil.rmtree(temp)
    return {n:sha(b) for n,b in sorted(files.items())}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);a=p.parse_args()
    try:
        result=prepare(a.output);print(json.dumps({'status':'LOCAL_OVERLAY_ONLY','files':result},indent=2));return 0
    except Exception as e:print('SOURCE_OVERLAY_BLOCKED:',type(e).__name__,str(e));return 1
if __name__=='__main__':raise SystemExit(main())
