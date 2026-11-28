import sys, unittest, tempfile, zipfile, json
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'tools'))
import collect_media as mod

class MediaTests(unittest.TestCase):
    def test_svg_rejects_script_and_external(self):
        for x in [b'<svg><script/></svg>',b'<svg><path style="fill:url(https://x)"/></svg>',b'<svg><path onload="x"/></svg>',b'<!DOCTYPE svg><svg/>']:
            with self.assertRaises(ValueError):mod.check_svg(x)
    def test_exact_layout_not_modern_layout(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.zip'
            with zipfile.ZipFile(p,'w') as z:
                for name in ['black/monza-1.svg','white/monza-1.svg','black/monza-2.svg']:
                    z.writestr('repo/src/assets/circuits/'+name,'<svg><path d="M0 0L10 10"/></svg>')
            with zipfile.ZipFile(p) as z:
                self.assertEqual(len(mod.circuit_files(z,'monza-1')),1);self.assertIsNone(mod.circuit_item(z,'monza-3'));self.assertEqual(mod.circuit_item(z,'monza-1')['license'],'CC BY 4.0')
    def test_dob_check(self):
        def val(v):return {'mainsnak':{'datavalue':{'value':v}}}
        d={'name':'Test Driver','birthDate':'1980-02-02'}
        bad={'claims':{'P569':[val({'time':'+1981-02-02T00:00:00Z','precision':11})],'P18':[val('wrong.jpg')]}}
        good={'claims':{'P569':[val({'time':'+1980-02-02T00:00:00Z','precision':11})],'P18':[val('right.jpg')]}}
        with patch.object(mod,'entities',return_value=[bad,good]):self.assertEqual(mod.photo_file(d),'right.jpg')
        with patch.object(mod,'entities',return_value=[bad]):self.assertIsNone(mod.photo_file(d))
    def test_pack_rejects_remote_and_missing_license(self):
        p={'version':1,'photos':{'x':{'src':'https://example.org/a.jpg','author':'A','license':'CC BY 4.0','source':'https://example.org'}},'logos':{},'circuits':{}}
        with self.assertRaises(ValueError):mod.validate_pack(p)
        p['photos']['x']['src']=mod.uri(b'\xff\xd8\xffabc','jpeg');self.assertIs(mod.validate_pack(p),p)
        p['photos']['x']['license']='Fair use';
        with self.assertRaises(ValueError):mod.validate_pack(p)
    def test_logo_year_required(self):
        p={'version':1,'photos':{},'logos':{'x@2000':{'src':mod.uri(b'\xff\xd8\xffa','jpeg'),'author':'A','source':'https://example.org','license':'CC BY 4.0'}},'circuits':{}}
        with self.assertRaises(ValueError):mod.validate_pack(p)
        p['logos']['x@2000']['years']=[2000];mod.validate_pack(p)
    def test_build_default_empty_pack(self):
        p=json.loads((ROOT/'web/preview/visual-media.json').read_text());self.assertEqual(mod.validate_pack(p),p);self.assertFalse(p['photos'])

class MediaRecoveryTests(unittest.TestCase):
    @staticmethod
    def ent(dob,files):
        def val(v):return {'mainsnak':{'datavalue':{'value':v}}}
        return {'claims':{'P569':[val({'time':'+'+dob+'T00:00:00Z','precision':11})],'P18':[val(f) for f in files]}}
    def test_redirect_lead_and_multiple_candidates(self):
        page={'query':{'pages':[{'pageprops':{'wikibase_item':'Q1'},'pageimage':'lead.jpg'}]}}
        with patch.object(mod,'api',return_value=page),patch.object(mod,'entity_by_id',return_value=[self.ent('1980-02-02',['first.jpg','second.jpg'])]):
            self.assertEqual(mod.photo_candidates({'name':'Test','birthDate':'1980-02-02'},[]),['first.jpg','second.jpg','lead.jpg'])
    def test_reject_wrong_person_lead_image(self):
        page={'query':{'pages':[{'pageprops':{'wikibase_item':'Q1'},'pageimage':'wrong.jpg'}]}}
        with patch.object(mod,'api',side_effect=[page,{'search':[]}]),patch.object(mod,'entity_by_id',return_value=[self.ent('1981-02-02',['wrong.jpg'])]),patch.object(mod,'entities',return_value=[]):
            notes=[];self.assertEqual(mod.photo_candidates({'name':'Test','birthDate':'1980-02-02'},notes),[]);self.assertEqual(notes[0]['reason'],'no_identity_with_exact_birth_date')
    def test_try_next_image(self):
        with patch.object(mod,'photo_candidates',return_value=['first.jpg','second.jpg']),patch.object(mod,'image_item',side_effect=[None,{'file':'second.jpg'}]):
            self.assertEqual(mod.find_photo({},[])['file'],'second.jpg')
    def test_license_url_normalization_and_diagnostic(self):
        result={'query':{'pages':[{'title':'File:Test.jpg','imageinfo':[{'thumburl':'https://upload.wikimedia.org/x.jpg','descriptionurl':'https://commons.wikimedia.org/wiki/File:Test.jpg','extmetadata':{'LicenseShortName':{'value':'localized'},'LicenseUrl':{'value':'https://creativecommons.org/licenses/by-sa/4.0/'},'Artist':{'value':'<b>Author</b>'}}}]}]}}
        with patch.object(mod,'api',return_value=result),patch.object(mod,'read_url',return_value=b'\xff\xd8\xffabc'):
            self.assertEqual(mod.image_item('Test.jpg')['license'],'CC BY-SA 4.0')
            result['query']['pages'][0]['imageinfo'][0]['extmetadata']['LicenseUrl']['value']='https://example.org/nonfree'
            notes=[];self.assertIsNone(mod.image_item('Test.jpg',notes));self.assertEqual(notes[0]['reason'],'license_or_author')
    def test_retry_tls_error(self):
        import urllib.error
        class Response:
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,n):return b'ok'
        with patch.object(mod.urllib.request,'urlopen',side_effect=[urllib.error.URLError('timeout'),Response()]) as f,patch.object(mod.time,'sleep'):
            self.assertEqual(mod.read_url('https://example.org'),b'ok');self.assertEqual(f.call_count,2)
    def test_maxlag_retry(self):
        with patch.object(mod,'read_url',side_effect=[b'{"error":{"code":"maxlag"}}',b'{"ok":true}']),patch.object(mod.time,'sleep'):
            self.assertTrue(mod.api(mod.COMMONS,action='query')['ok'])
    def test_logo_candidates_not_arbitrary_files(self):
        result={'query':{'search':[{'title':'File:Example logo.svg'},{'title':'File:Example car.jpg'},{'title':'File:Example logo.exe'}]}}
        with patch.object(mod,'entities',return_value=[]),patch.object(mod,'api',return_value=result):
            self.assertEqual(mod.discover_logo_files('Example F1','Example'),['Example logo.svg'])
    def test_transient_failure_not_silent_missing(self):
        with patch.object(mod,'photo_candidates',return_value=['first.jpg']),patch.object(mod,'image_item',side_effect=TimeoutError('TLS')):
            notes=[]
            with self.assertRaisesRegex(ValueError,'incomplete network'):mod.find_photo({},notes)
            self.assertEqual(notes[0]['reason'],'image_request_failed')

