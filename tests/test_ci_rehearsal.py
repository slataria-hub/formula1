import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import ci_rehearsal as ci
from activate_update import json_bytes
from persist_draft import manifest,SEED
from validate_data import read
class CIRehearsalTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'private').mkdir(exist_ok=True);self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'private');self.addCleanup(self.tmp.cleanup);self.out=Path(self.tmp.name)/'ci';d=read(ROOT/'examples/synthetic-dataset.json');d['datasetStatus']='draft';d['sources'][0]['provider']='F1DB';e=d['events'][0];e.update(status='scheduled',externalEventId='f1db:race-1',grandPrixKey='f1db:gp-1');e['sessions'][0].update(status='scheduled',results=[]);self.raw=json_bytes(d);self.meta=manifest(self.raw,SEED,None);self.store=Mock();self.store.load.return_value=('1'*40,self.raw,self.meta);self.store.remote_head.return_value='1'*40
    def test_all_stages_readonly(self):
        with patch.object(ci,'Store',return_value=self.store),patch.dict(os.environ,{'CHECK_UPSTREAM':'false'},clear=True):
            for s in ['data','media','build']:ci.execute(s,self.out)
        self.store.save.assert_not_called();self.assertFalse(read(self.out/'bundle/publication-report.json')['publicationAuthorized'])
    def test_data_changed(self):
        with patch.object(ci,'Store',return_value=self.store),patch.dict(os.environ,{'CHECK_UPSTREAM':'false'},clear=True):ci.execute('data',self.out)
        (self.out/'official.json').write_bytes(b'{}');self.assertRaises(ValueError,ci.execute,'media',self.out)
    def test_optional_upstream_is_disposable(self):
        with patch.object(ci,'Store',return_value=self.store),patch.object(ci,'rehearse') as replay,patch.dict(os.environ,{'CHECK_UPSTREAM':'true'},clear=True):ci.execute('data',self.out)
        replay.assert_called_once_with(self.out/'upstream',baseline_raw=self.raw);self.store.save.assert_not_called()
if __name__=='__main__':unittest.main()
