"""Local-only visual pack for 2000–2026. Never writes official data or public site.
F1DB circuit silhouettes: exact archive layout IDs. Commons photos: exact DOB match.
Team logos require explicit season-level review; discovery is not approval.
"""
import argparse, base64, csv, hashlib, io, json, re, time, urllib.parse, urllib.request, urllib.error, zipfile, unicodedata
from pathlib import Path
from xml.etree import ElementTree as ET
from html.parser import HTMLParser

ROOT=Path(__file__).resolve().parents[1]
UA='F1AnalyticsLocalMedia/1.0 (https://github.com/slataria-hub/formula1; local historical preview)'
TAG='v2026.21.0'
CSV_SHA='8c33f41f7e095e995634305a33b28bd8638366056f877109ffc290d06d341950'
MAX_IMAGE=700000
LICENSES={'CC BY 4.0','CC BY 3.0','CC BY 2.5','CC BY 2.0','CC BY 1.0','CC BY-SA 4.0','CC BY-SA 3.0','CC BY-SA 2.5','CC BY-SA 2.0','CC BY-SA 1.0','CC0','Public domain','PD'}
WIKIDATA='https://www.wikidata.org/w/api.php'
COMMONS='https://commons.wikimedia.org/w/api.php'
WIKIPEDIA='https://en.wikipedia.org/w/api.php'

class Plain(HTMLParser):
    def __init__(self,s):
        super().__init__(); self.parts=[]; self.feed(s)
    def handle_data(self,s): self.parts.append(s)
    def text(self): return ' '.join(''.join(self.parts).split())

def local_path(p):
    p=Path(p).resolve()
    if ROOT/'private' not in p.parents: raise ValueError('output must be under private/')
    return p

def commons_media_url(value):
    # Commons now returns both thumbnail CDN URLs and Special:FilePath redirects.
    if not isinstance(value,str) or not value or any(ord(c)<32 for c in value):return None
    if value.startswith('//'):value='https:'+value
    elif value.startswith('/wiki/Special:FilePath/'):value='https://commons.wikimedia.org'+value
    try:
        p=urllib.parse.urlsplit(value)
        if p.scheme!='https' or p.username is not None or p.password is not None or p.port not in (None,443):return None
        if p.hostname in ('upload.wikimedia.org','thumb.wikimedia.org') and p.path.startswith('/'):return value
        if p.hostname=='commons.wikimedia.org' and p.path.startswith('/wiki/Special:FilePath/'):return value
    except ValueError:pass
    return None

class CommonsRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        safe=commons_media_url(newurl)
        if not safe:raise ValueError('blocked media redirect outside approved Wikimedia hosts')
        return super().redirect_request(req,fp,code,msg,headers,safe)

def read_url(url,limit=MAX_IMAGE,*,media=False):
    if urllib.parse.urlparse(url).scheme!='https': raise ValueError('HTTPS required')
    if media:
        url=commons_media_url(url)
        if not url:raise ValueError('unapproved Wikimedia media URL')
        open_url=urllib.request.build_opener(CommonsRedirect()).open
    else:open_url=urllib.request.urlopen
    for i in range(3):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'*/*'})
            with open_url(req,timeout=45) as r:
                if media and not commons_media_url(r.geturl()):raise ValueError('unapproved final Wikimedia URL')
                raw=r.read(limit+1)
                if len(raw)>limit: raise ValueError('response exceeds size limit')
                return raw
        except urllib.error.HTTPError as e:
            if e.code not in (429,500,502,503,504) or i==2: raise
            delay=int(e.headers.get('Retry-After','0')) if e.headers.get('Retry-After','').isdigit() else 0
            if delay>60:raise
            time.sleep(max(2**i,delay))
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if i==2:raise
            time.sleep(2**i)

def api(url,**kw):
    for i in range(3):
        time.sleep(.4)
        raw=json.loads(read_url(url+'?'+urllib.parse.urlencode(dict(format='json',formatversion=2,maxlag=5,**kw)),5_000_000))
        error=raw.get('error')
        if not error:return raw
        if error.get('code') not in ('maxlag','ratelimited','cirrussearch-too-busy-error') or i==2:raise ValueError('API: '+str(error.get('code')))
        time.sleep(5*(i+1))

def values(entity,prop):
    return [v['mainsnak']['datavalue']['value'] for v in entity.get('claims',{}).get(prop,[]) if v.get('rank')!='deprecated' and 'datavalue' in v.get('mainsnak',{})]

