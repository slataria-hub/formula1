"""Offline F1DB CSV -> v2 draft. Does not fetch, publish or modify user data."""
import argparse
import csv
import hashlib
import io
import json
import os
import tempfile
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from validate_data import validate

BASE = 'https://github.com/f1db/f1db'
KNOWN = {'8c33f41f7e095e995634305a33b28bd8638366056f877109ffc290d06d341950':'v2026.21.0'}
SESSION_TABLES = {'race':'race-results','qualifying':'qualifying-results',
                  'sprint':'sprint-race-results','sprint_qualifying':'sprint-qualifying-results'}
DATE_FIELDS = {'race':'date','qualifying':'qualifyingDate','sprint':'sprintRaceDate',
               'sprint_qualifying':'sprintQualifyingDate'}

def integer(value):
    return int(value) if value not in ('', None) else None

def ident(value):
    if not value: raise ValueError('empty F1DB identifier')
    return 'f1db:'+value

def rows(z, table):
    with z.open('f1db-'+table+'.csv') as f:
        reader=csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig',newline=''))
        for r in reader:
            if None in r or None in r.values(): raise ValueError('malformed CSV: '+table)
            yield r

def unique_index(items, key):
    result={}
    for r in items:
        k=r[key]
        if k in result: raise ValueError('duplicate '+key+': '+k)
        result[k]=r
    return result

def normalize_result(r, kind):
    race=kind in ('race','sprint'); p=integer(r['positionNumber']); raw=r['positionText']; laps=integer(r.get('laps'))
    reason=r.get('reasonRetired',''); raw_status=raw+(': '+reason if reason else '')
    if p is not None:
        status='retired' if race and reason else 'finished'; classified=True; started=True if race else None
    else:
        status={'DNF':'retired','DNS':'dns','DNQ':'dns','DNP':'dns','DSQ':'dsq','EX':'excluded','NC':'not_classified'}.get(raw)
        if status is None: raise ValueError('unsupported result status: '+repr(raw))
        classified=False
        started=(False if status=='dns' else True if status=='retired' or (laps is not None and laps>0) else None) if race else None
    q=None
    if not race:
        ts=[integer(r.get('q'+str(i)+'Millis')) for i in (1,2,3)]
        if any(x is not None for x in ts): q=ts
        elif r.get('timeMillis'): q=[integer(r['timeMillis'])]
    return dict(driverId=ident(r['driverId']),constructorId=ident(r['constructorId']),position=p,
        positionText=raw or None,points=float(r['points'] or 0) if race else None,started=started,
        classified=classified,status=status,rawStatus=raw_status or None,laps=laps,
        gridPosition=integer(r.get('gridPositionNumber')),timeMs=integer(r.get('timeMillis')),
        gapMs=integer(r.get('gapMillis')),qualifyingTimesMs=q)

def standing_row(r, key, wins):
    p=integer(r['positionNumber']); text=r['positionText']
    if p is None:
        text={'EX':'E','DSQ':'D','-':'-'}.get(text)
        if text is None: raise ValueError('unsupported standing position: '+repr(r['positionText']))
    return dict(entityId=ident(r[key]),position=p,positionText=text,points=float(r['points']),wins=wins)

