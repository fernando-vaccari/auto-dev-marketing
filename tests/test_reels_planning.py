from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

from app.reels.captions import ass_text, timestamp, write_captions
from app.reels.library import ReelLibrary
from app.reels.planning import RenderOptions, build_plan
from app.reels.render import ReelStudio, render_lock
from app.reels.tools import ReelError


class ReelPlanningTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.library = ReelLibrary(self.root / 'data')
        source = self.root / 'gameplay.mp4'
        source.write_bytes(b'fixture')
        metadata = {'duration': 65.2, 'format': 'mov', 'streams': [{'codec_type': 'video', 'width': 1280, 'height': 720}]}
        with patch('app.reels.library.probe', return_value=metadata):
            self.asset = self.library.import_media(source, tags=['cidades', 'exploração'])
        self.options = RenderOptions((self.asset['id'],), duration=15, themes=('cidades',))

    def test_exact_timeline_and_no_repeated_source_intervals(self):
        for duration in (15, 30, 60):
            plan = build_plan(self.library, replace(self.options, duration=duration))
            self.assertEqual(sum(cut['frames'] for cut in plan['cuts']), duration * 30)
            previous_end = 0
            for cut in plan['cuts']:
                self.assertGreaterEqual(cut['source_start'], previous_end)
                previous_end = cut['source_start'] + cut['duration']
            self.assertFalse(plan['publishing_enabled'])
            self.assertNotIn('demônios', plan['script'])
            self.assertEqual(plan['scene_evidence'], 'user_declared_tags')

    def test_requested_theme_without_footage_and_insufficient_duration_fail(self):
        with self.assertRaisesRegex(ReelError, 'Não há gravações'):
            build_plan(self.library, replace(self.options, themes=('demonios',)))
        with self.library.db.connect() as db:
            db.execute('UPDATE reel_assets SET metadata_json=?', (json.dumps({'duration': 2.0}),))
        with self.assertRaisesRegex(ReelError, 'importe pelo menos'):
            build_plan(self.library, self.options)

    def test_options_are_bounded_for_cpu_and_input_validation(self):
        for field, value in [('duration', 14), ('duration', 61), ('threads', 0), ('threads', 20),
                             ('zoom', float('nan')), ('music_volume', -1), ('asset_ids', (self.asset['id'],) * 2),
                             ('fit', 'stretch'), ('title', '')]:
            with self.subTest(field=field, value=value), self.assertRaises(ReelError):
                replace(self.options, **{field: value}).validate()

    def test_srt_and_ass_use_same_measured_phrase_times_and_escape_tags(self):
        narration = {'cues': [{'text': r'{\pos(0,0)} Magia e exploração.', 'start': .5, 'end': 4.25}]}
        write_captions(self.root, narration, title='Meu RPG', duration=15, signature='Autor')
        srt = (self.root / 'captions.srt').read_text()
        ass = (self.root / 'captions.ass').read_text()
        self.assertIn('00:00:00,500 --> 00:00:04,250', srt)
        self.assertIn('0:00:00.50,0:00:04.25', ass)
        self.assertNotIn(r'{\pos(0,0)}', ass)
        self.assertEqual(timestamp(59.9996), '00:01:00,000')
        self.assertNotIn('{', ass_text('{tag}'))

    def test_missing_dependency_records_a_failed_job_and_keeps_existing_posts(self):
        post = self.library.db.create('Post', 'Legenda', 'art.jpg', 'Texto', 'local')
        with patch('app.reels.render.doctor', return_value={'ffmpeg': {'available': False}, 'ffprobe': {'available': False}}):
            with self.assertRaisesRegex(ReelError, 'FFmpeg'):
                ReelStudio(self.library).render(self.options)
        jobs = self.library.jobs()
        self.assertEqual(jobs[0]['status'], 'failed')
        self.assertIn('FFmpeg', jobs[0]['error'])
        self.assertEqual(self.library.db.get(post['id']), post)

    def test_only_one_render_at_a_time_and_stale_jobs_recover(self):
        with render_lock(self.library.root):
            with self.assertRaisesRegex(ReelError, 'Já existe'):
                with render_lock(self.library.root):
                    self.fail('A segunda trava não deveria ser adquirida')
        job_id = self.library.create_job(self.options.to_dict())
        self.library.update_job(job_id, 'rendering', 'cuts', 30)
        self.library.recover_interrupted()
        recovered = self.library.jobs(job_id)[0]
        self.assertEqual(recovered['status'], 'failed')
        self.assertEqual(recovered['stage'], 'interrupted')


if __name__ == '__main__':
    unittest.main()