def entities(title):
    result=api(WIKIDATA,action='wbgetentities',sites='enwiki',titles=title,props='claims',redirects='yes')
    return [v for v in result.get('entities',{}).values() if 'missing' not in v]

def photo_file(driver):
    dob=driver.get('birthDate')
    if not dob:return None
    for title in (driver['name'],driver['name']+' (racing driver)',driver['name']+' (Formula One driver)'):
        for ent in entities(title):
            if not any(v.get('time','')[1:11]==dob and v.get('precision',0)>=11 for v in values(ent,'P569') if isinstance(v,dict)):continue
            files=values(ent,'P18')
            if files and isinstance(files[0],str):return files[0]
    return None

# Exact manually reviewed file pages; fallback author only for the same canonical
# filename and the same permitted license. Do not infer authors from uploader names.
REVIEWED_PHOTOS={
    'f1db:cristiano-da-matta':('1973-09-19','Cdmlb06.jpg','CC BY 2.5','DECHUSA Motorsport Photography+ / www.dechusa.tk'),
    'f1db:juan-pablo-montoya':('1975-09-20','J p montoya.jpg','CC BY-SA 3.0','Rick Dikeman'),
    'f1db:patrick-friesacher':('1980-09-26','Patrick Friesacher.jpg','CC BY-SA 2.0','Dan Smith'),
    'f1db:sergey-sirotkin':('1995-08-27','Sergey Sirotkin SMP Racing.jpg','CC0','SMP Racing'),
}
def canonical_file(name):return name.removeprefix('File:').replace('_',' ').strip()

def image_item(file,notes=None,*,reviewed=None):
    notes=[] if notes is None else notes
    result=api(COMMONS,action='query',titles='File:'+file.removeprefix('File:'),redirects=1,prop='imageinfo',iiprop='url|mime|extmetadata',iiurlwidth=320,iiextmetadatalanguage='en')
    for page in result.get('query',{}).get('pages',[]):
        for i in page.get('imageinfo',[]):
            m=i.get('extmetadata',{}); get=lambda k:Plain(str(m.get(k,{}).get('value',''))).text()
            lic=get('LicenseShortName'); author=get('Artist') or get('Credit')
            # A license URL can disambiguate a localized or abbreviated license name.
            link=get('LicenseUrl'); parsed=urllib.parse.urlparse(link)
            if parsed.hostname in ('creativecommons.org','www.creativecommons.org'):
                match=re.fullmatch(r'/licenses/(by|by-sa)/(1\.0|2\.0|2\.5|3\.0|4\.0)/?',parsed.path)
                if match:lic='CC '+match[1].upper()+' '+match[2]
                elif parsed.path.rstrip('/')=='/publicdomain/zero/1.0':lic='CC0'
                elif parsed.path.rstrip('/')=='/publicdomain/mark/1.0':lic='Public domain'
            # Canonical attribution comes from the resolved Commons file title, not a redirect URL.
            title=page.get('title','')
            if reviewed:
                expected_file,expected_license,expected_author=reviewed
                if canonical_file(title)!=canonical_file(expected_file) or lic!=expected_license:
                    notes.append({'file':file,'reason':'reviewed_file_or_license_changed','license':lic});continue
                author=expected_author
            if lic not in LICENSES or (lic.startswith('CC BY') and not author):
                notes.append({'file':file,'reason':'license_or_author','license':lic,'authorPresent':bool(author)});continue
            if not title.startswith('File:'):
                notes.append({'file':file,'reason':'missing_commons_file_title'});continue
            source='https://commons.wikimedia.org/wiki/'+urllib.parse.quote(title.replace(' ','_'))
            candidates=list(dict.fromkeys(u for u in (i.get('thumburl'),i.get('url')) if isinstance(u,str) and u))
            for candidate in candidates:
                url=commons_media_url(candidate)
                if not url:
                    notes.append({'file':file,'reason':'unexpected_image_or_source_host','imageHost':urllib.parse.urlsplit(candidate).hostname});continue
                try:raw=read_url(url,media=True)
                except (OSError,ValueError) as e:
                    notes.append({'file':file,'reason':'image_request_failed','imageHost':urllib.parse.urlsplit(url).hostname,'detail':str(e)});continue
                if raw.startswith(b'\x89PNG\r\n\x1a\n'): mime='png'
                elif raw.startswith(b'\xff\xd8\xff'):mime='jpeg'
                elif raw.startswith(b'RIFF') and raw[8:12]==b'WEBP':mime='webp'
                else:
                    notes.append({'file':file,'reason':'unsupported_image_bytes','imageHost':urllib.parse.urlsplit(url).hostname});continue
                notes.append({'file':file,'reason':'downloaded','imageHost':urllib.parse.urlsplit(url).hostname})
                return dict(src=uri(raw,mime),source=source,author=author or 'Wikimedia Commons',license=lic,licenseUrl=link,file=page.get('title','File:'+file).removeprefix('File:'))
    notes.append({'file':file,'reason':'no_usable_commons_image'})
    return None