def import_archive(path, season=None, from_season=2000, to_season=None, as_of=None, revision=None):
    path=Path(path); digest=hashlib.sha256(path.read_bytes()).hexdigest(); revision=revision or KNOWN.get(digest)
    sid='f1db:archive-'+digest
    # Stable local observation timestamp for re-importing the same file. Not a release timestamp.
    observed=datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat()
    source=dict(id=sid,provider='F1DB',url=BASE+('/releases/tag/'+revision if revision else '/releases'),retrievedAt=observed,sha256=digest,revision=revision)
    as_of=as_of or datetime.now(timezone.utc).date()
    data=dict(schemaVersion='2.0.0',datasetStatus='draft',sources=[source],drivers=[],constructors=[],circuits=[],events=[],standings=[],adjustments=[],fastestLaps=[],stints=[])
    report=dict(archiveSha256=digest,revision=revision,asOf=as_of.isoformat(),warnings=[],seasons={})
    with zipfile.ZipFile(path) as z:
        bad=z.testzip()
        if bad: raise ValueError('CRC failed: '+bad)
        calendar=list(rows(z,'races')); years=sorted({int(r['year']) for r in calendar})
        low=season if season is not None else from_season; high=season if season is not None else (to_season if to_season is not None else max(years))
        if low<2000 or high<low: raise ValueError('supported range starts at 2000; earlier seasons require contract extension')
        selected=[y for y in years if low<=y<=high]
        if not selected or selected!=list(range(low,high+1)): raise ValueError('archive missing requested season(s)')
        report['availableSeasons']=years; report['selectedSeasons']=selected
        events=sorted((r for r in calendar if int(r['year']) in selected),key=lambda r:(int(r['year']),int(r['round'])))
        event_index=unique_index(events,'id')
        def selected_rows(table):
            for r in rows(z,table):
                if int(r['year']) not in selected: continue
                e=event_index.get(r['raceId'])
                if not e or (r['year'],r['round'])!=(e['year'],e['round']): raise ValueError('calendar mismatch: '+table+' '+str(r))
                yield r
        by_kind={}
        for kind,table in SESSION_TABLES.items():
            group=defaultdict(list)
            for r in selected_rows('races-'+table):
                if r.get('sharedCar')=='true': raise ValueError('shared-car results not supported')
                group[r['raceId']].append(r)
            by_kind[kind]=group
        gp=unique_index(rows(z,'grands-prix'),'id'); drivers=unique_index(rows(z,'drivers'),'id'); teams=unique_index(rows(z,'constructors'),'id'); circuits=unique_index(rows(z,'circuits'),'id'); countries=unique_index(rows(z,'countries'),'id')
        used_d=set(); used_t=set(); used_c=set(); won_d=Counter(); won_t=Counter(); snapshots=defaultdict(list)
        for kind in ('driver','constructor'):
            for r in selected_rows('races-'+kind+'-standings'): snapshots[(r['raceId'],kind)].append(r)
        fastest={}
        for r in selected_rows('races-fastest-laps'):
            if r['positionNumber']=='1':
                if r['raceId'] in fastest: raise ValueError('multiple fastest laps cannot be represented')
                fastest[r['raceId']]=r
        for e in events:
            year=int(e['year']); rnd=int(e['round']); rid=e['id']; eid=f'{year}-R{rnd:02d}'; day=date.fromisoformat(e['date']); completed=bool(by_kind['race'][rid]); in_progress=any(by_kind[k][rid] for k in SESSION_TABLES if k!='race')
            event_status='completed' if completed else 'in_progress' if in_progress else 'scheduled' if day>=as_of else 'unknown'
            event=dict(id=eid,season=year,round=rnd,name=gp[e['grandPrixId']]['fullName'],circuitId=ident(e['circuitId']),date=e['date'],status=event_status,sourceIds=[sid],sessions=[])
            used_c.add(e['circuitId']); stat=report['seasons'].setdefault(str(year),dict(events=0,completed=0,raceRows=0,qualifyingRows=0,sprintRows=0,sprintQualifyingRows=0,missingQualifyingRounds=[],pendingRaceRounds=[])); stat['events']+=1; stat['completed']+=completed
            for kind in SESSION_TABLES:
                rr=sorted(by_kind[kind][rid],key=lambda r:int(r['positionDisplayOrder']))
                if kind.startswith('sprint') and not rr and not e[DATE_FIELDS[kind]] and not (kind=='sprint_qualifying' and e['sprintQualifyingFormat']): continue
                session_day=date.fromisoformat(e[DATE_FIELDS[kind]]) if e[DATE_FIELDS[kind]] else day
                status='final' if rr else 'unavailable' if completed else 'scheduled' if session_day>=as_of else 'pending_results'
                norm=[normalize_result(r,kind) for r in rr]; session_id=eid+'-'+kind
                if kind in ('qualifying','sprint_qualifying'):
                    positions=Counter(r['position'] for r in norm if r['position'] is not None)
                    for pos,count in positions.items():
                        if count<2: continue
                        tied=[r for r in norm if r['position']==pos]
                        timed=[r for r in tied if r['qualifyingTimesMs']]
                        if len(timed)!=1: raise ValueError(f'{session_id}: ambiguous duplicate position {pos}')
                        for r in tied:
                            if r not in timed:
                                report['warnings'].append(f"{session_id}: {r['driverId']} shares source position {pos} without time; classification unresolved")
                                # Retain the published text, not a fabricated classified place.
                                r.update(position=None,classified=None,status='unknown')
                event['sessions'].append(dict(id=session_id,kind=kind,status=status,scheduledAt=None,sourceIds=[sid],results=norm))
                for r in rr: used_d.add(r['driverId']);used_t.add(r['constructorId'])
                stat[{'race':'raceRows','qualifying':'qualifyingRows','sprint':'sprintRows','sprint_qualifying':'sprintQualifyingRows'}[kind]]+=len(rr)
                if kind=='race':
                    if not rr: stat['pendingRaceRounds'].append(rnd)
                    for r in rr:
                        if r['positionNumber']=='1': won_d[year,r['driverId']]+=1; won_t[year,r['constructorId']]+=1
                if kind=='qualifying' and completed and not rr: stat['missingQualifyingRounds'].append(rnd)
            if rid in fastest:
                f=fastest[rid]; data['fastestLaps'].append(dict(sessionId=eid+'-race',driverId=ident(f['driverId']),lap=integer(f['lap']),timeMs=integer(f['timeMillis']),compound=None,sourceIds=[sid]))
            for kind,used,wins in [('driver',used_d,won_d),('constructor',used_t,won_t)]:
                rr=sorted(snapshots[rid,kind],key=lambda r:int(r['positionDisplayOrder'])); key=kind+'Id'
                if rr:
                    if not completed: raise ValueError('standings without race results: '+eid)
                    used.update(r[key] for r in rr)
                    data['standings'].append(dict(season=year,afterRound=rnd,kind=kind+'s',sourceIds=[sid],rows=[standing_row(r,key,wins[year,r[key]]) for r in rr]))
                elif completed: report['warnings'].append(f'{eid}: missing {kind} standings')
            data['events'].append(event)
        # Check season tables independently against the latest per-round snapshot.
        # Do not silently collapse distinct entrants sharing a constructor ID (e.g. 2018).
        for kind in ('driver','constructor'):
            key=kind+'Id'; groups=defaultdict(list)
            for r in rows(z,'seasons-'+kind+'-standings'):
                if int(r['year']) in selected: groups[int(r['year'])].append(r)
            for year,rr in groups.items():
                latest=max((s for s in data['standings'] if s['season']==year and s['kind']==kind+'s'),key=lambda s:s['afterRound'],default=None)
                if not latest:
                    report['warnings'].append(f'{year}: season {kind} standings without round snapshot');continue
                expected=[standing_row(r,key,None) for r in rr]; actual=[dict(r,wins=None) for r in latest['rows']]
                if Counter(tuple(sorted(r.items())) for r in expected)!=Counter(tuple(sorted(r.items())) for r in actual):
                    report['warnings'].append(f'{year}: season {kind} standings differ from latest round; retained round snapshot; requires reconciliation')
                    report.setdefault('standingConflicts',[]).append(dict(season=year,kind=kind+'s',latestRound=latest['afterRound'],seasonRows=expected,roundRows=actual))
        def base(r): return dict(id=ident(r['id']),name=r['name'],aliases=[dict(provider='F1DB',externalId=r['id'])],sourceIds=[sid])
        def country(cid,field): return countries[cid][field] if cid else None
        for k in sorted(used_d):
            r=drivers[k]; data['drivers'].append(dict(base(r),givenName=r['firstName'] or None,familyName=r['lastName'] or None,birthDate=r['dateOfBirth'] or None,nationality=country(r['nationalityCountryId'],'demonym')))
        for k in sorted(used_t):
            r=teams[k];data['constructors'].append(dict(base(r),nationality=country(r['countryId'],'demonym'),lineageId=None))
        for k in sorted(used_c):
            r=circuits[k];data['circuits'].append(dict(base(r),name=r['fullName'],country=country(r['countryId'],'name'),locality=r['placeName'] or None))
    errors=validate(data)
    if errors: raise ValueError('validation failed:\n'+'\n'.join(errors[:30]))
    report['status']='draft';report['structuralValidation']='pass';report['scope']='F1DB only; independent verification pending';report['pointsPolicy']='Blank awarded race/sprint points treated as zero; standings taken directly from archive; no deductions reapplied.'
    return data,report

