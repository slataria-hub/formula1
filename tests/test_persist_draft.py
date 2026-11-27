import copy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import persist_draft as p
import cloud_update as c
from activate_update import json_bytes, digest, sports_digest
from validate_data import read

class PersistenceTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'private').mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'private'); self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name); self.remote=self.path/'remote.git'; self.repo=self.path/'repo'
        subprocess.run(['git','init','--bare',str(self.remote)],check=True,capture_output=True)
        subprocess.run(['git','init',str(self.repo)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(self.repo),'remote','add','origin',str(self.remote)],check=True,capture_output=True)
        with patch.dict(os.environ,{'F1_DATA_GIT_TOKEN':''}): self.store=p.Store(self.repo)
        self.old=read(ROOT/'examples/synthetic-dataset.json'); self.old['datasetStatus']='draft'; self.old['sources'][0]['provider']='F1DB'
        e=self.old['events'][0]; e.update(status='scheduled',externalEventId='f1db:race-1',grandPrixKey='f1db:gp-1'); e['sessions'][0].update(status='scheduled',results=[])
        self.raw=json_bytes(self.old); self.seed=self.path/'seed.json'; self.seed.write_bytes(self.raw)
        self.release={'tag':'v2034.1.0','sha256':'a'*64}; self.new=copy.deepcopy(self.old)
        self.out=self.path/'run'
    def init(self):
        with patch.object(p,'SEED_SPORTS',sports_digest(self.old)):
            return p.bootstrap(self.store,self.seed)
    def prepared(self,baseline,output,cache,**kwargs):
        output.mkdir(); raw=json_bytes(self.new); (output/'candidate.json').write_bytes(raw)
        report=dict(status='draft_ready',stage='complete',activated=False,publicationAuthorized=False,baselineSha256=digest(baseline.read_bytes()),candidateSha256=digest(raw),audit={'issues':0},release=self.release,changes={})
        (output/'update-report.json').write_bytes(json_bytes(report)); return report
    def update(self):
        with patch.object(c,'prepare',side_effect=self.prepared): return p.update(self.store,self.out)
    def test_missing_requires_explicit_bootstrap(self):
        with self.assertRaisesRegex(ValueError,'explicit one-time bootstrap'): self.store.load()
    def test_bootstrap_and_load(self):
        head=self.init(); got,raw,meta=self.store.load(); self.assertEqual(head,got); self.assertEqual(raw,self.raw); self.assertFalse(meta['publicationAuthorized']); self.assertEqual(self.store.git('ls-tree','--name-only',head).decode().splitlines(),['manifest.json','official.json'])
    def test_bootstrap_refuses_repeat(self):
        self.init()
        with self.assertRaisesRegex(ValueError,'already exists'): self.init()
    def test_bootstrap_fingerprint(self):
        with self.assertRaisesRegex(ValueError,'pinned sporting reference'): p.bootstrap(self.store,self.seed)
    def test_no_change_does_not_commit(self):
        head=self.init(); self.new['sources'][0]['retrievedAt']='2026-11-28T00:00:00Z'; result=self.update(); self.assertEqual(result['status'],'no_change'); self.assertEqual(self.store.remote_head(),head)
    def test_changed_persists_and_next_run_uses_it(self):
        head=self.init(); self.new['events'][0]['date']='2026-02-01'; r=self.update(); self.assertEqual(r['status'],'stored'); self.assertNotEqual(r['afterCommit'],head)
        got,raw,meta=self.store.load(); self.assertEqual(raw,json_bytes(self.new)); self.assertEqual(meta['parentCommit'],head); self.assertEqual(self.store.git('rev-parse',got+'^').decode().strip(),head)
        self.out=self.path/'run2'; r2=self.update(); self.assertEqual(r2['status'],'no_change'); self.assertEqual(self.store.remote_head(),got)
    def test_stale_write(self):
        head=self.init(); meta=p.manifest(self.raw,self.release,head); self.store.load(); self.store.save(self.raw,meta,head)
        with self.assertRaisesRegex(ValueError,'stale write'): self.store.save(self.raw,meta,head)
    def test_exact_lease_rejects_race(self):
        head=self.init(); meta=p.manifest(self.raw,self.release,head); self.store.load()
        advanced=self.store.save(self.raw,meta,head)
        meta=dict(meta, storedAt='2034-01-01T00:00:00+00:00')
        with patch.object(self.store,'remote_head',return_value=head):
            # Stale check is spoofed; the actual git lease must still reject the push.
            with self.assertRaisesRegex(ValueError,'git push failed'): self.store.save(self.raw,meta,head)
        self.assertEqual(self.store.remote_head(),advanced)
    def test_missing_branch_diagnostic(self):
        with self.assertRaisesRegex(ValueError,'explicit one-time bootstrap'): self.update()
        self.assertEqual(read(self.out/'reports/persistence.json')['status'],'blocked')
    def test_refuse_existing_output(self):
        self.out.mkdir(); marker=self.out/'marker'; marker.write_text('keep')
        with self.assertRaises(FileExistsError): self.update()
        self.assertEqual(marker.read_text(),'keep')
    def test_corrupt_manifest(self):
        self.init(); _,raw,meta=self.store.load(); meta['officialSha256']='b'*64
        with self.assertRaisesRegex(ValueError,'checksum mismatch'): p.verify(raw,meta)
    def test_regression_blocked(self):
        head=self.init(); self.release={'tag':'v2020.1.0','sha256':'a'*64}
        with self.assertRaisesRegex(ValueError,'downgrade'): self.update()
        self.assertEqual(self.store.remote_head(),head)
    def test_replaced_release_blocked(self):
        head=self.init(); self.release={'tag':p.SEED['tag'],'sha256':'a'*64}
        with self.assertRaisesRegex(ValueError,'different archive hash'): self.update()
        self.assertEqual(self.store.remote_head(),head)
    def test_identity_change_leaves_branch(self):
        head=self.init(); self.new['events'][0]['externalEventId']='f1db:changed'
        with self.assertRaisesRegex(ValueError,'compatibility blocked'): self.update()
        self.assertEqual(self.store.remote_head(),head)
    def test_failed_fetch_leaves_branch(self):
        head=self.init()
        with patch.object(c,'prepare',side_effect=OSError('network failure')):
            with self.assertRaises(OSError): p.update(self.store,self.out)
        self.assertEqual(self.store.remote_head(),head)

if __name__=='__main__': unittest.main()
