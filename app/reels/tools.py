from pathlib import Path
import json
import math
import os
import shutil
import subprocess


class ReelError(Exception):
    """Falha de entrada, dependência ou processamento, exibível pela CLI."""


def executable(name):
    override = os.getenv('REELS_' + name.upper().replace('-', '_'))
    path = shutil.which(override or name)
    if not path:
        raise ReelError(f'{name} não encontrado. Consulte docs/reels.md para instalar as ferramentas locais.')
    return path


def run(args, *, cwd=None, input_data=None, timeout=120, log=None):
    try:
        result = subprocess.run([str(arg) for arg in args], input=input_data, cwd=cwd,
                                capture_output=True, timeout=timeout, check=False)
    except FileNotFoundError:
        raise ReelError(f'Ferramenta não encontrada: {Path(args[0]).name}') from None
    except subprocess.TimeoutExpired:
        raise ReelError(f'Tempo de processamento excedido: {Path(args[0]).name}') from None
    if log:
        with Path(log).open('ab') as file:
            file.write(result.stderr)
    if result.returncode:
        detail = result.stderr.decode('utf-8', errors='replace')[-2500:]
        raise ReelError(f'{Path(args[0]).name} falhou (código {result.returncode}): {detail}')
    return result.stdout


def probe(path):
    raw = run([executable('ffprobe'), '-v', 'error', '-protocol_whitelist', 'file,pipe',
               '-show_entries', 'format=duration,format_name:stream=codec_type,codec_name,width,height,pix_fmt,avg_frame_rate,sample_rate,channels,duration,nb_frames',
               '-of', 'json', str(path)], timeout=30)
    try:
        data = json.loads(raw)
        duration = float(data.get('format', {}).get('duration', 0))
        streams = data['streams']
        if not math.isfinite(duration) or duration <= 0 or not streams:
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise ReelError('Não foi possível medir a duração ou os streams da mídia.') from None
    return {'duration': duration, 'format': data['format'].get('format_name', ''), 'streams': streams}


def doctor():
    result = {}
    for name in ('ffmpeg', 'ffprobe', 'espeak-ng', 'piper'):
        try:
            result[name] = {'available': True, 'path': executable(name)}
        except ReelError:
            result[name] = {'available': False}
    if result['ffmpeg']['available']:
        binary = result['ffmpeg']['path']
        filters = run([binary, '-hide_banner', '-filters']).decode()
        encoders = run([binary, '-hide_banner', '-encoders']).decode()
        result['filters'] = {name: name in filters for name in ('scale', 'pad', 'ass', 'zoompan', 'fade', 'amix', 'loudnorm','xfade','sidechaincompress','alimiter','silenceremove','boxblur','vignette','eq','unsharp')}
        result['encoders'] = {name: name in encoders for name in ('libx264', 'aac')}
    result['network_required_for_render'] = False
    return result
