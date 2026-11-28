"""Build a private local or Pages DRAFT preview from the same static assets."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
from validate_data import read, validate, ROOT
from static_build import ASSETS, media_info, build_manifest, sha, parse_json, preview_assets, write_assets, code_provenance

def build(input_path, output, media=None, *, mode="local", media_manifest=None, synthetic=False, manifest=False, rehearsal=False):
    output = Path(output).resolve()
    private = (ROOT / 'private').resolve()
    if private not in output.parents:
        raise ValueError('output must be a new subdirectory of project private/')
    if output.exists():
        raise FileExistsError('refusing to overwrite ' + str(output))
    input_raw = Path(input_path).read_bytes()
    data = parse_json(input_raw)
    if data.get('datasetStatus') != 'draft' or not data.get('events'):
        raise ValueError('nonempty draft required; no publication')
    errors = validate(data)
    if errors:
        raise ValueError('validation failed: ' + str(errors[:5]))
    if mode not in ('local','pages'):
        raise ValueError('invalid mode')
    if rehearsal and (mode != 'pages' or synthetic or media is None or media_manifest is None):
        raise ValueError('private rehearsal requires pages mode and explicit media plus pending-rights manifest')
    if mode == 'pages' and not synthetic and (media is None or media_manifest is None):
        raise ValueError('explicit media and review manifest required')
    if media_manifest is not None and media is None:
        raise ValueError('media manifest without explicit media')
    if synthetic and media is not None:
        raise ValueError('synthetic mode uses only the empty fixture media')
    assets = preview_assets(ROOT)
    if media is not None:
        media = Path(media).resolve()
        if private not in media.parents or not media.is_file():
            raise ValueError('media must be a local file under private/')
        assets['visual-media.json'] = media.read_bytes()
    review = None
    if media_manifest is not None:
        media_manifest = Path(media_manifest).resolve()
        if private not in media_manifest.parents or not media_manifest.is_file():
            raise ValueError('media manifest must be under private/')
        review = read(media_manifest)
        if not isinstance(review,dict) or type(review.get('rightsReviewed')) is not bool:
            raise ValueError('invalid media review manifest')
    assets['official.json'] = input_raw
    info = media_info(assets['visual-media.json'], data, review, strict=(mode=='pages' and not synthetic and not rehearsal) or (mode=='local' and review is not None and review.get('rightsReviewed') is True), official_sha=sha(input_raw), rehearsal=rehearsal or (mode=='local' and review is not None and review.get('rightsReviewed') is False))
    if synthetic and info['objects']:
        raise ValueError('synthetic media must be empty')
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='.preview-', dir=output.parent))
    try:
        write_assets(tmp, assets, set(ASSETS)|{'official.json'})
        if manifest or mode == 'pages':
            provenance = code_provenance(ROOT)
            record = build_manifest(assets,data,info,code_commit=provenance['codeCommit'],mode='synthetic-draft' if synthetic else ('pages-private-rehearsal' if rehearsal else mode+'-draft'),input_sha=sha(input_raw),provenance=provenance)
            (tmp/'build-manifest.json').write_text(json.dumps(record,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8')
        if output.exists():
            raise FileExistsError(str(output))
        tmp.rename(output)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    return len({e['season'] for e in data['events']})

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input'); p.add_argument('--output', required=True); p.add_argument('--media'); p.add_argument('--mode',choices=['local','pages'],default='local'); p.add_argument('--media-manifest'); p.add_argument('--synthetic',action='store_true'); p.add_argument('--manifest',action='store_true'); p.add_argument('--rehearsal',action='store_true',help='private Pages rehearsal, rights pending; never upload'); a = p.parse_args()
    try:
        n = build(a.input, a.output, a.media, mode=a.mode, media_manifest=a.media_manifest, synthetic=a.synthetic, manifest=a.manifest,rehearsal=a.rehearsal)
        print(f'PASS {a.mode} preview: {n} seasons; DRAFT only; publication not authorized')
        if a.synthetic: print('Synthetic MEDIA ONLY; sporting data may be real DRAFT data. DRAFT is not a privacy guarantee.')
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        print('PREVIEW FAILED:', e); return 1

if __name__ == '__main__':
    raise SystemExit(main())
