import sys,tempfile,unittest,zipfile,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from repository_audit import forbidden,inspect_bytes,scan_zip,scan_history,scan_tracked,scan_index
class AuditTests(unittest.TestCase):
    def test_paths(self):
        for p in ('private/x.json','foo/.env.production','backup/x','user.json','x.pem','predictions-a.json','../x'):
            self.assertTrue(forbidden(p),p)
        self.assertFalse(forbidden('examples/user.example.json'))
    def test_secret_redacted(self):
        raw=('gh'+'p_'+'x'*36).encode();self.assertEqual(inspect_bytes('x.txt',raw),['github_token']);self.assertNotIn(raw.decode(),str(inspect_bytes('x.txt',raw)))
    def test_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'artifact.zip'
            with zipfile.ZipFile(p,'w') as z:z.writestr('site/user.json','{}');z.writestr('site/index.html','test')
            r=scan_zip(p);self.assertEqual(r['scanned'],2);self.assertEqual(r['findings'],[{'path':'site/user.json','rule':'forbidden_path'}])
    def test_history_includes_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def git(*args):subprocess.run(['git','-C',tmp,*args],check=True,capture_output=True)
            git('init');git('config','user.email','test@example.invalid');git('config','user.name','Test');(root/'removed.txt').write_text('gh'+'p_'+'x'*36);git('add','removed.txt');git('commit','-m','fixture');git('rm','removed.txt');git('commit','-m','remove');self.assertFalse(scan_tracked(root)['findings']);r=scan_history(root);self.assertEqual(r['commits'],2);self.assertEqual(r['findings'][0]['rule'],'github_token')
    def test_index_secret_absent_from_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def git(*args):subprocess.run(['git','-C',tmp,*args],check=True,capture_output=True)
            git('init');p=root/'x.txt';p.write_text('gh'+'p_'+'x'*36);git('add','x.txt');p.write_text('clean')
            self.assertFalse(scan_tracked(root)['findings'])
            self.assertEqual(scan_index(root)['findings'],[{'path':'x.txt','rule':'github_token'}])
            git('add','x.txt');self.assertEqual(scan_index(root),dict(scanned=1,findings=[],blocked=[]))
    def test_index_staged_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def git(*args):subprocess.run(['git','-C',tmp,*args],check=True,capture_output=True)
            git('init');(root/'x.txt').write_text('clean');git('add','x.txt');git('rm','--cached','x.txt')
            self.assertEqual(scan_index(root),dict(scanned=0,findings=[],blocked=[]))
    def test_index_conflict_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def git(*args,**kwargs):return subprocess.run(['git','-C',tmp,*args],check=True,capture_output=True,**kwargs).stdout
            git('init');oid=git('hash-object','-w','--stdin',input=b'clean').decode().strip()
            git('update-index','--index-info',input=('100644 '+oid+' 1\tx.txt\n100644 '+oid+' 2\tx.txt\n').encode())
            r=scan_index(root);self.assertEqual(r['scanned'],0);self.assertEqual(len(r['blocked']),2)
if __name__=='__main__':unittest.main()