def matches_dob(entity,driver):
    dob=driver.get('birthDate')
    return bool(dob and any(v.get('time','')[1:11]==dob and v.get('precision',0)>=11 for v in values(entity,'P569') if isinstance(v,dict)))

def entity_by_id(qid):
    if not re.fullmatch(r'Q[1-9][0-9]*',qid or ''):return []
    result=api(WIKIDATA,action='wbgetentities',ids=qid,props='claims|sitelinks',sitefilter='enwiki')
    return [v for v in result.get('entities',{}).values() if 'missing' not in v]

def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFKD',s.casefold()) if c.isalnum())

def photo_candidates(driver,notes):
    name=driver['name']; alias={'Alexander Albon':'Alex Albon','Kimi Antonelli':'Andrea Kimi Antonelli','Guanyu Zhou':'Zhou Guanyu','Carlos Sainz Jr.':'Carlos Sainz Jr.','Ryo Hirakawa':'Ryō Hirakawa'}.get(name)
    titles=list(dict.fromkeys(t for base in (name,alias) if base for t in (base,base+' (racing driver)',base+' (Formula One driver)')))
    seen=set(); files=[]; matched=False
    def add(ent):
        nonlocal matched
        if not matches_dob(ent,driver):return False
        matched=True
        for f in values(ent,'P18'):
            if isinstance(f,str) and f not in files:files.append(f)
        return True
    # Resolve Wikipedia redirects and confirm the page's Wikidata entity before accepting its lead image.
    try:
        pages=api(WIKIPEDIA,action='query',titles='|'.join(titles),redirects=1,prop='pageprops|pageimages',ppprop='wikibase_item',piprop='name',pilicense='free').get('query',{}).get('pages',[])
    except (OSError,ValueError) as e:
        notes.append({'reason':'wikipedia_lookup_failed','detail':str(e)});pages=[]
    for page in pages:
        qid=page.get('pageprops',{}).get('wikibase_item')
        if not qid:continue
        valid=False
        for ent in entity_by_id(qid):valid=add(ent) or valid
        seen.add(qid)
        if valid and page.get('pageimage') and page['pageimage'] not in files:files.append(page['pageimage'])
    if not files:
        for title in titles[:2]:
            for ent in entities(title):add(ent)
    if not files:
        hits=api(WIKIDATA,action='wbsearchentities',search=name,language='en',type='item',limit=10).get('search',[])
        for h in hits:
            qid=h.get('id'); labels=[h.get('label','')]+h.get('aliases',[])
            # Search fallback requires matching name or alias, not birth date alone.
            if qid in seen or not any(norm(x) in {norm(name),norm(alias or name)} for x in labels if isinstance(x,str)):continue
            for ent in entity_by_id(qid):add(ent)
    if not matched:notes.append({'reason':'no_identity_with_exact_birth_date'})
    elif not files:notes.append({'reason':'identity_verified_but_no_image'})
    return files

def find_photo(driver,notes):
    reviewed=REVIEWED_PHOTOS.get(driver.get('id'))
    if reviewed and driver.get('birthDate')==reviewed[0]:
        try:
            item=image_item(reviewed[1],notes,reviewed=reviewed[1:])
            if item:return item
        except (OSError,ValueError) as e:notes.append({'file':reviewed[1],'reason':'image_request_failed','detail':str(e)})
    for f in photo_candidates(driver,notes):
        try:
            item=image_item(f,notes)
            if item:return item
        except (OSError,ValueError) as e:notes.append({'file':f,'reason':'image_request_failed','detail':str(e)})
    if any(n['reason'] in ('image_request_failed','wikipedia_lookup_failed') for n in notes):raise ValueError('incomplete network lookup; see photoDiagnostics')
    return None

