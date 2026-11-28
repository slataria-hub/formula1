"""Assemble and verify an exact DRAFT site from f1-data. Never authorize or deploy Pages."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from activate_update import digest, json_bytes, parse, private_path
from audit_championships import audit
from build_preview import ASSETS
from persist_draft import Store, verify, release_record
from validate_data import ROOT
from static_build import media_info, build_manifest, preview_assets, write_assets, code_provenance, sha

SITE_FILES = set(ASSETS) | {'official.json', 'SOURCE.txt'}
BLOCKERS = ['independent historical acceptance pending', 'visual acceptance of exact build pending',
            'explicit publication approval absent', 'deployment and remote rollback not enabled']
COMMIT = re.compile(r'[0-9a-f]{40}')
SOURCE = ('F1DB (https://github.com/f1db/f1db), CC BY 4.0 '\
          '(https://creativecommons.org/licenses/by/4.0/).\n'\
          'Transformed by F1 Analytics: historical reconciliation and normalization.\n'\
          'DRAFT: independent verification pending; not authorized for publication.\n')


def code_assets(code_commit=None):
    assets = preview_assets(ROOT)
    if code_commit is not None:
        if not COMMIT.fullmatch(code_commit):
            raise ValueError('invalid code commit')
        def git(*args):
            return subprocess.check_output(['git', '-C', str(ROOT), *args], stderr=subprocess.DEVNULL)
        if git('rev-parse', 'HEAD').decode().strip() != code_commit:
            raise ValueError('checked out code commit mismatch')
        for name, raw in assets.items():
            if git('show', code_commit+':web/preview/'+name) != raw:
                raise ValueError('asset differs from committed code: '+name)
    return assets


def verify_bundle(path, *, expected_commit=None, expected_sha=None):
    path = Path(path)
    if path.is_symlink() or {p.name for p in path.iterdir()} != {'site', 'publication-report.json'}:
        raise ValueError('unexpected bundle files')
    report_path = path/'publication-report.json'
    site = path/'site'
    if report_path.is_symlink() or not report_path.is_file() or site.is_symlink() or not site.is_dir():
        raise ValueError('invalid bundle paths')
    report = parse(report_path.read_bytes())
    if (report.get('version'), report.get('status'), report.get('publicationAuthorized'),
            report.get('independentVerification'), report.get('blockers')) != (1, 'draft_bundle_ready', False, 'pending', BLOCKERS):
        raise ValueError('invalid DRAFT publication gate')
    if not COMMIT.fullmatch(report['dataCommit']):
        raise ValueError('invalid data commit')
    if report['codeCommit'] is not None and not COMMIT.fullmatch(report['codeCommit']):
        raise ValueError('invalid code commit')
    if expected_commit is not None and report['dataCommit'] != expected_commit:
        raise ValueError('bundle data commit mismatch')
    if expected_sha is not None and report['officialSha256'] != expected_sha:
        raise ValueError('bundle official checksum mismatch')
    if set(report['files']) != SITE_FILES or {p.name for p in site.iterdir()} != SITE_FILES:
        raise ValueError('unexpected site files')
    for name in SITE_FILES:
        f = site/name
        if f.is_symlink() or not f.is_file():
            raise ValueError('invalid site file: '+name)
        raw = f.read_bytes()
        if report['files'][name] != {'sha256': digest(raw), 'bytes': len(raw)}:
            raise ValueError('site checksum mismatch: '+name)
    raw = (site/'official.json').read_bytes()
    meta = report['dataManifest']
    data = verify(raw, meta)
    if report['officialSha256'] != meta['officialSha256'] or report['release'] != release_record(meta['release']):
        raise ValueError('manifest/report mismatch')
    if (site/'SOURCE.txt').read_bytes() != SOURCE.encode('utf-8'):
        raise ValueError('attribution missing or changed')
    if report['seasons'] != sorted({e['season'] for e in data['events']}) or report['events'] != len(data['events']):
        raise ValueError('bundle counts mismatch')
    info = media_info((site/'visual-media.json').read_bytes(), data, report.get('mediaReview'), strict=report.get('mediaMode')=='reviewed-draft',official_sha=digest(raw))
    if report.get('mediaMode') not in ('synthetic-draft','reviewed-draft') or report.get('media') != info:
        raise ValueError('invalid media report')
    if report['mediaMode']=='synthetic-draft' and info['objects']:
        raise ValueError('unexpected synthetic media')
    b = report.get('build', {})
    expected = build_manifest({name:(site/name).read_bytes() for name in SITE_FILES},data,info,code_commit=report['codeCommit'],mode='synthetic-draft' if report['mediaMode']=='synthetic-draft' else 'pages-draft',input_sha=digest(raw),timestamp=b.get('builtAt'),provenance=b.get('provenance'))
    provenance=b.get('provenance')
    if not isinstance(provenance,dict) or provenance.get('codeCommit')!=report['codeCommit'] or not isinstance(provenance.get('sourceFiles'),dict) or provenance.get('sourceSha256')!=sha(json.dumps(provenance['sourceFiles'],sort_keys=True,separators=(',',':')).encode()):
        raise ValueError('invalid source provenance')
    for name in set(ASSETS)-{'visual-media.json'}:
        if provenance['sourceFiles'].get('web/preview/'+name)!=digest((site/name).read_bytes()):
            raise ValueError('source provenance mismatch: '+name)
    if b != expected:
        raise ValueError('invalid build manifest')
    return report


def prepare(store, output, *, expected_commit=None, expected_sha=None, code_commit=None, media=None, media_manifest=None, synthetic=False):
    output = private_path(output)
    if output.exists():
        raise FileExistsError('output exists; use a fresh directory')
    head, raw, meta = store.load()
    if expected_commit is not None and head != expected_commit:
        raise ValueError('f1-data advanced since update; rerun')
    if expected_sha is not None and meta['officialSha256'] != expected_sha:
        raise ValueError('stored data does not match update checksum')
    data = verify(raw, meta)
    result = audit(data)
    if result['issues']:
        raise ValueError('audit blocked: '+str(result['issues'][:5]))
    assets = code_assets(code_commit)
    provenance = code_provenance(ROOT)
    if code_commit is not None and provenance['codeCommit'] != code_commit:
        raise ValueError('build sources differ from committed code')
    if code_commit is None:
        code_commit = provenance['codeCommit']
    if media is not None:
        if synthetic or media_manifest is None:
            raise ValueError('explicit media review manifest required')
        assets['visual-media.json'] = private_path(media).read_bytes()
        review = parse(private_path(media_manifest).read_bytes())
    else:
        if not synthetic:
            raise ValueError('explicit media required; use --synthetic for rehearsal')
        review = None
    info = media_info(assets['visual-media.json'],data,review,strict=not synthetic,official_sha=digest(raw))
    if synthetic and info['objects']:
        raise ValueError('synthetic media must be empty')
    assets.update({'official.json':raw, 'SOURCE.txt':SOURCE.encode('utf-8')})
    report = dict(version=1, status='draft_bundle_ready', publicationAuthorized=False,
                  independentVerification='pending', blockers=BLOCKERS, dataCommit=head, codeCommit=code_commit,
                  dataManifest=meta, officialSha256=digest(raw), release=release_record(meta['release']),
                  seasons=sorted({e['season'] for e in data['events']}), events=len(data['events']),
                  audit={'issues':0,'countbackCandidates':len(result['countbackReviewCandidates'])},
                  mediaMode='synthetic-draft' if synthetic else 'reviewed-draft', media=info, mediaReview=review,
                  build=build_manifest(assets,data,info,code_commit=code_commit,mode='synthetic-draft' if synthetic else 'pages-draft',input_sha=digest(raw),provenance=provenance),
                  files={name:{'sha256':digest(value),'bytes':len(value)} for name,value in assets.items()})
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.publication-', dir=output.parent))
    try:
        site = temp/'site'; site.mkdir()
        write_assets(site, assets, SITE_FILES)
        (temp/'publication-report.json').write_bytes(json_bytes(report))
        verify_bundle(temp, expected_commit=head, expected_sha=digest(raw))
        if store.remote_head() != head:
            raise ValueError('f1-data changed during assembly; rerun')
        if output.exists():
            raise FileExistsError('output exists')
        temp.rename(output)
    finally:
        if temp.exists(): shutil.rmtree(temp)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    b = sub.add_parser('build'); b.add_argument('--output',required=True); b.add_argument('--code-commit'); b.add_argument('--media'); b.add_argument('--media-manifest'); b.add_argument('--synthetic',action='store_true')
    v = sub.add_parser('verify'); v.add_argument('--bundle',required=True)
    for s in (b,v):
        s.add_argument('--expected-commit'); s.add_argument('--expected-sha')
    a = p.parse_args()
    try:
        if a.command == 'build':
            report=prepare(Store(),a.output,expected_commit=a.expected_commit,expected_sha=a.expected_sha,code_commit=a.code_commit,media=a.media,media_manifest=a.media_manifest,synthetic=a.synthetic)
        else:
            report=verify_bundle(private_path(a.bundle),expected_commit=a.expected_commit,expected_sha=a.expected_sha)
        print(json.dumps({k:report[k] for k in ('status','dataCommit','codeCommit','officialSha256','audit','blockers','publicationAuthorized')},ensure_ascii=False,indent=2))
        if report['mediaMode']=='synthetic-draft': print('Synthetic MEDIA ONLY; sporting data may be real DRAFT data.')
        print('DRAFT SITE ONLY; DEPLOYMENT BLOCKED; artifact visibility not assessed')
        return 0
    except Exception as exc:
        print('PUBLICATION PREPARATION BLOCKED:',exc)
        return 1

if __name__=='__main__':
    raise SystemExit(main())
