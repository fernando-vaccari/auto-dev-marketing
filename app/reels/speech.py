from pathlib import Path
import importlib.util
import json
import re
import sys
import wave

from .tools import ReelError, executable, run


def phrases(text):
    result = []
    for sentence in re.split(r'(?<=[.!?;])\s+', ' '.join(text.split())):
        words = sentence.split()
        current = []
        for word in words:
            if len(word) > 45:
                raise ReelError('O roteiro contém uma palavra muito longa para uma legenda legível.')
            if current and (len(current) >= 10 or len(' '.join(current + [word])) > 74):
                result.append(' '.join(current))
                current = []
            current.append(word)
        if current:
            result.append(' '.join(current))
    return result


def wave_duration(path):
    with wave.open(str(path), 'rb') as audio:
        return audio.getnframes() / audio.getframerate()


def choose_voice(engine, model=None):
    if engine == 'auto':
        engine = 'piper' if model else 'espeak'
    if engine == 'piper':
        path = Path(model).expanduser().resolve() if model else None
        if not path or not path.is_file() or not Path(str(path) + '.json').is_file():
            raise ReelError('Piper exige um modelo .onnx local e seu arquivo .onnx.json. Nenhum modelo é baixado durante o render.')
        try:
            config = json.loads(Path(str(path) + '.json').read_text(encoding='utf-8'))
            language = config.get('language', {}).get('code', '')
            espeak_voice = config.get('espeak', {}).get('voice', '')
            if language not in {'pt_BR', 'pt-br'} and espeak_voice != 'pt-br':
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise ReelError('Escolha um modelo Piper em português brasileiro (pt_BR), com configuração JSON válida.') from None
        try:
            binary = [executable('piper')]
        except ReelError:
            if not importlib.util.find_spec('piper'):
                raise ReelError('Instale requirements-reels-piper.txt ou use --tts espeak.') from None
            binary = [sys.executable, '-m', 'piper']
        return engine, binary + ['-m', str(path)]
    return engine, [executable('espeak-ng'), '-v', 'pt-br', '-s', '165']


def synthesize(text, directory, *, engine='auto', model=None, duration=30, threads=4):
    directory = Path(directory)
    speech_dir = directory / 'speech'
    speech_dir.mkdir(exist_ok=True)
    engine, command = choose_voice(engine, model)
    normalized = []
    timings = []
    for index, phrase in enumerate(phrases(text)):
        raw = speech_dir / f'raw-{index:03d}.wav'
        target = speech_dir / f'phrase-{index:03d}.wav'
        args = command + (['-f', str(raw)] if engine == 'piper' else ['-w', str(raw), '--stdin'])
        # Locale pt-BR é explícito no eSpeak. Para Piper, o idioma vem do modelo local escolhido.
        run(args, input_data=(phrase + '\n').encode(), timeout=120, log=directory / 'render.log')
        run([executable('ffmpeg'), '-nostdin', '-v', 'error', '-y', '-i', raw,
             '-ac', '1', '-ar', '48000', '-c:a', 'pcm_s16le', '-threads', str(threads), target],
            log=directory / 'render.log')
        measured = wave_duration(target)
        if measured <= 0:
            raise ReelError('O sintetizador produziu um trecho vazio.')
        normalized.append(target)
        timings.append({'text': phrase, 'duration': measured})
    voice_total = sum(item['duration'] for item in timings)
    intro = 0.5
    available_frames = round((duration - intro - 0.5) * 48000)
    voice_frames = sum(round(item['duration'] * 48000) for item in timings)
    if voice_frames > available_frames:
        raise ReelError(f'A narração tem {voice_total:.2f}s e não cabe no Reel de {duration}s. Reduza o roteiro ou aumente a duração; nenhuma palavra foi acelerada ou cortada.')
    gap_frames = min(72000, (available_frames - voice_frames) // max(1, len(timings) - 1))
    audio_path = directory / 'narration.wav'
    cursor = round(intro * 48000)
    cues = []
    with wave.open(str(audio_path), 'wb') as destination:
        destination.setnchannels(1)
        destination.setsampwidth(2)
        destination.setframerate(48000)
        destination.writeframes(b'\0\0' * cursor)
        for index, (path, item) in enumerate(zip(normalized, timings)):
            with wave.open(str(path), 'rb') as source:
                frames = source.readframes(source.getnframes())
                count = source.getnframes()
            cues.append({'text': item['text'], 'start': cursor / 48000, 'end': (cursor + count) / 48000})
            destination.writeframes(frames)
            cursor += count
            if index < len(timings) - 1:
                count = gap_frames
                destination.writeframes(b'\0\0' * count)
                cursor += count
        destination.writeframes(b'\0\0' * max(0, duration * 48000 - cursor))
    return {'engine': engine, 'audio': 'narration.wav', 'speech_duration': voice_total,
            'audio_duration': wave_duration(audio_path), 'cues': cues,
            'timing_method': 'measured_separate_tts_phrases', 'speed_changed': False}
