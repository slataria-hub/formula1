"""Offline, season-specific reconciliation. Preserve raw input and never publish as verified."""
import argparse
from collections import Counter
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from validate_data import read, validate
from import_data import dump

ROOT=Path(__file__).resolve().parents[1]
REF=ROOT/'references/season-2000.json'

def require(ok, message):
    if not ok: raise ValueError(message)

def dec(v): return Decimal(str(v))

def review(data, ref):
    """Fail closed on unexpected discrepancies; leave unknown results missing."""
    errors=validate(data)
    require(not errors, 'Invalid input: '+ '; '.join(errors[:5]))
    require(data['datasetStatus']=='draft','Only draft candidates are supported')
    out=deepcopy(data)
    events={e['round']:e for e in out['events']}
    require(len(events)==len(out['events'])==17 and set(events)==set(range(1,18)) and all(e['season']==2000 for e in events.values()),'Expected exactly season 2000 and 17 events')
    ids=ref['sourceIds']; adj=ref['adjustment']; mc=adj['entityId']
    existing=out['adjustments']
    require(not existing or existing==[adj], 'Unknown or duplicate championship adjustments; manual review required')
    source_by_id={s['id']:s for s in out['sources']}
    ds=Counter(); cs=Counter(); wins=Counter(); team_wins=Counter(); missing=[]; race_rows=q_rows=0
    for expected in ref['races']:
        rnd=expected['round']; e=events[rnd]
        require(e['date']==expected['date'],f'Round {rnd}: date differs')
        sessions={s['kind']:s for s in e['sessions']}
        race=sessions.get('race'); require(race and race['status']=='final',f'Round {rnd}: missing final race')
        rows=race['results']; race_rows+=len(rows)
        require(len(rows)==(21 if rnd==6 else 22),f'Round {rnd}: unexpected number of result entries')
        winners=[r for r in rows if r['position']==1 and r['classified'] is True]
        require(len(winners)==1 and all(winners[0][k]==expected[k] for k in ('driverId','laps','timeMs')),f'Round {rnd}: winner/laps/time differs')
        wins[winners[0]['driverId']]+=1; team_wins[winners[0]['constructorId']]+=1
        require(sum((dec(r['points']) for r in rows),Decimal(0))==26,f'Round {rnd}: unexpected race point total')
        for r in rows:
            ds[r['driverId']]+=dec(r['points']); cs[r['constructorId']]+=dec(r['points'])
        q=sessions.get('qualifying')
        if q and q['results']:
            q_rows+=len(q['results']); poles=[r for r in q['results'] if r['position']==1]
            require(len(q['results'])==(21 if rnd==6 else 22) and len(poles)==1 and poles[0]['driverId']==expected['poleDriverId'] and poles[0]['qualifyingTimesMs'][0]==expected['poleTimeMs'],f'Round {rnd}: qualifying count/pole differs')
        else:
            missing.append(rnd)
            if q is None:
                # An attempted query is recorded in the uploaded candidate; do not invent results.
                attempts=[s['id'] for s in out['sources'] if urlsplit(s['url']).path==f'/ergast/f1/2000/{rnd}/qualifying/' and parse_qs(urlsplit(s['url']).query).get('offset')==['0']]
                require(bool(attempts),f'Round {rnd}: no qualification request provenance')
                e['sessions'].append({'id':e['id']+'-qualifying','kind':'qualifying','status':'unavailable','scheduledAt':None,'sourceIds':attempts,'results':[]})
            else: require(q['status']=='unavailable',f'Round {rnd}: unexpected empty qualification status')
    require(len(out['standings'])==2,'Expected two final standings snapshots')
    standings={s['kind']:s for s in out['standings']}
    require(set(standings)=={'drivers','constructors'} and all(s['season']==2000 and s['afterRound']==17 for s in standings.values()),'Wrong standings scope')
    for kind, totals, victories in [('drivers',ds,wins),('constructors',cs,team_wins)]:
        st=standings[kind]; actual={r['entityId']:r for r in st['rows']}; expected={r['entityId']:r for r in ref[kind]}
        absent=set(ref['unlistedConstructors']) if kind=='constructors' else set()
        require(set(actual)==set(expected)|absent and set(totals)==set(actual),f'{kind}: different participant set')
        for ident,row in actual.items():
            if ident in absent:
                require(dec(row['points'])==totals[ident]==0 and row['position'] is None and row.get('positionText')=='-',f'{ident}: unexpected unlisted constructor values'); continue
            official=expected[ident]; target=dec(official['points']); raw_total=totals[ident]
            require(row['wins']==victories[ident],f'{ident}: victory count mismatch')
            if kind=='constructors' and ident==mc:
                require(raw_total+dec(adj['pointsDelta'])==target,f'{ident}: unexpected raw total')
                require(dec(row['points']) in (raw_total,target),f'{ident}: unexpected standings points')
                row['points']=official['points']
            else: require(dec(row['points'])==raw_total==target,f'{ident}: unexpected points mismatch')
            if row['position']!=official['position']:
                require(kind=='drivers' and row['position'] is None and row.get('positionText')=='-' and target==0,f'{ident}: unexpected standings position')
                row['position']=official['position']; row['positionText']=str(official['position'])
        if ids[kind] not in st['sourceIds']: st['sourceIds'].append(ids[kind])
        st['rows'].sort(key=lambda r:(r['position'] is None,r['position'] or 0,r['entityId']))
    if not existing: out['adjustments'].append(deepcopy(adj))
    for s in ref['sources']:
        if s['id'] not in source_by_id: out['sources'].append(deepcopy(s))
        else: require(source_by_id[s['id']]==s,'Conflicting reference source ID')
    errors=validate(out); require(not errors,'Invalid output: '+'; '.join(errors[:5]))
    summary={'season':2000,'datasetStatus':'draft','events':17,'raceRows':race_rows,'qualificationRows':q_rows,'missingQualificationRounds':missing,'drivers':len(ds),'constructors':len(cs),'driverPoints':int(sum(ds.values())),'constructorPointsBeforeAdjustment':int(sum(cs.values())),'constructorPointsAfterAdjustment':int(sum(cs.values())+dec(adj['pointsDelta'])),'mclarenOfficialPoints':152,'checks':['17 winners, winner times and lap counts','23 driver totals and positions','9 published constructor totals and positions','2 unlisted zero-point constructors preserved','available qualifying counts and pole results'],'limits':['Not a row-by-row independent verification of all classifications.','Any missing qualifying results are listed separately.','No original raw API bodies supplied for checksum re-verification.','No verified dataset or production release is created.']}
    return out,summary

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('input',type=Path); p.add_argument('--output',type=Path,required=True); p.add_argument('--report',type=Path,required=True); a=p.parse_args()
    paths={a.input.resolve(),a.output.resolve(),a.report.resolve()}
    if len(paths)!=3 or a.output.exists() or a.report.exists(): p.error('Use distinct new output and report paths; no overwrite')
    try:
        out,summary=review(read(a.input),read(REF)); dump(a.output,out,exclusive=True); dump(a.report,summary,exclusive=True)
        print(f'PASS 2000 reconciliation: {summary["raceRows"]} race entries; {summary["qualificationRows"]} qualifying entries; McLaren 152 points.')
        print('MISSING QUALIFYING ROUNDS:',','.join(map(str,summary['missingQualificationRounds'])))
        print('DRAFT only: independent row-by-row verification pending.')
        return 0
    except (OSError,ValueError,KeyError,TypeError) as e: print('REVIEW FAILED:',e); return 1
if __name__=='__main__': raise SystemExit(main())
