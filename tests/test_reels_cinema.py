from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import unittest

from app.reels.library import ReelLibrary
from app.reels.planning import RenderOptions, build_plan
from app.reels.cinema import PRESETS
from app.reels.analysis import analyze,select,record_usage
from app.reels.render import ReelStudio
from app.reels.tools import executable,run,probe,ReelError


class CinemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:cls.ffmpeg=executable('ffmpeg');executable('espeak-ng')
        except ReelError as error:
            if os.getenv('REELS_REQUIRE_TOOLS')=='1':raise
            raise unittest.SkipTest(str(error))
        cls.temp=TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        cls.source=Path(cls.temp.name)/'fixture.mp4'
        run([cls.ffmpeg,'-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=30','-t','18','-c:v','libx264','-threads','2',cls.source])
        cls.sound=Path(cls.temp.name)/'sound.wav'
        run([cls.ffmpeg,'-v','error','-f','lavfi','-i','sine=frequency=160','-t','2',cls.sound])

    def setUp(self):
        self.directory=TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.library=ReelLibrary(self.directory.name)
        self.asset=self.library.import_media(self.source,tags=['cidades'])
        self.options=RenderOptions((self.asset['id'],),duration=15,tts='espeak',threads=2,zoom=0,
              title='TESTE SINTÉTICO: não é gameplay',script='Estas imagens são apenas um teste sintético de edição. Acompanhe o projeto.')

    def test_analysis_scores_and_usage_prevent_reusing_intervals(self):
        info=analyze(self.library,self.asset['id'])
        self.assertFalse(info['semantic_understanding'])
        self.assertLessEqual(len(info['samples']),60)
        self.assertTrue(all(0<=s['score']<=1 for s in info['samples']))
        cuts=select(self.library,[self.asset],450,90)
        self.assertEqual(sum(c['frames'] for c in cuts),450)
        record_usage(self.library,'previous',cuts)
        with self.assertRaisesRegex(ReelError,'inéditos'):select(self.library,[self.asset],450,90)
        self.assertEqual(sum(c['frames'] for c in select(self.library,[self.asset],450,90,avoid_reuse=False)),450)

    def test_presets_plan_exact_timeline_and_revised_cuts_validate(self):
        for name in PRESETS:
            with self.subTest(preset=name):
                plan=build_plan(self.library,replace(self.options,preset=name))
                total=sum(c['frames'] for c in plan['cuts'])-round(plan['overlap']*30)*(len(plan['cuts'])-1)
                self.assertEqual(total,450)
                self.assertLessEqual(max(c['source_start']+c['duration'] for c in plan['cuts']),18)
        plan=build_plan(self.library,self.options)
        values=tuple({k:c[k] for k in ('asset_id','source_start','duration')} for c in plan['cuts'])
        self.assertEqual(build_plan(self.library,replace(self.options,cuts_override=values))['duration'],15)
        with self.assertRaises(ReelError):build_plan(self.library,replace(self.options,cuts_override=({'asset_id':self.asset['id'],'source_start':16,'duration':15},)))

    def test_all_eight_cinematic_presets_render_valid_full_hd_with_ducking_and_effects(self):
        music=self.library.import_media(self.sound,kind='music')
        effect=self.library.import_media(self.sound,kind='effect')
        for name in PRESETS:
            if name=='legacy':continue
            with self.subTest(preset=name):
                options=replace(self.options,preset=name,music_id=music['id'],effect_id=effect['id'],
                    fit='blur' if name=='fantasia' else 'contain',caption_style='gamer',highlight_words=('teste',))
                report=ReelStudio(self.library).render(options)
                meta=probe(report['output'])
                self.assertEqual((meta['streams'][0]['width'],meta['streams'][0]['height']),(1080,1920))
                self.assertEqual(meta['streams'][0]['avg_frame_rate'],'30/1')
                self.assertAlmostEqual(meta['duration'],15,delta=.1)
                self.assertEqual(meta['streams'][1]['codec_name'],'aac')
                directory=Path(report['output']).parent.parent
                commands=json.loads((directory/'commands.json').read_text())
                final=' '.join(str(value) for c in commands for value in c)
                self.assertIn('sidechaincompress',final)
                self.assertIn('alimiter',final)
                self.assertIn('fad(', (directory/'captions.ass').read_text())
                self.assertFalse(report['network_used'])