def write_new(path, obj):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists(): raise FileExistsError('refusing to overwrite '+str(path))
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.'+path.name,suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as f:
            json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False); f.write('\n');f.flush();os.fsync(f.fileno())
        # Hard link atomically creates a new destination without replacing an existing file (NTFS supported).
        os.link(tmp,path)
    finally:
        Path(tmp).unlink(missing_ok=True)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',required=True);p.add_argument('--season',type=int);p.add_argument('--from-season',type=int,default=2000);p.add_argument('--to-season',type=int);p.add_argument('--as-of',type=date.fromisoformat);p.add_argument('--revision');p.add_argument('--output',required=True);p.add_argument('--report');a=p.parse_args()
    try:
        if a.season is not None and (a.from_season!=2000 or a.to_season is not None): raise ValueError('use --season or a range, not both')
        paths=[Path(x).resolve() for x in (a.archive,a.output,a.report) if x]
        if len(paths)!=len(set(paths)): raise ValueError('archive, output and report must be distinct')
        for x in (a.output,a.report):
            if x and Path(x).exists(): raise FileExistsError('refusing to overwrite '+x)
        data,report=import_archive(a.archive,a.season,a.from_season,a.to_season,a.as_of,a.revision)
        write_new(a.output,data)
        if a.report: write_new(a.report,report)
        for year,s in report['seasons'].items(): print(f"{year}: {s['events']} events, {s['completed']} completed, {s['raceRows']} race rows, {s['qualifyingRows']} qualifying rows, {s['sprintRows']} sprint rows")
        for w in report['warnings']: print('WARNING:',w)
        print('DRAFT:',a.output,'PASS structural validation; independent verification pending.')
        return 0
    except (OSError,ValueError,KeyError,zipfile.BadZipFile) as e:
        print('F1DB IMPORT FAILED:',e);return 1
    except KeyboardInterrupt:
        print('F1DB IMPORT CANCELLED');return 130

if __name__=='__main__': raise SystemExit(main())
