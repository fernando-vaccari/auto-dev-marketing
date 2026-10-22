from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import shutil
import unittest
import wave

from app.reels.speech import choose_voice, phrases, synthesize, wave_duration
from app.reels.tools import ReelError


class ReelSpeechTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def test_phrase_split_keeps_words_and_readable_limits(self):
        text = 'Um RPG medieval está em desenvolvimento no Roblox. Acompanhe estas capturas de cidades e cavernas do projeto.'
        chunks = phrases(text)
        self.assertEqual(' '.join(chunks), text)
        self.assertTrue(all(len(chunk.split()) <= 10 and len(chunk) <= 74 for chunk in chunks))

    def test_measured_wav_is_caption_clock_and_audio_is_padded_without_speed_change(self):
        def fake_run(args, **kwargs):
            if args[0] == '/fake/espeak-ng':
                path = Path(args[args.index('-w') + 1])
                with wave.open(str(path), 'wb') as file:
                    file.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
                    file.writeframes(b'\0\0' * 48000)
            else:
                shutil.copyfile(args[args.index('-i') + 1], args[-1])
            return b''
        with patch('app.reels.speech.executable', side_effect=lambda name: '/fake/' + name), patch('app.reels.speech.run', side_effect=fake_run):
            result = synthesize('Primeira frase. Segunda frase.', self.root, engine='espeak', duration=15)
        self.assertEqual([cue['end'] - cue['start'] for cue in result['cues']], [1.0, 1.0])
        self.assertEqual(result['cues'][0]['start'], .5)
        self.assertEqual(wave_duration(self.root / 'narration.wav'), 15)
        self.assertFalse(result['speed_changed'])

    def test_too_long_narration_is_not_cut_or_accelerated(self):
        def fake_run(args, **kwargs):
            if args[0] == '/fake/espeak-ng':
                with wave.open(str(args[args.index('-w') + 1]), 'wb') as file:
                    file.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
                    file.writeframes(b'\0\0' * (16 * 48000))
            else:
                shutil.copyfile(args[args.index('-i') + 1], args[-1])
            return b''
        with patch('app.reels.speech.executable', side_effect=lambda name: '/fake/' + name), patch('app.reels.speech.run', side_effect=fake_run):
            with self.assertRaisesRegex(ReelError, 'não cabe'):
                synthesize('Uma frase longa.', self.root, engine='espeak', duration=15)
        self.assertFalse((self.root / 'narration.wav').exists())

    def test_explicit_piper_requires_a_local_model_and_never_silently_switches_engine(self):
        with self.assertRaisesRegex(ReelError, 'modelo .onnx local'):
            choose_voice('piper', str(self.root / 'missing.onnx'))
        model = self.root / 'pt_BR.onnx'
        model.write_bytes(b'test model, not executed')
        Path(str(model) + '.json').write_text('{"language":{"code":"pt_BR"}}')
        with patch('app.reels.speech.executable', return_value='/fake/piper'):
            engine, command = choose_voice('piper', str(model))
        self.assertEqual(engine, 'piper')
        self.assertEqual(command, ['/fake/piper', '-m', str(model)])
        Path(str(model) + '.json').write_text('{"language":{"code":"en_US"}}')
        with self.assertRaisesRegex(ReelError, 'português brasileiro'):
            choose_voice('piper', str(model))


if __name__ == '__main__':
    unittest.main()
