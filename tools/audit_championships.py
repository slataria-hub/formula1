"""F1-003.2: read-only championship arithmetic and coverage audit (not external certification)."""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from validate_data import read, validate
from import_f1db import write_new

ZERO = Decimal(0)
def dec(v): return Decimal(str(v))

# Evidence for discrepancies, NOT changes to awarded points or standings.
EXCEPTIONS = {
    (2000, 10, 'f1db:mclaren'): (-10, 'McLaren Austrian GP deduction', 'https://www.formula1.com/en/results/2000/team/McLaren-Mercedes'),
    (2018, 13, 'f1db:force-india'): (-59, 'Force India entry transition', 'https://api.fia.com/news/fia-approves-mid-season-entry-racing-point-force-india'),
    (2020, 5, 'f1db:racing-point'): (-15, 'Racing Point brake duct deduction', 'https://www.formula1.com/en/results/2020/team/Racing-Point-BWT-Mercedes'),
}
EXCLUSION_2007 = 'https://www.formula1.com/en/results/2007/team'

def known_delta(year, rnd, kind, entity, previous, earned, published, final_rows, excluded_entry):
    if kind != 'constructors': return None
    difference = published - previous - earned
    rule = EXCEPTIONS.get((year,rnd,entity))
    if rule and difference == dec(rule[0]):
        # Do not waive the reset if the entrant split has not been established.
        if year == 2018 and not (excluded_entry and previous == dec(59) and published == earned): return None
        return {'reason':rule[1], 'reference':rule[2]}
    if year == 2007 and entity == 'f1db:mclaren' and previous == published == ZERO and earned > ZERO:
        final = [x for x in final_rows if x['entityId']==entity]
        if len(final)==1 and final[0]['position'] is None and final[0].get('positionText')=='E' and final[0]['points']==0:
            return {'reason':'F1DB retrospective exclusion (not contemporaneous round standings)', 'reference':EXCLUSION_2007}
    return None