def discover_logo_files(title,name):
    found=list(dict.fromkeys(v for ent in entities(title) for v in values(ent,'P154') if isinstance(v,str)))
    # Commons search yields review candidates only, never approved images.
    for term in dict.fromkeys((title,name+' F1')):
        result=api(COMMONS,action='query',list='search',srnamespace=6,srsearch='intitle:logo '+term.replace('"',''),srlimit=10)
        for row in result.get('query',{}).get('search',[]):
            f=row.get('title','').removeprefix('File:')
            if f and re.search(r'logo|emblem|wordmark',f,re.I) and re.search(r'\.(svg|png|jpg|jpeg|webp)$',f,re.I) and f not in found:found.append(f)
    return found

def uri(raw,mime):return 'data:image/'+mime+';base64,'+base64.b64encode(raw).decode('ascii')

def check_svg(raw):
    if len(raw)>MAX_IMAGE or re.search(br'<!\s*(DOCTYPE|ENTITY)',raw,re.I):raise ValueError('unsafe SVG')
    r=ET.fromstring(raw)
    tags={'svg','g','path','polyline','polygon','line','rect','circle','ellipse','title','desc','metadata'}
    if r.tag.split('}')[-1]!='svg':raise ValueError('not SVG')
    for el in r.iter():
        if el.tag.split('}')[-1] not in tags:raise ValueError('unsupported SVG tag')
        for k,v in el.attrib.items():
            if k.split('}')[-1].lower().startswith('on') or k.split('}')[-1].lower() in ('href','src') or re.search(r'url\s*\(|javascript:|@import',v,re.I):raise ValueError('unsafe SVG attribute')
    return raw

def catalog(archive,data):
    if hashlib.sha256(Path(archive).read_bytes()).hexdigest()!=CSV_SHA:raise ValueError('asset catalog expects original pinned F1DB CSV archive')
    with zipfile.ZipFile(archive) as z:
        rr=list(csv.DictReader(io.TextIOWrapper(z.open('f1db-races.csv'),encoding='utf-8-sig')))
    byid={'f1db:race-'+r['id']:r for r in rr}; layouts=set(); driverids=set(); teams={}
    for e in data['events']:
        if not 2000<=e['season']<=2026:continue
        row=byid.get(e.get('externalEventId'))
        if row and int(row['year'])==e['season'] and 'f1db:'+row['circuitId']==e['circuitId']:layouts.add(row['circuitLayoutId'])
        for s in e['sessions']:
            for r in s['results']:
                driverids.add(r['driverId']);teams.setdefault(r['constructorId'],set()).add(e['season'])
    # Include zero-start entries from championship standings.
    for s in data['standings']:
        if not 2000<=s['season']<=2026:continue
        for r in s['rows']:
            if s['kind']=='drivers':driverids.add(r['entityId'])
            else:teams.setdefault(r['entityId'],set()).add(s['season'])
    return layouts,[d for d in data['drivers'] if d['id'] in driverids],{t['id']:{'name':t['name'],'years':sorted(teams[t['id']])} for t in data['constructors'] if t['id'] in teams}

def circuit_files(z,layout):
    # Accept exact ID with explicit black style only, no fuzzy circuit match.
    out=[]
    for n in z.namelist():
        p=n.lower().split('/'); stem=p[-1].removesuffix('.svg')
        if 'src/assets/circuits/' not in n or not n.lower().endswith('.svg'):continue
        if stem==layout and 'black' in p[:-1]:out.append(n)
        elif stem in (layout+'-black','black-'+layout,layout+'_black','black_'+layout):out.append(n)
        elif stem=='black' and layout in p[:-1]:out.append(n)
    return out

def circuit_item(z,layout,tag=TAG):
    matches=circuit_files(z,layout)
    if len(matches)!=1:return None
    if z.getinfo(matches[0]).file_size>MAX_IMAGE:raise ValueError('oversized SVG')
    raw=check_svg(z.read(matches[0])); source='https://github.com/f1db/f1db/blob/'+tag+'/'+matches[0].split('/',1)[1]
    return dict(src=uri(raw,'svg+xml'),source=source,author='F1DB / Jules Roy',license='CC BY 4.0',licenseUrl='https://creativecommons.org/licenses/by/4.0/')

