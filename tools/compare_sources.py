"""Conservative driver crosswalk and race comparison; no automatic ID migration."""
import argparse
import unicodedata
from collections import defaultdict
from validate_data import read,validate
from import_f1db import write_new

def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFKD',s.casefold()) if c.isalnum())

def key(r):
    return (norm((r.get('givenName') or '')+' '+(r.get('familyName') or '')),r.get('birthDate'))

def compare(primary, secondary):
    for d in (primary,secondary):
        if validate(d): raise ValueError('invalid input dataset')
    indices=[]
    for d in (primary,secondary):
        idx=defaultdict(list)
        for r in d['drivers']:
            k=key(r)
            if r.get('givenName') and r.get('familyName') and k[0] and k[1]: idx[k].append(r['id'])
        indices.append(idx)
    a,b=indices; mapping={ids[0]:a[k][0] for k,ids in b.items() if len(ids)==1 and len(a.get(k,[]))==1}
    ea={e['id']:e for e in primary['events']}; eb={e['id']:e for e in secondary['events']}; differences=[]; compared=0; unmatched=[]; team_candidates=defaultdict(set); circuit_candidates=defaultdict(set)
    for eid in sorted(ea.keys()&eb.keys()):
        x,y=ea[eid],eb[eid]
        if not x['date'] or x['date']!=y['date'] or norm(x['name'])!=norm(y['name']):
            differences.append({'event':eid,'field':'event identity','primary':x['name'],'secondary':y['name']});continue
        if x['circuitId'] and y['circuitId']: circuit_candidates[y['circuitId']].add(x['circuitId'])
        ss={s['kind']:s for s in x['sessions']}
        for s in y['sessions']:
            if s['kind'] not in ss or not s['results'] or not ss[s['kind']]['results']:continue
            rr={r['driverId']:r for r in ss[s['kind']]['results']}; seen=set()
            for r in s['results']:
                did=mapping.get(r['driverId']); z=rr.get(did)
                if not z: unmatched.append({'session':s['id'],'secondaryDriver':r['driverId']});continue
                seen.add(did);compared+=1;team_candidates[r['constructorId']].add(z['constructorId'])
                for f in ('position','points','qualifyingTimesMs','timeMs'):
                    if z[f]!=r[f]:differences.append({'session':s['id'],'driver':did,'field':f,'primary':z[f],'secondary':r[f]})
            for did in sorted(rr.keys()-seen):unmatched.append({'session':s['id'],'primaryDriver':did})
    return dict(driverCrosswalk=mapping,unmappedSecondaryDrivers=sorted(r['id'] for r in secondary['drivers'] if r['id'] not in mapping),comparedRows=compared,differences=differences,unmatchedRows=unmatched,constructorCandidates={k:sorted(v) for k,v in team_candidates.items()},circuitCandidates={k:sorted(v) for k,v in circuit_candidates.items()},scope='candidate crosswalk only; team/circuit candidates not approved aliases; absent sessions not compared')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('primary');p.add_argument('secondary');p.add_argument('--report',required=True);a=p.parse_args()
    try:
        r=compare(read(a.primary),read(a.secondary));write_new(a.report,r);print(f"{len(r['driverCrosswalk'])} driver matches; {r['comparedRows']} session rows compared; {len(r['differences'])} field differences; {len(r['unmatchedRows'])} unmatched rows");return 0
    except (OSError,ValueError,KeyError) as e:print('COMPARE FAILED:',e);return 1
if __name__=='__main__':raise SystemExit(main())
