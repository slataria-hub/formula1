"""Incremental local DRAFT media sync, using the exact archive of the candidate.
No activation, no public uploads, no automatic logo approvals. Legacy packs remain readable.
"""
import argparse, copy, csv, hashlib, io, json, os, re, tempfile, zipfile
from pathlib import Path
from contextlib import contextmanager
import collect_media as media
from validate_data import ROOT, read, validate
from fetch_f1db import verify_archive, MAX_BYTES


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def exact_source(data):
    sources=[s for s in data['sources'] if s['provider']=='F1DB']
    if len(sources)!=1:raise ValueError('exactly one F1DB archive source required')
    s=sources[0]; digest=s.get('sha256'); tag=s.get('revision')
    if not isinstance(digest,str) or not re.fullmatch(r'[0-9a-f]{64}',digest) or not isinstance(tag,str) or not re.fullmatch(r'v\d+\.\d+\.\d+',tag) or s['id']!='f1db:archive-'+digest:
        raise ValueError('invalid F1DB source digest/tag')
    if any(s['id'] not in e['sourceIds'] for e in data['events']):raise ValueError('event source mismatch')
    return s


def resolve_archive(source, archive=None, cache='private/f1db/releases'):
    paths=[Path(archive)] if archive else [Path(cache)/source['revision']/source['sha256']/'f1db-csv.zip',ROOT/'private/f1db/f1db-csv.zip']
    for p in paths:
        if p.is_file() and 0<p.stat().st_size<=MAX_BYTES and sha(p)==source['sha256']:
            return verify_archive(p,dict(size=p.stat().st_size,sha256=source['sha256']))
    raise ValueError('matching verified CSV archive not found; use --archive or prepare_update cache')


def rows(z,table):
    with z.open('f1db-'+table+'.csv') as f:
        yield from csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig'))


def index(iterable,key):
    result={}
    for r in iterable:
        k=r[key]
        if k in result:raise ValueError('duplicate archive key: '+k)
        result[k]=r
    return result


def targets(data, archive, source):
    years=sorted({e['season'] for e in data['events']}); driverids=set(); teams={}; layouts={}; unmapped=[]
    for e in data['events']:
        for session in e['sessions']:
            for r in session['results']:
                driverids.add(r['driverId']);teams.setdefault(r['constructorId'],set()).add(e['season'])
    for s in data['standings']:
        for r in s['rows']:
            if s['kind']=='drivers':driverids.add(r['entityId'])
            else:teams.setdefault(r['entityId'],set()).add(s['season'])
    with zipfile.ZipFile(archive) as z:
        race=index(rows(z,'races'),'id'); circuit_layouts=index(rows(z,'circuits-layouts'),'id')
        countries=index(rows(z,'countries'),'id'); flags={}; ambiguous=set()
        for c in countries.values():
            code=c['alpha2Code'].lower()
            if not re.fullmatch(r'[a-z]{2}',code):continue
            for name in (c['name'],c['demonym']):
                if not name:continue
                if name in flags and flags[name]!=code:ambiguous.add(name)
                flags[name]=code
        for name in ambiguous:flags.pop(name,None)
        for e in data['events']:
            eid=e.get('externalEventId',''); r=race.get(eid.removeprefix('f1db:race-')) if eid.startswith('f1db:race-') else None
            if not r or int(r['year'])!=e['season'] or int(r['round'])!=e['round'] or 'f1db:'+r['circuitId']!=e['circuitId'] or r['date']!=e['date']:
                raise ValueError('archive/event identity mismatch: '+e['id'])
            layout=r['circuitLayoutId']; record=circuit_layouts.get(layout)
            if not record or record['circuitId']!=r['circuitId']:
                unmapped.append(e['id']);continue
            layouts[eid]=[e['season'],e['circuitId'],layout,source['id']]
        # For calendar-only seasons, prefetch published season rosters, if present.
        # Do not create entrants or change sporting data.
        upcoming={y for y in years if not any(e['season']==y and any(s['results'] for s in e['sessions']) for e in data['events'])}
        rawdrivers=index(rows(z,'drivers'),'id'); rawteams=index(rows(z,'constructors'),'id')
        if upcoming:
            for table,field in [('seasons-entrants-drivers','driverId'),('seasons-entrants-constructors','constructorId')]:
                if 'f1db-'+table+'.csv' not in z.namelist():continue
                for r in rows(z,table):
                    y=int(r['year'])
                    if y not in upcoming:continue
                    if r.get('testDriver')=='true':continue
                    if field=='driverId':driverids.add('f1db:'+r[field])
                    else:teams.setdefault('f1db:'+r[field],set()).add(y)
        drivers={d['id']:d for d in data['drivers'] if d['id'] in driverids}; constructors={t['id']:t['name'] for t in data['constructors']}
        for key in driverids-drivers.keys():
            raw=rawdrivers.get(key.removeprefix('f1db:'))
            if not raw:raise ValueError('unknown roster driver: '+key)
            drivers[key]=dict(id=key,name=raw['name'],birthDate=raw['dateOfBirth'] or None)
        for key in teams.keys()-constructors.keys():
            raw=rawteams.get(key.removeprefix('f1db:'))
            if not raw:raise ValueError('unknown roster constructor: '+key)
            constructors[key]=raw['name']
    return dict(years=years,eventLayouts=layouts,layouts=sorted({v[2] for v in layouts.values()}),unmappedEvents=unmapped,
                drivers=drivers,teams={k:dict(name=constructors[k],years=sorted(v)) for k,v in sorted(teams.items())},countryCodes=flags)


