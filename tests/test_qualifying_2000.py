import copy
import hashlib
import sys
import unittest
from datetime import date
from html import escape
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from import_qualifying_2000 import parse,recover,url_for,TEAMS
from review_2000 import review, REF
from validate_data import read,validate

# Synthetic HTML, using real candidate's IDs and reference pole only. Never published as historical results.
def fixture(e, drivers, expected):
    byid={d['id']:d['name'] for d in drivers}; teams={v:k for k,v in TEAMS.items()}
    rows=next(s['results'] for s in e['sessions'] if s['kind']=='race')
    rows=sorted(rows,key=lambda r:(r['driverId']!=expected['poleDriverId'],r['driverId']))
    parts=['<h1>2000 - QUALIFYING</h1>',f'<p>{date.fromisoformat(e["date"]).strftime("%d %b %Y")}</p>','<table><thead><tr>'+''.join(f'<th>{c}</th>' for c in ['Pos.','No.','Driver','Team','Time','Laps'])+'</tr></thead><tbody>']
    for i,r in enumerate(rows,1):
        ms=expected['poleTimeMs']+(i-1)*200
        text=f'{ms//60000}:{ms//1000%60:02d}.{ms%1000:03d}'
        cells=[str(i),str(i+1),byid[r['driverId']]+' ABC',teams[r['constructorId'].split(':')[1]],text,'10']
        parts.append('<tr>'+''.join('<td>'+escape(c)+'</td>' for c in cells)+'</tr>')
    return (''.join(parts)+'</tbody></table>').encode()

@unittest.skipUnless((ROOT/'private/candidate-2000.json').exists(),'Real candidate not available')
class Tests(unittest.TestCase):
    def setUp(self):
        self.ref=read(REF); self.data,_=review(read(ROOT/'private/candidate-2000.json'),self.ref); self.events={e['round']:e for e in self.data['events']}; self.exp={e['round']:e for e in self.ref['races']}
    def raw(self,r): return fixture(self.events[r],self.data['drivers'],self.exp[r])
    def parse(self,r,raw=None): return parse(self.raw(r) if raw is None else raw,self.events[r],self.data['drivers'],self.exp[r])
    def test_europe_21(self): self.assertEqual(len(self.parse(6)),21)
    def test_distinct_schumachers(self): self.assertEqual(len([r for r in self.parse(2) if 'schumacher' in r['driverId']]),2)
    def test_reject_wrong_date(self):
        with self.assertRaisesRegex(ValueError,'date mismatch'): self.parse(2,self.raw(2).replace(b'26 Mar 2000',b'25 Mar 2000'))
    def test_reject_surname_only(self):
        with self.assertRaisesRegex(ValueError,'driver name'): self.parse(2,self.raw(2).replace(b'Michael Schumacher ABC',b'Schumacher ABC'))
    def test_reject_wrong_team(self):
        with self.assertRaisesRegex(ValueError,'team mismatch'): self.parse(2,self.raw(2).replace(b'McLaren Mercedes',b'Ferrari',1))
    def test_reject_wrong_pole(self):
        with self.assertRaisesRegex(ValueError,'Pole/time'): self.parse(2,self.raw(2).replace(b'1:14.111',b'1:14.110',1))
    def test_recover_without_changing_races_standings(self):
        initial=copy.deepcopy(self.data)
        def load(r):
            raw=self.raw(r); digest=hashlib.sha256(raw).hexdigest()
            return raw,{'id':f'fixture:r{r}','provider':'synthetic test fixture','url':url_for(r),'retrievedAt':'2026-11-26T00:00:00Z','sha256':digest,'revision':None}
        out,report=recover(self.data,self.ref,load)
        self.assertEqual(initial,self.data); self.assertEqual(out['standings'],initial['standings']); self.assertEqual(out['adjustments'],initial['adjustments'])
        self.assertEqual([s for e in out['events'] for s in e['sessions'] if s['kind']=='race'],[s for e in initial['events'] for s in e['sessions'] if s['kind']=='race'])
        self.assertEqual(report['addedRows'],285); self.assertEqual(report['totalQualifyingRows'],373); self.assertEqual(len(report['addedRounds']),13)
        self.assertFalse(validate(out)); self.assertTrue(validate(out,release=True)); self.assertEqual(out['datasetStatus'],'draft')
        again,rep=recover(out,self.ref,lambda r: self.fail('unexpected fetch'))
        self.assertEqual(again,out); self.assertEqual(rep['addedRows'],0)
