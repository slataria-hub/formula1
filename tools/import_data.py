"""F1-002 pilot importer. Produces only a draft, never overwrites a dataset."""
import argparse
import hashlib
import json
import os
import tempfile
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from validate_data import read, validate

BASE = 'https://api.jolpi.ca/ergast/f1/'
ROOT = Path(__file__).resolve().parents[1]

def now():
    return datetime.now(timezone.utc).isoformat()

def dump(path, data, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive:
        # Publish a fully written candidate without replacing an existing path.
        fd, name = tempfile.mkstemp(prefix='.candidate-', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
                f.write('\n'); f.flush(); os.fsync(f.fileno())
            os.link(name,path)
        finally:
            Path(name).unlink(missing_ok=True)
    else:
        tmp = path.with_suffix(path.suffix + '.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        tmp.replace(path)

class NetworkReadError(RuntimeError):
    """A request exhausted network retries; caller may use a smaller page."""

class Client:
    def __init__(self, cache, refresh=False, timeout=90, page_size=10):
        self.cache = Path(cache); self.refresh = refresh; self.sources = {}; self.last = 0; self.timeout = timeout; self.page_size = page_size
    def get(self, route, offset, limit=100):
        url = BASE + route.strip('/') + '/?' + urlencode({'limit':limit,'offset':offset})
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.cache / (key+'.json')
        if path.exists() and not self.refresh:
            print(f'CACHE {route} offset={offset} limit={limit}', flush=True)
            entry = read(path)
            if entry['url'] != url: raise ValueError('Cache URL mismatch')
        else:
            attempts = 5 if route.endswith('/races') or limit==1 else 2
            for attempt in range(attempts):
                print(f'GET {url} (attempt {attempt+1}/{attempts}, timeout={self.timeout}s)', flush=True)
                time.sleep(max(0, 1.2-(time.monotonic()-self.last)))
                self.last=time.monotonic()
                try:
                    with urlopen(Request(url, headers={'User-Agent':'F1Analytics/0.2-pilot'}),timeout=self.timeout) as response:
                        raw=response.read(10_000_001)
                        if len(raw)>10_000_000: raise ValueError('Response exceeds 10 MB')
                    body=raw.decode('utf-8'); json.loads(body)
                    entry={'url':url,'retrievedAt':now(),'body':body,'sha256':hashlib.sha256(raw).hexdigest()}
                    dump(path,entry); break
                except HTTPError as e:
                    print(f'HTTP {e.code}: {url}', file=sys.stderr, flush=True)
                    if e.code not in (429,500,502,503,504) or attempt==attempts-1: raise RuntimeError(f'{url}: HTTP {e.code}') from e
                    retry=e.headers.get('Retry-After','')
                    time.sleep(max(2**(attempt+1), int(retry) if retry.isdigit() else 60 if e.code==429 else 0))
                except (URLError,TimeoutError) as e:
                    print(f'NETWORK {url}: {type(e).__name__}: {e}', file=sys.stderr, flush=True)
                    if attempt==attempts-1: raise NetworkReadError(f'{url}: {type(e).__name__}: {e}') from e
                    time.sleep(2**(attempt+1))
        digest=hashlib.sha256(entry['body'].encode('utf-8')).hexdigest()
        if digest!=entry['sha256']: raise ValueError('Cache checksum mismatch')
        sid='jolpica:response-'+key[:24]+'-'+digest[:24]
        self.sources[sid]={'id':sid,'provider':'Jolpica F1','url':url,'retrievedAt':entry['retrievedAt'],'sha256':digest,'revision':None}
        return json.loads(entry['body'])['MRData'],sid
    def pages(self, route, table, collection, nested=None):
        offset=0; expected=None; self.last_page_source=None
        requested=100 if route.endswith('/races') else self.page_size
        while True:
            try:
                data,sid=self.get(route,offset,requested)
            except NetworkReadError:
                if requested==1: raise
                requested=max(1,requested//2)
                print(f'REDUCE {route} offset={offset} limit={requested}',flush=True)
                continue
            self.last_page_source=sid
            total=int(data['total']); actual=int(data['offset']); limit=int(data['limit'])
            if expected is None: expected=total
            if actual!=offset or total!=expected or limit<=0: raise ValueError(f'{route}: inconsistent pagination')
            groups=data[table][collection]
            count=sum(len(g[nested]) for g in groups) if nested else len(groups)
            if count!=min(limit,total-offset): raise ValueError(f'{route}: unexpected page length {count}, offset={offset}, total={total}')
            for group in groups: yield group,sid
            offset+=count
            if offset>=total: return
            if not count: raise ValueError(f'{route}: empty page before total')

def integer(v, minimum=0):
    if v is None or v=='': return None
    n=int(v)
    return n if n>=minimum else None

def milliseconds(v):
    if not v: return None
    from decimal import Decimal
    parts=str(v).split(':')
    if len(parts)>3 or not re.fullmatch(r'\d+(?:\.\d+)?',parts[-1]): return None
    try: return int(sum(Decimal(x)*60**i for i,x in enumerate(reversed(parts)))*1000)
    except (ValueError, ArithmeticError): return None

def flags(row):
    raw=row.get('status'); p=str(row.get('positionText') or '')
    if p.isdecimal(): classified=True
    elif p in ('R','D','E','W','F','N'): classified=False
    else: classified=None
    if p=='D' or raw=='Disqualified': return 'dsq',None,False
    if p=='E' or raw=='Excluded': return 'excluded',None,False
    if p=='W' or raw=='Withdrawn': return 'withdrawn',None,False
    if p=='F' or raw in ('Did not start','Did not qualify','Did not prequalify'): return 'dns',False,False
    if raw=='Finished' or re.fullmatch(r'\+\d+ Laps?',raw or ''): return 'finished',True,classified
    if raw=='Not classified' or p=='N': return 'not_classified',None,False
    # Do not infer a start from an ambiguous technical status with zero laps.
    started=True if (integer(row.get('laps')) or 0)>0 else None
    return ('retired' if p=='R' or raw=='Retired' else 'unknown'),started,classified

def import_season(client, year):
    data=read(ROOT/'examples/empty-dataset.json'); data['datasetStatus']='draft'
    registries={k:{} for k in ('drivers','constructors','circuits')}; events={}; notes=[]
    def register(kind,obj,sid):
        if kind=='drivers':
            ext=obj['driverId']; fields={'name':obj['givenName']+' '+obj['familyName'],'givenName':obj.get('givenName'),'familyName':obj.get('familyName'),'birthDate':obj.get('dateOfBirth'),'nationality':obj.get('nationality')}
        elif kind=='constructors':
            ext=obj['constructorId']; fields={'name':obj['name'],'nationality':obj.get('nationality'),'lineageId':None}
        else:
            ext=obj['circuitId']; loc=obj.get('Location',{}); fields={'name':obj['circuitName'],'country':loc.get('country'),'locality':loc.get('locality')}
        did='jolpica:'+ext; reg=registries[kind]
        if did not in reg: reg[did]={'id':did,'aliases':[{'provider':'jolpica','externalId':ext}],'sourceIds':[],**fields}
        elif reg[did]['name']!=fields['name']: notes.append(f'{did}: source name variation: {fields["name"]}')
        if sid not in reg[did]['sourceIds']: reg[did]['sourceIds'].append(sid)
        return did
    def identity(r):
        if int(r['season'])!=year: raise ValueError('Unexpected season')
        return f'{year}-R{int(r["round"]):02d}'
    def schedule(r,api_key):
        item=r if api_key=='race' else r.get(api_key,{})
        return item['date']+'T'+item['time'] if item.get('date') and item.get('time') else None
    def session(ev,kind,at,sid):
        s=next((s for s in ev['sessions'] if s['kind']==kind),None)
        if s is None:
            s={'id':ev['id']+'-'+kind,'kind':kind,'status':'unavailable','scheduledAt':at,'sourceIds':[],'results':[]}; ev['sessions'].append(s)
        if sid not in s['sourceIds']: s['sourceIds'].append(sid)
        return s
    for r,sid in client.pages(f'{year}/races','RaceTable','Races'):
        eid=identity(r)
        if eid in events: raise ValueError('Duplicate calendar event '+eid)
        ev={'id':eid,'season':year,'round':int(r['round']),'name':r['raceName'],'circuitId':register('circuits',r['Circuit'],sid),'date':r.get('date'),'status':'unknown','sourceIds':[sid],'sessions':[]}; events[eid]=ev
        session(ev,'race',schedule(r,'race'),sid)
        for api,kind in [('Qualifying','qualifying'),('Sprint','sprint'),('SprintQualifying','sprint_qualifying'),('SprintShootout','sprint_qualifying'),('FirstPractice','practice_1'),('SecondPractice','practice_2'),('ThirdPractice','practice_3')]:
            if api in r: session(ev,kind,schedule(r,api),sid)
    if not events: raise ValueError('No calendar returned')
    types=[('results','Results','race'),('qualifying','QualifyingResults','qualifying')]
    if year>=2021: types.append(('sprint','SprintResults','sprint'))
    for route,key,kind in types:
        for ev in sorted(events.values(),key=lambda e:e['round']):
            print(f'SESSION {ev["id"]} {kind}',flush=True)
            for r,sid in client.pages(f'{year}/{ev["round"]}/{route}','RaceTable','Races',key):
                if identity(r)!=ev['id']: raise ValueError('Unexpected result round: '+ev['id'])
                s=session(ev,kind,None,sid)
                if r.get('raceName')!=ev['name']: raise ValueError('Calendar/result race name mismatch: '+ev['id'])
                for x in r[key]:
                    did=register('drivers',x['Driver'],sid); tid=register('constructors',x['Constructor'],sid)
                    if any(z['driverId']==did for z in s['results']): raise ValueError(f'{s["id"]}: duplicate {did}')
                    isq=kind=='qualifying'; status,started,classified=('unknown',None,None) if isq else flags(x)
                    pts=None if isq else float(x['points'])
                    s['results'].append({'driverId':did,'constructorId':tid,'position':integer(x.get('position'),1),'positionText':x.get('positionText') or (str(x['position']) if isq and x.get('position') is not None else None),'points':pts,'started':started,'classified':classified,'status':status,'rawStatus':x.get('status'),'laps':integer(x.get('laps')),'gridPosition':integer(x.get('grid')),'timeMs':integer(x.get('Time',{}).get('millis')),'gapMs':None,'qualifyingTimesMs':[milliseconds(x.get(k)) for k in ('Q1','Q2','Q3')] if isq else None})
                    fl=x.get('FastestLap') or {}; ms=milliseconds(fl.get('Time',{}).get('time'))
                    if kind=='race' and str(fl.get('rank'))=='1' and ms:
                        data['fastestLaps'].append({'sessionId':s['id'],'driverId':did,'lap':integer(fl.get('lap'),1),'timeMs':ms,'compound':None,'sourceIds':[sid]})
            # Older calendars may omit qualifying entirely; preserve a successful empty query.
            if kind=='qualifying' and any(s['kind']=='race' and s['results'] for s in ev['sessions']):
                q=next((s for s in ev['sessions'] if s['kind']=='qualifying'),None)
                if (q is None or not q['results']) and client.last_page_source:
                    session(ev,'qualifying',None,client.last_page_source)
    for ev in events.values():
        for s in ev['sessions']:
            s['results'].sort(key=lambda x:(x['position'] is None,x['position'] or 0,x['driverId']))
            if s['results']: s['status']='final' if year<datetime.now(timezone.utc).year else 'provisional'
            elif s['scheduledAt'] and s['scheduledAt']>now(): s['status']='scheduled'
            elif s['kind'] in ('race','sprint','qualifying'): notes.append(f'{s["id"]}: no published result')
        race=next(s for s in ev['sessions'] if s['kind']=='race')
        ev['status']='completed' if race['results'] else 'scheduled' if race['status']=='scheduled' else 'unknown'
    for endpoint,kind,rows_key,objkey,registry in [('driverstandings','drivers','DriverStandings','Driver','drivers'),('constructorstandings','constructors','ConstructorStandings','Constructor','constructors')]:
        snapshots={}
        for group,sid in client.pages(f'{year}/{endpoint}','StandingsTable','StandingsLists',rows_key):
            if int(group['season'])!=year or f'{year}-R{int(group["round"]):02d}' not in events: raise ValueError('Unknown standings round')
            rnd=int(group['round']); st=snapshots.setdefault(rnd,{'season':year,'afterRound':rnd,'kind':kind,'sourceIds':[],'rows':[]})
            if sid not in st['sourceIds']: st['sourceIds'].append(sid)
            for x in group[rows_key]:
                did=register(registry,x[objkey],sid)
                pos=integer(x.get('position'),1)
                text=x.get('positionText')
                if pos is None and text not in ('-','E','D'):
                    raise ValueError(f'{year}/{endpoint} round {rnd}/{did}: missing or invalid position (positionText={text!r})')
                st['rows'].append({'entityId':did,'position':pos,'positionText':text if text is not None else str(pos),'points':float(x['points']),'wins':integer(x.get('wins'))})
        if not snapshots: notes.append(f'{year}: no {kind} standings')
        data['standings'].extend(snapshots.values())
    data['events']=sorted(events.values(),key=lambda e:e['round'])
    for k,reg in registries.items(): data[k]=list(reg.values())
    data['sources']=list(client.sources.values())
    errors=validate(data)
    if errors: raise ValueError('\n'.join(errors[:30]))
    return data,notes

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--season',type=int,required=True); p.add_argument('--output',type=Path,required=True); p.add_argument('--cache',type=Path,default=ROOT/'private'/'jolpica-cache'); p.add_argument('--refresh',action='store_true'); p.add_argument('--timeout', type=int, default=90, help='HTTP socket timeout in seconds (default: 90)'); p.add_argument('--page-size',type=int,default=10,help='Initial results page size (default: 10)'); a=p.parse_args()
    if not 1<=a.page_size<=100: p.error('--page-size must be between 1 and 100')
    if not 1<=a.timeout<=300: p.error('--timeout must be between 1 and 300')
    if not 2000<=a.season<=2026: p.error('pilot supports 2000–2026')
    if a.output.exists(): p.error('output exists; select a new candidate path')
    try:
        data,notes=import_season(Client(a.cache,a.refresh,a.timeout,a.page_size),a.season)
        dump(a.output,data,exclusive=True)
        print(f'DRAFT {a.output}: {len(data["events"])} events, {len(data["drivers"])} drivers, {len(data["constructors"])} constructors')
        for note in notes: print('WARNING:',note)
        for st in data['standings']:
            print(st['kind'], 'round',st['afterRound'], sorted(st['rows'],key=lambda x:(x['position'] is None,x['position'] or 0))[:3])
        print('PASS structural validation; independent verification pending.')
        return 0
    except KeyboardInterrupt:
        print('IMPORT CANCELLED: cached responses retained; no incomplete candidate published.',file=sys.stderr); return 130
    except Exception as e:
        print('IMPORT FAILED:',e,file=sys.stderr); return 1
if __name__=='__main__': raise SystemExit(main())
