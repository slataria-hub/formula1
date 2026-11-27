"""Build a local-only, preview with local-only user state from a structurally valid draft v2 dataset."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
from validate_data import read, validate, ROOT

ASSETS = ('index.html', 'style.css', 'app.mjs', 'model.mjs', 'user.mjs', 'championship.mjs')

def build(input_path, output):
    output = Path(output).resolve()
    private = (ROOT / 'private').resolve()
    if private not in output.parents:
        raise ValueError('output must be a new subdirectory of project private/')
    if output.exists():
        raise FileExistsError('refusing to overwrite ' + str(output))
    data = read(input_path)
    if data.get('datasetStatus') != 'draft' or not data.get('events'):
        raise ValueError('nonempty draft required; no publication')
    errors = validate(data)
    if errors:
        raise ValueError('validation failed: ' + str(errors[:5]))
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='.preview-', dir=output.parent))
    try:
        for name in ASSETS:
            shutil.copyfile(ROOT / 'web' / 'preview' / name, tmp / name)
        (tmp / 'official.json').write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')
        if output.exists():
            raise FileExistsError(str(output))
        tmp.rename(output)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    return len({e['season'] for e in data['events']})

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input'); p.add_argument('--output', required=True); a = p.parse_args()
    try:
        n = build(a.input, a.output)
        print(f'PASS local preview: {n} seasons; DRAFT only; publication not authorized'); return 0
    except (OSError, ValueError, KeyError, TypeError) as e:
        print('PREVIEW FAILED:', e); return 1

if __name__ == '__main__':
    raise SystemExit(main())
