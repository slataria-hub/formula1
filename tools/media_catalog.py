"""Inventory and version an existing sync_media output; never grants publication rights."""
import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import re
from static_build import parse_json, media_info, sha, data_bytes
from activate_update import draft, private_path, json_bytes
from sync_media import exact_source
from validate_data import ROOT

FIELDS=['objectType','objectId','sha256','bytes','source','author','license','licenseUrl','attribution','periodStatus','verificationStatus','publicAllowed','notes']

def inventory(raw, flag_module):
    pack=parse_json(raw); rows=[]
    for group in ('photos','logos','circuits'):
        for key,item in sorted(pack[group].items()):
            b=base64.b64decode(item['src'].split(',',1)[1],validate=True)
            rows.append(dict(objectType=group,objectId=key,sha256=sha(b),bytes=len(b),source=item['source'],author=item['author'],license=item['license'],licenseUrl=item.get('licenseUrl',''),attribution=f"{item.get('file',key)} — {item['author']}; {item['license']}; {item['source']}; {item.get('licenseUrl','')}; check thumbnail/crop and derivative notices",periodStatus=item.get('periodStatus','not_applicable'),verificationStatus='metadata_present_independent_review_pending',publicAllowed='NO',notes='Trademark and contextual rights review required' if group=='logos' else 'Verify source/version, attribution and applicable rights'))
    # Flags are embedded PNGs, not the countryCodes mappings. Inventory exact bytes in code.
    match=re.search(r'^export const FLAGS=(\{[^\n]*\});\s*$',flag_module.decode('utf-8'),re.M)
    if not match:raise ValueError('cannot identify embedded flag map')
    for code,src in sorted(parse_json(match[1].encode()).items()):
        b=base64.b64decode(src.split(',',1)[1],validate=True)
        rows.append(dict(objectType='flags',objectId=code,sha256=sha(b),bytes=len(b),source='https://github.com/googlefonts/noto-emoji',author='Noto Emoji project (code comment; not independently confirmed)',license='SIL OFL 1.1 (claimed for font rasterization)',licenseUrl='https://openfontlicense.org/open-font-license-official-text/',attribution='Verify exact source font/revision and notice requirements; rasterization from Noto Emoji per code comment',periodStatus='not_applicable',verificationStatus='provenance_pending',publicAllowed='NO',notes='No font distributed; exact raster origin and flag-specific usage rules pending'))
    for name,code in sorted(pack.get('countryCodes',{}).items()):
        rows.append(dict(objectType='countryCodeMapping',objectId=name,sha256='',bytes=0,source='F1DB (sync_media target mapping; confirm archive)',author='F1DB / F1 Analytics',license='CC BY 4.0 (source database)',licenseUrl='https://creativecommons.org/licenses/by/4.0/',attribution='F1DB; normalized by F1 Analytics',periodStatus='not_applicable',verificationStatus='mapping_only_review_pending',publicAllowed='NO',notes='Code '+code+'; not an image'))
    return rows

def csv_bytes(rows):
    f=io.StringIO(newline='');w=csv.DictWriter(f,fieldnames=FIELDS,lineterminator='\n');w.writeheader();w.writerows(rows);return f.getvalue().encode('utf-8-sig')

def make_manifest(official, media, flags, *, sync_report=None):
    return catalog_for_verified_data(official,media,flags,draft(official),sync_report=sync_report)

def catalog_for_verified_data(official, media, flags, data, *, sync_report=None):
    # Internal use only after draft()/verify_data() has validated exactly these bytes.
    source=exact_source(data)
    # Existing strict structural validation, not a rights review.
    binding=dict(version=1,mediaSha256=sha(media),officialSha256=sha(official),rightsReviewed=False,reviewReference='F1-012.3 local audit; publication blocked')
    info=media_info(media,data,binding,rehearsal=True,official_sha=sha(official))
    rows=inventory(media,flags); register=csv_bytes(rows);pack=parse_json(media)
    if sync_report is not None:
        r=parse_json(sync_report)
        if r.get('packSha256')!=sha(media) or r.get('sourceTag')!=source['revision'] or r.get('archiveSha256')!=source['sha256'] or r.get('publicationAuthorized') is not False or r.get('status') not in ('draft_media_ready','draft_media_review_required'):
            raise ValueError('sync report does not bind these media bytes and source')
    manifest=dict(version=1,mediaVersion='sha256:'+sha(media),mediaSha256=sha(media),officialSha256=sha(official),schemaVersion=data['schemaVersion'],sourceTag=source['revision'],archiveSha256=source['sha256'],flagsModuleSha256=sha(flags),rightsRegisterSha256=sha(register),rightsStatus='pending',publicationAuthorized=False,counts=dict(photos=len(pack['photos']),logos=len(pack['logos']),circuits=len(pack['circuits']),eventLayouts=len(pack.get('eventLayouts',{})),countryCodes=len(pack.get('countryCodes',{})),flags=sum(r['objectType']=='flags' for r in rows)),media=info,syncReportSha256=sha(sync_report) if sync_report is not None else None)
    return manifest,register,binding

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--official',required=True);p.add_argument('--media',required=True);p.add_argument('--sync-report');p.add_argument('--output',required=True);a=p.parse_args()
    try:
        out=private_path(a.output); m,r,b=make_manifest(Path(a.official).read_bytes(),Path(a.media).read_bytes(),(ROOT/'web/preview/media.mjs').read_bytes(),sync_report=Path(a.sync_report).read_bytes() if a.sync_report else None)
        out.mkdir(parents=True,exist_ok=False);(out/'media-manifest.json').write_bytes(json_bytes(m));(out/'rights-register.csv').write_bytes(r);(out/'rehearsal-binding.json').write_bytes(json_bytes(b));print('MEDIA_CATALOG_PASS; rights pending; LOCAL ONLY')
    except Exception as e:print('MEDIA_CATALOG_BLOCKED:',type(e).__name__);return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