def validate_pack(pack):
    required={'version','photos','logos','circuits'}
    if pack.get('version')!=1 or not required<=set(pack) or set(pack)-required-{'eventLayouts','countryCodes'}:raise ValueError('bad media pack')
    if 'eventLayouts' in pack:
        mappings=pack['eventLayouts']
        if not isinstance(mappings,dict):raise ValueError('bad event layout map')
        for key,row in mappings.items():
            if not re.fullmatch(r'f1db:race-[0-9]+',key) or not isinstance(row,list) or len(row)!=4 or type(row[0]) is not int or not 2000<=row[0]<=9999 or not isinstance(row[1],str) or not re.fullmatch(r'f1db:[a-z0-9-]+',row[1]) or not isinstance(row[2],str) or not re.fullmatch(r'[a-z0-9-]+',row[2]) or not isinstance(row[3],str) or not re.fullmatch(r'f1db:archive-[0-9a-f]{64}',row[3]):raise ValueError('bad event layout binding')
    if 'countryCodes' in pack:
        if not isinstance(pack['countryCodes'],dict) or any(not isinstance(k,str) or not isinstance(v,str) or not re.fullmatch(r'[a-z]{2}',v) for k,v in pack['countryCodes'].items()):raise ValueError('bad country code map')
    for kind in ('photos','logos','circuits'):
        if not isinstance(pack[kind],dict):raise ValueError('bad media group')
        for key,v in pack[kind].items():
            if not isinstance(key,str) or not isinstance(v,dict) or v.get('license') not in LICENSES or not v.get('source','').startswith('https://') or not v.get('author'):raise ValueError('missing attribution')
            if not isinstance(v.get('src'),str) or len(v['src'])>1_000_000:raise ValueError('image too large')
            mat=re.fullmatch(r'data:image/(png|jpeg|webp|svg\+xml);base64,([A-Za-z0-9+/]+={0,2})',v['src'])
            if not mat:raise ValueError('bad image source')
            raw=base64.b64decode(mat[2],validate=True)
            if mat[1]=='svg+xml':check_svg(raw)
            if mat[1]=='png' and not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('bad PNG')
            if mat[1]=='jpeg' and not raw.startswith(b'\xff\xd8\xff'):raise ValueError('bad JPEG')
            if mat[1]=='webp' and not(raw.startswith(b'RIFF') and raw[8:12]==b'WEBP'):raise ValueError('bad WebP')
            if kind=='logos' and (not isinstance(v.get('years'),list) or not v['years'] or any(type(y)!=int or not 2000<=y<=9999 for y in v['years'])):raise ValueError('logo must have approved years')
            if kind=='logos' and ('@' not in key or not key.rsplit('@',1)[1].isdigit() or int(key.rsplit('@',1)[1]) not in v['years']):raise ValueError('logo key must match approved year')
    return pack

def save(path,pack):
    validate_pack(pack); temp=path.with_suffix('.tmp');temp.write_text(json.dumps(pack,ensure_ascii=False,separators=(',',':')),encoding='utf-8');temp.replace(path)

LOGO_STATUSES={'dated_source','provisional_representative','manufacturer_brand','fan_icon','historical_photo','unverified_season'}
def logo_status(item, record):
    """Only classify the exact downloaded file, never replace image bytes."""
    if not record or canonical_file(item.get('file',''))!=canonical_file(record.get('file','')):
        return 'unverified_season'
    status=record.get('periodStatus','unverified_season')
    if status not in LOGO_STATUSES:raise ValueError('unknown logo status: '+str(status))
    return status

def annotate_logos(pack, records):
    for key,item in pack['logos'].items():
        item['periodStatus']=logo_status(item,records.get(key))

