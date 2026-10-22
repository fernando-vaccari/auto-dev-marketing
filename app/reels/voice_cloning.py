"""Perfis locais e conversão OpenVoice isolada; nenhuma dependência neural nova no servidor."""
from contextlib import contextmanager
from pathlib import Path
import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import time
import uuid
import wave
from datetime import datetime, timezone

from .tools import ReelError, executable, probe, run

PROJECT = Path(__file__).resolve().parents[2]
MAX_BYTES = 20 * 1024 * 1024
EXTENSIONS = {'.wav', '.mp3', '.webm', '.ogg', '.m4a', '.mp4'}


def private_root(root):
    root = Path(root)
    if root.is_symlink():
        raise ReelError('Diretório de voz inválido.')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    return root


def profile_dir(root, identifier):
    if not re.fullmatch(r'[a-f0-9]{32}', identifier or ''):
        raise ReelError('Perfil de voz inválido.')
    root = private_root(root).resolve()
    path = root / identifier
    if path.is_symlink() or path.resolve() != path or not path.is_dir():
        raise ReelError('Perfil de voz não encontrado.')
    return path


def read_profile(root, identifier):
    path = profile_dir(root, identifier)
    if any((path / name).is_symlink() for name in ('profile.json', 'reference.wav')):
        raise ReelError('Arquivo de voz inválido.')
    try:
        result = json.loads((path / 'profile.json').read_text())
        if hashlib.sha256((path / 'reference.wav').read_bytes()).hexdigest() != result['sha256']:
            raise ValueError
        return result
    except (OSError, ValueError, KeyError):
        raise ReelError('Perfil de voz danificado; importe novamente.') from None


