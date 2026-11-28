"""F1-012.4: deterministic publication candidate and fail-closed gate. No Git writes.
The existing release_store remains DRAFT-only; reuse its canonical/hash contracts.
Approval is an externally pinned exact SHA-256, not a boolean supplied by dispatch.
"""
import argparse, csv, io, json, os, re, subprocess, tempfile, shutil
from datetime import datetime, timezone
from pathlib import Path
from static_build import ASSETS, parse_json, sha, media_info, write_assets
from release_store import canon, record, require_id, load_files
from validate_data import validate
from activate_update import sports_digest
from persist_draft import release_record, verify as verify_draft
from audit_championships import audit
from media_catalog import inventory
from repository_audit import inspect_bytes

COMMIT=re.compile(r'[0-9a-f]{40}')
SITE=set(ASSETS)|{'official.json','SOURCE.txt','release-manifest.json'}
INPUT_FILES={'release.json','approval.json'}
BODY_KEYS={'contractVersion','codeCommit','dataCommit','sourceDataCommit','mediaCommit','mediaVersion','sourceTag','schemaVersion','rightsRegistrySha256','officialSha256','dataManifestSha256','mediaManifestSha256','mediaSha256','fileManifest','formedAt','verificationStatus','rightsStatus','publicationAuthorized'}

def commit_id(v):
    if not isinstance(v,str) or not COMMIT.fullmatch(v):raise ValueError('commit must be full SHA')
    return v

def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args],stderr=subprocess.DEVNULL,timeout=120)

def reachable(root,commit,ref):
    commit_id(commit)
    if git(root,'cat-file','-t',commit).strip()!=b'commit':raise ValueError('not a commit')
    git(root,'merge-base','--is-ancestor',commit,ref)

def tree_files(root,commit,expected):
    entries=git(root,'ls-tree','-rz',commit).split(b'\0')
    found={}
    for e in entries:
        if not e:continue
        meta,n=e.split(b'\t',1); mode,kind,oid=meta.decode().split();name=n.decode()
        if mode not in ('100644','100755') or kind!='blob' or name not in expected:raise ValueError('unexpected input tree')
        found[name]=git(root,'cat-file','blob',oid)
    if set(found)!=expected:raise ValueError('incomplete input tree')
    return found

def approved_data(raw,raw_manifest):
    d=parse_json(raw);m=parse_json(raw_manifest)
    if (m.get('version'),m.get('datasetStatus'),m.get('publicationAuthorized'),m.get('independentVerification'))!=(1,'verified',True,'passed'):
        raise ValueError('data publication not authorized')
    if len(raw)>=90*1024*1024:raise ValueError('approved data near Git size limit')
    if m.get('officialSha256')!=sha(raw) or m.get('sportsSha256')!=sports_digest(d):raise ValueError('data checksum mismatch')
    if validate(d,release=True):raise ValueError('data validation failed')
    rr=release_record(m['release'])
    if not any(s.get('provider')=='F1DB' and s.get('revision')==rr['tag'] and s.get('sha256')==rr['sha256'] for s in d['sources']):raise ValueError('data source mismatch')
    if audit(d)['issues']:raise ValueError('sporting audit failed')
    return d,m

