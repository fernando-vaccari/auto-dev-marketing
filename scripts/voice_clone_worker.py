"""Conversor CPU isolado, sem rede/serviço público; termina junto com o job pai."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import socket
import sys
import time


def deny_network(*args, **kwargs):
    raise RuntimeError('Rede desativada no motor de clonagem local.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--threads', type=int, default=4, choices=range(1, 9))
    parser.add_argument('--parent-pid', type=int, required=True)
    args = parser.parse_args()
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0 or os.getppid() != args.parent_pid:
        return 2
    resource.setrlimit(resource.RLIMIT_AS, (8 * 1024**3, 8 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (240, 240))
    socket.create_connection = deny_network
    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    started = time.monotonic()
    runtime = Path(__file__).resolve().parents[1] / '.venv-voiceclone'
    models = runtime / 'models'
    manifest = json.loads((models / 'manifest.json').read_text())
    for name in ('config.json', 'checkpoint.pth'):
        if hashlib.sha256((models / name).read_bytes()).hexdigest() != manifest['sha256'][name]:
            raise RuntimeError('Modelo alterado desde a instalação.')
    sys.path.insert(0, str(runtime / 'OpenVoice'))
    import torch
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    from openvoice.api import OpenVoiceBaseClass, ToneColorConverter
    # A API upstream tenta baixar wavmark no construtor. Inicialização documentada
    # sem watermark evita qualquer download ou dependência de ASR/serviço externo.
    converter = ToneColorConverter.__new__(ToneColorConverter)
    OpenVoiceBaseClass.__init__(converter, str(models / 'config.json'), device='cpu')
    converter.watermark_model = None
    converter.version = getattr(converter.hps, '_version_', 'v2')
    checkpoint = torch.load(models / 'checkpoint.pth', map_location='cpu', weights_only=True)
    converter.model.load_state_dict(checkpoint['model'], strict=True)
    with torch.inference_mode():
        source = converter.extract_se(str(args.source))
        target = converter.extract_se(str(args.reference))
        converter.convert(str(args.source), source, target, output_path=str(args.output), message=None)
    print(json.dumps({'seconds': round(time.monotonic()-started, 3), 'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except MemoryError:
        print('Memória insuficiente.', file=sys.stderr);raise SystemExit(75)
    except Exception as error:
        if any(term in str(error).lower() for term in ('out of memory','cannot allocate memory',"can't allocate memory")):
            raise SystemExit(75)
        print(f'Motor indisponível: {type(error).__name__}: {error}', file=sys.stderr)
        raise SystemExit(2)
