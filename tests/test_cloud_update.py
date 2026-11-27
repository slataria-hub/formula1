import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import cloud_update as mod
from activate_update import digest, json_bytes
from validate_data import read


class CloudTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'private').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'private')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.output = self.base/'run'
        self.old = read(ROOT/'examples/synthetic-dataset.json')
        self.old['datasetStatus'] = 'draft'
        self.old['sources'][0]['provider'] = 'F1DB'
        event = self.old['events'][0]
        event.update(status='scheduled', externalEventId='f1db:race-1', grandPrixKey='f1db:gp-1')
        event['sessions'][0].update(status='scheduled', results=[])
        self.new = copy.deepcopy(self.old)

    def seed(self, output, cache, seed_archive=None):
        output.write_bytes(json_bytes(self.old))
        return 'LOCAL'

    def prepared(self, baseline, output, cache, **kwargs):
        output.mkdir()
        raw = json_bytes(self.new)
        (output/'candidate.json').write_bytes(raw)
        report = dict(status='draft_ready', stage='complete', activated=False, publicationAuthorized=False,
                      baselineSha256=digest(baseline.read_bytes()), candidateSha256=digest(raw),
                      audit={'issues': 0}, release={'tag': 'v2034.1.0'}, changes={})
        (output/'update-report.json').write_bytes(json_bytes(report))
        return report

    def run_mock(self):
        with patch.object(mod, 'make_baseline', side_effect=self.seed), patch.object(mod, 'prepare', side_effect=self.prepared):
            return mod.rehearse(self.output)

    def test_metadata_only_noop(self):
        self.new['sources'][0]['retrievedAt'] = '2026-11-27T00:00:00Z'
        r = self.run_mock()
        self.assertEqual(r['rehearsal'], 'no_change')
        self.assertEqual(r['activeSha256'], r['seedSha256'])
        self.assertFalse(r['publicationAuthorized'])
        self.assertFalse(r['persistentState'])
        self.assertEqual(r['release'], 'v2034.1.0')

    def test_changed_candidate_only_disposable(self):
        self.new['events'][0]['date'] = '2026-02-01'
        r = self.run_mock()
        self.assertEqual(r['rehearsal'], 'committed')
        self.assertEqual(r['candidateSha256'], r['activeSha256'])
        self.assertEqual((self.output/'baseline.json').read_bytes(), json_bytes(self.old))
        self.assertEqual(len(list((self.output/'disposable-managed/backups').glob('*.json'))), 1)

    def test_identity_change_blocks(self):
        self.new['events'][0]['externalEventId'] = 'f1db:other'
        with self.assertRaisesRegex(ValueError, 'compatibility blocked'):
            self.run_mock()
        r = read(self.output/'reports/cloud-summary.json')
        self.assertEqual(r['status'], 'blocked')
        self.assertEqual(r['stage'], 'activation rehearsal')
        self.assertFalse(r['publicationAuthorized'])
        self.assertEqual((self.output/'disposable-managed/site/official.json').read_bytes(), json_bytes(self.old))

    def test_fetch_failure_records_block(self):
        with patch.object(mod, 'make_baseline', side_effect=OSError('network unavailable')):
            with self.assertRaises(OSError):
                mod.rehearse(self.output)
        r = read(self.output/'reports/cloud-summary.json')
        self.assertEqual(r['stage'], 'reference')
        self.assertEqual(r['status'], 'blocked')
        self.assertFalse((self.output/'disposable-managed').exists())

    def test_prepare_failure_records_block(self):
        with patch.object(mod, 'make_baseline', side_effect=self.seed), patch.object(mod, 'prepare', side_effect=ValueError('audit failed')):
            with self.assertRaises(ValueError):
                mod.rehearse(self.output)
        self.assertEqual(read(self.output/'reports/cloud-summary.json')['stage'], 'prepare')
        self.assertFalse((self.output/'disposable-managed').exists())

    def test_refuses_existing_output(self):
        self.output.mkdir()
        with self.assertRaises(FileExistsError):
            mod.rehearse(self.output)

    def test_refuses_outside_private(self):
        with self.assertRaises(ValueError):
            mod.rehearse(ROOT/'unsafe-output')

    def test_requires_offline_pair(self):
        with self.assertRaises(ValueError):
            mod.rehearse(self.output, release_json='release.json')
        self.assertFalse(self.output.exists())

    def test_reference_fingerprint_gate(self):
        with patch.object(mod, 'acquire', return_value=('archive.zip', 'LOCAL')), \
             patch.object(mod, 'import_archive', return_value=(self.old, {'archiveSha256':mod.SEED['sha256']})), \
             patch.object(mod, 'reconcile', return_value=(self.old, {})), \
             patch.object(mod, 'correct', return_value=(self.old, [])):
            with self.assertRaisesRegex(ValueError, 'fingerprint mismatch'):
                mod.make_baseline(self.base/'baseline.json', self.base/'cache')
        self.assertFalse((self.base/'baseline.json').exists())

    def test_reference_import_hash_gate(self):
        with patch.object(mod, 'acquire', return_value=('archive.zip', 'LOCAL')), \
             patch.object(mod, 'import_archive', return_value=(self.old, {'archiveSha256':'wrong'})):
            with self.assertRaisesRegex(ValueError, 'archive changed'):
                mod.make_baseline(self.base/'baseline.json', self.base/'cache')


if __name__ == '__main__':
    unittest.main()
