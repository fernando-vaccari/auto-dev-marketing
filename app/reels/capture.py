"""OBS websocket v5 oficial. Captura assistida real, sem executar Luau remotamente."""
import base64
import hashlib
import json
from pathlib import Path
import threading
import time
import uuid

from .tools import ReelError, executable, run, probe
from ..db import now_iso


class OBS:
    def __init__(self, port=4455, password='', connector=None):
        self.port,self.password,self.connector=port,password,connector
        self.socket=None

    def __enter__(self):
        try:
            if self.connector is None:
                from websockets.sync.client import connect
                self.connector=connect
            self.socket=self.connector(f'ws://127.0.0.1:{self.port}',open_timeout=5,close_timeout=2,max_size=1024*1024)
            hello=json.loads(self.socket.recv(timeout=5))
            if hello.get('op') != 0: raise ReelError('Handshake OBS inválido.')
            data={'rpcVersion':1,'eventSubscriptions':0}
            auth=hello['d'].get('authentication')
            if auth:
                secret=base64.b64encode(hashlib.sha256((self.password+auth['salt']).encode()).digest()).decode()
                data['authentication']=base64.b64encode(hashlib.sha256((secret+auth['challenge']).encode()).digest()).decode()
            self.socket.send(json.dumps({'op':1,'d':data}))
            if json.loads(self.socket.recv(timeout=5)).get('op') != 2:
                raise ReelError('OBS recusou a autenticação.')
            return self
        except Exception:
            if self.socket:self.socket.close()
            raise ReelError('Não foi possível autenticar no OBS local. Confira porta, senha e obs-websocket v5.') from None

    def __exit__(self,*args):
        if self.socket:self.socket.close()

    def call(self, name, data=None):
        identifier=uuid.uuid4().hex
        try:
            self.socket.send(json.dumps({'op':6,'d':{'requestType':name,'requestId':identifier,'requestData':data or {}}}))
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                reply=json.loads(self.socket.recv(timeout=5))
                if reply.get('op') != 7 or reply['d'].get('requestId') != identifier:continue
                if not reply['d']['requestStatus']['result']:
                    raise ReelError(f'OBS recusou {name} (código {reply["d"]["requestStatus"].get("code",0)}).')
                return reply['d'].get('responseData',{})
        except ReelError:raise
        except Exception:pass
        raise ReelError('Falha ou timeout na comunicação OBS; confira o gravador antes de tentar novamente.')