def audit(data):
    errors=validate(data)
    if errors: raise ValueError('structural validation failed: '+str(errors[:5]))
    groups=defaultdict(list)
    for e in data['events']: groups[e['season']].append(e)
    snapshots={(s['season'],s['afterRound'],s['kind']):s for s in data['standings']}
    fastest={f['sessionId']:f for f in data['fastestLaps']}
    issues=[]; exceptions=[]; seasons={}; tie_reviews=[]; shared_ranks=[]; missing_fastest=[]; totals=Counter()
    def issue(code,year,round=None,**extra):
        issues.append(dict(code=code,season=year,round=round,**extra))
    if not groups: issue('empty_dataset',None)
    if groups and sorted(groups)!=list(range(min(groups),max(groups)+1)):
        issue('missing_season',None,years=sorted(groups))
    for year,ee in sorted(groups.items()):
        ee.sort(key=lambda e:e['round']); rounds=[e['round'] for e in ee]
        if rounds!=list(range(1,max(rounds)+1)): issue('calendar_round_gap',year,rounds=rounds)
        prev={k:{} for k in ('drivers','constructors')}; wins={k:Counter() for k in prev}; finishes=defaultdict(Counter)
        previous_round={k:0 for k in prev}; intervening={k:Counter() for k in prev}; count=Counter(); last={}
        for kind in prev:
            last[kind]=max((s for s in data['standings'] if s['season']==year and s['kind']==kind),key=lambda s:s['afterRound'],default={'rows':[]})['rows']
        excluded_entry=any(r.get('entrantId')=='entrant:2018-sahara-force-india' and r['position'] is None and r.get('positionText')=='E' and r['points']==0 for r in last['constructors']) and any(r.get('entrantId')=='entrant:2018-racing-point-force-india' and r['points']==52 for r in last['constructors'])
        for e in ee:
            rnd=e['round']; count['events']+=1; ss={s['kind']:s for s in e['sessions']}; race=ss.get('race')
            if e['status']!='completed':
                count['notCompleted']+=1
                if e['status']=='unknown' or any(s['status']=='pending_results' for s in ss.values()): issue('pending_or_unknown_event',year,rnd)
                continue
            count['completed']+=1
            for kind in ('race','qualifying','sprint','sprint_qualifying'):
                s=ss.get(kind)
                if not s:
                    if kind in ('race','qualifying'):issue('missing_session',year,rnd,kind=kind)
                    continue
                if s['status']!='final' or not s['results']:
                    issue('incomplete_session',year,rnd,kind=kind,status=s['status']);continue
                count[kind+'Sessions']+=1; count[kind+'Rows']+=len(s['results'])
                classified=[v for v in s['results'] if v['classified'] is True and v['position'] is not None]
                leaders=[v for v in classified if v['position']==1]
                if len(leaders)!=1: issue('missing_or_multiple_leader',year,rnd,kind=kind,count=len(leaders))
                if kind=='race':
                    count['raceWins']+=len(leaders); count['podiumRows']+=sum(v['position']<=3 for v in classified)
                    if s['id'] in fastest: count['fastestLapRecords']+=1
                    else:
                        count['missingFastestLapRecords']+=1
                        missing_fastest.append(dict(season=year,round=rnd,event=e['id']))
                    for v in classified: finishes[v['driverId']][v['position']]+=1
                if kind=='qualifying':count['qualifyingLeaders']+=len(leaders)
                if kind in ('race','sprint'):
                    for v in s['results']:
                        if v['points'] is None: issue('missing_awarded_points',year,rnd,driver=v['driverId']);continue
                        for k,entity in [('drivers',v['driverId']),('constructors',v['constructorId'])]:
                            intervening[k][entity]+=dec(v['points'])
                            if kind=='race' and v['classified'] is True and v['position']==1: wins[k][entity]+=1
            for k in prev:
                snap=snapshots.get((year,rnd,k))
                if snap is None: issue('missing_standings',year,rnd,kind=k);continue
                count['standingSnapshots']+=1; rows=snap['rows']; actual=defaultdict(Decimal)
                for v in rows:
                    actual[v['entityId']]+=dec(v['points'])
                    if v.get('wins') is not None and not v.get('entrantId') and v['wins']!=wins[k][v['entityId']]:
                        issue('win_count_difference',year,rnd,kind=k,entity=v['entityId'],calculated=wins[k][v['entityId']],published=v['wins'])
                ordered=sorted((v for v in rows if v['position'] is not None),key=lambda v:v['position'])
                by_position=defaultdict(list)
                for v in ordered: by_position[v['position']].append(v)
                for pos, tied in by_position.items():
                    if len(tied)<2: continue
                    if len({v['points'] for v in tied})>1: issue('shared_rank_unequal_points',year,rnd,kind=k,position=pos)
                    else: shared_ranks.append(dict(season=year,round=rnd,kind=k,position=pos,entities=[v['entityId'] for v in tied],points=tied[0]['points']))
                for a,b in zip(ordered,ordered[1:]):
                    if a['points']<b['points']:issue('standing_points_order',year,rnd,kind=k,first=a['entityId'],second=b['entityId'])
                    if k=='drivers' and a['position']!=b['position'] and a['points']==b['points']:
                        fa,fb=finishes[a['entityId']],finishes[b['entityId']]; n=max([0,*fa,*fb]); ka=tuple(fa[i] for i in range(1,n+1));kb=tuple(fb[i] for i in range(1,n+1))
                        if ka<kb:tie_reviews.append(dict(season=year,round=rnd,first=a['entityId'],second=b['entityId'],points=a['points']))
                for entity in sorted(set(prev[k])|set(actual)|set(intervening[k])):
                    before=prev[k].get(entity,ZERO); earned=intervening[k][entity]; after=actual.get(entity,ZERO); count['pointComparisons']+=1
                    delta=after-before-earned
                    if not delta: continue
                    record=dict(season=year,round=rnd,kind=k,entity=entity,previous=float(before),earned=float(earned),published=float(after),delta=float(delta))
                    rule=known_delta(year,rnd,k,entity,before,earned,after,last[k],excluded_entry) if previous_round[k]==rnd-1 else None
                    if rule: exceptions.append(dict(record,**rule))
                    else: issue('unexplained_points_delta',year,rnd,**{f:v for f,v in record.items() if f not in ('season','round')})
                prev[k]=dict(actual);intervening[k].clear();previous_round[k]=rnd
        seasons[str(year)]=dict(count);totals.update(count)
    return dict(scope='internal arithmetic and coverage only; not independent official row-by-row verification',datasetStatus=data['datasetStatus'],publicationAuthorized=False,seasons=seasons,totals=dict(totals),knownPointExceptions=exceptions,issues=issues,countbackReviewCandidates=tie_reviews,sharedRanks=shared_ranks,missingFastestLaps=missing_fastest,notes=['Uses awarded race/sprint points; does not reconstruct points from sporting regulations.','Constructor arithmetic aggregates by constructor, not by entrant; 2018 reset checked explicitly.','Countback candidates use classified race finishes only; do not change published rankings.','Fastest lap presence is counted, not verified independently.','Missing future results are not errors; unknown or pending events are review items.','Historical standings may be retrospective.'])

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input');p.add_argument('--report',required=True);a=p.parse_args()
    try:
        if Path(a.input).resolve()==Path(a.report).resolve(): raise ValueError('distinct input and report required')
        r=audit(read(a.input));write_new(a.report,r)
        print(f"{len(r['seasons'])} seasons; {r['totals'].get('completed',0)} completed; {r['totals'].get('pointComparisons',0)} point comparisons")
        print(f"{len(r['knownPointExceptions'])} known point exceptions; {len(r['issues'])} issues; {len(r['countbackReviewCandidates'])} countback candidates; {len(r['sharedRanks'])} shared rank groups")
        print('REVIEW REQUIRED' if r['issues'] or r['countbackReviewCandidates'] else 'PASS internal checks only; publication not authorized')
        return int(bool(r['issues'] or r['countbackReviewCandidates']))
    except (ValueError,OSError,KeyError) as e:print('AUDIT FAILED:',e);return 2
if __name__=='__main__':raise SystemExit(main())
