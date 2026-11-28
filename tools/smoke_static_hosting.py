"""Private loopback browser smoke; fresh contexts, synthetic forecasts, no publication."""
import argparse
from datetime import datetime, timedelta, timezone
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading

KEY = 'f1-analytics:v2:user:1'
FILES = ['style.css','app.mjs','model.mjs','user.mjs','championship.mjs','media.mjs','official.json','visual-media.json']

class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args): pass


def require(condition, message):
    if not condition: raise AssertionError(message)


def digest(raw): return hashlib.sha256(raw).hexdigest()


def deadline(event, session):
    scheduled=session.get('scheduledAt')
    if scheduled and 'T' in scheduled and re.search(r'(Z|[+-]\d\d:\d\d)$',scheduled):
        return datetime.fromisoformat(scheduled.replace('Z','+00:00'))
    return datetime.fromisoformat(event['date']).replace(tzinfo=timezone.utc)-timedelta(hours=14)


def fixture_event(data):
    for e in reversed(data['events']):
        if e.get('status')!='scheduled' or not e.get('externalEventId'): continue
        s=next((s for s in e['sessions'] if s['kind']=='race' and s['status']=='scheduled' and not s['results']),None)
        if s:
            try: return e,s,deadline(e,s)
            except (ValueError,TypeError,KeyError): continue
    raise ValueError('No scheduled race fixture in supplied identical builds')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--local',required=True);p.add_argument('--pages',required=True,help='parent of formula1/')
    p.add_argument('--profile',choices=['full','circuits-only'],default='full')
    p.add_argument('--chromium',help='optional installed Chromium executable');p.add_argument('--output',required=True)
    a=p.parse_args();report={};servers=[];contexts=[]
    def check(results,label,fn):
        try: fn();results[label]='PASS';return True
        except Exception as e:results[label]='FAIL: '+str(e)[:700];return False
    def blocked(error):
        return any(x in str(error) for x in ('ERR_BLOCKED_BY_ADMINISTRATOR','Executable doesn\'t exist','Operation not permitted','Permission denied','ERR_NETWORK_ACCESS_DENIED'))
    try:
        local=Path(a.local).resolve();pages=Path(a.pages).resolve();sites=[local,pages/'formula1']
        root=Path(__file__).resolve().parents[1]/'private'
        require(all(root.resolve() in s.parents for s in sites),'Smoke requires disposable sites under project private/')
        initial=[(s/'official.json').read_bytes() for s in sites]
        require(initial[0]==initial[1],'official.json differs between builds')
        require((sites[0]/'visual-media.json').read_bytes()==(sites[1]/'visual-media.json').read_bytes(),'media differs between builds')
        data=json.loads(initial[0]);event,session,cutoff=fixture_event(data)
        report['inputs']={'matching_data_and_media':'PASS'}
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            report['environment']='BLOCKED: '+str(exc);return 1
        with sync_playwright() as pw:
            try: browser=pw.chromium.launch(headless=True,executable_path=a.chromium)
            except Exception as exc:
                report['environment']='BLOCKED: '+str(exc)[:800];return 1
            views={}
            for name,directory,suffix,clock in [('root',local,'/',cutoff-timedelta(days=1)),('pages',pages,'/formula1/',cutoff+timedelta(seconds=1))]:
                srv=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(directory)));servers.append(srv)
                threading.Thread(target=srv.serve_forever,daemon=True).start()
                ctx=browser.new_context(accept_downloads=True);contexts.append(ctx);page=ctx.new_page();page.set_default_timeout(10000)
                # Virtual clock is ONLY for synthetic forecast testing, never a proof of real submission.
                page.clock.set_fixed_time(clock)
                errors=[];bad=[];responses=[]
                page.on('pageerror',lambda e,errors=errors:errors.append(str(e)))
                page.on('response',lambda r,rs=responses,b=bad:(rs.append(r.url),b.append(str(r.status)+' '+r.url) if r.status>=400 else None))
                page.on('requestfailed',lambda r,b=bad:b.append(str(r.failure)+' '+r.url))
                url=f'http://127.0.0.1:{srv.server_port}{suffix}';results={};report[name]=results
                try: page.goto(url,wait_until='networkidle',timeout=20000)
                except Exception as exc:
                    results['navigation']=('BLOCKED: ' if blocked(exc) else 'FAIL: ')+str(exc)[:700];continue
                if not check(results,'navigation',lambda:page.locator('[data-tab="gps"]').wait_for()):continue
                views[name]=(page,ctx,url,errors,bad)
                check(results,'assets',lambda:require(all(any(u.endswith('/'+f) for u in responses) for f in FILES),'missing resource'))
                check(results,'initial_empty',lambda:require(page.evaluate('(k)=>localStorage.getItem(k)',KEY) is None,'unexpected stored state in fresh context'))
                def media(selector):
                    im=page.locator(selector).first;im.scroll_into_view_if_needed();page.wait_for_function('(s)=>{const i=document.querySelector(s);return i&&i.complete&&i.naturalWidth>0}',arg=selector)
                check(results,'circuit',lambda:media('.circuit-art img'))
                check(results,'season',lambda:page.select_option('#year',str(event['season']-1 if event['season']-1 in {e['season'] for e in data['events']} else event['season'])))
                check(results,'event',lambda:page.locator('[data-event]').first.click())
                check(results,'event_detail',lambda:page.locator('.gp-track').wait_for())
                check(results,'standings',lambda:page.locator('[data-tab="stand"]').click())
                if a.profile=='full':
                    for k,selector in [('photo','.media-photo'),('logo','.media-logo'),('flag','.media-flag')]:check(results,k,lambda s=selector:media(s))
                else:
                    for k,selector in [('photo','.media-photo'),('logo','.media-logo'),('flag','.media-flag')]:
                        fallback='.media-name small.mu' if k=='flag' else '.media-placeholder'
                        check(results,k,lambda s=selector,f=fallback:require(page.locator(s).count()==0 and page.locator(f).count()>0,'expected textual fallback and no excluded image'))
                for tab in ['table','mates','dash']:check(results,tab,lambda tab=tab:page.locator(f'[data-tab="{tab}"]').click())
                check(results,'charts',lambda:page.locator('[data-dash-mode="charts"]').click())
                check(results,'predictions',lambda:page.locator('[data-dash-mode="predictions"]').click())
            if set(views)=={'root','pages'}:
                src,srcctx,srcurl,_,_=views['root'];dst,dstctx,dsturl,_,_=views['pages'];tr={};report['transfer']=tr
                def state(page):
                    raw=page.evaluate('(k)=>localStorage.getItem(k)',KEY)
                    return json.loads(raw) if raw else None
                def raw_state(page):return page.evaluate('(k)=>localStorage.getItem(k)',KEY)
                def backups(page):return page.evaluate('(k)=>Object.fromEntries(Object.keys(localStorage).filter(x=>x.startsWith(k+":backup:")).map(x=>[x,localStorage.getItem(x)]))',KEY)
                def dash(page):
                    page.locator('[data-tab="dash"]').click();page.locator('[data-dash-mode="predictions"]').click()
                def prediction(page):
                    page.select_option('#year',str(event['season']));page.locator('[data-tab="gps"]').click();page.locator(f'[data-event="{event["id"]}"]').first.click();page.locator('.gp-sessions [data-kind="prediction"]').click()
                def upload(payload,expected):
                    with dst.expect_file_chooser() as fc:dst.locator('[data-user-import]').click()
                    fc.value.set_files({'name':'synthetic-backup.json','mimeType':'application/json','buffer':payload})
                    dst.locator('[role="status"]').filter(has_text=expected).wait_for()
                try:
                    require(srcctx!=dstctx and src.evaluate('location.origin')!=dst.evaluate('location.origin'),'origins/context not independent');tr['independent_origins']='PASS'
                    require(not (state(dst) or {'user':{'predictions':[]}})['user']['predictions'],'destination was not empty');tr['destination_empty']='PASS'
                    prediction(src);ids=[]
                    for _ in range(2):
                        option=src.locator('#pred-driver option').first.get_attribute('value');require(bool(option),'no synthetic pick available');ids.append(option);src.locator('[data-pred-add]').click()
                    src.locator('[data-pred-save]').click();src.locator('[role="status"]').filter(has_text='Прогноз сохранён').wait_for()
                    saved=state(src);require(len(saved['user']['predictions'])==1,'expected nonempty single forecast');record=saved['user']['predictions'][0]
                    require(record['driverIds']==ids and record['sessionId']==session['id'],'source picks or session mismatch');require(saved['bindings'][session['id']]['externalEventId']==event['externalEventId'],'source stable identity mismatch');tr['source_prediction']='PASS'
                    dash(src)
                    with src.expect_download() as dl:src.locator('[data-user-export]').click()
                    exported=Path(dl.value.path()).read_bytes();require(json.loads(exported)==saved,'export does not equal source state');tr['export']='PASS'
                    other_year=next((y for y in sorted({e['season'] for e in data['events']}) if y!=event['season']),event['season']);dst.select_option('#year',str(other_year));dst.select_option('#theme','dark');dash(dst);before=state(dst);require(before and not before['user']['predictions'],'destination setup not empty');before_raw=raw_state(dst);before_backups=backups(dst)
                    dialogs=[];dst.on('dialog',lambda d:(dialogs.append(d.message),d.accept()))
                    upload(exported,'Импорт завершён');actual=state(dst);require(actual['user']['predictions']==[record],'forecast content changed')
                    require(actual['bindings'][session['id']]=={**saved['bindings'][session['id']],'imported':True},'stable binding or provenance mismatch');tr['import_content_and_binding']='PASS'
                    require(actual['user']['preferences']==before['user']['preferences'],'destination preferences changed');require(dst.locator('#theme').input_value()=='dark','theme control changed');tr['preferences']='PASS'
                    after_backups=backups(dst);new=set(after_backups)-set(before_backups);require(len(new)==1 and json.loads(after_backups[new.pop()])==json.loads(before_raw),'backup does not match pre-import state');tr['backup']='PASS'
                    dst.select_option('#year',str(event['season']));dash(dst);dst.locator(f'[data-pred-event="{event["id"]}"]').click();names={d['id']:d['name'] for d in data['drivers']};require(dst.locator('.pred-list li .media-name > span').all_text_contents()==[names[i] for i in ids],'imported forecast UI content/order mismatch');require(dst.get_by_text('своевременность не подтверждена',exact=False).count()>0,'missing retrospective label');require(dst.locator('[data-pred-save]').count()==0,'import bypasses edit deadline');tr['historical_ui_and_lock']='PASS'
                    dash(dst);after=raw_state(dst);n=len(dialogs);upload(exported,'Импорт: изменений нет.');require(raw_state(dst)==after and backups(dst)==after_backups and len(dialogs)==n,'repeat changed state or created redundant backup');tr['repeat']='PASS'
                    conflict=json.loads(exported);conflict['user']['predictions'][0]['driverIds'].reverse();upload(json.dumps(conflict).encode(),'Конфликт прогноза');require(raw_state(dst)==after and backups(dst)==after_backups and len(dialogs)==n,'conflicting input modified storage');tr['conflict']='PASS'
                    # Force a distinct status for malformed input; require a parse error, not just any click.
                    upload(b'{broken',re.compile(r'JSON|Expected|Unexpected|property|position|syntax',re.I));require(raw_state(dst)==after and backups(dst)==after_backups and len(dialogs)==n,'broken input modified storage');tr['corrupt']='PASS'
                    require(state(src)==saved,'destination changed source storage');tr['source_unchanged']='PASS'
                    for i,(page,url) in enumerate([(src,srcurl),(dst,dsturl)]):
                        res=page.request.get(url+'official.json');require(res.ok and digest(res.body())==digest(initial[i]),'served sports data changed');require((sites[i]/'official.json').read_bytes()==initial[i],'disk sports data changed')
                    tr['sports_unchanged']='PASS'
                except Exception as exc:tr['transaction']='FAIL: '+str(exc)[:800]
                finally:
                    # Check entire session, including the transfer, not only initial navigation.
                    for name,(_,_,_,errors,bad) in views.items():
                        check(report[name],'http_errors',lambda b=bad:require(not b,str(b)))
                        check(report[name],'js_errors',lambda e=errors:require(not e,str(e)))
            else:
                report['transfer']={'transaction':'BLOCKED: navigation unavailable in one or both contexts' if any('BLOCKED' in str(report.get(k,{})) for k in ('root','pages')) else 'FAIL: prerequisite navigation failed'}
            for ctx in contexts:ctx.close()
            browser.close()
    except Exception as exc:report['environment']=('BLOCKED: ' if blocked(exc) else 'FAIL: ')+str(exc)[:1000]
    finally:
        for srv in servers:srv.shutdown();srv.server_close()
        Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))
    required={'inputs','root','pages','transfer'}
    return 0 if set(report)==required and all(isinstance(v,dict) and v and all(x=='PASS' for x in v.values()) for v in report.values()) else 1

if __name__=='__main__':raise SystemExit(main())