class CaptureStudio:
    def __init__(self, service):
        self.service=service;self.library=service.library
        self.root=self.library.root/'captures';self.root.mkdir(exist_ok=True)
        self.lock=threading.Lock();self.owned_id=None;self.deadline=0
        self.obs_factory=None
        with self.library.db.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS reel_captures (
                id TEXT PRIMARY KEY,status TEXT NOT NULL,config_json TEXT NOT NULL,
                asset_id TEXT,error TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);''')
    def recover(self):
        with self.library.db.connect() as db:
            db.execute("UPDATE reel_captures SET status='review_required',error='Servidor reiniciado. Confira o OBS; nenhuma gravação foi interrompida automaticamente.' WHERE status='recording'")

    def obs(self):
        if self.obs_factory:return self.obs_factory()
        config=self.service.preferences.get('obs',{})
        return OBS(port=config.get('port',4455),password=self.service.secrets.get('obs_password',''))

    def status(self):
        with self.obs() as obs:
            version=obs.call('GetVersion')
            recording=obs.call('GetRecordStatus')
            inputs=obs.call('GetInputList').get('inputs',[])
            scenes=obs.call('GetSceneList').get('scenes',[])
        return {'connected':True,'version':version.get('obsVersion'),'recording':recording.get('outputActive',False),
                'owned_capture':self.owned_id,'inputs':inputs,'scenes':scenes,'mode':'assisted'}

    def history(self):
        with self.library.db.connect() as db:
            return [dict(row)|{'config':json.loads(row['config_json'])} for row in db.execute('SELECT * FROM reel_captures ORDER BY created_at DESC LIMIT 100')]

    def start(self, config):
        with self.lock:
            if not self.service.media_gate.acquire(blocking=False):
                raise ReelError('Aguarde o processamento local atual terminar.')
            try:return self._start_owned(config)
            except BaseException:
                self.service.media_gate.release()
                raise

    def _start_owned(self, config):
        if self.owned_id or self.service.current:raise ReelError('Aguarde o render ou a captura atual terminar.')
        if not config['game_confirmed']:raise ReelError('Confirme que o jogo e a sequência estão abertos e visíveis na fonte OBS.')
        self.service.require_space(256*1024*1024)
        directory=(self.root/config['directory']).resolve()
        if not directory.is_relative_to(self.root.resolve()):raise ReelError('Diretório de captura inválido.')
        directory.mkdir(parents=True,exist_ok=True)
        with self.obs() as obs:
            if obs.call('GetRecordStatus').get('outputActive'):raise ReelError('Já existe gravação no OBS. Não iremos interrompê-la.')
            inputs={i['inputName'] for i in obs.call('GetInputList').get('inputs',[])}
            if config['input_name'] not in inputs:raise ReelError('A fonte escolhida não existe no OBS.')
            obs.call('SetCurrentProgramScene',{'sceneName':config['scene_name']})
            items=obs.call('GetSceneItemList',{'sceneName':config['scene_name']}).get('sceneItems',[])
            if not any(i.get('sourceName')==config['input_name'] and i.get('sceneItemEnabled') for i in items):
                raise ReelError('A fonte deve estar habilitada na cena escolhida.')
            if not obs.call('GetSourceActive',{'sourceName':config['input_name']}).get('videoActive'):
                raise ReelError('A fonte de vídeo não está ativa.')
            obs.call('SetRecordDirectory',{'recordDirectory':str(directory)})
            obs.call('StartRecord')
            identifier=uuid.uuid4().hex
            try:
                with self.library.db.connect() as db:
                    db.execute("INSERT INTO reel_captures VALUES (?,'recording',?,NULL,NULL,?,?)",(identifier,json.dumps(config),now_iso(),now_iso()))
            except BaseException:
                obs.call('StopRecord');raise
        self.owned_id=identifier;self.deadline=time.monotonic()+config['duration']+config['lead_seconds']
        return {'id':identifier,'mode':'assisted','instruction':'Gravação iniciada. Execute agora a sequência no jogo; a parada ocorrerá após a duração e a margem configuradas.'}


    def finish(self, identifier):
        with self.lock:
            if self.owned_id != identifier:raise ReelError('Esta instância não iniciou essa gravação; confira o OBS manualmente.')
            config=next(c['config'] for c in self.history() if c['id']==identifier)
            try:
                with self.obs() as obs:
                    result=obs.call('StopRecord')
                path=Path(result.get('outputPath','')).resolve()
                expected=(self.root/config['directory']).resolve()
                if not path.is_relative_to(expected) or not path.is_file() or path.is_symlink():
                    raise ReelError('O OBS retornou arquivo fora do diretório de captura autorizado ou indisponível.')
                self.service.require_space(path.stat().st_size)
                probe(path)
                if path.suffix.lower()=='.mkv':
                    converted=expected/(uuid.uuid4().hex+'.mp4')
                    run([executable('ffmpeg'),'-nostdin','-v','error','-protocol_whitelist','file,pipe','-i',path,
                         '-map','0:v:0','-map','0:a?','-c','copy','-movflags','+faststart',converted],timeout=120)
                    path=converted
                asset=self.library.import_media(path,tags=config['themes'])
                with self.library.db.connect() as db:
                    db.execute("UPDATE reel_captures SET status='imported',asset_id=?,updated_at=? WHERE id=?",(asset['id'],now_iso(),identifier))
                return {'asset_id':asset['id']}
            except Exception as error:
                message=str(error) if isinstance(error,ReelError) else 'Falha na captura. Confira o OBS e o arquivo local.'
                with self.library.db.connect() as db:
                    db.execute("UPDATE reel_captures SET status='review_required',error=?,updated_at=? WHERE id=?",(message[:500],now_iso(),identifier))
                raise ReelError(message) from None
            finally:
                self.owned_id=None
                self.service.media_gate.release()

    def tick(self):
        if self.owned_id and time.monotonic()>=self.deadline:
            try:self.finish(self.owned_id)
            except ReelError:pass