def logo_counts(pack):
    counts={k:0 for k in sorted(LOGO_STATUSES)}
    for item in pack['logos'].values():
        status=item.get('periodStatus','unverified_season')
        counts[status if status in counts else 'unverified_season']+=1
    return counts

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',required=True);p.add_argument('--archive',required=True);p.add_argument('--output',required=True);p.add_argument('--source-zip');p.add_argument('--tracks',action='store_true');p.add_argument('--photos',action='store_true');p.add_argument('--logo-plan',action='store_true');p.add_argument('--approved-logos',help='JSON array of {id,file,years}; exact Commons file and reviewed years');p.add_argument('--logo-catalog',help='Optional exact-file status map for all historical team visuals');p.add_argument('--retry-missing',action='store_true');p.add_argument('--priority-season',type=int,default=2026);p.add_argument('--limit-photos',type=int);p.add_argument('--driver',action='append',help='Exact driver ID for a focused retry');a=p.parse_args()
    if a.limit_photos is not None and a.limit_photos<1:p.error('--limit-photos must be positive')
    data=json.loads(Path(a.baseline).read_text(encoding='utf-8'));out=local_path(a.output);out.mkdir(parents=True,exist_ok=True); file=out/'visual-media.json'; pack=validate_pack(json.loads(file.read_text(encoding='utf-8'))) if file.exists() else {'version':1,'photos':{},'logos':{},'circuits':{}}
    records=json.loads(Path(a.logo_catalog).read_text(encoding='utf-8-sig')) if a.logo_catalog else None
    if records is not None:
        if not isinstance(records,dict) or any(not isinstance(v,dict) or v.get('periodStatus') not in LOGO_STATUSES for v in records.values()):raise ValueError('invalid logo status catalog')
        annotate_logos(pack,records)
    layouts,drivers,teams=catalog(a.archive,data);report={'target':{'layouts':len(layouts),'photos':len(drivers),'teams':len(teams)},'errors':{},'missing':{},'logoReviewRequired':teams,'photoDiagnostics':{}}
    old=out/'media-report.json'; previous=json.loads(old.read_text(encoding='utf-8')) if old.exists() else {}
    report['missing']={k:list(v) for k,v in previous.get('missing',{}).items()}
    report['photoDiagnostics']=dict(previous.get('photoDiagnostics',{}))
    report['logoDiagnostics']=dict(previous.get('logoDiagnostics',{}))
    def checkpoint():
        report['present']={k:len(pack[k]) for k in ('photos','logos','circuits')}
        report['teamVisualTypes']=logo_counts(pack)
        report['teamVisualsPresent']=len(pack['logos'])
        report['historicalLogoReviewPending']=True
        report['coverageMissing']={'layouts':sorted(layouts-set(pack['circuits'])),'photos':[d['id'] for d in drivers if d['id'] not in pack['photos']],'teamSeasons':[key+'@'+str(y) for key,t in teams.items() for y in t['years'] if key+'@'+str(y) not in pack['logos']]}
        tmp=old.with_suffix('.tmp');tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(old)
    def attempt(kind,key,fn):
        if key in pack[kind]:return
        if not a.retry_missing and key in previous.get('missing',{}).get(kind,[]):return
        if key in report['missing'].get(kind,[]):report['missing'][kind].remove(key)
        try:
            item=fn()
            if item:
                pack[kind][key]=item
                try:save(file,pack)
                except Exception:
                    del pack[kind][key];raise
                print('OK',kind,key,flush=True)
            else:report['missing'].setdefault(kind,[]).append(key);print('MISSING',kind,key,flush=True)
        except Exception as e:report['errors'][kind+':'+key]=str(e);print('ERROR',kind,key,str(e),flush=True)
    if a.tracks:
        src=Path(a.source_zip) if a.source_zip else out/'f1db-source.zip'
        if a.source_zip and not src.is_file():
            report['errors']['circuitSource']='supplied source ZIP not found'
        if not src.exists() and not a.source_zip:
            try:src.write_bytes(read_url('https://codeload.github.com/f1db/f1db/zip/refs/tags/'+TAG,200_000_000))
            except Exception as e:report['errors']['circuitSource']=str(e)
        if src.exists():
            try:
                with zipfile.ZipFile(src) as z:
                    for layout in sorted(layouts):attempt('circuits',layout,lambda layout=layout:circuit_item(z,layout))
            except Exception as e:report['errors']['circuitSource']=str(e)
    if a.photos:
        if a.driver and not set(a.driver)<={d['id'] for d in drivers}:p.error('unknown driver ID')
        priority={r['driverId'] for e in data['events'] if e['season']==a.priority_season for s in e['sessions'] for r in s['results']}
        queue=[d for d in sorted(drivers,key=lambda d:(d['id'] not in priority,d['id'])) if (not a.driver or d['id'] in a.driver) and d['id'] not in pack['photos'] and (a.retry_missing or d['id'] not in previous.get('missing',{}).get('photos',[]))]
        for d in queue[:a.limit_photos]:
            notes=[]
            attempt('photos',d['id'],lambda d=d:find_photo(d,notes))
            report['photoDiagnostics'][d['id']]=notes or [{'reason':'downloaded' if d['id'] in pack['photos'] else 'see_errors'}]
            checkpoint()
    # Candidate discovery never authorizes display or assumes historical applicability.
    if a.logo_plan:
        titles={'alfa-romeo':'Alfa Romeo in Formula One','alphatauri':'Scuderia AlphaTauri','alpine':'Alpine F1 Team','arrows':'Arrows Grand Prix International','aston-martin':'Aston Martin in Formula One','audi':'Audi in Formula One','bar':'British American Racing','benetton':'Benetton Formula','bmw-sauber':'BMW Sauber','brawn':'Brawn GP','cadillac':'Cadillac Formula 1 Team','caterham':'Caterham F1 Team','ferrari':'Scuderia Ferrari','force-india':'Force India','haas':'Haas F1 Team','honda':'Honda in Formula One','hrt':'HRT Formula 1 Team','jaguar':'Jaguar Racing','jordan':'Jordan Grand Prix','kick-sauber':'Sauber Motorsport','lotus-f1':'Lotus F1 Team','lotus-racing':'Team Lotus (2010–2011)','manor':'Manor Racing','marussia':'Marussia F1 Team','mclaren':'McLaren','mercedes':'Mercedes-Benz in Formula One','midland':'Midland F1 Racing','minardi':'Minardi','prost':'Prost Grand Prix','racing-bulls':'Racing Bulls','racing-point':'Racing Point F1 Team','rb':'RB Formula One Team','red-bull':'Red Bull Racing','renault':'Renault in Formula One','sauber':'Sauber Motorsport','spyker':'Spyker F1','super-aguri':'Super Aguri F1','toro-rosso':'Scuderia Toro Rosso','toyota':'Toyota Racing (Formula One)','virgin':'Virgin Racing','williams':'Williams Grand Prix Engineering'}
        candidates=[]
        plan=out/'logo-candidates.json'
        old_plan={x['id']:x for x in json.loads(plan.read_text(encoding='utf-8'))} if plan.exists() else {}
        for key,team in teams.items():
            title=titles.get(key.split(':')[-1],team['name']); found=[]
            try:
                found=discover_logo_files(title,team['name'])
            except Exception as e:report['errors']['logoPlan:'+key]=str(e)
            found=list(dict.fromkeys([f['file'] for f in old_plan.get(key,{}).get('candidateFiles',[])]+found))
            candidates.append(dict(id=key,team=team['name'],seasonYears=team['years'],article='https://en.wikipedia.org/wiki/'+urllib.parse.quote(title.replace(' ','_')),candidateFiles=[{'file':f,'source':'https://commons.wikimedia.org/wiki/File:'+urllib.parse.quote(f.replace(' ','_'))} for f in found],approvedYears=[]))
        (out/'logo-candidates.json').write_text(json.dumps(candidates,ensure_ascii=False,indent=2),encoding='utf-8')
    # Actual team logo only after explicit review of file+years.
    if a.approved_logos:
        for x in json.loads(Path(a.approved_logos).read_text(encoding='utf-8-sig')):
            key=x['id']; years=x['years']
            if key not in teams or not years or not set(years)<=set(teams[key]['years']):raise ValueError('invalid reviewed logo years: '+key)
            loaded=[]; notes=[]
            def logo(x=x):
                if not loaded:loaded.append(image_item(x['file'],notes))
                return dict(loaded[0],years=x['years'],periodStatus=logo_status(loaded[0],x)) if loaded[0] else None
            for year in years:
                season_key=key+'@'+str(year)
                should_attempt=season_key not in pack['logos'] and (a.retry_missing or season_key not in previous.get('missing',{}).get('logos',[]))
                attempt('logos',season_key,logo)
                if should_attempt:
                    report['logoDiagnostics'][season_key]=list(notes) or [{'file':x['file'],'reason':'downloaded' if season_key in pack['logos'] else 'see_errors' if 'logos:'+season_key in report['errors'] else 'no_usable_commons_image'}]
                checkpoint()
    if records is not None:annotate_logos(pack,records)
    save(file,pack);checkpoint();print(json.dumps(report['present'],ensure_ascii=False));print('LOCAL MEDIA ONLY; review media-report.json; no publication authorized')
    return 1 if report['errors'] else 0

if __name__=='__main__':raise SystemExit(main())
