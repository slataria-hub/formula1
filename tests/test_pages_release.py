import copy,csv,io,json,os,sys,tempfile,unittest,subprocess
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import pages_release as p
from activate_update import json_bytes,sports_digest
from persist_draft import manifest,SEED
from media_catalog import inventory
from static_build import ASSETS,sha
from release_store import canon,record

class GateTests(unittest.TestCase):
    def setUp(self):
        self.d=json.loads((ROOT/'examples/synthetic-dataset.json').read_bytes());self.d['datasetStatus']='draft';s=self.d['sources'][0];s.update(provider='F1DB',revision=SEED['tag'],sha256=SEED['sha256']);e=self.d['events'][0];e.update(status='scheduled',externalEventId='f1db:race-1',grandPrixKey='f1db:gp-1');e['sessions'][0].update(status='scheduled',results=[])
        self.rawdraft=json_bytes(self.d);self.md=manifest(self.rawdraft,SEED,None);self.d['datasetStatus']='verified';self.raw=json_bytes(self.d);self.meta=json_bytes(dict(self.md,datasetStatus='verified',publicationAuthorized=True,independentVerification='passed',officialSha256=sha(self.raw),sportsSha256=sports_digest(self.d)))
        self.media=json_bytes(dict(version=1,photos={self.d['drivers'][0]['id']:dict(src='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1ZkAAAAASUVORK5CYII=',source='https://example.invalid/fixture',author='synthetic test',license='CC BY 4.0')},logos={},circuits={}))
        self.code={n:(ROOT/'web/preview'/n).read_bytes() for n in set(ASSETS)-{'visual-media.json'}};self.code['media.mjs']=b'export const FLAGS={};\n'
        self.rows=inventory(self.media,self.code['media.mjs']);self.rows=[dict(r,verificationStatus='verified',publicAllowed='YES',evidence='https://example.invalid/test-only') for r in self.rows];self.reg=self.registry(self.rows)
        self.body=dict(contractVersion=1,codeCommit='1'*40,dataCommit='2'*40,sourceDataCommit='3'*40,mediaCommit='4'*40,mediaVersion='sha256:'+sha(self.media),sourceTag=SEED['tag'],schemaVersion=self.d['schemaVersion'],rightsRegistrySha256=sha(self.reg),officialSha256=sha(self.raw),dataManifestSha256=sha(self.meta),mediaManifestSha256='a'*64,mediaSha256=sha(self.media),fileManifest={},formedAt='2026-11-28T00:00:00+00:00',verificationStatus='passed',rightsStatus='verified',publicationAuthorized=True)
        # Test-only mock attribution file derived using the same fixed formatting, not approval of real material.
        lines=['F1DB (https://github.com/f1db/f1db), CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).','Transformed by F1 Analytics: historical reconciliation and normalization.','Source: '+SEED['tag'],'Media attribution:']
        for r in self.rows:lines.append(f"{r['objectType']} {r['objectId']}: {r['attribution']} | {r['source']} | {r['license']} {r['licenseUrl']}")
        files={**self.code,'official.json':self.raw,'visual-media.json':self.media,'SOURCE.txt':('\n'.join(lines)+'\n').encode()};self.body['fileManifest']={n:record(b) for n,b in sorted(files.items())}
        self.desc=dict(self.body,releaseId=sha(canon(self.body)));self.approval=canon(dict(releaseId=self.desc['releaseId'],decision='publish',owner='fixture owner',architect='fixture architect',reference='test-only',approvedAt='2026-11-28T00:00:00+00:00'));self.pin=sha(self.approval)
    def registry(self,rows):
        f=io.StringIO(newline='');w=csv.DictWriter(f,fieldnames=list(self.rows[0]) if hasattr(self,'rows') and 'evidence' in self.rows[0] else list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows);return f.getvalue().encode()
    def materialize(self,**kw):return p.materialize(kw.get('code',self.code),kw.get('raw',self.raw),kw.get('meta',self.meta),kw.get('media',self.media),kw.get('registry',self.reg),kw.get('descriptor',self.desc))
    def test_exact_approval(self):self.assertEqual(p.authorize(self.desc,self.approval,self.pin)['releaseId'],self.desc['releaseId'])
    def test_missing_pin(self):
        with self.assertRaises(ValueError):p.authorize(self.desc,self.approval,'')
    def test_wrong_pin(self):
        with self.assertRaises(ValueError):p.authorize(self.desc,self.approval,'0'*64)
    def test_changed_descriptor(self):
        d=dict(self.desc,mediaCommit='5'*40)
        with self.assertRaises(ValueError):p.authorize(d,self.approval,self.pin)
    def test_false_authorization(self):
        b=dict(self.body,publicationAuthorized=False);d=dict(b,releaseId=sha(canon(b)))
        with self.assertRaises(ValueError):p.authorize(d,self.approval,self.pin)
    def test_real_draft_contract_refused(self):
        with self.assertRaisesRegex(ValueError,'not authorized'):p.approved_data(self.rawdraft,json_bytes(self.md))
    def test_data_corrupt(self):
        with self.assertRaises(ValueError):p.approved_data(self.raw+b' ',self.meta)
    def test_materialize_exact(self):
        a=self.materialize();b=self.materialize();self.assertEqual(a,b);self.assertEqual(a['official.json'],self.raw);self.assertEqual(a['visual-media.json'],self.media);self.assertEqual(set(a),p.SITE-{'release-manifest.json'})
    def test_unapproved_rights(self):
        rows=copy.deepcopy(self.rows);rows[0]['publicAllowed']='NO'
        with self.assertRaisesRegex(ValueError,'unapproved'):self.materialize(registry=self.registry(rows))
    def test_wrong_rights_identity(self):
        rows=copy.deepcopy(self.rows);rows[0]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'identity'):self.materialize(registry=self.registry(rows))
    def test_extra_asset(self):
        with self.assertRaises(ValueError):self.materialize(code={**self.code,'user.json':b'{}'})
    def test_changed_asset(self):
        with self.assertRaises(ValueError):self.materialize(code={**self.code,'style.css':b'changed'})
    def test_unknown_media_id(self):
        m=json.loads(self.media);m['photos']['unknown']=next(iter(m['photos'].values()));raw=json_bytes(m)
        rows=[dict(r,verificationStatus='verified',publicAllowed='YES',evidence='https://example.invalid/test-only') for r in inventory(raw,self.code['media.mjs'])]
        with self.assertRaises(ValueError):self.materialize(media=raw,registry=self.registry(rows))
    def test_build_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td,patch.object(p,'resolve',return_value=({n:b'fixture' for n in p.SITE},self.desc)):
            target=Path(td)/'site';p.build(ROOT,'5'*40,self.pin,target)
            with self.assertRaises(FileExistsError):p.build(ROOT,'5'*40,self.pin,target)
            self.assertEqual((target/'official.json').read_bytes(),b'fixture')
    def test_failed_gate_no_output(self):
        with tempfile.TemporaryDirectory() as td,patch.object(p,'resolve',side_effect=ValueError('blocked')):
            target=Path(td)/'site'
            with self.assertRaises(ValueError):p.build(ROOT,'5'*40,self.pin,target)
            self.assertFalse(target.exists())
    def test_git_tree_exact(self):
        with tempfile.TemporaryDirectory() as td:
            def g(*args):return subprocess.check_output(['git','-C',td,*args],stderr=subprocess.DEVNULL).decode().strip()
            g('init');g('config','user.email','test@example.invalid');g('config','user.name','fixture');(Path(td)/'official.json').write_bytes(b'{}');(Path(td)/'manifest.json').write_bytes(b'{}');g('add','official.json','manifest.json');g('commit','-m','fixture');c=g('rev-parse','HEAD');self.assertEqual(set(p.tree_files(td,c,{'official.json','manifest.json'})),{'official.json','manifest.json'})
            with self.assertRaises(ValueError):p.tree_files(td,c,{'official.json'})
if __name__=='__main__':unittest.main()
