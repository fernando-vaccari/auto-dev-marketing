from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import httpx

from app.config import Settings
from app.reels.service import ReelService
from app.reels.instagram import ReelMetaClient
from app.reels.tools import ReelError


class InstagramTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.service=ReelService(Settings(data_dir=Path(self.temp.name),password='test-password',reels_min_free_mb=0))
        self.pub=self.service.publishing
        self.config={'mode':'live','account_id':'123','api_version':'v26.0','enabled':True,'business_login_confirmed':True,'permissions_confirmed':True,'revision':1}
        self.service.preferences.set('instagram',self.config)
        self.job=self.service.library.create_job({'title':'Teste','cta':'Acompanhe'},origin='web')
        directory=self.service.library.root/'jobs'/self.job/'deliverables';directory.mkdir(parents=True)
        self.path=directory/'reel.mp4';self.path.write_bytes(b'fixture-mp4-transport-only')
        self.service.library.update_job(self.job,'ready','ready',100)
        self.pub.register(self.job)
        self.pub.approve(self.job,True,authorize_live=True)
        self.requests=[];self.processing=False;self.fail=None

    async def handler(self,request):
        body=await request.aread();self.requests.append((request.method,request.url.path,body))
        if self.fail and request.url.path.endswith('/media_publish'):
            if self.fail=='timeout':raise httpx.ReadTimeout('token must not leak',request=request)
            return httpx.Response(500,json={'error':{'code':2,'message':'secret-token'}})
        if request.url.host=='rupload.facebook.com':
            self.assertEqual(body,self.path.read_bytes())
            self.assertEqual(request.headers['offset'],'0')
            self.assertEqual(request.headers['file_size'],str(len(body)))
            return httpx.Response(200,json={'success':True})
        if request.url.path.endswith('/media'):return httpx.Response(200,json={'id':'456'})
        if request.url.path.endswith('/media_publish'):return httpx.Response(200,json={'id':'789'})
        if request.url.path.endswith('/456'):return httpx.Response(200,json={'status_code':'IN_PROGRESS' if self.processing else 'FINISHED'})
        return httpx.Response(200,json={'id':'123','username':'test','data':[]})

    def client(self):
        settings=Settings(data_dir=Path(self.temp.name),meta_token='secret-token',instagram_id='123',api_version='v26.0')
        return ReelMetaClient(settings,transport=httpx.MockTransport(self.handler),poll_seconds=0,poll_attempts=1)

    async def tick(self):
        self.pub.client_factory=self.client
        with patch('app.reels.instagram.probe',return_value={}):await self.pub.tick()

    async def test_official_upload_processing_publish_and_duplicate_prevention(self):
        await self.tick();await self.tick()
        result=self.pub.history()[0]
        self.assertEqual(result['status'],'published')
        self.assertEqual(result['media_id'],'789')
        self.assertEqual(sum(path.endswith('/media_publish') for _,path,_ in self.requests),1)
        self.assertTrue(any(path=='/ig-api-upload/v26.0/456' for _,path,_ in self.requests))
        creation=next(body for _,path,body in self.requests if path.endswith('/media'))
        self.assertIn(b'media_type=REELS',creation);self.assertIn(b'upload_type=resumable',creation)

    async def test_processing_pending_reuses_container_without_duplicate_upload(self):
        self.processing=True;await self.tick()
        self.assertEqual(self.pub.history()[0]['status'],'waiting')
        self.processing=False;await self.tick()
        self.assertEqual(self.pub.history()[0]['status'],'published')
        self.assertEqual(sum('/ig-api-upload/' in path for _,path,_ in self.requests),1)

    async def test_ambiguous_publish_timeout_never_retries_and_redacts_errors(self):
        self.fail='timeout';await self.tick();await self.tick()
        delivery=self.pub.history()[0]
        self.assertEqual(delivery['status'],'review_required')
        self.assertNotIn('secret-token',delivery['error'])
        self.assertEqual(sum(path.endswith('/media_publish') for _,path,_ in self.requests),1)
        with self.assertRaises(ReelError):self.pub.approve(self.job,True,True)

    async def test_expired_token_permission_rate_limit_and_upload_failures(self):
        for code in (190,200,4):
            async def denied(request):return httpx.Response(400,json={'error':{'code':code,'message':'secret-token'}})
            client=ReelMetaClient(Settings(data_dir=Path(self.temp.name),instagram_id='123'),transport=httpx.MockTransport(denied))
            with self.assertRaises(Exception) as raised:await client.account()
            self.assertNotIn('secret-token',str(raised.exception))
            self.assertIn(str(code),str(raised.exception))
        async def bad_upload(request):return httpx.Response(400,json={'success':False})
        client=ReelMetaClient(Settings(data_dir=Path(self.temp.name)),transport=httpx.MockTransport(bad_upload))
        with self.assertRaises(Exception):await client.upload_reel('456',self.path)

    async def test_demo_never_contacts_meta_and_live_requires_explicit_approval(self):
        self.service.preferences.set('instagram',self.config|{'mode':'demo'})
        self.pub.approve(self.job,True)
        await self.tick()
        self.assertEqual(self.pub.history()[0]['status'],'simulated')
        self.assertEqual(self.requests,[])
        another=self.service.library.create_job({'title':'Teste'},origin='web')
        self.service.library.update_job(another,'ready','ready',100)
        self.service.preferences.set('instagram',self.config)
        self.pub.register(another)
        with self.assertRaises(ReelError):self.pub.approve(another,True)

    async def test_account_change_and_paused_rule_revoke_queued_authorization(self):
        self.service.preferences.set('instagram',self.config|{'revision':2})
        await self.tick()
        self.assertEqual(self.pub.history()[0]['status'],'review_required')
        self.assertEqual(self.requests,[])
