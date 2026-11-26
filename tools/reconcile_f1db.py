"""F1-003: explicit historical reconciliation, always produces a draft."""
import argparse
from copy import deepcopy
from pathlib import Path
from validate_data import read, validate
from import_f1db import write_new

REFERENCES={
 'drivers2000':('Formula1.com','https://www.formula1.com/en/results/2000/drivers'),
 'teams2000':('Formula1.com','https://www.formula1.com/en/results/2000/team'),
 'gasly2017':('FIA','https://www.fia.com/news/f1-vettel-takes-crucial-pole-mexico-ahead-verstappen-and-hamilton'),
 'entry2018':('FIA','https://api.fia.com/news/fia-approves-mid-season-entry-racing-point-force-india'),
 'teams2018':('FIA','https://www.fia.com/events/fia-formula-one-world-championship/season-2018/2018-classifications'),
}
OLD='entrant:2018-sahara-force-india'; NEW='entrant:2018-racing-point-force-india'; TEAM='f1db:force-india'

def reconcile(original):
    errors=validate(original)
    if errors: raise ValueError('invalid input: '+str(errors[:5]))
    if not any(s['provider']=='F1DB' for s in original['sources']): raise ValueError('F1DB input required')
    data=deepcopy(original); data['datasetStatus']='draft'; report={'changes':[],'checks':[],'status':'draft','scope':'targeted historical checks, not full independent verification'}
    events={e['id']:e for e in data['events']}; years={e['season'] for e in events.values()}
    def ref(key, row):
        sid='review:'+key; provider,url=REFERENCES[key]
        if not any(s['id']==sid for s in data['sources']):
            data['sources'].append(dict(id=sid,provider=provider,url=url,retrievedAt='2026-11-26T00:00:00+00:00',sha256=None,revision='manual reference review 2026-11-26 (date only)'))
        if sid not in row['sourceIds']: row['sourceIds'].append(sid)
        return sid
    def final(year,kind): return max((s for s in data['standings'] if s['season']==year and s['kind']==kind),key=lambda x:x['afterRound'])
    def lookup(rows,key,val):
        found=[r for r in rows if r[key]==val]
        if len(found)!=1: raise ValueError(f'expected unique {key} {val}, got {len(found)}')
        return found[0]
    def verify_points(year,kind,expected):
        snap=final(year,kind)
        for entity,points in expected.items():
            r=lookup(snap['rows'],'entityId','f1db:'+entity)
            if r['points']!=points: raise ValueError(f'{year} {entity}: unexpected points {r["points"]}')
        report['checks'].append(f'{year} {kind} control points matched')
        return snap
    if 2000 in years:
        s=verify_points(2000,'drivers',{'michael-schumacher':108,'ralf-schumacher':24})
        for k,old,new in [('pedro-diniz',18,17),('johnny-herbert',17,18),('gaston-mazzacane',21,20),('nick-heidfeld',20,21)]:
            r=lookup(s['rows'],'entityId','f1db:'+k)
            if r['points']!=0 or r['position'] not in (old,new): raise ValueError('unexpected 2000 standing '+k)
            if r['position']!=new: report['changes'].append({'case':'2000 standings','id':k,'before':r['position'],'after':new})
            r.update(position=new,positionText=str(new))
        s['rows'].sort(key=lambda r:(r['position'] is None,r['position'] or 0));ref('drivers2000',s)
        s=verify_points(2000,'constructors',{'mclaren':152,'ferrari':170,'williams':36});ref('teams2000',s)
        if any(a['season']==2000 and a['entityId']=='f1db:mclaren' and a['pointsDelta']==-10 for a in data['adjustments']): raise ValueError('McLaren deduction already included by F1DB; remove duplicate adjustment before review')
    if 2007 in years:
        verify_points(2007,'drivers',{'kimi-raikkonen':110,'lewis-hamilton':109,'fernando-alonso':109})
        m=lookup(final(2007,'constructors')['rows'],'entityId','f1db:mclaren')
        if (m['position'],m['positionText'],m['points'])!=(None,'E',0): raise ValueError('unexpected McLaren 2007 exclusion')
        report['checks'].append('2007 McLaren source exclusion preserved')
    if 2021 in years: verify_points(2021,'drivers',{'max-verstappen':395.5,'lewis-hamilton':387.5})
    if 2017 in years:
        q=lookup(events['2017-R18']['sessions'],'kind','qualifying'); g=lookup(q['results'],'driverId','f1db:pierre-gasly')
        if g['position'] is not None or g['qualifyingTimesMs'] or g['positionText']!='19': raise ValueError('2017 Gasly source changed: manual review required')
        if g['classified'] is not False: report['changes'].append({'case':'2017 Gasly','before':g['classified'],'after':False})
        g.update(classified=False,status='not_classified');ref('gasly2017',q)
    if 2018 in years:
        # FIA confirmed transition; not inferred from constructor name or CSV display order.
        for eid,name,start,end in [(OLD,'Sahara Force India F1 Team',1,12),(NEW,'Racing Point Force India F1 Team',13,21)]:
            en=dict(id=eid,name=name,constructorId=TEAM,season=2018,fromRound=start,toRound=end,sourceIds=[]);ref('entry2018',en)
            existing=[x for x in data.setdefault('entrants',[]) if x['id']==eid]
            if existing and existing[0]!=en: raise ValueError('entrant definition changed')
            if not existing: data['entrants'].append(en)
        for e in data['events']:
            if e['season']!=2018: continue
            entry=OLD if e['round']<=12 else NEW
            for s in e['sessions']:
                for r in s['results']:
                    if r['constructorId']==TEAM:
                        if r.get('entrantId',entry)!=entry: raise ValueError('conflicting entrant assignment')
                        r['entrantId']=entry;ref('entry2018',s)
        for s in data['standings']:
            if s['season']!=2018 or s['kind']!='constructors': continue
            for r in s['rows']:
                if r['entityId']==TEAM and r.get('entrantId')!=OLD:
                    r['entrantId']=OLD if s['afterRound']<=12 else NEW;ref('entry2018',s)
        s=final(2018,'constructors'); active=lookup([r for r in s['rows'] if 'entrantId' in r],'entrantId',NEW)
        if (active['points'],active['position'])!=(52,7): raise ValueError('unexpected Force India final standings')
        old=[r for r in s['rows'] if r.get('entrantId')==OLD]
        excluded=dict(entityId=TEAM,entrantId=OLD,position=None,positionText='E',points=0,wins=None)
        if old and old!=[excluded]: raise ValueError('unexpected excluded entrant')
        if not old: s['rows'].append(excluded);report['changes'].append({'case':'2018 entrants','added':OLD,'retained':NEW})
        ref('teams2018',s)
    errors=validate(data)
    if errors: raise ValueError('invalid output: '+str(errors[:10]))
    report['structuralValidation']='pass';return data,report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input');p.add_argument('--output',required=True);p.add_argument('--report',required=True);a=p.parse_args()
    try:
        paths=[Path(x).resolve() for x in (a.input,a.output,a.report)]
        if len(set(paths))!=3 or any(x.exists() for x in paths[1:]): raise ValueError('distinct new output/report paths required')
        data,report=reconcile(read(a.input));write_new(a.output,data);write_new(a.report,report)
        print('PASS targeted reconciliation;',len(report['changes']),'changes; DRAFT only');return 0
    except (OSError,ValueError,KeyError,StopIteration) as e: print('RECONCILIATION FAILED:',e);return 1
if __name__=='__main__': raise SystemExit(main())
