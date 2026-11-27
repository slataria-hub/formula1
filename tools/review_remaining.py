"""Targeted historical corrections and status crosswalk; never authorizes publication."""
import argparse
from collections import Counter
from copy import deepcopy
from pathlib import Path
from validate_data import read, validate
from import_f1db import write_new
from compare_sources import compare
from classify_crosswalk import classify

RULES=[(2021,10,'nicholas-latifi','nikita-mazepin',19,20,0,'FIA','https://www.fia.com/sites/default/files/decision-document/2021%20British%20Grand%20Prix%20-%20Championship%20Points.pdf'),(2022,6,'daniel-ricciardo','yuki-tsunoda',11,12,11,'RaceFans','https://www.racefans.net/2022/05/22/2022-spanish-grand-prix-championship-points/')]

def correct(data):
    if validate(data): raise ValueError('invalid input')
    if not any(s['provider']=='F1DB' for s in data['sources']): raise ValueError('F1DB input required')
    out=deepcopy(data);out['datasetStatus']='draft';changes=[]
    for y,r,a,b,p,q,pts,provider,url in RULES:
        if not any(e['season']==y and e['round']==r for e in out['events']):continue
        s=next((s for s in out['standings'] if (s['season'],s['afterRound'],s['kind'])==(y,r,'drivers')),None)
        if s is None:raise ValueError('missing snapshot')
        rows={v['entityId']:v for v in s['rows']};x,z=rows['f1db:'+a],rows['f1db:'+b];before=(x['position'],z['position'])
        if x['points']!=pts or z['points']!=pts or before not in ((p,q),(q,p)):raise ValueError(f'changed historical evidence {y}/{r}')
        if before==(q,p):
            x.update(position=p,positionText=str(p));z.update(position=q,positionText=str(q));changes.append(dict(season=y,round=r,drivers=[a,b],before=list(before),after=[p,q],reference=url))
        sid=f'review:countback-{y}-{r}';source=dict(id=sid,provider=provider,url=url,retrievedAt='2026-11-26T00:00:00+00:00',sha256=None,revision='manual review 2026-11-26 (date only)')
        existing=next((v for v in out['sources'] if v['id']==sid),None)
        if existing is not None and existing!=source:raise ValueError('conflicting source')
        if existing is None:out['sources'].append(source)
        if sid not in s['sourceIds']:s['sourceIds'].append(sid)
        s['rows'].sort(key=lambda v:(v['position'] is None,v['position'] or 0))
    errors=validate(out)
    if errors:raise ValueError(str(errors[:5]))
    return out,changes

def status_review(primary,secondary):
    report=compare(primary,secondary)
    def index(data):return {(s['id'],v['driverId']):v for e in data['events'] for s in e['sessions'] for v in s['results']}
    a,b=index(primary),index(secondary);rev={v:k for k,v in report['driverCrosswalk'].items()};counts=Counter();details=[]
    for d in report['differences']:
        category=classify(d);extra={}
        if category=='classification_review':
            x,z=a[d['session'],d['driver']],b[d['session'],rev[d['driver']]]
            extra={k:{'primary':x[k],'secondary':z[k]} for k in ('status','classified','started','rawStatus')}
            if x['classified'] is False and z['classified'] is False:category='unclassified_position_representation' if x['status']==z['status'] else 'unclassified_status_review'
        counts[category]+=1;details.append(dict(d,category=category,**extra))
    pd={x['id']:x for x in primary['drivers']};sd={x['id']:x for x in secondary['drivers']}
    candidates=[dict(secondaryId=k,primaryId=v,primaryName=pd[v]['name'],secondaryName=sd[k]['name'],birthDate=pd[v]['birthDate'],approved=False) for k,v in sorted(report['driverCrosswalk'].items())]
    return dict(scope='comparison only; not official independent row verification',publicationAuthorized=False,categories=dict(counts),differences=details,unmatchedRows=report['unmatchedRows'],driverCandidates=candidates,constructorCandidates=report['constructorCandidates'],circuitCandidates=report['circuitCandidates'],comparedRows=report['comparedRows'])

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input');p.add_argument('--secondary',required=True);p.add_argument('--output',required=True);p.add_argument('--report',required=True);a=p.parse_args()
    try:
        paths=[Path(v).resolve() for v in (a.input,a.secondary,a.output,a.report)]
        if len(set(paths))!=4 or any(x.exists() for x in paths[2:]):raise ValueError('distinct new paths required')
        data,changes=correct(read(a.input));report=status_review(data,read(a.secondary));report['changes']=changes;report['remainingCountbackReview']=[dict(season=2012,round=6,reason='conflicting secondary sources; retain F1DB pending official evidence')]
        write_new(a.output,data);write_new(a.report,report)
        print(f'PASS targeted review; {len(changes)} ranking corrections; {len(report["driverCandidates"])} driver candidates; DRAFT only')
        for k,v in sorted(report['categories'].items()):print(f'{k}: {v}')
        return 0
    except (ValueError,OSError,KeyError) as e:print('REVIEW FAILED:',e);return 1
if __name__=='__main__':raise SystemExit(main())
