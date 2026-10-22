"""Diagnóstico sem download, sem carregar pesos e sem ler gravações privadas."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.reels.voice_cloning import runtime_status


def main():
    runtime = ROOT / '.venv-voiceclone'
    result = {'main_python': platform.python_version(), 'cpu': platform.machine(), 'logical_cpus': os.cpu_count(),
              'runtime': runtime_status(), 'private_audio_uploaded_to_network': False}
    profiles = Path(os.getenv('DATA_DIR', str(ROOT / '.data'))) / 'reels/voice-cloning'
    result['directories'] = {'runtime': str(runtime), 'models': str(runtime / 'models'),
                            'profiles': str(profiles), 'profiles_exists': profiles.is_dir(),
                            'profiles_private': (profiles.stat().st_mode & 0o777) == 0o700 if profiles.is_dir() else None}
    try:
        result['memory_available_mib'] = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))) // 1024
    except (OSError, StopIteration, ValueError):
        result['memory_available_mib'] = None
    if (runtime / 'bin/python').is_file():
        code = 'import json,sys,torch;sys.path.insert(0,sys.argv[1]);from openvoice.api import ToneColorConverter;print(json.dumps(dict(python=sys.version.split()[0],torch=torch.__version__,cuda=torch.version.cuda)))'
        process = subprocess.run([str(runtime / 'bin/python'), '-c', code, str(runtime / 'OpenVoice')],capture_output=True,text=True,timeout=45)
        result['dependencies_ok'] = process.returncode == 0
        if process.returncode == 0:
            result['isolated_runtime'] = json.loads(process.stdout)
        else:
            result['error'] = 'Falha na importação do motor; execute o instalador isolado.'
    if result['runtime']['installed']:
        models = runtime / 'models'
        try:
            manifest = json.loads((models / 'manifest.json').read_text())
            result['model_hashes_ok'] = all(hashlib.sha256((models / name).read_bytes()).hexdigest() == manifest['sha256'][name] for name in ('config.json','checkpoint.pth'))
        except (OSError, ValueError, KeyError):
            result['model_hashes_ok'] = False
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['runtime']['installed'] and result.get('dependencies_ok') and result.get('model_hashes_ok') else 2


if __name__ == '__main__':
    raise SystemExit(main())