@contextmanager
def profile_lock(root):
    with (private_root(root) / 'profiles.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ReelError('Outro pedido está utilizando os perfis de voz. Aguarde.') from None
        yield


def profiles(root):
    result = []
    for path in private_root(root).iterdir():
        if re.fullmatch(r'[a-f0-9]{32}', path.name) and path.is_dir() and not path.is_symlink():
            try:
                item = read_profile(root, path.name)
                result.append({key: item[key] for key in ('id', 'name', 'duration', 'created_at', 'consent_at')})
            except ReelError:
                continue
    return sorted(result, key=lambda p: p['created_at'])


def create_profile(root, source, *, name, consent):
    if consent is not True:
        raise ReelError('Confirme que a voz é sua ou que possui autorização para utilizá-la.')
    name = ' '.join(name.split())
    if not name or len(name) > 60 or any(ord(c) < 32 for c in name):
        raise ReelError('Nome de perfil inválido (1 a 60 caracteres).')
    source = Path(source)
    if source.suffix.lower() not in EXTENSIONS or source.stat().st_size > MAX_BYTES:
        raise ReelError('Formato ou tamanho da amostra inválido (máximo 20 MiB).')
    # MediaRecorder WebM pode não informar duração no cabeçalho. Inspecionamos
    # streams e medimos uma decodificação limitada a 61 s, nunca confiamos no cabeçalho.
    metadata = json.loads(run([executable('ffprobe'), '-v', 'error', '-protocol_whitelist', 'file,pipe',
                              '-show_entries', 'stream=codec_type', '-of', 'json', source], timeout=30))
    streams = metadata.get('streams', [])
    if len(streams) != 1 or streams[0].get('codec_type') != 'audio':
        raise ReelError('Envie apenas áudio, com uma faixa e sem vídeo.')
    with profile_lock(root):
        if len(profiles(root)) >= 5:
            raise ReelError('Limite de cinco perfis. Exclua um perfil antes de importar outro.')
        identifier = uuid.uuid4().hex
        directory = private_root(Path(root) / identifier)
        try:
            shutil.copyfile(source, directory / ('original' + source.suffix.lower()))
            decoded = directory / 'decoded.wav'
            run([executable('ffmpeg'), '-nostdin', '-v', 'error', '-protocol_whitelist', 'file,pipe', '-i', source,
                 '-t', '61', '-ac', '1', '-ar', '24000', '-c:a', 'pcm_s16le', '-threads', '2', decoded], timeout=60)
            with wave.open(str(decoded)) as sound:
                original_duration = sound.getnframes() / sound.getframerate()
            if not 6 <= original_duration <= 60:
                raise ReelError('A amostra precisa ter entre 6 e 60 segundos de áudio decodificado.')
            target = directory / 'reference.wav'
            run([executable('ffmpeg'), '-nostdin', '-v', 'error', '-i', decoded, '-t', '60',
                 '-af', 'silenceremove=start_periods=1:start_duration=0.1:start_threshold=-40dB,areverse,silenceremove=start_periods=1:start_duration=0.1:start_threshold=-40dB,areverse,loudnorm=I=-20:TP=-3:LRA=9,alimiter=limit=0.9:level=false',
                 '-ac', '1', '-ar', '24000', '-c:a', 'pcm_s16le', '-threads', '2', target], timeout=60)
            with wave.open(str(target)) as sound:
                duration = sound.getnframes() / sound.getframerate()
                import array
                samples = array.array('h', sound.readframes(sound.getnframes()))
            rms = math.sqrt(sum(x*x for x in samples) / max(1, len(samples))) / 32768
            active = sum(abs(x) > 160 for x in samples) / max(1, len(samples))
            if duration < 6 or rms < .005 or active < .15:
                raise ReelError('Áudio vazio, muito baixo ou com silêncio excessivo. Grave ao menos 6 segundos de fala limpa.')
            decoded.unlink()
            now = datetime.now(timezone.utc).isoformat()
            result = dict(id=identifier, name=name, duration=round(duration, 3), created_at=now,
                          consent_at=now, sha256=hashlib.sha256(target.read_bytes()).hexdigest())
            (directory / 'profile.json').write_text(json.dumps(result, ensure_ascii=False))
            for path in directory.iterdir():
                path.chmod(0o600)
            return {k: v for k, v in result.items() if k != 'sha256'}
        except BaseException:
            shutil.rmtree(directory)
            raise


def runtime_status():
    runtime = PROJECT / '.venv-voiceclone'
    models = runtime / 'models'
    source = runtime / 'OpenVoice'
    present = (runtime / 'bin/python').is_file() and (source / 'openvoice/api.py').is_file()
    ready = present and all((models / p).is_file() for p in ('config.json', 'checkpoint.pth', 'manifest.json'))
    return {'installed': ready, 'environment_present': present, 'engine': 'OpenVoice V2 + Kokoro pt-BR',
            'cpu_only': True, 'reason': None if ready else 'Instale o motor isolado: bash scripts/install-voice-cloning.sh. Nenhuma voz é enviada para fora do computador.'}


def generate(text, output, *, root, profile_id, kokoro_dir, threads=4):
    from .voices import generate as base_voice
    directory = profile_dir(root, profile_id)
    profile = read_profile(root, profile_id)
    if not runtime_status()['installed']:
        raise ReelError(runtime_status()['reason'])
    output = Path(output)
    base = output.with_name(output.stem + '-base.wav')
    lock = private_root(root) / 'synthesis.lock'
    with profile_lock(root), lock.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ReelError('Uma clonagem já está em andamento. Aguarde antes de iniciar outra.') from None
        started = time.monotonic()
        try:
            base_voice(text, base, directory=kokoro_dir, voice='pf_dora', threads=threads)
            # Não herda tokens, proxies ou senhas. O filho permanece no grupo do job para cancelamento.
            environment = {k: os.environ[k] for k in ('PATH', 'LANG', 'LC_ALL', 'TMPDIR') if k in os.environ}
            environment.update(OMP_NUM_THREADS=str(threads), OPENBLAS_NUM_THREADS=str(threads),
                               MKL_NUM_THREADS=str(threads), CUDA_VISIBLE_DEVICES='', HF_HUB_OFFLINE='1',
                               TRANSFORMERS_OFFLINE='1', PYTHONNOUSERSITE='1')
            runtime = PROJECT / '.venv-voiceclone'
            try:
                result = subprocess.run([str(runtime / 'bin/python'), str(PROJECT / 'scripts/voice_clone_worker.py'),
                    '--source', str(base.resolve()), '--reference', str((directory / 'reference.wav').resolve()),
                    '--output', str(output.resolve()), '--threads', str(threads), '--parent-pid', str(os.getpid())],
                    env=environment, capture_output=True, timeout=240)
            except subprocess.TimeoutExpired:
                raise ReelError('A clonagem excedeu 240 segundos. Reduza o roteiro ou use Dora.') from None
            if result.returncode in (75, -9):
                raise ReelError('Memória insuficiente no motor de voz. Feche outros programas ou use Dora.')
            if result.returncode:
                raise ReelError('O motor de clonagem falhou. Execute o diagnóstico; nenhuma voz foi substituída por outra silenciosamente.')
            measured = probe(output)
            if not any(s['codec_type'] == 'audio' for s in measured['streams']):
                raise ReelError('O motor não gerou áudio válido.')
            performance = {'engine': 'openvoice_v2', 'elapsed_seconds': round(time.monotonic()-started, 3),
                           'audio_seconds': measured['duration'], 'threads': threads, 'profile_id': profile['id']}
            with (output.parent / 'voice-cloning-performance.jsonl').open('a') as log:
                log.write(json.dumps(performance) + '\n')
        finally:
            base.unlink(missing_ok=True)
