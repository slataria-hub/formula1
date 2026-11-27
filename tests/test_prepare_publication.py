"""Fail-closed packaging tests without network or publication rights."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import prepare_publication as p
from activate_update import digest,json_bytes,parse
from persist_draft import manifest,SEED
from validate_data import read

class PublicationTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'private').mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'private'); self.addCleanup(self.tmp.cleanup)
        self.out=Path(self.tmp.name)/'bundle'
        self.data=read(ROOT/'examples/synthetic-dataset.json'); self.data['datasetStatus']='draft'; self.data['sources'][0]['provider']='F1DB'
        e=self.data['events'][0]; e.update(status='scheduled',externalEventId='f1db:race-1',grandPrixKey='f1db:gp-1'); e['sessions'][0].update(status='scheduled',results=[])
        self.raw=json_bytes(self.data); self.meta=manifest(self.raw,SEED,None); self.head='1'*40
        self.store=Mock(); self.store.load.return_value=(self.head,self.raw,self.meta); self.store.remote_head.return_value=self.head
    def build(self,**kw): return p.prepare(self.store,self.out,**kw)
    def verify(self,**kw): return p.verify_bundle(self.out,**kw)
    def mutate_report(self,**kw):
        f=self.out/'publication-report.json'; r=parse(f.read_bytes()); r.update(kw); f.write_bytes(json_bytes(r))
    def test_exact_bundle(self):
        r=self.build(expected_commit=self.head,expected_sha=digest(self.raw)); self.assertEqual(self.verify(),r)
        self.assertEqual((self.out/'site/official.json').read_bytes(),self.raw); self.assertFalse(r['publicationAuthorized']); self.assertEqual(set(r['files']),p.SITE_FILES)
        self.assertIn('CC BY 4.0',(self.out/'site/SOURCE.txt').read_text()); self.store.save.assert_not_called()
    def test_data_advanced(self):
        with self.assertRaisesRegex(ValueError,'advanced'): self.build(expected_commit='2'*40)
        self.assertFalse(self.out.exists())
    def test_expected_hash(self):
        with self.assertRaisesRegex(ValueError,'checksum'): self.build(expected_sha='2'*64)
    def test_race_during_build(self):
        self.store.remote_head.return_value='2'*40
        with self.assertRaisesRegex(ValueError,'changed during'): self.build()
        self.assertFalse(self.out.exists())
    def test_invalid_source_manifest(self):
        self.meta['officialSha256']='2'*64
        with self.assertRaisesRegex(ValueError,'checksum'): self.build()
    def test_audit_fails_closed(self):
        with patch.object(p,'audit',return_value={'issues':['bad']}):
            with self.assertRaisesRegex(ValueError,'audit blocked'): self.build()
        self.assertFalse(self.out.exists())
    def test_refuse_overwrite(self):
        self.out.mkdir(); (self.out/'marker').write_text('keep')
        with self.assertRaises(FileExistsError): self.build()
        self.assertEqual((self.out/'marker').read_text(),'keep')
    def test_tampered_asset(self):
        self.build(); (self.out/'site/app.mjs').write_text('changed')
        with self.assertRaisesRegex(ValueError,'site checksum'): self.verify()
    def test_tampered_data(self):
        self.build(); (self.out/'site/official.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'site checksum'): self.verify()
    def test_unexpected_private_file(self):
        self.build(); (self.out/'site/user.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'unexpected site files'): self.verify()
    def test_forged_approval(self):
        self.build(); self.mutate_report(publicationAuthorized=True,blockers=[])
        with self.assertRaisesRegex(ValueError,'invalid DRAFT publication gate'): self.verify()
    def test_verify_against_expected(self):
        self.build()
        with self.assertRaisesRegex(ValueError,'data commit mismatch'): self.verify(expected_commit='2'*40)
        with self.assertRaisesRegex(ValueError,'official checksum mismatch'): self.verify(expected_sha='2'*64)
    def test_committed_asset_check(self):
        def fake(cmd,**kw):
            if 'rev-parse' in cmd: return (self.head+'\n').encode()
            return b'not committed content'
        with patch.object(p.subprocess,'check_output',side_effect=fake):
            with self.assertRaisesRegex(ValueError,'asset differs'): self.build(code_commit=self.head)
        self.assertFalse(self.out.exists())
    def test_attribution_tampered_even_if_rehashed(self):
        self.build(); f=self.out/'site/SOURCE.txt'; f.write_text('removed'); r=parse((self.out/'publication-report.json').read_bytes()); r['files']['SOURCE.txt']={'sha256':digest(f.read_bytes()),'bytes':len(f.read_bytes())}; self.mutate_report(files=r['files'])
        with self.assertRaisesRegex(ValueError,'attribution'): self.verify()

if __name__=='__main__': unittest.main()
