from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.reels.service import ReelService


class StudioSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.settings=Settings(data_dir=Path(self.temp.name),password='test-password-security',reels_min_free_mb=0)
        self.app=create_app(self.settings,scheduler=False,reels_worker=False)
        self.client=TestClient(self.app);self.addCleanup(self.client.close)

    def login(self):self.client.post('/api/login',json={'password':self.settings.password})

    def test_new_routes_are_authenticated_and_origin_protected(self):
        for method,path in [('GET','assets/'+'a'*32+'/preview'),('GET','summary'),('GET','preferences'),('PUT','preferences'),('GET','instagram/config'),('PUT','instagram/config'),('POST','instagram/check'),('GET','deliveries'),('POST','voice-preview'),('POST','analyze'),('GET','capture/package'),('POST','capture/start'),('POST','capture/unknown/stop'),('GET','schedules'),('POST','schedules'),('GET','schedule-history')]:
            with self.subTest(path=path):self.assertEqual(self.client.request(method,'/api/reels/'+path).status_code,401)
        self.login()
        self.assertEqual(self.client.put('/api/reels/instagram/config',json={},headers={'Origin':'https://evil.invalid'}).status_code,403)

    def test_credentials_are_write_only_encrypted_and_existing_values_are_preserved(self):
        self.login();secret='example-secret-never-returned'
        response=self.client.put('/api/reels/instagram/config',json={'token':secret,'account_id':'123','mode':'demo'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertNotIn(secret,self.client.get('/api/reels/instagram/config').text)
        self.assertTrue(self.client.get('/api/reels/instagram/config').json()['token_configured'])
        self.client.put('/api/reels/instagram/config',json={'account_id':'123','mode':'demo'})
        self.assertEqual(self.app.state.reels.secrets.get('meta_token'),secret)
        self.assertNotIn(secret.encode(),self.app.state.db.path.read_bytes())
        self.assertNotIn(secret.encode(),self.app.state.reels.secrets.path.read_bytes())
        self.assertEqual(self.client.put('/api/reels/instagram/config',json={'enabled':True,'mode':'live'}).status_code,422)

    def test_runtime_limits_persist_but_cannot_change_authentication(self):
        self.login();limits=self.client.get('/api/reels/preferences').json()['limits'];limits['reels_threads']=2;limits['reels_upload_mb']=32
        self.assertEqual(self.client.put('/api/reels/preferences',json={'limits':limits}).status_code,200)
        self.assertEqual(ReelService(self.settings).settings.reels_threads,2)
        self.assertEqual(self.client.put('/api/reels/preferences',json={'limits':limits|{'password':'oops'}}).status_code,422)
        self.assertEqual(self.client.put('/api/reels/preferences',json={'limits':limits|{'reels_threads':100}}).status_code,422)
        self.assertEqual(self.app.state.settings.password,self.settings.password)

    def test_cleanup_preserves_originals_deliverables_texts_and_active_jobs(self):
        self.login();library=self.app.state.reels.library
        identifier=library.create_job({'title':'Teste'},origin='web')
        directory=library.root/'jobs'/identifier;(directory/'speech').mkdir(parents=True);(directory/'deliverables').mkdir()
        (directory/'speech'/'raw.wav').write_bytes(b'temporary')
        for name in ('script.txt','captions.srt','captions.ass'):(directory/name).write_text('keep')
        (directory/'cut-000.mp4').write_bytes(b'temporary');(directory/'deliverables'/'reel.mp4').write_bytes(b'keep')
        original=library.imports/'original.mp4';original.write_bytes(b'original')
        self.assertEqual(self.client.post(f'/api/reels/jobs/{identifier}/cleanup').status_code,409)
        self.assertEqual(self.client.get('/api/reels/summary').json()['queue'],1)
        library.update_job(identifier,'ready','ready',100)
        self.assertEqual(self.client.get('/api/reels/summary').json()['ready'],1)
        result=self.client.post(f'/api/reels/jobs/{identifier}/cleanup?path=/etc/passwd')
        self.assertEqual(result.status_code,200,result.text)
        self.assertFalse((directory/'speech').exists());self.assertFalse((directory/'cut-000.mp4').exists())
        self.assertEqual(original.read_bytes(),b'original');self.assertEqual((directory/'deliverables'/'reel.mp4').read_bytes(),b'keep')
        self.assertTrue((directory/'captions.srt').is_file())
