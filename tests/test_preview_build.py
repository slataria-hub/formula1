"""Preview generation tests; no browser or network needed."""
import json, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_preview import build
from validate_data import read

class PreviewBuildTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'private').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'private');self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.src=self.base/'input.json';self.out=self.base/'preview'
        self.data=read(ROOT/'examples/synthetic-dataset.json');self.data['datasetStatus']='draft'
        self.src.write_text(json.dumps(self.data),encoding='utf-8')
    def test_build_preserves_input_and_copies_only_assets(self):
        before=self.src.read_bytes();self.assertEqual(build(self.src,self.out),1)
        self.assertEqual(before,self.src.read_bytes());self.assertEqual(read(self.out/'official.json'),self.data)
        self.assertEqual({p.name for p in self.out.iterdir()},{'official.json','index.html','style.css','app.mjs','model.mjs','user.mjs','championship.mjs','media.mjs','visual-media.json'})
    def test_refuses_overwrite(self):
        self.out.mkdir();sentinel=self.out/'sentinel';sentinel.write_text('keep')
        with self.assertRaises(FileExistsError):build(self.src,self.out)
        self.assertEqual(sentinel.read_text(),'keep')
    def test_refuses_invalid_and_fixture(self):
        for status in ('fixture','verified'):
            self.data['datasetStatus']=status;self.src.write_text(json.dumps(self.data))
            with self.assertRaises(ValueError):build(self.src,self.out)
        self.data['datasetStatus']='draft';self.data['events'][0]['sessions'][0]['results'][0]['driverId']='test:missing';self.src.write_text(json.dumps(self.data))
        with self.assertRaises(ValueError):build(self.src,self.out)
        self.assertFalse(self.out.exists())
    def test_refuses_public_output(self):
        with self.assertRaises(ValueError):build(self.src,ROOT/'preview-public-test')

    def test_legacy_cli_with_and_without_media(self):
        import subprocess
        media=ROOT/'private'/self.base.name/'media.json';media.write_bytes((ROOT/'web/preview/visual-media.json').read_bytes())
        for i,args in enumerate([[],['--media',str(media)]]):
            out=self.base/f'legacy-{i}'
            result=subprocess.run([sys.executable,str(ROOT/'tools/build_preview.py'),str(self.src),'--output',str(out),*args],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual((out/'official.json').read_bytes(),self.src.read_bytes())
            self.assertEqual((out/'visual-media.json').read_bytes(),media.read_bytes())
            self.assertFalse((out/'build-manifest.json').exists())
