"""Read-only CI entrypoints over existing Store, cloud_update, prepare_publication.
Never persists remote state, uploads artifacts, or authorizes publication.
"""
import argparse
import os
from pathlib import Path
from activate_update import private_path, parse, json_bytes
from persist_draft import Store, verify
from cloud_update import rehearse
from prepare_publication import prepare, verify_bundle
from static_build import media_info, sha
from validate_data import ROOT


def execute(stage, output):
    output = private_path(output)
    if stage == 'data':
        output.mkdir(parents=True, exist_ok=False)
        head, raw, meta = Store().load()
        verify(raw, meta)
        (output/'official.json').write_bytes(raw)
        (output/'data-manifest.json').write_bytes(json_bytes(meta))
        (output/'binding.json').write_bytes(json_bytes({'commit':head,'sha256':sha(raw)}))
        if os.environ.get('CHECK_UPSTREAM','false').lower() == 'true':
            rehearse(output/'upstream', baseline_raw=raw)
        return
    raw = (output/'official.json').read_bytes()
    binding = parse((output/'binding.json').read_bytes())
    data = verify(raw, parse((output/'data-manifest.json').read_bytes()))
    if binding['sha256'] != sha(raw):
        raise ValueError('stored binding mismatch')
    media = (ROOT/'web/preview/visual-media.json').read_bytes()
    info = media_info(media,data)
    if info['objects']:
        raise ValueError('nonempty media cannot enter public CI rehearsal')
    if stage == 'media':
        (output/'media-binding.json').write_bytes(json_bytes(info))
        return
    if parse((output/'media-binding.json').read_bytes()) != info:
        raise ValueError('media binding changed')
    result = prepare(Store(),output/'bundle',expected_commit=binding['commit'],expected_sha=binding['sha256'],code_commit=os.environ.get('GITHUB_SHA'),synthetic=True)
    verify_bundle(output/'bundle',expected_commit=binding['commit'],expected_sha=binding['sha256'])
    if result['publicationAuthorized'] is not False:
        raise ValueError('publication gate changed')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=['data','media','build']);p.add_argument('--output',required=True);a=p.parse_args()
    try:
        execute(a.stage,a.output)
        print(a.stage.upper()+'_PASS; DRAFT; no publication or upload')
    except Exception as e:
        # Avoid echoing any source or credential-bearing input to public logs.
        print(a.stage.upper()+'_BLOCKED:',type(e).__name__);return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
