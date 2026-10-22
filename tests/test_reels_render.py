from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import subprocess
import sys
import unittest

from app.reels.library import ReelLibrary
from app.reels.planning import RenderOptions
from app.reels.planning import make_script
from app.reels.render import ReelStudio
from app.reels.speech import synthesize
from app.reels.tools import ReelError, executable, probe, run


class ReelRenderIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.ffmpeg = executable('ffmpeg')
            executable('ffprobe')
            executable('espeak-ng')
        except ReelError as error:
            if os.getenv('REELS_REQUIRE_TOOLS') == '1':
                raise RuntimeError(str(error)) from error
            raise unittest.SkipTest('Instale FFmpeg e eSpeak NG para os testes de mídia reais.') from error
        cls.temporary = TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.sources = []
        for name, source, codec in [
            ('captura sintética.mp4', 'testsrc2=size=640x360:rate=24', 'libx264'),
            ('vertical.mov', 'testsrc2=size=180x320:rate=30', 'libx264'),
            ('silencioso.webm', 'testsrc2=size=320x180:rate=25', 'libvpx-vp9'),
        ]:
            path = cls.root / name
            run([cls.ffmpeg, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', source, '-t', '6', '-an',
                 '-c:v', codec, '-threads', '2', '-pix_fmt', 'yuv420p', path])
            cls.sources.append(path)
        cls.music = cls.root / 'trilha de teste.wav'
        run([cls.ffmpeg, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=220:sample_rate=48000',
             '-t', '2', cls.music])

    def test_import_mixed_formats_and_render_full_hd_reel_with_real_offline_voice(self):
        library = ReelLibrary(self.root / 'full-render')
        assets = [library.import_media(path, tags=['gameplay']) for path in self.sources]
        music = library.import_media(self.music, kind='music')
        events = []
        options = RenderOptions(tuple(asset['id'] for asset in assets), duration=15,
                                title='TESTE SINTÉTICO — NÃO É GAMEPLAY ROBLOX',
                                music_id=music['id'], tts='espeak', threads=2)
        report = ReelStudio(library, progress=events.append).render(options)
        output = Path(report['output'])
        metadata = probe(output)
        video = next(stream for stream in metadata['streams'] if stream['codec_type'] == 'video')
        audio = next(stream for stream in metadata['streams'] if stream['codec_type'] == 'audio')
        self.assertEqual((video['width'], video['height'], video['codec_name'], video['pix_fmt']), (1080, 1920, 'h264', 'yuv420p'))
        self.assertEqual((audio['codec_name'], audio['sample_rate'], audio['channels']), ('aac', '48000', 2))
        self.assertAlmostEqual(metadata['duration'], 15, delta=.1)
        self.assertEqual(video['avg_frame_rate'], '30/1')
        self.assertFalse(report['gpu_used'])
        self.assertFalse(report['network_used'])
        self.assertFalse(report['publishing_enabled'])
        job = library.jobs(report['job_id'])[0]
        self.assertEqual(job['status'], 'ready')
        self.assertEqual(job['progress'], 100)
        self.assertEqual(events[-1]['progress'], 100)
        directory = output.parent.parent
        narration = json.loads((directory / 'narration.json').read_text())
        self.assertGreater(narration['speech_duration'], 1)
        self.assertLessEqual(narration['cues'][-1]['end'], 14.5)
        self.assertTrue((directory / 'captions.srt').is_file())
        self.assertTrue((directory / 'commands.json').is_file())
        # Decodificar todo o resultado encontra corrupção que um cabeçalho válido não detecta.
        run([self.ffmpeg, '-nostdin', '-v', 'error', '-i', output, '-f', 'null', '-'], timeout=120)
        # faststart deve deixar moov antes de mdat para reprodução progressiva.
        data = output.read_bytes()
        self.assertLess(data.index(b'moov'), data.index(b'mdat'))

    def test_cli_import_and_plan_have_json_output_and_no_publication(self):
        root = self.root / 'cli'
        base = [sys.executable, '-m', 'app.reels', '--data-dir', str(root)]
        response = subprocess.run(base + ['import', str(self.sources[0]), '--tags', 'cidades'], capture_output=True, text=True)
        self.assertEqual(response.returncode, 0, response.stderr)
        asset = json.loads(response.stdout)
        # Um arquivo de 6s não pode ser inventado ou repetido para montar 15s.
        response = subprocess.run(base + ['plan', '--asset', asset['id'], '--duration', '15'], capture_output=True, text=True)
        self.assertEqual(response.returncode, 2)
        self.assertIn('importe pelo menos', response.stderr)
        self.assertEqual(ReelLibrary(root).db.posts(), [])

    def test_default_no_music_crop_without_zoom_renders_with_real_tools(self):
        library = ReelLibrary(self.root / 'crop-render')
        assets = [library.import_media(path, tags=['gameplay']) for path in self.sources]
        report = ReelStudio(library).render(RenderOptions(tuple(asset['id'] for asset in assets),
                    duration=15, title='Teste sintético de crop, sem trilha', tts='espeak', fit='crop', zoom=0, threads=2))
        self.assertEqual(library.jobs(report['job_id'])[0]['status'], 'ready')
        self.assertEqual(report['metadata']['streams'][0]['nb_frames'], '450')

    def test_generated_scripts_fit_real_pt_br_voice_at_supported_durations(self):
        themes = ['cidades', 'cavernas', 'demonios', 'npcs', 'batalhas', 'magia', 'exploracao']
        for duration in (15, 30, 45, 60):
            with self.subTest(duration=duration):
                directory = self.root / f'voice-{duration}'
                directory.mkdir()
                voice = synthesize(make_script(themes, duration), directory, engine='espeak', duration=duration, threads=2)
                self.assertEqual(voice['audio_duration'], duration)
                self.assertLessEqual(voice['cues'][-1]['end'], duration - .5)


if __name__ == '__main__':
    unittest.main()