class ThumbnailHostTests(unittest.TestCase):
    def response(self, thumb, original=None):
        i={'thumburl':thumb,'descriptionurl':'https://commons.wikimedia.org/wiki/File:Test.jpg','extmetadata':{'LicenseShortName':{'value':'CC BY 4.0'},'Artist':{'value':'Photographer'}}}
        if original:i['url']=original
        return {'query':{'pages':[{'title':'File:Test.jpg','imageinfo':[i]}]}}
    def test_current_thumbnail_hosts(self):
        for url in ['https://thumb.wikimedia.org/example.jpg','https://commons.wikimedia.org/wiki/Special:FilePath/Test.jpg?width=320','https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Test.jpg/320px-Test.jpg','//thumb.wikimedia.org/example.jpg','/wiki/Special:FilePath/Test.jpg?width=320']:
            with self.subTest(url=url),patch.object(mod,'api',return_value=self.response(url)),patch.object(mod,'read_url',return_value=b'\xff\xd8\xffabc') as read:
                notes=[]; item=mod.image_item('Test.jpg',notes)
                self.assertEqual(item['source'],'https://commons.wikimedia.org/wiki/File%3ATest.jpg');self.assertEqual(notes[-1]['reason'],'downloaded');read.assert_called_once_with(mod.commons_media_url(url),media=True)
    def test_reject_untrusted_hosts_and_paths(self):
        for url in ['http://thumb.wikimedia.org/a.jpg','https://thumb.wikimedia.org.evil.test/a.jpg','https://thumb.wikimedia.org@evil.test/a.jpg','https://evil.test@thumb.wikimedia.org/a.jpg','https://thumb.wikimedia.org:444/a.jpg','https://commons.wikimedia.org/w/api.php','https://127.0.0.1/a.jpg']:
            with self.subTest(url=url),patch.object(mod,'api',return_value=self.response(url)),patch.object(mod,'read_url') as read:
                self.assertIsNone(mod.image_item('Test.jpg',[]));read.assert_not_called()
    def test_fallback_to_original_if_thumbnail_fails(self):
        thumb='https://thumb.wikimedia.org/example.jpg'; original='https://upload.wikimedia.org/wikipedia/commons/a/ab/Test.jpg'
        with patch.object(mod,'api',return_value=self.response(thumb,original)),patch.object(mod,'read_url',side_effect=[ValueError('response exceeds size limit'),b'\xff\xd8\xffabc']) as read:
            notes=[];self.assertIsNotNone(mod.image_item('Test.jpg',notes));self.assertEqual(read.call_count,2);self.assertEqual(notes[0]['reason'],'image_request_failed')
    def test_reject_html_even_on_approved_host(self):
        with patch.object(mod,'api',return_value=self.response('https://thumb.wikimedia.org/a.jpg')),patch.object(mod,'read_url',return_value=b'<html>error</html>'):
            notes=[];self.assertIsNone(mod.image_item('Test.jpg',notes));self.assertEqual(notes[0]['reason'],'unsupported_image_bytes')
    def test_redirect_validated_before_request(self):
        import urllib.request
        handler=mod.CommonsRedirect(); req=urllib.request.Request('https://commons.wikimedia.org/wiki/Special:FilePath/Test.jpg')
        new=handler.redirect_request(req,None,302,'',{},'https://thumb.wikimedia.org/a.jpg')
        self.assertEqual(new.full_url,'https://thumb.wikimedia.org/a.jpg')
        for target in ['https://example.org/a.jpg','http://upload.wikimedia.org/a.jpg','https://commons.wikimedia.org/wiki/Main_Page']:
            with self.assertRaises(ValueError):handler.redirect_request(req,None,302,'',{},target)
    def test_final_url_checked_before_reading(self):
        from unittest.mock import MagicMock
        response=MagicMock();response.__enter__.return_value=response;response.geturl.return_value='https://evil.test/image.jpg'
        opener=MagicMock();opener.open.return_value=response
        with patch.object(mod.urllib.request,'build_opener',return_value=opener):
            with self.assertRaisesRegex(ValueError,'final Wikimedia URL'):mod.read_url('https://thumb.wikimedia.org/a.jpg',media=True)
            response.read.assert_not_called()
    def test_media_size_limit(self):
        from unittest.mock import MagicMock
        response=MagicMock();response.__enter__.return_value=response;response.geturl.return_value='https://thumb.wikimedia.org/a.jpg';response.read.return_value=b'x'*11
        opener=MagicMock();opener.open.return_value=response
        with patch.object(mod.urllib.request,'build_opener',return_value=opener):
            with self.assertRaisesRegex(ValueError,'size limit'):mod.read_url('https://thumb.wikimedia.org/a.jpg',10,media=True)

