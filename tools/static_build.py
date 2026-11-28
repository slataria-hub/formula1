"""Shared DRAFT packaging primitives. No network, deployment or authorization."""
import base64
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from collect_media import validate_pack, LOGO_STATUSES

ASSETS = ('index.html', 'style.css', 'app.mjs', 'model.mjs', 'user.mjs', 'championship.mjs', 'media.mjs', 'visual-media.json')

def parse_json(raw):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise ValueError('duplicate JSON key: '+k)
            result[k] = v
        return result
    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique, parse_constant=lambda v: (_ for _ in ()).throw(ValueError('invalid number: '+v)))

def preview_assets(root):
    return {name: (Path(root)/'web'/'preview'/name).read_bytes() for name in ASSETS}

def write_assets(directory, assets, expected):
    if set(assets) != set(expected):
        raise ValueError('unexpected site files')
    for name, raw in assets.items():
        (Path(directory)/name).write_bytes(raw)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def media_info(raw, data, manifest=None, *, strict=False, official_sha=None, rehearsal=False):
    pack = validate_pack(parse_json(raw))
    hashes = Counter(); sizes = {}
    for kind in ('photos', 'logos', 'circuits'):
        for item in pack[kind].values():
            if (strict or rehearsal) and (set(item)-{'src','source','author','license','licenseUrl','file','years','periodStatus'} or (kind=='logos' and item.get('periodStatus', 'unverified_season') not in LOGO_STATUSES)):
                raise ValueError('unexpected media metadata')
            image = base64.b64decode(item['src'].split(',', 1)[1], validate=True)
            h = sha(image); hashes[h] += 1; sizes[h] = len(image)
    events = {e.get('externalEventId'): e for e in data['events']}
    for key, row in pack.get('eventLayouts', {}).items():
        e = events.get(key)
        if e is None or row[0] != e['season'] or row[1] != e.get('circuitId') or row[3] not in e.get('sourceIds', []):
            raise ValueError('incompatible event layout: '+key)
    if strict or rehearsal:
        drivers = {x['id'] for x in data['drivers']}
        teams = {x['id'] for x in data['constructors']}
        if set(pack['photos']) - drivers or any(k.rsplit('@',1)[0] not in teams for k in pack['logos']):
            raise ValueError('media references unknown driver or constructor')
        if any(row[2] not in pack['circuits'] for row in pack.get('eventLayouts', {}).values()):
            raise ValueError('missing circuit image for mapped layout')
    info = dict(version=pack['version'], sha256=sha(raw), bytes=len(raw), objects=sum(hashes.values()), uniqueObjects=len(hashes), duplicateBytes=sum((n-1)*sizes[h] for h,n in hashes.items()), maxObjectBytes=max(sizes.values(),default=0))
    if strict or rehearsal:
        if not info['objects'] or not isinstance(manifest, dict):
            raise ValueError('explicit nonempty media and review manifest required')
        if manifest.get('version') != 1 or manifest.get('mediaSha256') != info['sha256'] or manifest.get('officialSha256') != (official_sha or sha(data_bytes(data))) or manifest.get('rightsReviewed') is not (not rehearsal) or set(manifest) != {'version','mediaSha256','officialSha256','rightsReviewed','reviewReference'} or not isinstance(manifest['reviewReference'], str) or not manifest['reviewReference'].strip() or len(manifest['reviewReference']) > 200:
            raise ValueError('media manifest checksum or rights review mismatch')
    return info


def data_bytes(data):
    return json.dumps(data, ensure_ascii=False, separators=(',', ':'), sort_keys=True, allow_nan=False).encode('utf-8')


def code_provenance(root):
    root = Path(root)
    paths = ['tools/static_build.py', 'tools/build_preview.py', 'tools/prepare_publication.py', 'tools/collect_media.py', 'tools/validate_data.py', 'tools/persist_draft.py', 'tools/activate_update.py', 'tools/audit_championships.py', 'schemas/official.schema.json']
    code = {'web/preview/'+k:sha((root/'web/preview'/k).read_bytes()) for k in ASSETS}
    code.update({k:sha((root/k).read_bytes()) for k in paths})
    head = None; commit = None
    try:
        def git(*a):
            return subprocess.check_output(['git','-C',str(root),*a],stderr=subprocess.DEVNULL)
        head=git('rev-parse','HEAD').decode().strip()
        if all(sha(git('show',head+':'+k))==h for k,h in code.items()):
            commit=head
    except (OSError, subprocess.CalledProcessError):
        pass
    if head is None and (root/'SOURCE_SNAPSHOT_MANIFEST.json').is_file():
        snapshot=parse_json((root/'SOURCE_SNAPSHOT_MANIFEST.json').read_bytes())
        head=snapshot.get('head')
    return dict(baseCommit=head, codeCommit=commit, sourceSha256=sha(json.dumps(code,sort_keys=True,separators=(',',':')).encode()), sourceFiles=code)


def build_manifest(assets, data, media, *, code_commit=None, mode='local-draft', input_sha=None, timestamp=None, provenance=None):
    return dict(version=1, applicationVersion='2.0+f1-012.2.1', codeCommit=code_commit, provenance=provenance, sportingDataVersion={'schemaVersion':data['schemaVersion'],'sourceRevisions':sorted({s['revision'] for s in data['sources'] if s.get('revision')})}, sportingDataSha256=sha(data_bytes(data)), inputSha256=input_sha, media=media, mode=mode, syntheticMediaOnly=(mode=='synthetic-draft'), sportingDataStatus=data['datasetStatus'], visibility='not-assessed; DRAFT does not imply private', status='DRAFT', verification='structural-only', permittedUse='local-rehearsal-only; no publication authorization', publicationAuthorized=False, independentVerification='pending', builtAt=timestamp or datetime.now(timezone.utc).isoformat(), files={k:dict(bytes=len(v),sha256=sha(v)) for k,v in sorted(assets.items())})
