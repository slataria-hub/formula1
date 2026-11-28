import csv,io,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from prepare_approved_inputs import prepare
from static_build import sha
from release_store import canon
import test_pages_release as fixtures
class ReceiptTests(unittest.TestCase):
    def setUp(self):
        f=fixtures.GateTests();f.setUp();self.f=f
        rows=[dict(x,candidateEligible='YES',reviewDecision='eligible_after_approval',publicAllowed='NO',verificationStatus='pending') for x in f.rows]
        out=io.StringIO(newline='');w=csv.DictWriter(out,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
        self.reg=out.getvalue().encode();self.meta=canon(f.md);self.flags=f.code['media.mjs'];self.r=dict(sourceDataCommit='a'*40,officialSha256=sha(f.rawdraft),draftManifestSha256=sha(self.meta),mediaSha256=sha(f.media),candidateRightsSha256=sha(self.reg),flagsSha256=sha(self.flags),independentVerification='passed',rightsDecision='approved',owner='fixture owner',architect='fixture architect',evidenceReference='test only',approvedAt='2026-11-28T00:00:00+00:00')
    def run_receipt(self,r=None,pin=None):
        b=canon(r or self.r);return prepare(self.f.rawdraft,self.meta,self.f.media,self.reg,self.flags,b,pin if pin is not None else sha(b))
    def test_wrong_pin(self):
        with self.assertRaises(ValueError):self.run_receipt(pin='0'*64)
    def test_pending_independent_review(self):
        with self.assertRaises(ValueError):self.run_receipt(dict(self.r,independentVerification='pending'))
    def test_changed_media(self):
        with self.assertRaises(ValueError):self.run_receipt(dict(self.r,mediaSha256='0'*64))
    def test_verified_copy_only(self):
        files=self.run_receipt();self.assertEqual(json.loads(files['data/official.json']),dict(json.loads(self.f.rawdraft),datasetStatus='verified'));self.assertEqual(json.loads(self.f.rawdraft)['datasetStatus'],'draft');self.assertFalse(self.f.md['publicationAuthorized']);self.assertEqual(files['media/visual-media.json'],self.f.media);self.assertEqual(json.loads(files['data/manifest.json'])['independentReviewSha256'],sha(canon(self.r)))
if __name__=='__main__':unittest.main()