class ReviewedPhotoTests(unittest.TestCase):
    def test_manual_author_only_for_exact_file_and_license(self):
        f='Patrick Friesacher.jpg'
        review=(f,'CC BY-SA 2.0','Dan Smith')
        page={'title':'File:'+f,'imageinfo':[{'thumburl':'https://thumb.wikimedia.org/a.jpg','extmetadata':{'LicenseShortName':{'value':'CC BY-SA 2.0'}}}]}
        result={'query':{'pages':[page]}}
        with patch.object(mod,'api',return_value=result),patch.object(mod,'read_url',return_value=b'\xff\xd8\xffabc') as read:
            self.assertEqual(mod.image_item(f,reviewed=review)['author'],'Dan Smith')
            page['title']='File:Different.jpg';self.assertIsNone(mod.image_item(f,reviewed=review))
            page['title']='File:'+f;page['imageinfo'][0]['extmetadata']['LicenseShortName']['value']='Fair use';self.assertIsNone(mod.image_item(f,reviewed=review))
            self.assertEqual(read.call_count,1)
    def test_reviewed_photo_requires_exact_driver_and_dob(self):
        d={'id':'f1db:juan-pablo-montoya','birthDate':'1975-09-20'}
        with patch.object(mod,'image_item',return_value={'file':'J p montoya.jpg'}) as image,patch.object(mod,'photo_candidates',return_value=[]) as auto:
            self.assertEqual(mod.find_photo(d,[])['file'],'J p montoya.jpg');auto.assert_not_called()
            d['birthDate']='1975-09-21';self.assertIsNone(mod.find_photo(d,[]));self.assertEqual(image.call_count,1)
    def test_temporary_search_overload_retries(self):
        with patch.object(mod,'read_url',side_effect=[b'{"error":{"code":"cirrussearch-too-busy-error"}}',b'{"ok":true}']),patch.object(mod.time,'sleep'):
            self.assertTrue(mod.api(mod.COMMONS,action='query')['ok'])
    def test_logo_batch_unique_years_and_matches_report(self):
        rows=json.loads((ROOT/'references/f1-logo-reviewed-batch-01.json').read_text())
        keys=[(r['id'],y) for r in rows for y in r['years']]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertEqual(len(keys),7)
    def test_logo_diagnostics_for_multiple_seasons(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); base=root/'base.json'; base.write_text('{}'); out=root/'out'; approvals=root/'approved.json'
            approvals.write_text(json.dumps([{'id':'f1db:test','file':'test.png','years':[2015,2016]}]))
            def reject(file,notes):
                notes.append({'file':file,'reason':'license_or_author','license':'Unknown'});return None
            with patch.object(mod,'local_path',return_value=out),patch.object(mod,'catalog',return_value=(set(),[],{'f1db:test':{'years':[2015,2016]}})),patch.object(mod,'image_item',side_effect=reject) as loader,patch.object(sys,'argv',['collect_media.py','--baseline',str(base),'--archive','unused','--output',str(out),'--approved-logos',str(approvals),'--retry-missing']):
                self.assertEqual(mod.main(),0);self.assertEqual(loader.call_count,1)
            r=json.loads((out/'media-report.json').read_text())
            self.assertEqual(r['present']['logos'],0)
            for year in [2015,2016]:self.assertEqual(r['logoDiagnostics'][f'f1db:test@{year}'][0]['reason'],'license_or_author')

