"""Contratos reais de arquivos/fila; conversão simulada NÃO comprova clonagem."""
from dataclasses import replace
from pathlib import Path
import json
import os
import signal
import sys
import time
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.reels import voice_cloning as cloning
from app.reels.planning import RenderOptions
from app.reels.render import ReelStudio
from app.reels.speech import synthesize_fitting
from app.reels.tools import ReelError, probe, run
from tests import test_reels_web as baseline


class VoiceCloningTests(unittest.TestCase):
    setUpClass = classmethod(baseline.ReelsWebTests.setUpClass.__func__)
    setUp = baseline.ReelsWebTests.setUp
    upload = baseline.ReelsWebTests.upload
    body = baseline.ReelsWebTests.body

    def sample(self, *, filename='amostra.wav', consent=True):
        # Tom sintético é fixture técnica, não referência de voz humana/clonagem real.
        path = Path(self.temp.name) / filename
        run([self.ffmpeg,'-v','error','-y','-f','lavfi','-i','sine=frequency=240','-t','8',path])
        return self.client.post('/api/reels/my-voice',params={'filename':filename,'name':'Voz de teste','consent':str(consent).lower()},content=path.read_bytes())

    def test_upload_consent_profile_private_audio_default_and_delete(self):
        self.assertEqual(self.sample(consent=False).status_code,422)
        response=self.sample();self.assertEqual(response.status_code,201,response.text)
        identifier=response.json()['id'];root=self.library.root/'voice-cloning'
        self.assertEqual((root/identifier).stat().st_mode&0o777,0o700)
        self.assertEqual((root/identifier/'reference.wav').stat().st_mode&0o777,0o600)
        result=self.client.get('/api/reels/my-voice').json()
        self.assertEqual(len(result['profiles']),1);self.assertNotIn('sha256',result['profiles'][0])
        audio=self.client.get(f'/api/reels/my-voice/{identifier}/audio',headers={'Range':'bytes=0-99'})
        self.assertEqual(audio.status_code,206);self.assertEqual(audio.content[:4],b'RIFF')
        self.assertEqual(self.client.put('/api/reels/my-voice/default',json={'profile_id':identifier}).status_code,200)
        self.assertEqual(self.client.get('/static/reels/voice-cloning/'+identifier+'/reference.wav').status_code,404)
        self.assertEqual(self.client.delete('/api/reels/my-voice/'+identifier).status_code,200)
        self.assertFalse((root/identifier).exists())
        self.assertIsNone(self.client.get('/api/reels/my-voice').json()['default_profile_id'])

    def test_mp3_valid_invalid_audio_names_limits_and_silence(self):
        self.assertEqual(self.sample(filename='amostra.mp3').status_code,201)
        for name in ('../x.wav','/tmp/x.wav','x.exe','x\u202e.wav'):
            self.assertEqual(self.client.post('/api/reels/my-voice',params={'filename':name,'consent':'true'},content=b'bad').status_code,422)
        response=self.client.post('/api/reels/my-voice',params={'filename':'x.wav','consent':'true'},content=b'not audio')
        self.assertEqual(response.status_code,422)
        self.assertEqual(self.client.post('/api/reels/my-voice',params={'filename':'x.wav','consent':'true'},content=b'x',headers={'content-length':str(cloning.MAX_BYTES+1)}).status_code,413)
        path=Path(self.temp.name)/'silent.wav'
        run([self.ffmpeg,'-v','error','-f','lavfi','-i','anullsrc=r=24000:cl=mono','-t','8',path])
        self.assertEqual(self.client.post('/api/reels/my-voice',params={'filename':'silent.wav','consent':'true'},content=path.read_bytes()).status_code,422)
        self.assertEqual(list((self.library.root/'voice-cloning').glob('upload-*')),[])
        self.assertEqual(len(self.client.get('/api/reels/my-voice').json()['profiles']),1)

    def test_auth_origin_symlinks_and_reference_integrity(self):
        identifier=self.sample().json()['id'];url='/api/reels/my-voice'
        anonymous=TestClient(self.app);self.addCleanup(anonymous.close)
        for method,path in [('GET',url),('POST',url),('PUT',url+'/default'),('GET',url+'/'+identifier+'/audio'),('DELETE',url+'/'+identifier)]:
            self.assertEqual(anonymous.request(method,path).status_code,401)
        self.assertEqual(self.client.delete(url+'/'+identifier,headers={'Origin':'https://evil.example'}).status_code,403)
        reference=self.library.root/'voice-cloning'/identifier/'reference.wav'
        reference.unlink();reference.symlink_to(self.music)
        self.assertEqual(self.client.get(url+'/'+identifier+'/audio').status_code,422)
        self.assertEqual(self.client.get(url).json()['profiles'],[])

    def test_missing_model_does_not_fallback_or_create_job(self):
        identifier=self.sample().json()['id']
        with patch.object(cloning,'runtime_status',return_value={'installed':False,'reason':'Modelo ausente.'}):
            result=self.client.post('/api/reels/voice-preview',json={'title':'Teste','duration':15,'script':'Texto de teste.','tts':'my_voice','clone_profile_id':identifier})
        self.assertEqual(result.status_code,422);self.assertIn('Modelo ausente',result.text)
        self.assertEqual(self.library.jobs(),[])

    def test_preview_job_cancel_and_profile_deletion_guard(self):
        identifier=self.sample().json()['id']
        with patch.object(cloning,'runtime_status',return_value={'installed':True}),patch('app.reels.api.choose_voice',return_value=('my_voice',[])):
            response=self.client.post('/api/reels/voice-preview',json={'title':'Teste','duration':15,'script':'Texto de teste.','tts':'my_voice','clone_profile_id':identifier})
        self.assertEqual(response.status_code,202,response.text);job=response.json()
        self.assertNotIn('clone_root',job['config'])
        self.assertEqual(job['config']['clone_profile_id'],identifier)
        self.assertEqual(self.client.delete('/api/reels/my-voice/'+identifier).status_code,409)
        self.assertEqual(self.client.post('/api/reels/jobs/'+job['id']+'/cancel').json()['status'],'cancelled')
        self.assertEqual(self.client.delete('/api/reels/my-voice/'+identifier).status_code,200)

    def test_model_failure_memory_timeout_and_temporary_cleanup(self):
        identifier=self.sample().json()['id'];root=self.library.root/'voice-cloning';output=Path(self.temp.name)/'out.wav'
        def base(text,path,**kwargs):path.write_bytes(self.music.read_bytes())
        for code in (75,-9,2):
            with self.subTest(code=code),patch.object(cloning,'runtime_status',return_value={'installed':True}),patch('app.reels.voices.generate',side_effect=base),patch.object(cloning.subprocess,'run',return_value=SimpleNamespace(returncode=code)):
                with self.assertRaises(ReelError) as found:cloning.generate('Teste.',output,root=root,profile_id=identifier,kokoro_dir='unused')
                self.assertIn('Memória' if code in (75,-9) else 'falhou',str(found.exception))
                self.assertFalse(output.with_name('out-base.wav').exists())
        with patch.object(cloning,'runtime_status',return_value={'installed':True}),patch('app.reels.voices.generate',side_effect=base),patch.object(cloning.subprocess,'run',side_effect=subprocess.TimeoutExpired('worker',240)):
            with self.assertRaisesRegex(ReelError,'240 segundos'):cloning.generate('Teste.',output,root=root,profile_id=identifier,kokoro_dir='unused')

    def test_one_synthesis_lock_at_a_time(self):
        root=self.library.root/'voice-cloning'
        with cloning.profile_lock(root):
            with self.assertRaisesRegex(ReelError,'Outro pedido'):
                with cloning.profile_lock(root):pass

    def test_reel_pipeline_with_simulated_converter_keeps_measured_captions(self):
        identifier=self.sample().json()['id'];body=self.body();body.update(tts='my_voice',clone_profile_id=identifier)
        with patch.object(cloning,'runtime_status',return_value={'installed':True}),patch('app.reels.api.choose_voice',return_value=('my_voice',[])):
            response=self.client.post('/api/reels/jobs',json=body)
        self.assertEqual(response.status_code,202,response.text);job=response.json();config=self.library.jobs(job['id'])[0]['config']
        def simulated(text,path,**kwargs):
            from app.reels.tools import executable
            run([executable('espeak-ng'),'-v','pt-br','-s','165','-w',path,'--stdin'],input_data=text.encode())
        with patch('app.reels.speech.choose_voice',return_value=('my_voice',[])),patch.object(cloning,'generate',side_effect=simulated) as conversion:
            ReelStudio(self.library).render(RenderOptions(**config),job_id=job['id'])
        self.assertTrue(conversion.called)
        self.assertEqual(self.client.get('/api/reels/jobs/'+job['id']).json()['status'],'ready')
        output=self.library.root/self.library.jobs(job['id'])[0]['output_path'];metadata=probe(output)
        self.assertTrue(any(s.get('codec_name')=='h264' for s in metadata['streams']))
        self.assertTrue(any(s.get('codec_name')=='aac' for s in metadata['streams']))
        texts=self.client.get('/api/reels/jobs/'+job['id']+'/texts').json();self.assertIn('-->',texts['captions'])
        self.assertEqual(self.client.delete('/api/reels/my-voice/'+identifier).status_code,200)
        self.assertTrue(output.exists(),'MP4 pronto é preservado quando sua exclusão não foi pedida.')

    def test_reference_duration_and_profile_quota(self):
        path=Path(self.temp.name)/'short.wav'
        run([self.ffmpeg,'-v','error','-f','lavfi','-i','sine=frequency=250','-t','2',path])
        response=self.client.post('/api/reels/my-voice',params={'filename':'short.wav','consent':'true'},content=path.read_bytes())
        self.assertEqual(response.status_code,422)
        for index in range(5):self.assertEqual(self.sample().status_code,201)
        self.assertEqual(self.sample().status_code,422)
        self.assertEqual(len(self.client.get('/api/reels/my-voice').json()['profiles']),5)

    def test_delete_preview_derivatives_preserves_other_profile(self):
        first=self.sample().json()['id'];second=self.sample().json()['id']
        identifier=self.library.create_job({'clone_profile_id':first,'_task':'voice_preview'},origin='web')
        directory=self.library.root/'jobs'/identifier;directory.mkdir()
        (directory/'narration.wav').write_bytes(self.music.read_bytes())
        self.library.update_job(identifier,'ready','ready',100,output_path=str((directory/'narration.wav').relative_to(self.library.root)))
        self.assertEqual(self.client.delete('/api/reels/my-voice/'+first).status_code,200)
        self.assertFalse(directory.exists())
        self.assertEqual(self.library.jobs(identifier)[0]['status'],'failed')
        self.assertEqual(self.client.get('/api/reels/my-voice/'+second+'/audio').status_code,200)

    def test_cancellation_kills_only_clone_process_group(self):
        identifier=self.sample().json()['id'];runtime=Path(self.temp.name)/'isolated'
        (runtime/'.venv-voiceclone/bin').mkdir(parents=True);(runtime/'scripts').mkdir()
        (runtime/'.venv-voiceclone/bin/python').symlink_to(sys.executable)
        marker=runtime/'child.pid'
        (runtime/'scripts/voice_clone_worker.py').write_text('import os,time\nfrom pathlib import Path\nPath('+repr(str(marker))+').write_text(str(os.getpid()))\ntime.sleep(60)\n')
        script = """import sys,shutil
from pathlib import Path
from app.reels import voice_cloning as c,voices
c.PROJECT=Path(sys.argv[1]);c.runtime_status=lambda:{'installed':True}
voices.generate=lambda text,output,**kwargs:shutil.copyfile(sys.argv[5],output)
c.generate('Texto.',Path(sys.argv[4]),root=Path(sys.argv[2]),profile_id=sys.argv[3],kokoro_dir='unused')
"""
        sentinel=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],start_new_session=True)
        parent=subprocess.Popen([sys.executable,'-c',script,str(runtime),str(self.library.root/'voice-cloning'),identifier,str(runtime/'output.wav'),str(self.music)],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            deadline=time.monotonic()+10
            while not marker.exists():
                if parent.poll() is not None:self.fail(parent.stderr.read().decode())
                if time.monotonic()>deadline:self.fail('Conversor de teste não iniciou.')
                time.sleep(.05)
            child=int(marker.read_text());self.assertEqual(os.getpgid(child),parent.pid)
            os.killpg(parent.pid,signal.SIGTERM);parent.wait(timeout=5)
            deadline=time.monotonic()+5
            while Path(f'/proc/{child}/stat').exists():
                if Path(f'/proc/{child}/stat').read_text().split()[2]=='Z':break
                if time.monotonic()>deadline:self.fail('Processo de conversão continuou após cancelamento.')
                time.sleep(.05)
            self.assertIsNone(sentinel.poll(),'Cancelamento afetou outro processo.')
        finally:
            if parent.poll() is None:os.killpg(parent.pid,signal.SIGKILL);parent.wait()
            parent.stderr.close();sentinel.terminate();sentinel.wait(timeout=5)

    def test_real_conversion_when_official_weights_available(self):
        if not cloning.runtime_status()['installed']:
            if os.getenv('VOICE_CLONE_REQUIRE_REAL')=='1':self.fail('Pesos oficiais indisponíveis; clonagem real não validada.')
            self.skipTest('Pesos oficiais OpenVoice bloqueados/ausentes; mocks não comprovam clonagem.')
        model=Path(os.getenv('REELS_TEST_MODEL_DIR','.data/reels/models/kokoro')).resolve()
        if not (model/'kokoro-v1.0.onnx').is_file():self.fail('Kokoro precisa estar instalado para o teste real.')
        # Referência sintética Dora; valida conversão real sem usar voz pessoal de terceiros.
        from app.reels.voices import generate
        sample=Path(self.temp.name)/'reference.wav'
        generate('Esta referência sintética foi criada apenas para testar o processamento local da voz em português brasileiro.',sample,directory=model)
        root=self.library.root/'voice-cloning'
        profile=cloning.create_profile(root,sample,name='Referência sintética autorizada',consent=True)
        output=Path(self.temp.name)/'converted.wav'
        cloning.generate('Esta é uma frase nova para validar o conversor local.',output,root=root,profile_id=profile['id'],kokoro_dir=model)
        self.assertGreater(probe(output)['duration'],1)