def missing(t,pack):
    return dict(photos=sorted(set(t['drivers'])-pack['photos'].keys()),layouts=sorted(set(t['layouts'])-pack['circuits'].keys()),
                teamSeasons=sorted(k+'@'+str(y) for k,v in t['teams'].items() for y in v['years'] if k+'@'+str(y) not in pack['logos']))


def atomic(path,raw):
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name+'-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:Path(tmp).unlink(missing_ok=True)


def json_bytes(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


@contextmanager
def lock(out):
    p=out/'.media-sync.lock'
    fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:
        with os.fdopen(fd,'w') as f:f.write(str(os.getpid()))
        yield
    finally:p.unlink(missing_ok=True)


def source_zip(out,tag, supplied=None):
    path=Path(supplied) if supplied else out/('f1db-source-'+tag+'.zip')
    def check(z):
        names=z.namelist(); root='f1db-'+tag.removeprefix('v')+'/'
        if not names or len(names)!=len(set(names)) or any(not n.startswith(root) or '..' in n.split('/') or '\\' in n for n in names):raise ValueError('source ZIP tag/path mismatch')
        if len(names)>200000 or sum(v.file_size for v in z.infolist())>1_000_000_000:raise ValueError('source ZIP safety limit')
        for filename,needle in [('LICENSE','Creative Commons Attribution 4.0 International Public License'),('README.md','Jules Roy')]:
            try:info=z.getinfo(root+filename)
            except KeyError as exc:raise ValueError('source license/attribution requires review: '+filename) from exc
            if info.file_size>1_000_000 or needle not in z.read(info).decode('utf-8'):raise ValueError('source license/attribution requires review: '+filename)
    if not path.exists() and supplied:raise ValueError('supplied source ZIP missing')
    if not path.exists():
        raw=media.read_url('https://codeload.github.com/f1db/f1db/zip/refs/tags/'+tag,200_000_000)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:check(z)
        atomic(path,raw)
    if path.stat().st_size>200_000_000:raise ValueError('source ZIP too large')
    with zipfile.ZipFile(path) as z:check(z)
    return path


def sync(baseline, output, *, archive=None, cache='private/f1db/releases', source=None, plan_only=False, approvals=None):
    out=media.local_path(output); data=read(baseline)
    if data.get('datasetStatus')!='draft' or not data.get('events') or validate(data):raise ValueError('valid nonempty DRAFT required')
    s=exact_source(data); csv_path=resolve_archive(s,archive,cache); t=targets(data,csv_path,s)
    out.mkdir(parents=True,exist_ok=True); path=out/'visual-media.json'; report_path=out/'media-sync-report.json'
    with lock(out):
        original=path.read_bytes() if path.exists() else None
        pack=media.validate_pack(read(path)) if original is not None else dict(version=1,photos={},logos={},circuits={})
        initial=missing(t,pack); before=copy.deepcopy(pack)
        report=dict(status='plan' if plan_only else 'draft_media_ready',publicationAuthorized=False,activated=False,sourceTag=s['revision'],archiveSha256=s['sha256'],seasons=t['years'],target=dict(photos=len(t['drivers']),layouts=len(t['layouts']),teamSeasons=sum(len(v['years']) for v in t['teams'].values()),events=len(t['eventLayouts'])),missingBefore=initial,unmappedEvents=t['unmappedEvents'],errors={},photoDiagnostics={},logoDiagnostics={},logoCandidates={},added=dict(photos=[],circuits=[],logos=[]))
        if plan_only:
            report['present']={k:len(pack[k]) for k in ('photos','logos','circuits')};report['coverageMissing']=initial;report['packChanged']=False
            atomic(out/'media-sync-plan.json',json_bytes(report));return report
        # Validate every explicit approval before making network requests.
        reviewed={}
        for a in read(approvals) if approvals else []:
            key=a['id']; years=a['years']; file=a['file']
            if key not in t['teams'] or not isinstance(years,list) or not years or any(type(y) is not int or y not in t['teams'][key]['years'] for y in years) or not isinstance(file,str) or not file.strip():raise ValueError('invalid explicit approval')
            for y in years:
                slot=key+'@'+str(y)
                if slot in reviewed:raise ValueError('duplicate explicit approval: '+slot)
                reviewed[slot]=a
        def attempt(kind,key,fn):
            if key in pack[kind]:return
            try:
                item=fn()
                if item:
                    check=dict(version=1,photos={},logos={},circuits={});check[kind][key]=item;media.validate_pack(check)
                    pack[kind][key]=item;report['added'][kind].append(key);print('OK',kind,key,flush=True)
                else:print('MISSING',kind,key,flush=True)
            except Exception as exc:report['errors'][kind+':'+key]=str(exc);print('ERROR',kind,key,str(exc),flush=True)
        pack['eventLayouts']=t['eventLayouts'];pack['countryCodes']=t['countryCodes']
        if initial['layouts']:
            try:
                sp=source_zip(out,s['revision'],source);report['sourceZipSha256']=sha(sp)
                with zipfile.ZipFile(sp) as z:
                    for key in initial['layouts']:attempt('circuits',key,lambda key=key:media.circuit_item(z,key,s['revision']))
            except Exception as exc:report['errors']['circuitSource']=str(exc)
        for key in initial['photos']:
            notes=[];attempt('photos',key,lambda key=key:media.find_photo(t['drivers'][key],notes));report['photoDiagnostics'][key]=notes
        for slot,a in sorted(reviewed.items()):
            if slot in pack['logos']:continue
            notes=[]
            def approved():
                item=media.image_item(a['file'],notes)
                if item and media.canonical_file(item['file'])!=media.canonical_file(a['file']):raise ValueError('reviewed file resolved to another title')
                return dict(item,years=a['years'],periodStatus=media.logo_status(item,a)) if item else None
            attempt('logos',slot,approved);report['logoDiagnostics'][slot]=notes
        # Reuse discovery results for the same archive + constructor; never display a candidate automatically.
        old=read(report_path) if report_path.exists() else {}; old_candidates=old.get('logoCandidates',{}) if old.get('archiveSha256')==s['sha256'] else {}
        pending=missing(t,pack)['teamSeasons']
        for key in sorted({v.rsplit('@',1)[0] for v in pending}):
            team=t['teams'][key]; slots=[v for v in pending if v.startswith(key+'@')]
            try:
                cached=old_candidates.get(key,{}).get('files',[])
                files=cached or media.discover_logo_files(team['name']+' Formula One',team['name']+' F1')
                report['logoCandidates'][key]=dict(name=team['name'],slots=slots,files=files,approved=False)
            except Exception as exc:report['errors']['logoPlan:'+key]=str(exc)
        media.validate_pack(pack)
        if any(pack[k].get(key)!=item for k in ('photos','logos','circuits') for key,item in before[k].items()):raise ValueError('existing image modified')
        changed=pack!=before or original is None
        if changed:
            if (path.read_bytes() if path.exists() else None)!=original:raise ValueError('media pack changed concurrently; stop other collectors and retry')
            if original is not None:
                backups=out/'backups';backups.mkdir(exist_ok=True); backup=backups/('visual-media-'+hashlib.sha256(original).hexdigest()+'.json')
                if backup.exists() and backup.read_bytes()!=original:raise ValueError('backup hash conflict')
                if not backup.exists():atomic(backup,original)
                report['backup']=str(backup.relative_to(out))
            atomic(path,json_bytes(pack))
        report['present']={k:len(pack[k]) for k in ('photos','logos','circuits')};report['coverageMissing']=missing(t,pack);report['packChanged']=changed;report['packSha256']=sha(path)
        if report['errors'] or any(report['coverageMissing'].values()) or t['unmappedEvents']:report['status']='draft_media_review_required'
        atomic(report_path,json_bytes(report));return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',required=True);p.add_argument('--output',required=True);p.add_argument('--archive');p.add_argument('--cache-dir',default='private/f1db/releases');p.add_argument('--source-zip');p.add_argument('--approved-logos');p.add_argument('--plan-only',action='store_true');a=p.parse_args()
    try:
        r=sync(a.baseline,a.output,archive=a.archive,cache=a.cache_dir,source=a.source_zip,plan_only=a.plan_only,approvals=a.approved_logos)
        print(json.dumps(dict(status=r['status'],present=r['present'],missing={k:len(v) for k,v in r['coverageMissing'].items()},events=r['target']['events'],seasons=r['seasons'],packChanged=r['packChanged'],errors=r['errors']),ensure_ascii=False));print('DRAFT LOCAL ONLY; publication not authorized');return 2 if r['errors'] else 0
    except KeyboardInterrupt:print('MEDIA CANCELLED; existing pack retained');return 130
    except Exception as exc:print('MEDIA SYNC BLOCKED:',exc);return 1

if __name__=='__main__':raise SystemExit(main())
