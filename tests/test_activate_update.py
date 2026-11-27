import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import activate_update as mod
from validate_data import read


class ActivationTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'private').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'private')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.managed = mod.Managed(self.base/'managed')
        self.old = read(ROOT/'examples/synthetic-dataset.json')
        self.old['datasetStatus'] = 'draft'
        self.old['sources'][0]['provider'] = 'F1DB'
        event = self.old['events'][0]
        event.update(status='scheduled', externalEventId='f1db:race-1', grandPrixKey='f1db:gp-1')
        event['sessions'][0].update(status='scheduled', results=[])
        self.baseline = self.base/'baseline.json'
        self.baseline.write_bytes(mod.json_bytes(self.old))
        self.before = self.managed.initialize(self.baseline)
        self.new = copy.deepcopy(self.old)
        self.new['events'][0]['date'] = '2026-02-01'
        self.run = self.base/'run'
        self.run.mkdir()

    def candidate(self, data=None, **extra):
        data = self.new if data is None else data
        raw = mod.json_bytes(data)
        (self.run/'candidate.json').write_bytes(raw)
        report = dict(status='draft_ready', stage='complete', activated=False, publicationAuthorized=False,
                      baselineSha256=self.before, candidateSha256=mod.digest(raw), audit={'issues': 0})
        report.update(extra)
        (self.run/'update-report.json').write_bytes(mod.json_bytes(report))
        return raw

    def assert_old(self):
        self.assertEqual(self.managed.active.read_bytes(), self.baseline.read_bytes())

    def test_exact_baseline_and_site_assets(self):
        self.assert_old()
        self.assertEqual(set(p.name for p in self.managed.site.iterdir()), set(mod.ASSETS)|{'official.json'})
        self.assertFalse((self.managed.site/'backups').exists())
        with self.assertRaises(FileExistsError): self.managed.initialize(self.baseline)

    def test_metadata_no_change(self):
        new = copy.deepcopy(self.old)
        new['sources'][0]['retrievedAt'] = '2026-11-27T00:00:00Z'
        self.candidate(new)
        r = self.managed.activate(self.run)
        self.assertEqual(r['status'], 'no_change')
        self.assert_old()
        self.assertEqual(list(self.managed.backups.iterdir()), [])

    def test_source_id_no_change(self):
        new = copy.deepcopy(self.old)
        new = json.loads(json.dumps(new).replace('test:sample','test:other'))
        self.candidate(new)
        self.assertEqual(self.managed.activate(self.run)['status'], 'no_change')
        self.assert_old()

    def test_changed_date_switch_and_rollback(self):
        raw = self.candidate()
        r = self.managed.activate(self.run)
        self.assertEqual(r['status'], 'committed')
        self.assertEqual(self.managed.active.read_bytes(), raw)
        self.assertEqual((self.managed.backups/(self.before+'.json')).read_bytes(), self.baseline.read_bytes())
        rb = self.managed.rollback(self.before, mod.digest(raw))
        self.assertEqual(rb['status'], 'committed')
        self.assert_old()
        self.assertEqual(len(self.managed.status()['backups']), 2)

    def test_future_season(self):
        event = copy.deepcopy(self.new['events'][0])
        event.update(id='2027-R01', season=2027, externalEventId='f1db:race-2', date='2027-03-01')
        event['sessions'][0]['id'] = '2027-R01-race'
        self.new['events'].append(event)
        self.candidate()
        self.assertEqual(self.managed.activate(self.run)['status'], 'committed')
        self.assertEqual(read(self.managed.active)['events'][-1]['season'], 2027)

    def test_non_reported_field_change(self):
        # Report's changes arrays are not trusted: detect actual data changes.
        self.new['drivers'][0]['nationality'] = 'Example'
        self.new['events'][0]['date'] = self.old['events'][0]['date']
        self.candidate(changes={'newEvents': [], 'changedDates': []})
        self.assertEqual(self.managed.activate(self.run)['status'], 'committed')

    def test_stale_report(self):
        self.candidate(baselineSha256='a'*64)
        with self.assertRaisesRegex(ValueError, 'stale baseline'): self.managed.activate(self.run)
        self.assert_old()

    def test_tampered_candidate(self):
        self.candidate()
        with (self.run/'candidate.json').open('ab') as f: f.write(b' ')
        with self.assertRaisesRegex(ValueError, 'checksum'): self.managed.activate(self.run)
        self.assert_old()

    def test_blocked_report(self):
        self.candidate(status='blocked')
        with self.assertRaisesRegex(ValueError, 'draft report'): self.managed.activate(self.run)
        self.assert_old()

    def test_identity_conflict(self):
        self.new['events'][0]['externalEventId'] = 'f1db:race-other'
        self.candidate()
        with self.assertRaisesRegex(ValueError, 'identity changed'): self.managed.activate(self.run)
        self.assert_old()

    def test_audit_not_trusted(self):
        self.new['events'][0]['status'] = 'unknown'
        self.candidate()
        with self.assertRaisesRegex(ValueError, 'audit blocked'): self.managed.activate(self.run)
        self.assert_old()

    def test_new_countback_blocks(self):
        self.candidate()
        with patch.object(mod, 'checked_audit', side_effect=[set(), {b'new-review'}]):
            with self.assertRaisesRegex(ValueError, 'new countback'): self.managed.activate(self.run)
        self.assert_old()

    def test_lock(self):
        self.candidate()
        self.managed.lock.write_text('other process')
        with self.assertRaisesRegex(ValueError, 'lock exists'): self.managed.activate(self.run)
        self.assert_old()
        self.assertTrue(self.managed.lock.exists())

    def test_failed_replace(self):
        self.candidate()
        real = mod.atomic_write
        def fail(path, raw):
            if path == self.managed.active: raise OSError('simulated replacement failure')
            real(path, raw)
        with patch.object(mod, 'atomic_write', side_effect=fail):
            with self.assertRaises(OSError): self.managed.activate(self.run)
        self.assert_old()
        self.assertFalse(self.managed.lock.exists())
        self.assertIn('rolled_back', [read(p)['status'] for p in self.managed.journal.glob('*.json')])

    def test_failed_post_replace_verification(self):
        self.candidate()
        real = mod.atomic_write
        failures = [True]
        def corrupt(path, raw):
            if path == self.managed.active and failures:
                failures.pop(); real(path, b'bad'); return
            real(path, raw)
        with patch.object(mod, 'atomic_write', side_effect=corrupt):
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'): self.managed.activate(self.run)
        self.assert_old()

    def test_recover_interrupted_commit(self):
        raw = self.candidate()
        real = self.managed.record
        def fail(path, report):
            if report['status'] == 'committed': raise OSError('journal write failure')
            real(path, report)
        with patch.object(self.managed, 'record', side_effect=fail):
            with self.assertRaises(OSError): self.managed.activate(self.run)
        self.assertEqual(self.managed.status()['activeSha256'], mod.digest(raw))
        self.assertIn('recovered_committed', [read(p)['status'] for p in self.managed.journal.glob('*.json')])

    def test_rollback_stale_and_corrupt_backup(self):
        raw = self.candidate()
        self.managed.activate(self.run)
        with self.assertRaisesRegex(ValueError, 'active hash changed'): self.managed.rollback(self.before, 'b'*64)
        (self.managed.backups/(self.before+'.json')).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'backup checksum'): self.managed.rollback(self.before, mod.digest(raw))
        self.assertEqual(self.managed.active.read_bytes(), raw)

    def test_user_backup_preserved(self):
        self.candidate()
        u = read(ROOT/'examples/user.example.json')
        store = dict(version=1, user=u, bindings={'2026-R01-race':dict(externalEventId='f1db:race-1',season=2026,kind='race')})
        p = self.base/'user.json'; p.write_bytes(mod.json_bytes(store)); original=p.read_bytes()
        self.managed.activate(self.run, p)
        self.assertEqual(p.read_bytes(), original)
        self.assertFalse((self.managed.site/'user.json').exists())

    def test_user_binding_mismatch(self):
        self.candidate()
        store = dict(version=1, user=read(ROOT/'examples/user.example.json'), bindings={'2026-R01-race':dict(externalEventId='f1db:wrong',season=2026,kind='race')})
        p = self.base/'user.json'; p.write_bytes(mod.json_bytes(store))
        with self.assertRaisesRegex(ValueError, 'binding mismatch'): self.managed.activate(self.run, p)
        self.assert_old()

    def test_refuses_public_path(self):
        with self.assertRaisesRegex(ValueError, 'private'): mod.Managed(ROOT/'public')

if __name__ == '__main__': unittest.main()
