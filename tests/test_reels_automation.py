from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.config import Settings
from app.main import create_app
from app.reels.service import ReelService
from fastapi.testclient import TestClient


class ReelAutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.service=ReelService(Settings(data_dir=Path(self.temp.name),password='password-testing',reels_min_free_mb=0))
        self.auto=self.service.automation
        self.config={'enabled':True,'name':'RPG','days':[0,1,2,3,4,5],'times':['12:30','19:30'],
                     'timezone':'America/Sao_Paulo','quantity':1,'policy':'approval','template':{
                         'asset_ids':['test'],'duration':15,'title':'Teste','tts':'espeak'}}

    def test_two_slots_timezone_idempotence_restart_and_edit(self):
        identifier=self.auto.save(self.config)
        with patch('app.reels.automation.build_plan'),patch('app.reels.automation.choose_voice'):
            noon=datetime(2026,10,22,15,30,tzinfo=timezone.utc)
            self.auto.tick(noon);self.auto.tick(noon)
            self.assertEqual(len(self.auto.history()),1)
            restarted=ReelService(self.service.settings).automation
            restarted.tick(noon)
            self.assertEqual(len(restarted.history()),1)
            restarted.save(self.config|{'name':'Novo nome'},identifier)
            restarted.tick(noon)
            self.assertEqual(len(restarted.history()),1)
            restarted.tick(datetime(2026,10,22,22,30,tzinfo=timezone.utc))
            self.assertEqual(len(restarted.history()),2)
            jobs=self.service.library.jobs()
            self.assertEqual(len(jobs),2)
            self.assertNotEqual(jobs[0]['config']['variation'],jobs[1]['config']['variation'])
            self.assertTrue(all(job['config']['script'] is None for job in jobs))
        with self.service.library.db.connect() as db:
            rows=list(db.execute('SELECT * FROM reel_deliveries'))
        self.assertEqual(len(rows),2)
        self.assertEqual({r['approved'] for r in rows},{0})

    def test_paused_sunday_missed_slots_and_missing_footage(self):
        identifier=self.auto.save(self.config|{'enabled':False})
        self.auto.tick(datetime(2026,10,22,15,30,tzinfo=timezone.utc))
        self.assertEqual(self.auto.history(),[])
        self.auto.save(self.config,identifier)
        self.auto.tick(datetime(2026,10,25,15,30,tzinfo=timezone.utc))
        self.auto.tick(datetime(2026,10,22,18,0,tzinfo=timezone.utc))
        self.assertEqual(self.auto.history(),[])
        with patch('app.reels.automation.choose_voice'):
            self.auto.tick(datetime(2026,10,22,15,30,tzinfo=timezone.utc))
        self.assertEqual(self.auto.history()[0]['status'],'failed')
        self.assertEqual(self.service.library.jobs(),[])

    def test_http_auth_crud_and_explicit_auto_authorization(self):
        app=create_app(self.service.settings,scheduler=False,reels_worker=False)
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/reels/schedules').status_code,401)
            client.post('/api/login',json={'password':self.service.settings.password})
            bad=client.post('/api/reels/schedules',json=self.config|{'policy':'automatic'})
            self.assertEqual(bad.status_code,422)
            self.assertEqual(client.post('/api/reels/schedules',json=self.config|{'timezone':'invalid'}).status_code,422)
            identifier=client.post('/api/reels/schedules',json=self.config|{'enabled':False}).json()['id']
            self.assertEqual(len(client.get('/api/reels/schedules').json()),1)
            self.assertEqual(client.put('/api/reels/schedules/'+identifier,json=self.config).status_code,200)
            self.assertEqual(client.post('/api/reels/schedules/'+identifier+'/run').status_code,200)
            self.assertEqual(client.get('/api/reels/schedule-history').json()[0]['status'],'failed')
            client.delete('/api/reels/schedules/'+identifier)
            self.assertEqual(client.get('/api/reels/schedules').json(),[])