def rights_check(raw,flags,registry,d):
    # inventory includes actual inline flags and mappings, not just JSON images.
    expected=inventory(raw,flags)
    reader=csv.DictReader(io.StringIO(registry.decode('utf-8-sig')))
    rows={}
    if not reader.fieldnames or len(reader.fieldnames)!=len(set(reader.fieldnames)):raise ValueError('bad rights header')
    for r in reader:
        key=(r['objectType'],r['objectId'])
        if key in rows or None in r:raise ValueError('duplicate or malformed rights row')
        rows[key]=r
    if set(rows)!={(r['objectType'],r['objectId']) for r in expected}:raise ValueError('rights coverage mismatch')
    for e in expected:
        r=rows[e['objectType'],e['objectId']]
        for k in ('sha256','bytes','source','author','license','licenseUrl','periodStatus'):
            if r.get(k)!=str(e[k]):raise ValueError('rights identity mismatch')
        if r.get('publicAllowed')!='YES' or r.get('verificationStatus')!='verified' or not r.get('attribution','').strip() or not r.get('evidence','').startswith('https://'):
            raise ValueError('unapproved media object')
    # strict validator checks object compatibility and media schema; approval comes from registry + external pin.
    binding={'version':1,'mediaSha256':sha(raw),'officialSha256':sha(canon(d)),'rightsReviewed':True,'reviewReference':'exact rights registry checked'}
    media_info(raw,d,binding,strict=True,official_sha=sha(canon(d)))
    return rows

def media_manifest(raw,registry,flags,official,source_tag,schema_version):
    return dict(version=1,mediaVersion='sha256:'+sha(raw),mediaSha256=sha(raw),rightsRegistrySha256=sha(registry),flagsModuleSha256=sha(flags),officialSha256=sha(official),sourceTag=source_tag,schemaVersion=schema_version,rightsStatus='verified')

def materialize(code,raw,meta,media,registry,descriptor=None):
    d,m=approved_data(raw,meta)
    if set(code)!=set(ASSETS)-{'visual-media.json'}:raise ValueError('code allowlist mismatch')
    rights=rights_check(media,code['media.mjs'],registry,d)
    # Publish explicit attribution; full registry stays in immutable media Git revision.
    lines=['F1DB (https://github.com/f1db/f1db), CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).','Transformed by F1 Analytics: historical reconciliation and normalization.','Source: '+m['release']['tag'],'Media attribution:']
    lines.extend(f"{k[0]} {k[1]}: {r['attribution']} | {r['source']} | {r['license']} {r['licenseUrl']}" for k,r in sorted(rights.items()))
    files={**code,'official.json':raw,'visual-media.json':media,'SOURCE.txt':('\n'.join(lines)+'\n').encode()}
    if any(inspect_bytes(n,b) for n,b in files.items()):raise ValueError('site security audit blocked')
    derived={'sourceTag':m['release']['tag'],'schemaVersion':d['schemaVersion'],'officialSha256':sha(raw),'dataManifestSha256':sha(meta),'mediaSha256':sha(media),'mediaVersion':'sha256:'+sha(media),'rightsRegistrySha256':sha(registry),'fileManifest':{n:record(b) for n,b in sorted(files.items())}}
    if descriptor is None:return files,derived
    for k,v in derived.items():
        if descriptor.get(k)!=v:raise ValueError('release input or output mismatch: '+k)
    return files

def validate_time(value):
    if not isinstance(value,str) or datetime.fromisoformat(value).tzinfo is None:raise ValueError('timezone required')

def descriptor_body(descriptor):
    if set(descriptor)!=BODY_KEYS|{'releaseId'}:raise ValueError('release contract fields')
    body={k:v for k,v in descriptor.items() if k!='releaseId'}
    if require_id(descriptor['releaseId'])!=sha(canon(body)):raise ValueError('release identity mismatch')
    for k in ('codeCommit','dataCommit','sourceDataCommit','mediaCommit'):commit_id(body[k])
    validate_time(body['formedAt'])
    if body['contractVersion']!=1:raise ValueError('release contract version')
    return body

