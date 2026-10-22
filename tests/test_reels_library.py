from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from app.db import Database
from app.reels.library import ReelLibrary, normalize_themes
from app.reels.tools import ReelError


class ReelLibraryTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.library = ReelLibrary(self.root / 'data')
        self.metadata = {'duration': 20, 'format': 'mov,mp4,m4a,3gp,3g2,mj2',
                         'streams': [{'codec_type': 'video', 'width': 1280, 'height': 720}]}

    def test_additive_schema_preserves_existing_posts_brand_and_automation(self):
        db = Database(self.root / 'data')
        brand = db.brand()
        brand['name'] = 'Marca existente'
        db.save_brand(brand)
        post = db.create('Título existente', 'Legenda', 'existing.jpg', 'Arte', 'local')
        automation = db.automation()
        ReelLibrary(self.root / 'data')
        self.assertEqual(db.get(post['id']), post)
        self.assertEqual(db.brand(), brand)
        self.assertEqual(db.automation(), automation)

    def test_import_copies_deduplicates_and_merges_only_declared_tags(self):
        source = self.root / 'cidade com espaços.MP4'
        source.write_bytes(b'recorded video fixture')
        with patch('app.reels.library.probe', return_value=self.metadata):
            first = self.library.import_media(source, tags=['cidades'])
            second = self.library.import_media(source, tags=['exploração'])
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(second['tags'], ['cidades', 'exploracao'])
        source.unlink()
        self.assertTrue(self.library.asset_path(second).exists())
        self.assertEqual(len(self.library.assets()), 1)

    def test_corrupted_private_copy_is_rejected_and_reimport_restores_it(self):
        source = self.root / 'capture.mp4'
        source.write_bytes(b'original fixture bytes')
        with patch('app.reels.library.probe', return_value=self.metadata):
            asset = self.library.import_media(source)
            stored = self.library.asset_path(asset)
            stored.write_bytes(b'corrupted bytes')
            with self.assertRaisesRegex(ReelError, 'corrompida'):
                self.library.asset_path(asset, verify=True)
            restored = self.library.import_media(source)
        self.assertEqual(restored['id'], asset['id'])
        self.assertEqual(self.library.asset_path(restored, verify=True).read_bytes(), source.read_bytes())

    def test_invalid_media_does_not_remain_in_library(self):
        path = self.root / 'fake.mp4'
        path.write_bytes(b'not a video')
        with patch('app.reels.library.probe', side_effect=ReelError('Arquivo inválido')):
            with self.assertRaises(ReelError):
                self.library.import_media(path)
        self.assertEqual(self.library.assets(), [])
        self.assertEqual(list(self.library.imports.iterdir()), [])

    def test_music_needs_audio_stream_and_does_not_add_scene_tags(self):
        source = self.root / 'trilha.wav'
        source.write_bytes(b'audio fixture')
        metadata = {'duration': 10, 'format': 'wav', 'streams': [{'codec_type': 'audio'}]}
        with patch('app.reels.library.probe', return_value=metadata):
            music = self.library.import_media(source, kind='music')
        self.assertEqual(music['tags'], [])
        with self.assertRaises(ReelError):
            self.library.asset(music['id'], 'video')

    def test_unknown_themes_and_path_escape_are_rejected(self):
        self.assertEqual(normalize_themes(['demônios, NPCs']), ['demonios', 'npcs'])
        with self.assertRaises(ReelError):
            normalize_themes(['cena não gravada'])
        with self.assertRaises(ReelError):
            self.library.asset_path({'relative_path': '../../outside.mp4'})


if __name__ == '__main__':
    unittest.main()
