from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

from app.config import Settings
from app.reels.service import ReelService
from app.reels.capture import OBS
from app.reels.tools import ReelError


class Wire:
    def __init__(self):self.sent=[];self.responses=[{'op':0,'d':{'authentication':{'salt':'salt','challenge':'challenge'}}},{'op':2,'d':{}}]
    def recv(self,timeout=5):
        if self.responses:return json.dumps(self.responses.pop(0))
        request=self.sent[-1]['d']
        return json.dumps({'op':7,'d':{'requestId':request['requestId'],'requestStatus':{'result':True},'responseData':{'obsVersion':'31'}}})
    def send(self,value):self.sent.append(json.loads(value))
    def close(self):pass


class FakeOBS:
    def __init__(self):self.active=False;self.calls=[];self.path='';self.directory=''
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def call(self,name,data=None):
        self.calls.append((name,data))
        if name=='GetRecordStatus':return {'outputActive':self.active}
        if name=='GetInputList':return {'inputs':[{'inputName':'Jogo'}]}
        if name=='GetSceneItemList':return {'sceneItems':[{'sourceName':'Jogo','sceneItemEnabled':True}]}
        if name=='GetSourceActive':return {'videoActive':True}
        if name=='SetRecordDirectory':self.directory=data['recordDirectory']
        if name=='StartRecord':self.active=True
        if name=='StopRecord':self.active=False;return {'outputPath':self.path}
        return {}


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.service=ReelService(Settings(data_dir=Path(self.temp.name),password='password-testing',reels_min_free_mb=0))
        self.obs=FakeOBS();self.service.capture.obs_factory=lambda:self.obs
        self.config={'input_name':'Jogo','scene_name':'Cena','game_confirmed':True,'duration':15,'lead_seconds':0,'directory':'gravacoes','sequence':'Cidade','themes':['cidades']}

    def test_official_v5_auth_and_request_correlation(self):
        wire=Wire()
        with OBS(password='password',connector=lambda *args,**kwargs:wire) as obs:
            self.assertEqual(obs.call('GetVersion')['obsVersion'],'31')
        self.assertEqual(wire.sent[0]['op'],1)
        self.assertIn('authentication',wire.sent[0]['d'])
        self.assertNotIn('password',json.dumps(wire.sent))
        self.assertEqual(wire.sent[1]['d']['requestType'],'GetVersion')

    def test_capture_import_auto_stop_and_ownership(self):
        started=self.service.capture.start(self.config)
        self.assertTrue(self.obs.active)
        self.assertEqual(started['mode'],'assisted')
        path=Path(self.obs.directory)/'record.mp4';path.write_bytes(b'fixture checked by mock probe')
        self.obs.path=str(path)
        with patch('app.reels.capture.probe'),patch.object(self.service.library,'import_media',return_value={'id':'asset'}) as imported:
            self.service.capture.deadline=0;self.service.capture.tick()
            self.assertEqual(imported.call_args.kwargs['tags'],['cidades'])
        self.assertEqual(self.service.capture.history()[0]['status'],'imported')
        self.assertIsNone(self.service.capture.owned_id)
        self.assertFalse(self.obs.active)
        with self.assertRaises(ReelError):self.service.capture.finish(started['id'])

    def test_refuses_existing_recording_unconfirmed_game_and_escaped_output(self):
        self.obs.active=True
        with self.assertRaises(ReelError):self.service.capture.start(self.config)
        self.assertNotIn('StopRecord',[c[0] for c in self.obs.calls])
        self.obs.active=False
        with self.assertRaises(ReelError):self.service.capture.start(self.config|{'game_confirmed':False})
        identifier=self.service.capture.start(self.config)['id']
        self.obs.path='/etc/passwd'
        with self.assertRaises(ReelError):self.service.capture.finish(identifier)
        self.assertEqual(self.service.capture.history()[0]['status'],'review_required')

    def test_local_secret_vault_and_no_overwrite_env(self):
        self.service.secrets.set('obs_password','example-test-secret')
        self.assertEqual(self.service.secrets.get('obs_password'),'example-test-secret')
        self.assertNotIn(b'example-test-secret',self.service.secrets.path.read_bytes())
        self.assertEqual(self.service.secrets.path.stat().st_mode&0o777,0o600)
        self.assertEqual(self.service.secrets.key.stat().st_mode&0o777,0o600)

    def test_simulated_obs_over_real_local_websocket_imports_probed_file(self):
        import base64,hashlib,threading
        from websockets.sync.server import serve
        from websockets.exceptions import ConnectionClosed
        from app.reels.tools import executable,run
        password='test-obs-only'
        auth_secret=base64.b64encode(hashlib.sha256((password+'salt').encode()).digest()).decode()
        expected=base64.b64encode(hashlib.sha256((auth_secret+'challenge').encode()).digest()).decode()
        def handler(connection):
            connection.send(json.dumps({'op':0,'d':{'rpcVersion':1,'authentication':{'salt':'salt','challenge':'challenge'}}}))
            identified=json.loads(connection.recv())
            if identified['d'].get('authentication')!=expected:return
            connection.send(json.dumps({'op':2,'d':{'negotiatedRpcVersion':1}}))
            try:
                while True:
                    request=json.loads(connection.recv())['d']
                    response=self.obs.call(request['requestType'],request.get('requestData',{}))
                    connection.send(json.dumps({'op':7,'d':{'requestId':request['requestId'],'requestStatus':{'result':True,'code':100},'responseData':response}}))
            except ConnectionClosed:pass
        self.service.capture.obs_factory=None
        with serve(handler,'127.0.0.1',0) as server:
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            self.service.preferences.set('obs',{'port':server.socket.getsockname()[1]})
            self.service.secrets.set('obs_password',password)
            identifier=self.service.capture.start(self.config)['id']
            self.assertTrue(self.service.media_gate.locked())
            video=Path(self.obs.directory)/'OBS-SIMULADO.mp4'
            run([executable('ffmpeg'),'-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=30','-t','16','-c:v','libx264','-threads','1',video])
            self.obs.path=str(video)
            result=self.service.capture.finish(identifier)
            asset=self.service.library.asset(result['asset_id'])
            self.assertGreaterEqual(asset['metadata']['duration'],16)
            self.assertEqual(asset['tags'],['cidades'])
            self.assertFalse(self.service.media_gate.locked())
            server.shutdown();thread.join(timeout=2)