def authorize(descriptor,approval_raw,pin):
    body=descriptor_body(descriptor);rid=descriptor['releaseId']
    if (body['verificationStatus'],body['rightsStatus'],body['publicationAuthorized'])!=('passed','verified',True):raise ValueError('release not authorized')
    if not pin or not re.fullmatch(r'[0-9a-f]{64}',pin) or sha(approval_raw)!=pin:raise ValueError('external approval pin missing or mismatch')
    a=parse_json(approval_raw)
    if canon(a)!=approval_raw:raise ValueError('approval must be canonical UTF-8 JSON')
    if set(a)!={'releaseId','decision','owner','architect','reference','approvedAt'} or a['releaseId']!=rid or a['decision']!='publish' or any(not isinstance(a[k],str) or not a[k].strip() for k in ('owner','architect','reference')):raise ValueError('approval record mismatch')
    validate_time(a['approvedAt'])
    if datetime.fromisoformat(a['approvedAt']) < datetime.fromisoformat(body['formedAt']):raise ValueError('approval predates candidate')
    if inspect_bytes('approval.json',approval_raw):raise ValueError('approval record security check blocked')
    return a

def resolve_inputs(root,d):
    for key,branch in [('codeCommit','main'),('dataCommit','f1-approved-data'),('sourceDataCommit','f1-data'),('mediaCommit','f1-media')]:reachable(root,d[key],'refs/remotes/origin/'+branch)
    code={}
    for n in set(ASSETS)-{'visual-media.json'}:
        entry=git(root,'ls-tree',d['codeCommit'],'web/preview/'+n).decode().split()
        if not entry or entry[0] not in ('100644','100755') or entry[1]!='blob':raise ValueError('unsafe code asset')
        code[n]=git(root,'show',d['codeCommit']+':web/preview/'+n)
    df=tree_files(root,d['dataCommit'],{'official.json','manifest.json'})
    original=tree_files(root,d['sourceDataCommit'],{'official.json','manifest.json'})
    baseline=verify_draft(original['official.json'],parse_json(original['manifest.json']))
    verified=parse_json(df['official.json']); projection=dict(baseline,datasetStatus='verified')
    approved_meta=parse_json(df['manifest.json'])
    if approved_meta.get('sourceDataCommit')!=d['sourceDataCommit']:raise ValueError('independent review source commit mismatch')
    require_id(approved_meta.get('independentReviewSha256',''))
    if verified!=projection or parse_json(df['manifest.json'])['release']!=parse_json(original['manifest.json'])['release']:raise ValueError('approved snapshot differs from source draft')
    mf=tree_files(root,d['mediaCommit'],{'visual-media.json','rights-register.csv','manifest.json'})
    expected=media_manifest(mf['visual-media.json'],mf['rights-register.csv'],code['media.mjs'],df['official.json'],parse_json(df['manifest.json'])['release']['tag'],verified['schemaVersion'])
    if parse_json(mf['manifest.json'])!=expected:raise ValueError('media manifest incompatibility')
    return code,df,mf

def describe(root,*,code_commit,data_commit,source_data_commit,media_commit,formed_at):
    body=dict(contractVersion=1,codeCommit=code_commit,dataCommit=data_commit,sourceDataCommit=source_data_commit,mediaCommit=media_commit,formedAt=formed_at,verificationStatus='pending',rightsStatus='verified',publicationAuthorized=False)
    validate_time(formed_at)
    code,df,mf=resolve_inputs(root,body)
    _,derived=materialize(code,df['official.json'],df['manifest.json'],mf['visual-media.json'],mf['rights-register.csv'])
    body.update(derived,mediaManifestSha256=sha(mf['manifest.json']))
    return dict(body,releaseId=sha(canon(body)))

def finalize(candidate,expected_id,owner,architect,reference,approved_at):
    # Administrative record preparation only, not authorization by itself.
    body=descriptor_body(candidate)
    if candidate['releaseId']!=expected_id or (body['verificationStatus'],body['rightsStatus'],body['publicationAuthorized'])!=('pending','verified',False):raise ValueError('wrong or already finalized candidate')
    body.update(verificationStatus='passed',publicationAuthorized=True)
    d=dict(body,releaseId=sha(canon(body)))
    a=canon(dict(releaseId=d['releaseId'],decision='publish',owner=owner,architect=architect,reference=reference,approvedAt=approved_at))
    authorize(d,a,sha(a)) # shape and chronology; actual authority is separate owner-controlled variable
    return d,a

