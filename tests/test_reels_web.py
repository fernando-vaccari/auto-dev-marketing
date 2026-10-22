"""Contratos HTTP e integração real do supervisor Linux, sem Meta ou APIs pagas."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import fcntl
import os
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.reels.tools import executable, probe, run, ReelError


class ReelsWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.ffmpeg = executable('ffmpeg')
            executable('espeak-ng')
        except ReelError as error:
            if os.getenv('REELS_REQUIRE_TOOLS') == '1':
                raise
            raise unittest.SkipTest(str(error))
        cls.sources = TemporaryDirectory()
        cls.addClassCleanup(cls.sources.cleanup)
        cls.video = Path(cls.sources.name) / 'synthetic.mp4'
        run([cls.ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=30',
             '-t', '16', '-c:v', 'libx264', '-threads', '2', '-pix_fmt', 'yuv420p', cls.video])
        cls.music = Path(cls.sources.name) / 'music.wav'
        run([cls.ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=220', '-t', '1', cls.music])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(data_dir=Path(self.temp.name), password='test-password-reels', reels_min_free_mb=0)
        self.app = create_app(self.settings, scheduler=False, reels_worker=False)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.client.post('/api/login', json={'password': self.settings.password})
        self.library = self.app.state.reels.library

    def upload(self, path=None, **params):
        path = path or self.video
        return self.client.post('/api/reels/assets', params={'filename': path.name, **params}, content=path.read_bytes())

    def body(self):
        asset = self.upload().json()
        return {'asset_ids': [asset['id']], 'title': 'TESTE SINTÉTICO — não é gameplay Roblox', 'duration': 15,
                'script': 'Este é um teste sintético de renderização local. Nenhuma cena de Roblox é mostrada.',
                'tts': 'espeak', 'fit': 'contain', 'zoom': 0}

    def test_every_route_requires_session_and_no_password_never_opens_studio(self):
        identifier = 'a' * 32
        endpoints = [('GET','config'), ('GET','assets'), ('POST','assets?filename=x.mp4'), ('POST','plan'),
                     ('POST','jobs'), ('GET','jobs'), ('GET',f'jobs/{identifier}'), ('POST',f'jobs/{identifier}/cancel'),
                     ('GET',f'jobs/{identifier}/video'), ('GET',f'jobs/{identifier}/download'), ('GET',f'jobs/{identifier}/texts')]
        anonymous = TestClient(self.app)
        self.addCleanup(anonymous.close)
        for method, path in endpoints:
            with self.subTest(path=path):
                self.assertEqual(anonymous.request(method, '/api/reels/'+path).status_code, 401)
        app = create_app(replace(self.settings, password=''), scheduler=False)
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/reels/config').status_code, 503)
            self.assertEqual(client.get('/api/status').status_code, 200)
        self.assertEqual(self.client.post('/api/reels/jobs', json=self.body(), headers={'Origin':'https://evil.example'}).status_code,403)

    def test_upload_video_music_metadata_and_private_paths(self):
        response = self.upload(tags='cidades,magia')
        self.assertEqual(response.status_code, 201, response.text)
        asset = response.json()
        self.assertNotIn('relative_path', asset)
        self.assertEqual(asset['original_name'], 'synthetic.mp4')
        self.assertEqual(asset['tags'], ['cidades','magia'])
        self.assertGreater(asset['metadata']['duration'],15)
        self.assertEqual(asset['size_bytes'],self.video.stat().st_size)
        self.assertEqual(self.upload(self.music,kind='music').status_code,201)
        self.assertEqual(len(self.client.get('/api/reels/assets').json()),2)
        private = self.library.asset(asset['id'])['relative_path']
        self.assertEqual(self.client.get('/static/'+private).status_code,404)
        self.assertEqual(self.client.get('/reels/'+private).status_code,404)
        self.assertEqual(list((self.library.root/'uploads').iterdir()),[])

    def test_upload_invalid_names_types_payload_sizes_and_cleanup(self):
        for name in ('../x.mp4', 'C:\\x.mp4', '/tmp/x.mp4', 'x\x00.mp4', 'x.exe', 'x\n.mp4', 'x\x7f.mp4', 'x\u202e.mp4'):
            with self.subTest(name=name):
                self.assertEqual(self.client.post('/api/reels/assets',params={'filename':name},content=b'invalid').status_code,422)
        self.assertEqual(self.client.post('/api/reels/assets',params={'filename':'x.mp4'},content=b'not a video').status_code,422)
        self.assertEqual(self.client.post('/api/reels/assets',params={'filename':'x.mp4'},content=b'x',headers={'Content-Length':str(513*1024*1024)}).status_code,413)
        self.assertEqual(self.client.post('/api/reels/assets',params={'filename':'x.mp4'},content=b'abc',headers={'Content-Length':'1'}).status_code,413)
        self.assertEqual(self.client.post('/api/reels/assets',params={'filename':'x.mp4'},content=b'abc',headers={'Content-Length':'10'}).status_code,422)
        self.assertEqual(self.client.post('/api/reels/assets',params={'filename':'x.mp4'},content=b'').status_code,411)
        self.assertEqual(list((self.library.root/'uploads').iterdir()),[])
        self.assertEqual(self.library.assets(),[])
        with (self.library.root/'upload.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(self.upload().status_code,409)
        with patch.object(self.app.state.reels,'require_space',side_effect=ReelError('Quota')):
            self.assertEqual(self.upload().status_code,507)

    def test_plan_queue_validation_progress_and_cancel(self):
        body = self.body()
        plan = self.client.post('/api/reels/plan',json=body)
        self.assertEqual(plan.status_code,200,plan.text)
        self.assertEqual(plan.json()['script'],body['script'])
        self.assertNotIn('sources',plan.json())
        for values in ({'duration':14}, {'zoom':.07}, {'fit':'../../'}, {'piper_model':'/tmp/evil'}, {'asset_ids':['missing']}, {'themes':['cavernas']}):
            self.assertEqual(self.client.post('/api/reels/jobs',json=body|values).status_code,422, values)
        created = self.client.post('/api/reels/jobs',json=body)
        self.assertEqual(created.status_code,202,created.text)
        job = created.json()
        self.assertEqual(job['status'],'queued')
        self.assertNotIn('piper_model',job['config'])
        self.library.update_job(job['id'],'rendering','cuts',45,'Corte de teste')
        progress = self.client.get('/api/reels/jobs/'+job['id']).json()
        self.assertEqual(progress['progress'],45)
        self.assertEqual(progress['events'][-1]['detail'],'Corte de teste')
        response = self.client.post('/api/reels/jobs/'+job['id']+'/cancel')
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['status'],'cancelled')
        self.assertEqual(self.client.post('/api/reels/jobs/'+job['id']+'/cancel').status_code,200)
        for unused in range(3):
            self.assertEqual(self.client.post('/api/reels/jobs',json=body).status_code,202)
        self.assertEqual(self.client.post('/api/reels/jobs',json=body).status_code,422)

    def test_download_fixed_paths_range_texts_and_symlink_defense(self):
        job_id = self.library.create_job(self.body(),origin='web')
        base = '/api/reels/jobs/'+job_id
        self.assertEqual(self.client.get(base+'/download').status_code,409)
        directory = self.library.root/'jobs'/job_id
        (directory/'deliverables').mkdir(parents=True)
        output = directory/'deliverables'/'reel.mp4'
        output.write_bytes(self.video.read_bytes())
        (directory/'script.txt').write_text('Teste privado')
        (directory/'captions.srt').write_text('1\n00:00:00,000 --> 00:00:01,000\nTeste\n')
        self.library.update_job(job_id,'ready','ready',100,output_path='/etc/passwd')
        response = self.client.get(base+'/download?path=/etc/passwd')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.content,self.video.read_bytes())
        self.assertIn('attachment',response.headers['content-disposition'])
        partial = self.client.get(base+'/video',headers={'Range':'bytes=0-99'})
        self.assertEqual(partial.status_code,206)
        self.assertEqual(len(partial.content),100)
        self.assertEqual(self.client.get(base+'/texts').json()['script'],'Teste privado')
        output.unlink(); output.symlink_to(self.video)
        self.assertEqual(self.client.get(base+'/download').status_code,404)
        self.assertEqual(self.client.get('/api/reels/jobs/not-a-job/download').status_code,404)
        self.assertEqual(self.client.post(base+'/cancel').status_code,422)

    def wait_status(self, client, job_id, statuses, timeout=90):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            job=client.get('/api/reels/jobs/'+job_id).json()
            if job['status'] in statuses:
                return job
            time.sleep(.05)
        self.fail(f'Timeout aguardando {statuses}: {job}')

    def test_real_worker_render_and_targeted_active_queued_cancellation(self):
        body=self.body()
        # Mesma biblioteca, agora com supervisor ativo no lifespan.
        app=create_app(self.settings,scheduler=False)
        sentinel=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)'])
        try:
            with TestClient(app) as client:
                client.post('/api/login',json={'password':self.settings.password})
                response=client.post('/api/reels/jobs',json=body)
                self.assertEqual(response.status_code,202,response.text)
                job_id=response.json()['id']
                rendering=self.wait_status(client,job_id,{'rendering','failed'})
                self.assertEqual(rendering['status'],'rendering',rendering)
                process=app.state.reels.current[1]
                self.assertNotEqual(process.pid,os.getpid())
                start=time.monotonic()
                self.assertEqual(client.get('/health').status_code,200)
                self.assertLess(time.monotonic()-start,2)
                job=self.wait_status(client,job_id,{'ready','failed'})
                self.assertEqual(job['status'],'ready',job)
                self.assertEqual(job['progress'],100)
                downloaded=client.get('/api/reels/jobs/'+job_id+'/download')
                self.assertEqual(downloaded.status_code,200)
                final=Path(self.temp.name)/'download.mp4';final.write_bytes(downloaded.content)
                meta=probe(final)
                self.assertEqual(meta['streams'][0]['width'],1080)
                self.assertEqual(meta['streams'][0]['height'],1920)
                self.assertAlmostEqual(meta['duration'],15,delta=.1)
                run([self.ffmpeg,'-v','error','-i',final,'-f','null','-'])
                texts=client.get('/api/reels/jobs/'+job_id+'/texts').json()
                self.assertIn('-->',texts['captions'])
                self.assertEqual(texts['script'].strip(),body['script'])
                active=client.post('/api/reels/jobs',json=body).json()['id']
                self.wait_status(client,active,{'rendering'})
                worker=app.state.reels.current[1]
                queued=client.post('/api/reels/jobs',json=body).json()['id']
                self.assertEqual(client.post('/api/reels/jobs/'+queued+'/cancel').json()['status'],'cancelled')
                self.assertEqual(client.post('/api/reels/jobs/'+active+'/cancel').json()['status'],'cancelled')
                self.assertIsNotNone(worker.returncode)
                self.assertIsNone(sentinel.poll())
                self.assertEqual(client.get('/api/reels/jobs/'+active+'/download').status_code,409)
                self.assertEqual(client.get('/api/reels/jobs/'+queued).json()['status'],'cancelled')
        finally:
            sentinel.terminate();sentinel.wait()

    def test_worker_timeout_shutdown_and_restart_recovery(self):
        body = self.body()
        config = replace(self.settings, reels_timeout_seconds=1)
        app = create_app(config, scheduler=False)
        with TestClient(app) as client:
            client.post('/api/login', json={'password': config.password})
            job_id = client.post('/api/reels/jobs', json=body).json()['id']
            failed = self.wait_status(client, job_id, {'failed'})
            self.assertIn('Tempo máximo', failed['error'])
        # Um job interrompido é recuperado sem retomar render ou sinalizar PIDs gravados.
        orphan = self.library.create_job(body, origin='web')
        self.library.begin_job(orphan)
        with TestClient(create_app(self.settings, scheduler=False)):
            recovered = self.library.jobs(orphan)[0]
            self.assertEqual(recovered['status'], 'failed')
            self.assertEqual(recovered['stage'], 'interrupted')
        app = create_app(self.settings, scheduler=False)
        with TestClient(app) as client:
            client.post('/api/login', json={'password': config.password})
            job_id = client.post('/api/reels/jobs', json=body).json()['id']
            self.wait_status(client, job_id, {'rendering'})
            process = app.state.reels.current[1]
        self.assertIsNotNone(process.returncode)
        self.assertEqual(self.library.jobs(job_id)[0]['status'], 'failed')

    def test_child_environment_does_not_inherit_credentials(self):
        with patch.dict(os.environ,{'META_ACCESS_TOKEN':'secret','APP_PASSWORD':'secret','AI_API_KEY':'secret'}):
            env=self.app.state.reels.child_environment()
        self.assertFalse({'META_ACCESS_TOKEN','APP_PASSWORD','AI_API_KEY'} & env.keys())
        self.assertEqual(env['OMP_NUM_THREADS'],'4')
