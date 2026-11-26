"""Offline schema and cross-reference validation. No data is ever modified."""
import argparse
import hashlib
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    def unique(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise ValueError(f'duplicate JSON key: {k}')
            out[k] = v
        return out
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError(f'invalid number: {v}')))

def schema_errors(data, name):
    schema = read(ROOT / 'schemas' / f'{name}.schema.json')
    Draft202012Validator.check_schema(schema)
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(data)]

def validate(data, user=None, release=False):
    errors = schema_errors(data, 'official')
    if errors:
        return errors
    def check(ok, msg):
        if not ok: errors.append(msg)
    def index(items, key, label):
        result = {}
        for row in items:
            k = key(row)
            check(k not in result, f'{label}: duplicate {k}')
            result[k] = row
        return result
    sources = index(data['sources'], lambda x:x['id'], 'source')
    drivers = index(data['drivers'], lambda x:x['id'], 'driver')
    teams = index(data['constructors'], lambda x:x['id'], 'constructor')
    circuits = index(data['circuits'], lambda x:x['id'], 'circuit')
    events = index(data['events'], lambda x:x['id'], 'event')
    sessions = {}
    participants = {}
    def provenance(row, label):
        for sid in row['sourceIds']:
            check(sid in sources, f'{label}: unknown source {sid}')
    for registry, label in [(drivers,'driver'),(teams,'constructor'),(circuits,'circuit')]:
        aliases = {}
        for k, row in registry.items():
            provenance(row,k)
            for a in row['aliases']:
                key = (a['provider'], a['externalId'])
                check(key not in aliases, f'{label}: duplicate alias {key}')
                aliases[key] = k
    for eid, event in events.items():
        check(eid == f"{event['season']}-R{event['round']:02d}", f'{eid}: season/round mismatch')
        check(event['circuitId'] is None or event['circuitId'] in circuits, f'{eid}: unknown circuit')
        provenance(event,eid)
        kinds = set()
        for s in event['sessions']:
            sid=s['id']; kind=s['kind']
            check(kind not in kinds, f'{eid}: duplicate session kind {kind}'); kinds.add(kind)
            check(sid == f'{eid}-{kind}', f'{sid}: wrong session ID')
            check(sid not in sessions, f'duplicate session ID {sid}'); sessions[sid]=s
            provenance(s,sid)
            if s['status'] in ('scheduled','cancelled','pending_results','unavailable'):
                check(not s['results'], f'{sid}: unexpected results for {s["status"]}')
            if s['status'] in ('final','provisional','partial'):
                check(bool(s['results']) and bool(s['sourceIds']), f'{sid}: missing results or provenance')
            seen=set(); positions=set()
            for r in s['results']:
                did=r['driverId']; p=r['position']; label=f'{sid}/{did}'
                check(did in drivers, f'{label}: unknown driver')
                check(r['constructorId'] in teams, f'{label}: unknown constructor')
                check(did not in seen, f'{label}: duplicate driver'); seen.add(did)
                if p is not None and r['classified'] is True:
                    check(p not in positions, f'{sid}: duplicate classified position {p}'); positions.add(p)
                if kind in ('race','sprint') and s['status']=='final':
                    check(r['points'] is not None, f'{label}: missing official points')
                if kind not in ('race','sprint'):
                    check(r['points'] is None, f'{label}: unexpected championship points')
                if r['status']=='dns': check(r['started'] is not True, f'{label}: DNS marked started')
            participants[sid]=seen
        if event['status']=='completed':
            check('race' in kinds, f'{eid}: completed event without race session')
    for row in data['standings']:
        label=f"standings {row['season']}/{row['afterRound']}/{row['kind']}"
        provenance(row,label)
        check(f"{row['season']}-R{row['afterRound']:02d}" in events, f'{label}: unknown round')
        registry=drivers if row['kind']=='drivers' else teams
        index(row['rows'],lambda x:x['entityId'],label)
        for r in row['rows']: check(r['entityId'] in registry,f'{label}: unknown entity {r["entityId"]}')
    index(data['standings'],lambda x:(x['season'],x['afterRound'],x['kind']),'standings snapshot')
    for row in data['adjustments']:
        label=f"adjustment {row['season']}/{row['entityId']}"; provenance(row,label)
        check(row['entityId'] in (drivers if row['kind']=='driver' else teams),f'{label}: unknown entity')
        check(any(e['season']==row['season'] for e in events.values()),f'{label}: unknown season')
        if row['afterRound'] is not None: check(f"{row['season']}-R{row['afterRound']:02d}" in events,f'{label}: unknown round')
    index(data['fastestLaps'],lambda x:x['sessionId'],'fastest lap')
    index(data['stints'],lambda x:(x['sessionId'],x['driverId'],x['number']),'stint')
    stints={}
    for key in ('fastestLaps','stints'):
        for row in data[key]:
            sid=row['sessionId']; did=row['driverId']; label=f'{key}/{sid}/{did}'
            provenance(row,label)
            check(sid in sessions, f'{label}: unknown session')
            check(did in participants.get(sid,set()),f'{label}: driver absent from session')
            if key=='stints':
                check(row['lapFrom']<=row['lapTo'],f'{label}: reversed lap range')
                stints.setdefault((sid,did),[]).append(row)
    for key, rows in stints.items():
        rows.sort(key=lambda x:x['lapFrom'])
        for a,b in zip(rows,rows[1:]): check(a['lapTo']<b['lapFrom'],f'{key}: overlapping stints')
    if user is not None:
        ue=schema_errors(user,'user'); errors.extend(ue)
        if not ue:
            index(user['predictions'],lambda x:x['sessionId'],'prediction')
            index(user['overrides'],lambda x:(x['sessionId'],x['driverId']),'override')
            for p in user['predictions']:
                check(p['sessionId'] in sessions,f'prediction: unknown session {p["sessionId"]}')
                for did in p['driverIds']: check(did in drivers,f'prediction: unknown driver {did}')
            for p in user['overrides']:
                check(p['driverId'] in participants.get(p['sessionId'],set()),'override: unknown session participant')
    if release:
        check(data['datasetStatus']=='verified','release requires verified dataset status')
        check(bool(events) and bool(drivers) and bool(teams),'release requires nonempty data')
        check(all(s['provider']!='synthetic test fixture' for s in sources.values()),'release contains synthetic data')
    return errors

def verify_backup():
    errors=[]
    for line in (ROOT/'legacy/SHA256SUMS.txt').read_text().splitlines():
        expected, name=line.split('  ',1)
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected: errors.append(f'checksum mismatch: {name}')
    return errors

def main():
    p=argparse.ArgumentParser(); p.add_argument('data',nargs='?'); p.add_argument('--user'); p.add_argument('--release',action='store_true'); p.add_argument('--backup',action='store_true'); a=p.parse_args()
    try:
        if not a.data and not a.backup: p.error('provide a dataset or --backup')
        errors=verify_backup() if a.backup else []
        if a.data: errors+=validate(read(a.data),read(a.user) if a.user else None,a.release)
    except (OSError, ValueError) as e: errors=[str(e)]
    for e in errors: print('ERROR:',e)
    print(f'FAIL ({len(errors)} errors)' if errors else 'PASS (structural checks only)')
    return int(bool(errors))
if __name__=='__main__': raise SystemExit(main())
