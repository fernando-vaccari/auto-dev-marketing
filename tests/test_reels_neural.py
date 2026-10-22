from pathlib import Path
from tempfile import TemporaryDirectory
import os
import json
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.reels.speech import synthesize_fitting, SpeechTooLong
from app.reels.tools import ReelError, executable
from scripts.install_voice import FILES, digest

ROOT=Path(__file__).resolve().parent.parent
MODELS=Path(os.getenv('REELS_TEST_MODEL_DIR',str(ROOT/'.data/reels/models/kokoro')))


class NeuralTests(unittest.TestCase):
    def test_shortening_retries_synthesis_preserves_words_and_limits_attempts(self):
        def speech(text,*args,**kwargs):
            if len(text.split())>8:raise SpeechTooLong('não cabe')
            return {'speech_duration':3,'cues':[]}
        with patch('app.reels.speech.synthesize',side_effect=speech) as call:
            result=synthesize_fitting('Uma frase bastante longa contendo muitas palavras para teste. Outra frase também longa. Acompanhe.',Path('.'),auto_shorten=True)
        self.assertLessEqual(len(result['text'].split()),8)
        self.assertGreater(call.call_count,1)
        self.assertLessEqual(call.call_count,4)
        with patch('app.reels.speech.synthesize',side_effect=SpeechTooLong('não cabe')) as call:
            with self.assertRaises(SpeechTooLong):synthesize_fitting('Texto',Path('.'),auto_shorten=True)
            self.assertEqual(call.call_count,4)

    def preview(self,engine):
        try:executable('ffmpeg')
        except ReelError:
            if os.getenv('REELS_REQUIRE_TOOLS')=='1':raise
            self.skipTest('FFmpeg ausente')
        with TemporaryDirectory() as temporary:
            settings=Settings(data_dir=Path(temporary),password='test-password-neural',reels_min_free_mb=0)
            if engine=='kokoro':
                modelpath=Path(temporary)/'reels/models/kokoro';modelpath.mkdir(parents=True)
                for name in FILES:(modelpath/name).symlink_to(MODELS/name)
            with TestClient(create_app(settings,scheduler=False)) as client:
                self.assertEqual(client.post('/api/reels/voice-preview',json={}).status_code,401)
                client.post('/api/login',json={'password':settings.password})
                text='Estas são gravações do projeto. Acompanhe o desenvolvimento.'
                if engine=='kokoro':
                    text='Estas são gravações do projeto. Este material serve para verificar a duração da narração de um vídeo curto e para conferir que todas as palavras possam ser ouvidas com clareza no resultado. Durante este teste nós incluímos uma quantidade maior de texto, com pausas naturais, para medir o áudio gerado de verdade antes de preparar o vídeo final. Acompanhe o desenvolvimento.'
                response=client.post('/api/reels/voice-preview',json={'title':'Prévia de voz','duration':15,'script':text,'tts':engine,'voice_id':'pf_dora'})
                self.assertEqual(response.status_code,202,response.text)
                identifier=response.json()['id'];deadline=time.monotonic()+90
                while True:
                    job=client.get('/api/reels/jobs/'+identifier).json()
                    if job['status'] in {'ready','failed'}:break
                    self.assertLess(time.monotonic(),deadline,job);time.sleep(.1)
                self.assertEqual(job['status'],'ready',job)
                self.assertEqual(job['kind'],'voice_preview')
                if engine=='kokoro':
                    narration=json.loads((Path(temporary)/'reels/jobs'/identifier/'narration.json').read_text())
                    self.assertGreaterEqual(len(narration['attempts']),2)
                    self.assertLessEqual(narration['speech_duration'],14)
                    self.assertFalse(narration['speed_changed'])
                self.assertIsNone(job['video_url'])
                audio=client.get(job['audio_url'])
                self.assertEqual(audio.status_code,200)
                self.assertEqual(audio.content[:4],b'RIFF')
                self.assertGreater(len(audio.content),10000)
                self.assertIn('Acompanhe',client.get('/api/reels/jobs/'+identifier+'/texts').json()['script'])

    def test_voice_preview_in_separate_worker_espeak(self):
        try:executable('espeak-ng')
        except ReelError:
            if os.getenv('REELS_REQUIRE_TOOLS')=='1':raise
            self.skipTest('eSpeak ausente')
        self.preview('espeak')

    def test_real_kokoro_pt_br_preview_and_pinned_models(self):
        if not all((MODELS/name).is_file() for name in FILES):
            if os.getenv('REELS_REQUIRE_NEURAL')=='1':self.fail('Modelos Kokoro obrigatórios ausentes')
            self.skipTest('Instale modelos Kokoro para teste neural real')
        for name,expected in FILES.items():self.assertEqual(digest(MODELS/name),expected)
        self.preview('kokoro')
