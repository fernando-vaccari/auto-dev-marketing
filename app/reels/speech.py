from pathlib import Path
import importlib.util
import json
import re
import sys
import wave

from .tools import ReelError, executable, run


class SpeechTooLong(ReelError):
    pass


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
    if engine in {'kokoro','my_voice'}:
        from .voices import available
        if not available(model):
            raise ReelError('Instale o modelo Kokoro local para utilizar narração neural pt-BR.')
        return engine, []
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


def synthesize(text, directory, *, engine='auto', model=None, duration=30, threads=4, voice_id='pf_dora', speed=1.0, volume=1.0, clone_profile_id=None, clone_root=None):
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
        if engine == 'my_voice':
            from .voice_cloning import generate
            generate(phrase,raw,root=clone_root,profile_id=clone_profile_id,kokoro_dir=model,threads=threads)
        elif engine == 'kokoro':
            from .voices import generate
            generate(phrase, raw, directory=model, voice=voice_id, threads=threads)
        else:
            run(args, input_data=(phrase + '\n').encode(), timeout=120, log=directory / 'render.log')
        run([executable('ffmpeg'), '-nostdin', '-v', 'error', '-y', '-i', raw,
             '-af', f'silenceremove=start_periods=1:start_duration=0.02:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_duration=0.02:start_threshold=-50dB,areverse,atempo={speed},loudnorm=I=-18:TP=-3:LRA=9,volume={volume},alimiter=limit=0.95:level=false',
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
        raise SpeechTooLong(f'A narração tem {voice_total:.2f}s e não cabe no Reel de {duration}s. Reduza o roteiro ou aumente a duração; nenhuma palavra foi acelerada ou cortada.')
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
            'timing_method': 'measured_separate_tts_phrases', 'speed_changed': speed != 1.0}


def synthesize_fitting(text, directory, *, auto_shorten=False, **kwargs):
    """Refaz o texto e a síntese, nunca corta áudio para caber no vídeo."""
    attempts=[]
    for attempt in range(4):
        try:
            result=synthesize(text,directory,**kwargs)
            result.update(text=text,attempts=attempts+[{'attempt':attempt+1,'duration':result['speech_duration']}])
            return result
        except SpeechTooLong as error:
            attempts.append({'attempt':attempt+1,'error':str(error)})
            if not auto_shorten or attempt==3:raise
            sentences=re.split(r'(?<=[.!?])\s+',text.strip())
            if len(sentences)>2:
                text=sentences[0]+' '+sentences[-1]
            else:
                words=text.split()
                reduced=words[:max(4,int(len(words)*.68))]
                text=' '.join(reduced).rstrip('.,;:!?')+'.'
    raise ReelError('Não foi possível ajustar a narração.')