def resolve(root,release_commit,pin):
    reachable(root,release_commit,'refs/remotes/origin/f1-releases')
    r=tree_files(root,release_commit,INPUT_FILES);d=parse_json(r['release.json']);a=authorize(d,r['approval.json'],pin)
    if os.environ.get('GITHUB_ACTIONS')=='true':
        mode=os.environ.get('F1_DEPLOY_MODE')
        if mode not in ('publish','rollback') or mode=='publish' and d['codeCommit']!=os.environ.get('GITHUB_SHA'):raise ValueError('workflow and approved code revision differ')
    code,df,mf=resolve_inputs(root,d)
    if d['mediaManifestSha256']!=sha(mf['manifest.json']):raise ValueError('media manifest hash mismatch')
    files=materialize(code,df['official.json'],df['manifest.json'],mf['visual-media.json'],mf['rights-register.csv'],d)
    files['release-manifest.json']=canon({**d,'approvalRecord':a,'approvalSha256':pin,'releaseCommit':release_commit})
    if inspect_bytes('release-manifest.json',files['release-manifest.json']):raise ValueError('release manifest security blocked')
    return files,d

def build(root,release_commit,pin,output):
    files,d=resolve(root,release_commit,pin)
    out=Path(output)
    if out.exists():raise FileExistsError('fresh output required')
    out.parent.mkdir(parents=True,exist_ok=True);temp=Path(tempfile.mkdtemp(dir=out.parent))
    try:
        write_assets(temp,files,SITE)
        if load_files(temp,SITE)!=files:raise ValueError('staged site differs')
        temp.rename(out)
    finally:
        if temp.exists():shutil.rmtree(temp)
    return d

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='stage',required=True)
    for stage in ('check','build','verify'):
        sp=sub.add_parser(stage);sp.add_argument('--release-commit',required=True)
        if stage!='check':sp.add_argument('--output',required=True)
    sp=sub.add_parser('describe')
    for key in ('code-commit','data-commit','source-data-commit','media-commit','formed-at','output'):sp.add_argument('--'+key,required=True)
    sp=sub.add_parser('finalize-record')
    for key in ('candidate','expected-candidate-id','owner','architect','reference','approved-at','output'):sp.add_argument('--'+key,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[1];pin=os.environ.get('F1_APPROVAL_SHA256','')
    try:
        if a.stage=='describe':
            d=describe(root,code_commit=a.code_commit,data_commit=a.data_commit,source_data_commit=a.source_data_commit,media_commit=a.media_commit,formed_at=a.formed_at)
            from activate_update import private_path
            out=private_path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
            with out.open('xb') as f:f.write(canon(d))
            print('CANDIDATE_ONLY:',d['releaseId']);return 0
        if a.stage=='finalize-record':
            from activate_update import private_path
            d,b=finalize(parse_json(private_path(a.candidate).read_bytes()),a.expected_candidate_id,a.owner,a.architect,a.reference,a.approved_at)
            out=private_path(a.output);out.mkdir(parents=True,exist_ok=False);(out/'release.json').write_bytes(canon(d));(out/'approval.json').write_bytes(b)
            print('RECORD_PREPARED_NOT_PUBLISHED:',d['releaseId'],'approval SHA256:',sha(b));return 0
        if a.stage=='build':build(root,a.release_commit,pin,a.output)
        else:
            f,d=resolve(root,a.release_commit,pin)
            if a.stage=='verify' and load_files(Path(a.output),SITE)!=f:raise ValueError('site changed')
        print('PUBLICATION_'+a.stage.upper()+'_PASS');return 0
    except Exception as exc:
        print('PUBLICATION_'+a.stage.upper()+'_BLOCKED:',type(exc).__name__);return 1
if __name__=='__main__':raise SystemExit(main())
