"""Prepare independent verified snapshot ONLY from an externally approved review receipt.
No push, no change to f1-data or original media. The receipt is not created here.
"""
import argparse, csv, io, json, shutil, tempfile
from pathlib import Path
from static_build import sha,parse_json
from release_store import canon,require_id
from pages_release import approved_data,rights_check,media_manifest,commit_id,validate_time
from persist_draft import verify as verify_draft
from activate_update import private_path,sports_digest

KEYS={'sourceDataCommit','officialSha256','draftManifestSha256','mediaSha256','candidateRightsSha256','flagsSha256','independentVerification','rightsDecision','owner','architect','evidenceReference','approvedAt'}

def prepare(raw,meta,media,registry,flags,receipt,pin):
    require_id(pin)
    if sha(receipt)!=pin:raise ValueError('independent review receipt pin mismatch')
    r=parse_json(receipt)
    if set(r)!=KEYS:raise ValueError('receipt contract')
    commit_id(r['sourceDataCommit']);validate_time(r['approvedAt'])
    if (r['independentVerification'],r['rightsDecision'])!=('passed','approved') or any(not isinstance(r[k],str) or not r[k].strip() for k in ('owner','architect','evidenceReference')):raise ValueError('independent review absent')
    expected={'officialSha256':sha(raw),'draftManifestSha256':sha(meta),'mediaSha256':sha(media),'candidateRightsSha256':sha(registry),'flagsSha256':sha(flags)}
    if any(r[k]!=v for k,v in expected.items()):raise ValueError('reviewed inputs changed')
    d=verify_draft(raw,parse_json(meta));old=parse_json(meta)
    approved=canon(dict(d,datasetStatus='verified'))
    new_meta=canon(dict(old,datasetStatus='verified',publicationAuthorized=True,independentVerification='passed',officialSha256=sha(approved),sportsSha256=sports_digest(parse_json(approved)),independentReviewSha256=pin,sourceDataCommit=r['sourceDataCommit']))
    verified,m=approved_data(approved,new_meta)
    reader=csv.DictReader(io.StringIO(registry.decode('utf-8-sig'))); rows=list(reader)
    if not rows or any(x.get('candidateEligible')!='YES' or x.get('reviewDecision')!='eligible_after_approval' for x in rows):raise ValueError('candidate contains excluded or unreviewed objects')
    o=io.StringIO(newline='');w=csv.DictWriter(o,fieldnames=reader.fieldnames,lineterminator='\n');w.writeheader()
    for x in rows:w.writerow(dict(x,publicAllowed='YES',verificationStatus='verified'))
    approved_registry=o.getvalue().encode('utf-8-sig');rights_check(media,flags,approved_registry,verified)
    return {'data/official.json':approved,'data/manifest.json':new_meta,'media/visual-media.json':media,'media/rights-register.csv':approved_registry,'media/manifest.json':canon(media_manifest(media,approved_registry,flags,approved,m['release']['tag'],verified['schemaVersion'])),'review-receipt.json':receipt}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('official','draft-manifest','media','registry','flags','receipt','expected-review-sha256','output'):p.add_argument('--'+k,required=True)
    a=p.parse_args()
    try:
        files=prepare(*(Path(getattr(a,k)).read_bytes() for k in ('official','draft_manifest','media','registry','flags','receipt')),a.expected_review_sha256)
        out=private_path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
        if out.exists():raise FileExistsError('fresh output required')
        tmp=Path(tempfile.mkdtemp(dir=out.parent))
        try:
            for n,b in files.items():f=tmp/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b)
            if out.exists():raise FileExistsError('fresh output required')
            tmp.rename(out)
        finally:
            if tmp.exists():shutil.rmtree(tmp)
        print('APPROVED_INPUTS_PREPARED_LOCALLY; no Git changes');return 0
    except Exception as e:print('APPROVED_INPUTS_BLOCKED:',type(e).__name__);return 1
if __name__=='__main__':raise SystemExit(main())
