"""Read-only HTTP hash smoke for an already approved deployment (never deploys)."""
import argparse, os, time, urllib.request
from pathlib import Path
from pages_release import resolve, sha
BASE='https://slataria-hub.github.io/formula1/'
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*a,**k):raise ValueError('unexpected redirect')
def check(files,attempts=6):
    opener=urllib.request.build_opener(NoRedirect())
    for i in range(attempts):
        try:
            for name,raw in sorted(files.items()):
                url=BASE+('' if name=='index.html' else name)
                with opener.open(urllib.request.Request(url,headers={'Cache-Control':'no-cache','Accept-Encoding':'identity'}),timeout=30) as r:
                    if r.status!=200 or r.geturl()!=url or sha(r.read(len(raw)+1))!=sha(raw):raise ValueError('HTTP payload mismatch: '+name)
            return
        except (OSError,ValueError):
            if i+1==attempts:raise
            time.sleep(15)
def require(condition,message):
    if not condition:raise ValueError(message)
def browser_check(files,chromium=None):
    from playwright.sync_api import sync_playwright
    import json
    d=json.loads(files['official.json']);pack=json.loads(files['visual-media.json']);years=sorted({e['season'] for e in d['events']})
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path=chromium)
        context=browser.new_context();page=context.new_page();bad=[];errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('response',lambda r:bad.append(r.status) if r.status>=400 else None)
        page.on('requestfailed',lambda r:bad.append(r.failure))
        page.goto(BASE,wait_until='networkidle',timeout=30000)
        page.locator('[data-tab="gps"]').wait_for()
        require(page.locator('#year option').all_text_contents()==[str(y) for y in years],'year options mismatch')
        require(page.evaluate("localStorage.getItem('f1-analytics:v2:user:1')") is None,'unexpected local state')
        page.select_option('#year',str(years[-1]));page.locator('[data-event]').first.click();page.locator('.gp-track').wait_for()
        page.locator('[data-tab="stand"]').click()
        if not pack['photos']:require(not page.locator('.media-photo').count() and page.locator('.media-placeholder').count()>0,'photo fallback')
        if not pack['logos']:require(not page.locator('.media-logo').count() and page.locator('.media-placeholder').count()>0,'logo fallback')
        if b'export const FLAGS={};' in files['media.mjs']:require(not page.locator('.media-flag').count(),'flag fallback')
        for tab in ('table','mates','dash'):page.locator(f'[data-tab="{tab}"]').click()
        page.locator('[data-dash-mode="charts"]').click();page.locator('[data-dash-mode="predictions"]').click()
        require(not bad and not errors,'browser resource or JS failure')
        context.close();browser.close()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--release-commit',required=True);p.add_argument('--browser',action='store_true');p.add_argument('--chromium');a=p.parse_args()
    try:
        files,_=resolve(Path(__file__).resolve().parents[1],a.release_commit,os.environ.get('F1_APPROVAL_SHA256',''));check(files);print('POST_DEPLOY_HTTP_PASS')
        if a.browser:browser_check(files,a.chromium);print('POST_DEPLOY_BROWSER_PASS')
        return 0
    except Exception as exc:print('POST_DEPLOY_BLOCKED_OR_FAILED:',type(exc).__name__);return 1
if __name__=='__main__':raise SystemExit(main())
