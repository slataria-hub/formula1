"""Recover 2000 qualifying from Formula1.com into a NEW draft. No race/standings changes."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import re
import time
import unicodedata
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from import_data import dump
from validate_data import read, validate
from review_2000 import review, REF

ROOT=Path(__file__).resolve().parents[1]
SLUGS='australia brazil san-marino great-britain spain europe monaco canada france austria germany hungary belgium italy united-states japan malaysia'.split()
TEAMS={'Ferrari':'ferrari','McLaren Mercedes':'mclaren','Williams BMW':'williams','Benetton Playlife':'benetton','BAR Honda':'bar','Jordan Mugen Honda':'jordan','Arrows Supertec':'arrows','Sauber Petronas':'sauber','Jaguar Cosworth':'jaguar','Minardi Fondmetal':'minardi','Prost Peugeot':'prost'}
LIMIT=10_000_000

def url_for(rnd):
    if not 1<=rnd<=17: raise ValueError('Unexpected round')
    return f'https://www.formula1.com/en/results/2000/races/{46+rnd}/{SLUGS[rnd-1]}/qualifying/0'

def norm(s):
    s=unicodedata.normalize('NFKD',s).casefold()
    return ' '.join(re.findall(r'[a-z0-9]+',''.join(c for c in s if not unicodedata.combining(c))))

def need(ok,msg):
    if not ok: raise ValueError(msg)

class Tables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.tables=[]; self.table=None; self.row=None; self.cell=None; self.heading=None; self.headings=[]; self.visible=[]; self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'): self.hidden+=1
        if tag=='h1': self.heading=[]
        if tag=='table': self.table=[]
        elif tag=='tr' and self.table is not None: self.row=[]
        elif tag in ('th','td') and self.row is not None: self.cell=[]
    def handle_data(self,data):
        if self.hidden: return
        if self.cell is not None: self.cell.append(data)
        if self.heading is not None: self.heading.append(data)
        if data.strip(): self.visible.append(data)
    def handle_endtag(self,tag):
        if tag in ('script','style'): self.hidden=max(0,self.hidden-1)
        if tag=='h1' and self.heading is not None: self.headings.append(' '.join(self.heading)); self.heading=None
        if tag in ('th','td') and self.cell is not None:
            self.row.append(' '.join(' '.join(self.cell).split())); self.cell=None
        elif tag=='tr' and self.row is not None: self.table.append(self.row); self.row=None
        elif tag=='table' and self.table is not None: self.tables.append(self.table); self.table=None

def parse(raw, event, drivers, expected):
    p=Tables(); p.feed(raw.decode('utf-8-sig')); p.close()
    need(any('2000' in h and 'qualifying' in h.lower() for h in p.headings),'Missing 2000 qualifying heading')
    date=datetime.fromisoformat(event['date']); month='Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()[date.month-1]
    need(re.search(rf'\b0?{date.day}\s+{month}\s+2000\b',' '.join(p.visible),re.I),f'Round {event["round"]}: archive date mismatch')
    headers=['pos','no','driver','team','time','laps']
    candidates=[t for t in p.tables if t and [norm(c) for c in t[0] if c.strip()]==headers]
    need(len(candidates)==1,'Expected exactly one single-session qualifying table')
    table=candidates[0]; keep=[i for i,c in enumerate(table[0]) if c.strip()]
    race=next(s for s in event['sessions'] if s['kind']=='race')
    entrants={r['driverId']:r['constructorId'] for r in race['results']}
    expected_count=21 if event['round']==6 else 22
    need(len(table)-1==expected_count,f'Round {event["round"]}: unexpected qualifying row count {len(table)-1}')
    out=[]; seen=set()
    for cells in table[1:]:
        need(len(cells)==len(table[0]),'Unexpected table row width')
        pos,num,driver,team,lap_time,laps=[cells[i] for i in keep]
        need(pos.isdecimal() and num.isdecimal() and laps.isdecimal(),'Invalid position, car number or laps')
        # Full normalized name only. Responsive duplicate abbreviations are tolerated, but never a surname-only match.
        n=' '+norm(driver)+' '
        matches=[d['id'] for d in drivers if ' '+norm(d['name'])+' ' in n]
        need(len(matches)==1,f'Ambiguous/unknown full driver name: {driver!r}')
        did=matches[0]; tid='jolpica:'+TEAMS.get(team,'')
        need(did in entrants and entrants[did]==tid,f'Round {event["round"]}: participant/team mismatch: {driver} / {team}')
        need(did not in seen,'Duplicate driver '+did); seen.add(did)
        m=re.fullmatch(r'(\d+):([0-5]\d)\.(\d{3})',lap_time)
        need(m is not None,f'Unrecognized qualifying time {lap_time!r}')
        ms=(int(m[1])*60+int(m[2]))*1000+int(m[3]); need(ms>0,'Nonpositive qualifying time')
        out.append({'driverId':did,'constructorId':tid,'position':int(pos),'positionText':pos,'points':None,'started':None,'classified':True,'status':'unknown','rawStatus':None,'laps':int(laps),'gridPosition':None,'timeMs':None,'gapMs':None,'qualifyingTimesMs':[ms,None,None]})
    out.sort(key=lambda r:r['position'])
    need(seen==set(entrants),'Qualifying/race entrant set differs; manual review required')
    need([r['position'] for r in out]==list(range(1,expected_count+1)),'Missing or duplicate qualifying position')
    need(out[0]['driverId']==expected['poleDriverId'] and out[0]['qualifyingTimesMs'][0]==expected['poleTimeMs'],'Pole/time differs from independent reference')
    need(all(a['qualifyingTimesMs'][0]<=b['qualifyingTimesMs'][0] for a,b in zip(out,out[1:])),'Qualifying time/order mismatch; manual review required')
    return out

def load_page(rnd, cache, html_dir=None, offline=False):
    url=url_for(rnd); body=cache/f'round-{rnd:02d}.html'; meta=cache/f'round-{rnd:02d}.json'
    if body.exists() and meta.exists():
        raw=body.read_bytes(); src=read(meta)
        need(src['url']==url and src['sha256']==hashlib.sha256(raw).hexdigest(),'Cache checksum/URL mismatch')
        print('CACHE',rnd,flush=True); return raw,src
    if html_dir is not None:
        path=html_dir/f'round-{rnd:02d}.html'; raw=path.read_bytes(); print('LOCAL HTML',path,flush=True)
    else:
        need(not offline,f'No cached HTML for round {rnd}')
        print('GET',url,flush=True)
        with urlopen(Request(url,headers={'User-Agent':'F1Analytics/0.2 (historical qualifying pilot)'}),timeout=30) as resp:
            need(resp.geturl().rstrip('/')==url.rstrip('/'),'Unexpected redirect; use a locally saved archive page')
            raw=resp.read(LIMIT+1)
        time.sleep(1.5)
    need(0<len(raw)<=LIMIT,'Invalid page size')
    digest=hashlib.sha256(raw).hexdigest()
    source={'id':f'formula1:2000-r{rnd:02d}-qualifying-{digest[:24]}','provider':'Formula1.com','url':url,'retrievedAt':datetime.now(timezone.utc).isoformat(),'sha256':digest,'revision':None}
    # Cache only after successful parsing (see recover).
    return raw,source

def recover(data, ref, loader, save_cache=None):
    # Reconcile first: refuses unknown points/adjustments and wrong season.
    out,_=review(data,ref); need(out==data,'Input must already be reconciled by review_2000.py'); expected={r['round']:r for r in ref['races']}; added=[]; rows=0
    for e in out['events']:
        q=next(s for s in e['sessions'] if s['kind']=='qualifying')
        if q['results']: continue
        rnd=e['round']; raw,source=loader(rnd)
        need(source['url']==url_for(rnd) and source['sha256']==hashlib.sha256(raw).hexdigest(),'Source hash or URL differs')
        result=parse(raw,e,out['drivers'],expected[rnd]); sid=source['id']
        if save_cache: save_cache(rnd,raw,source)
        need(not any(s['id']==sid for s in out['sources']),'Duplicate source ID')
        out['sources'].append(source); q['sourceIds'].append(sid); q['results']=result; q['status']='final'; added.append(rnd); rows+=len(result)
        print(f'PASS R{rnd:02d}: {len(result)} qualifying rows',flush=True)
    errors=validate(out); need(not errors,'Invalid output: '+'; '.join(errors[:5]))
    count=sum(len(s['results']) for e in out['events'] for s in e['sessions'] if s['kind']=='qualifying')
    need(count==373,'Unexpected complete season qualifying total')
    return out,{'season':2000,'datasetStatus':'draft','addedRounds':added,'addedRows':rows,'totalQualifyingRows':count,'note':'Missing qualifying tables recovered; existing 4 not independently compared row by row; race results/standings not re-published as verified.'}

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('input',type=Path); p.add_argument('--output',type=Path,required=True); p.add_argument('--report',type=Path,required=True); p.add_argument('--cache',type=Path,default=ROOT/'private/formula1-html-2000'); p.add_argument('--html-dir',type=Path); p.add_argument('--offline',action='store_true'); a=p.parse_args()
    if len({a.input.resolve(),a.output.resolve(),a.report.resolve()})!=3 or a.output.exists() or a.report.exists(): p.error('Use new distinct output and report paths')
    def cache(rnd,raw,src):
        a.cache.mkdir(parents=True,exist_ok=True); path=a.cache/f'round-{rnd:02d}.html'; tmp=path.with_suffix('.tmp'); tmp.write_bytes(raw); tmp.replace(path); dump(a.cache/f'round-{rnd:02d}.json',src)
    try:
        out,report=recover(read(a.input),read(REF),lambda r:load_page(r,a.cache,a.html_dir,a.offline),cache)
        dump(a.output,out,exclusive=True); dump(a.report,report,exclusive=True); print(f'DRAFT: {report["totalQualifyingRows"]} qualifying rows; {report["addedRows"]} added.'); return 0
    except KeyboardInterrupt: print('CANCELLED: no partial candidate published; cache retained'); return 130
    except Exception as exc: print('QUALIFYING IMPORT FAILED:',exc); return 1
if __name__=='__main__': raise SystemExit(main())