class LogoStatusTests(unittest.TestCase):
    def test_exact_file_only_no_image_replacement(self):
        item={'file':'Team logo.png','src':'unchanged'}
        pack={'logos':{'f1db:x@2000':item,'f1db:x@2001':dict(item)}}
        mod.annotate_logos(pack,{'f1db:x@2000':{'file':'Team_logo.png','periodStatus':'historical_photo'},'f1db:x@2001':{'file':'different.png','periodStatus':'dated_source'}})
        self.assertEqual(item['src'],'unchanged');self.assertEqual(item['periodStatus'],'historical_photo')
        self.assertEqual(pack['logos']['f1db:x@2001']['periodStatus'],'unverified_season')
        self.assertEqual(mod.logo_counts(pack)['historical_photo'],1)
    def test_catalog_covers_all_slots_and_new_status(self):
        rows=json.loads((ROOT/'references/f1-logo-reviewed-batch-07.json').read_text())
        catalog=json.loads((ROOT/'references/f1-logo-status-catalog.json').read_text())
        keys=[f"{r['id']}@{y}" for r in rows for y in r['years']]
        self.assertEqual(len(keys),57);self.assertEqual(len(set(keys)),57);self.assertEqual(len(catalog),286)
        self.assertEqual(sum(catalog[k]['periodStatus']=='historical_photo' for k in keys),22)
        self.assertEqual(sum(catalog[k]['periodStatus']=='fan_icon' for k in keys),14)
    def test_reject_unknown_status(self):
        with self.assertRaises(ValueError):mod.logo_status({'file':'x'},{'file':'x','periodStatus':'invented'})
    def test_local_catalog_migration_and_new_visual(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); base=root/'base.json'; base.write_text('{}'); out=root/'out';out.mkdir(); approvals=root/'approved.json'; status=root/'status.json'
            existing=dict(file='Existing.png',src=mod.uri(b'\x89PNG\r\n\x1a\nabc','png'),author='A',license='CC BY 4.0',source='https://commons.wikimedia.org/wiki/File:Existing.png',years=[2000]); new=dict(existing,file='New.jpg',src=mod.uri(b'\xff\xd8\xffabc','jpeg'))
            mod.save(out/'visual-media.json',{'version':1,'photos':{},'circuits':{},'logos':{'f1db:test@2000':existing}})
            approvals.write_text(json.dumps([{'id':'f1db:test','file':'New.jpg','years':[2001],'periodStatus':'historical_photo'}]))
            status.write_text(json.dumps({'f1db:test@2000':{'file':'Existing.png','periodStatus':'manufacturer_brand'},'f1db:test@2001':{'file':'New.jpg','periodStatus':'historical_photo'}}))
            with patch.object(mod,'local_path',return_value=out),patch.object(mod,'catalog',return_value=(set(),[],{'f1db:test':{'years':[2000,2001]}})),patch.object(mod,'image_item',return_value=new) as loader,patch.object(sys,'argv',['collect_media.py','--baseline',str(base),'--archive','unused','--output',str(out),'--approved-logos',str(approvals),'--logo-catalog',str(status),'--retry-missing']):
                self.assertEqual(mod.main(),0);self.assertEqual(loader.call_count,1)
            pack=json.loads((out/'visual-media.json').read_text()); report=json.loads((out/'media-report.json').read_text())
            self.assertEqual(pack['logos']['f1db:test@2000']['src'],existing['src']);self.assertEqual(report['teamVisualTypes']['manufacturer_brand'],1);self.assertEqual(report['teamVisualTypes']['historical_photo'],1);self.assertEqual(report['coverageMissing']['teamSeasons'],[])
