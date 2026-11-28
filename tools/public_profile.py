"""Create a separate LOCAL reduced-media candidate; never grant publication or write Git.
Inputs must be the exact independently catalogued snapshot. Output is not a release.
"""
import argparse, base64, csv, hashlib, io, json, re, shutil, tempfile
from pathlib import Path
from static_build import parse_json, sha, media_info
from media_catalog import inventory, FIELDS
from sync_media import targets, exact_source, resolve_archive
from repository_audit import inspect_bytes
from activate_update import private_path
from validate_data import ROOT

SOURCE=ROOT/'references/F1-012.4_circuit_sources.json'
ORIGINAL_MEDIA='a405ec3d411d8f27bad96ff047d2bf81b527bb35e91d7d5080b923e612283ef4'
ORIGINAL_OFFICIAL='9ce80d14bcc406f97f6a977a3cf005bf68878abf818eb52a40763190703a6807'
ORIGINAL_FLAGS='becdc8d20824210289909bd8a77fa9f1e643a2b6363184f81f5ce7a1b2d5198d'
ORIGINAL_REGISTER='74413125dfbf05cdfc21ccdb8c596b9398f546a611800e936e8163dc008660ef'
EXTRA=['reviewGroup','evidence','reviewDecision','candidateEligible']

def csv_data(rows):
    f=io.StringIO(newline=''); w=csv.DictWriter(f,fieldnames=FIELDS+EXTRA,lineterminator='\n');w.writeheader();w.writerows(rows);return f.getvalue().encode('utf-8-sig')

def strip_flags(raw):
    if sha(raw)!=ORIGINAL_FLAGS:raise ValueError('local flags module differs from reviewed version')
    text=raw.decode('utf-8')
    text,n=re.subn(r'^export const FLAGS=\{[^\n]*\};\s*$', 'export const FLAGS={};',text,flags=re.M)
    if n!=1 or 'data:image/' in text:raise ValueError('unexpected embedded images')
    return text.replace(' Flag glyph rasterizations: Noto Emoji (SIL OFL 1.1). No font distributed.',' Public candidate: textual country codes only.').encode()

def review(official,media,flags,register,archive):
    if (sha(official),sha(media),sha(flags),sha(register))!=(ORIGINAL_OFFICIAL,ORIGINAL_MEDIA,ORIGINAL_FLAGS,ORIGINAL_REGISTER):raise ValueError('input differs from reviewed snapshot')
    d=parse_json(official);pack=parse_json(media);s=exact_source(d);e=parse_json(SOURCE.read_bytes())
    if s['revision']!=e['sourceTag'] or s['sha256']!=e['archiveSha256']:raise ValueError('source differs')
    archive=resolve_archive(s,archive);t=targets(d,archive,s)
    if t['eventLayouts']!=pack['eventLayouts'] or t['countryCodes']!=pack['countryCodes']:raise ValueError('mapping differs from archive')
    source_base='https://github.com/f1db/f1db/blob/'+e['sourceCommit']+'/'
    if set(e['gitBlobs'])!=set(pack['circuits']):raise ValueError('circuit coverage differs')
    for k,item in pack['circuits'].items():
        b=base64.b64decode(item['src'].split(',',1)[1],validate=True)
        if hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()!=e['gitBlobs'][k] or item['license']!='CC BY 4.0' or item['author']!='F1DB / Jules Roy':raise ValueError('circuit source mismatch')
    actual=list(csv.DictReader(io.StringIO(register.decode('utf-8-sig'))))
    expected=inventory(media,flags)
    if actual!=[{k:str(v) for k,v in x.items()} for x in expected]:raise ValueError('register does not match original inputs')
    reviewed=[]
    for row in actual:
        r=dict(row);g=r['objectType']; k=r['objectId'];r['reviewGroup']=sha((r['sha256']+'\0'+r['source']).encode()) if r['sha256'] else 'country:'+k
        r['candidateEligible']='YES' if g in ('circuits','countryCodeMapping') else 'NO';r['publicAllowed']='NO'
        if g=='circuits':
            r.update(verificationStatus='source_bytes_verified_pending_release_approval',reviewDecision='eligible_after_approval',evidence=source_base+'src/assets/circuits/black/'+k+'.svg ; '+source_base+'LICENSE ; '+source_base+'README.md ; git blob '+e['gitBlobs'][k]);r['attribution']=f'{k} — F1DB / Jules Roy; CC BY 4.0; {source_base}src/assets/circuits/black/{k}.svg; https://creativecommons.org/licenses/by/4.0/; unchanged SVG embedded as data URI.'
        elif g=='countryCodeMapping':
            r.update(verificationStatus='archive_mapping_verified_pending_release_approval',reviewDecision='eligible_after_approval',evidence='https://github.com/f1db/f1db/releases/tag/'+s['revision']+' ; archive SHA-256 '+s['sha256'])
        elif g=='photos':
            evidence=r['source']
            status='individual_source_version_and_derivative_pending'
            if k in ('f1db:adrian-sutil','f1db:alex-yoong'):status='source_page_license_author_match_exact_thumbnail_pending'
            r.update(verificationStatus=status,reviewDecision='additional_review_required_excluded',evidence=evidence)
        elif g=='logos':r.update(verificationStatus='individual_source_trademark_period_pending',reviewDecision='additional_review_required_excluded',evidence=r['source'])
        else:r.update(verificationStatus='exact_raster_origin_pending',reviewDecision='additional_review_required_excluded',evidence='https://github.com/googlefonts/noto-emoji/blob/main/README.md ; font OFL vs assets Apache or public domain; actual raster origin unverified')
        reviewed.append(r)
    subset=dict(pack,photos={},logos={});raw=json.dumps(subset,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    sanitized=strip_flags(flags);binding=dict(version=1,mediaSha256=sha(raw),officialSha256=sha(official),rightsReviewed=False,reviewReference='F1-012.4 reduced candidate; no authorization')
    media_info(raw,d,binding,rehearsal=True,official_sha=sha(official))
    return reviewed,raw,sanitized,binding

def prepare(official,media,register,archive,output):
    out=private_path(output)
    if out.exists():raise FileExistsError('fresh output required')
    raw=Path(official).read_bytes();flags=(ROOT/'web/preview/media.mjs').read_bytes();rows,subset,safe,binding=review(raw,Path(media).read_bytes(),flags,Path(register).read_bytes(),archive)
    out.parent.mkdir(parents=True,exist_ok=True);tmp=Path(tempfile.mkdtemp(prefix='.public-candidate-',dir=out.parent))
    try:
        (tmp/'visual-media.json').write_bytes(subset);(tmp/'media.mjs').write_bytes(safe)
        (tmp/'rights-review.csv').write_bytes(csv_data(rows));(tmp/'rights-register-candidate.csv').write_bytes(csv_data([r for r in rows if r['candidateEligible']=='YES']))
        (tmp/'rehearsal-binding.json').write_text(json.dumps(binding,indent=2)+'\n')
        if out.exists():raise FileExistsError('candidate output exists')
        tmp.rename(out)
    finally:
        if tmp.exists():shutil.rmtree(tmp)
    return len(rows)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--official',required=True);p.add_argument('--media',required=True);p.add_argument('--register',required=True);p.add_argument('--archive',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    try:print('PUBLIC_PROFILE_CANDIDATE_ONLY:',prepare(a.official,a.media,a.register,a.archive,a.output),'rows; no approval or upload');return 0
    except Exception as e:print('PUBLIC_PROFILE_BLOCKED:',type(e).__name__);return 1
if __name__=='__main__':raise SystemExit(main())
