"""Prepare a private F1DB draft. Never activate or publish."""
import argparse
import hashlib
from datetime import date
from pathlib import Path
from fetch_f1db import latest, release_asset, acquire
from import_f1db import import_archive, write_new
from reconcile_f1db import reconcile
from review_remaining import correct
from audit_championships import audit
from check_update import check_update
from validate_data import ROOT, read, validate


def differences(old, new):
    a={e['id']:e for e in old['events']}; b={e['id']:e for e in new['events']}
    sa={s['id']:s for e in a.values() for s in e['sessions']}
    sb={s['id']:s for e in b.values() for s in e['sessions']}
    ka={(v['season'],v['afterRound'],v['kind']):v['rows'] for v in old.get('standings',[])}
    kb={(v['season'],v['afterRound'],v['kind']):v['rows'] for v in new.get('standings',[])}
    return dict(changedStandings=[list(k) for k in sorted(ka.keys()&kb.keys()) if ka[k]!=kb[k]],
                newStandings=[list(k) for k in sorted(kb.keys()-ka.keys())],
                newSeasons=sorted({e['season'] for e in b.values()}-{e['season'] for e in a.values()}),
                newEvents=sorted(b.keys()-a.keys()),
                newlyCompleted=sorted(k for k in a.keys()&b.keys() if a[k]['status']!='completed' and b[k]['status']=='completed'),
                changedDates=sorted(k for k in a.keys()&b.keys() if a[k]['date']!=b[k]['date']),
                changedResults=sorted(k for k in sa.keys()&sb.keys() if sa[k]['results']!=sb[k]['results']),
                newFinalSessions=sorted(k for k in sb if sb[k]['status']=='final' and (k not in sa or sa[k]['status']!='final')))


def user_payload(store, old, new):
    if store is None:return None
    if not isinstance(store,dict):raise ValueError('invalid user file')
    if 'version' not in store:return store
    if store.get('version')!=1 or not isinstance(store.get('user'),dict) or not isinstance(store.get('bindings'),dict):
        raise ValueError('invalid browser export')
    user=store['user']; bindings=store['bindings']
    if validate(old,user) or validate(new,user):raise ValueError('user backup fails validation')
    if user['overrides'] or set(bindings)!={p['sessionId'] for p in user['predictions']}:
        raise ValueError('invalid browser backup bindings')
    stable=set()
    for p in user['predictions']:
        sid=p['sessionId']; binding=bindings[sid]
        if not isinstance(binding,dict) or binding.get('kind')!='race' or not isinstance(binding.get('externalEventId'),str) or not binding['externalEventId']:
            raise ValueError('invalid prediction binding')
        if binding['externalEventId'] in stable:raise ValueError('duplicate stable prediction binding')
        stable.add(binding['externalEventId'])
        for data in (old,new):
            matches=[e for e in data['events'] if any(s['id']==sid and s['kind']=='race' for s in e['sessions'])]
            if len(matches)!=1 or matches[0].get('externalEventId')!=binding['externalEventId'] or matches[0]['season']!=binding.get('season'):
                raise ValueError('prediction binding mismatch: '+sid)
    return user


def prepare(baseline, output, cache, *, timeout=30, release_json=None, local_archive=None, user=None, as_of=None):
    output=Path(output).resolve(); private=(ROOT/'private').resolve()
    if private not in output.parents:raise ValueError('output must be a new directory under project private/')
    if bool(release_json)!=bool(local_archive):raise ValueError('offline mode requires both metadata and local archive')
    output.mkdir(parents=True,exist_ok=False)
    report=dict(status='blocked',publicationAuthorized=False,activated=False,stage='baseline',mode='offline' if release_json else 'live',userCheck='not supplied')
    try:
        old=read(baseline)
        if validate(old) or not old['events'] or not any(s['provider']=='F1DB' for s in old['sources']):
            raise ValueError('nonempty structurally valid F1DB baseline required')
        report['baselineSha256']=hashlib.sha256(Path(baseline).read_bytes()).hexdigest()
        report['stage']='fetch'
        asset=release_asset(read(release_json)) if release_json else latest(timeout)
        archive,state=acquire(asset,cache,timeout,local_archive)
        report['release']=dict(asset,result=state)
        print('RELEASE',asset['tag'],state,flush=True)
        report['stage']='import'
        raw,imported=import_archive(archive,from_season=min(e['season'] for e in old['events']),as_of=as_of,revision=asset['tag'])
        if imported['archiveSha256']!=asset['sha256']:raise ValueError('archive changed between verification and import')
        write_new(output/'import-report.json',imported)
        report['stage']='historical reconciliation'
        candidate,historical=reconcile(raw); candidate,corrections=correct(candidate)
        write_new(output/'historical-report.json',dict(historical,additionalChanges=corrections))
        report['stage']='compatibility'
        payload=user_payload(read(user) if user else None,old,candidate)
        errors=check_update(old,candidate,payload)
        if errors:
            report['compatibilityErrors']=errors
            raise ValueError('update compatibility failed')
        report['userCheck']='passed (supplied file only)' if user else 'not supplied (browser storage not accessed)'
        report['changes']=differences(old,candidate)
        report['stage']='audit'
        result=audit(candidate);write_new(output/'audit-report.json',result)
        report['audit']=dict(issues=len(result['issues']),countbackCandidates=len(result['countbackReviewCandidates']),knownPointExceptions=len(result['knownPointExceptions']),totals=result['totals'])
        if result['issues']:raise ValueError('internal audit requires review; no candidate exported')
        report['stage']='write draft'
        if candidate['datasetStatus']!='draft':raise ValueError('draft required')
        write_new(output/'candidate.json',candidate)
        report.update(status='draft_ready',stage='complete',independentVerification='pending',candidateSha256=hashlib.sha256((output/'candidate.json').read_bytes()).hexdigest())
    except Exception as exc:
        report['status']='blocked';report['error']=str(exc)
        write_new(output/'update-report.json',report)
        raise
    write_new(output/'update-report.json',report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',required=True);p.add_argument('--output',required=True)
    p.add_argument('--cache-dir',default='private/f1db/releases');p.add_argument('--timeout',type=int,default=30)
    p.add_argument('--release-json');p.add_argument('--local-archive');p.add_argument('--user')
    p.add_argument('--as-of',type=date.fromisoformat,help='Offline replay date')
    a=p.parse_args()
    if not 1<=a.timeout<=300:p.error('--timeout must be 1..300')
    if a.as_of and not a.release_json:p.error('--as-of requires offline metadata')
    try:
        r=prepare(a.baseline,a.output,a.cache_dir,timeout=a.timeout,release_json=a.release_json,local_archive=a.local_archive,user=a.user,as_of=a.as_of)
        print('DRAFT READY; new seasons:',r['changes']['newSeasons'],'; newly completed:',len(r['changes']['newlyCompleted']))
        print('AUDIT:',r['audit']['issues'],'issues;',r['audit']['countbackCandidates'],'countback candidates')
        print('NO ACTIVATION OR PUBLICATION AUTHORIZED');return 0
    except KeyboardInterrupt:
        print('UPDATE CANCELLED; no activation');return 130
    except Exception as exc:
        print('UPDATE BLOCKED:',exc);return 1

if __name__=='__main__':raise SystemExit(main())
