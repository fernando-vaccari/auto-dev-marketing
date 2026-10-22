"""Instalador exclusivamente local/isolado de OpenVoice; origem upstream fixada."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.venv-voiceclone'
COMMIT = '74a1d147b17a8c3092dd5430504bd83ef6c7eb23'
CHECKPOINT = 'https://myshell-public-repo-host.s3.amazonaws.com/openvoice/checkpoints_v2_0417.zip'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint-archive', type=Path, help='ZIP obtido da URL oficial documentada, sem modelos de terceiros.')
    parser.add_argument('--runtime-only', action='store_true', help='Prepara dependências; não baixa os pesos nem habilita a clonagem.')
    args = parser.parse_args()
    if not (3, 10) <= sys.version_info[:2] <= (3, 12):
        raise SystemExit('Use VOICE_CLONE_PYTHON=python3.12 (ou 3.10/3.11); o Python principal permanece intacto.')
    if RUNTIME.is_symlink() or RUNTIME.resolve() == (ROOT / '.venv').resolve():
        raise SystemExit('O ambiente isolado não pode ser um link para outro diretório. Nada alterado.')
    python = RUNTIME / 'bin/python'
    if python.exists() and not (RUNTIME / 'pyvenv.cfg').is_file():
        raise SystemExit('Diretório existente não é um venv próprio; preservado.')
    if not python.exists():
        subprocess.run([sys.executable, '-m', 'venv', str(RUNTIME)], check=True)
    version = subprocess.check_output([str(python), '-c', 'import sys;print("%d.%d"%sys.version_info[:2])'], text=True).strip()
    prefix = subprocess.check_output([str(python), '-c', 'import sys;print(sys.prefix)'], text=True).strip()
    if Path(prefix).resolve() != RUNTIME.resolve():
        raise SystemExit('O executável aponta para outro ambiente; instalação recusada.')
    if version not in {'3.10', '3.11', '3.12'}:
        raise SystemExit('Ambiente isolado incompatível. Não foi removido ou alterado.')
    subprocess.run([str(python), '-m', 'pip', 'install', 'torch==2.5.1+cpu', '--index-url', 'https://download.pytorch.org/whl/cpu'], check=True)
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements-voice-cloning.txt')], check=True)
    source = RUNTIME / 'OpenVoice'
    if not source.exists():
        subprocess.run(['git', 'clone', '--no-checkout', 'https://github.com/myshell-ai/OpenVoice.git', str(source)], check=True)
        subprocess.run(['git', '-C', str(source), 'checkout', '--detach', COMMIT], check=True)
    if subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() != COMMIT:
        raise SystemExit('OpenVoice existente em outra revisão; preservado, instalação interrompida.')
    if subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip():
        raise SystemExit('OpenVoice local modificado; preservado, instalação interrompida.')
    subprocess.run([str(python), '-c', 'import sys;sys.path.insert(0,sys.argv[1]);from openvoice.api import ToneColorConverter;import torch;assert not torch.version.cuda;print("OpenVoice importado em CPU")', str(source)], check=True)
    if args.runtime_only:
        print('Ambiente isolado preparado. PESOS AUSENTES: clonagem não habilitada.')
        return
    models = RUNTIME / 'models'
    models.mkdir(mode=0o700, exist_ok=True)
    files = ('config.json', 'checkpoint.pth')
    if all((models / n).is_file() for n in (*files, 'manifest.json')):
        manifest = json.loads((models / 'manifest.json').read_text())
        if all(hashlib.sha256((models / n).read_bytes()).hexdigest() == manifest['sha256'][n] for n in files):
            print('Modelos existentes conferidos; nenhuma substituição.');return
        raise SystemExit('Modelos existentes diferentes do manifesto; preservados.')
    if any((models / n).exists() for n in files):
        raise SystemExit('Instalação parcial de modelos existente; preservada. Consulte a documentação.')
    archive = args.checkpoint_archive
    downloaded = False
    if archive is None:
        archive = models / 'download.zip.part'
        if archive.exists():
            raise SystemExit('Download parcial existente; confira e remova manualmente apenas download.zip.part.')
        downloaded = True
        try:
            with urllib.request.urlopen(CHECKPOINT, timeout=60) as incoming, archive.open('xb') as target:
                shutil.copyfileobj(incoming, target)
        except Exception as error:
            archive.unlink(missing_ok=True)
            raise SystemExit(f'Não foi possível obter pesos oficiais ({type(error).__name__}). Motor indisponível; consulte docs/voice-cloning.md.')
    try:
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        with zipfile.ZipFile(archive) as packed:
            for name in files:
                matches = [n for n in packed.namelist() if n.endswith('/converter/' + name)]
                if len(matches) != 1 or packed.getinfo(matches[0]).file_size > 512 * 1024 * 1024:
                    raise SystemExit('Arquivo oficial incompatível; nada extraído por caminhos arbitrários.')
            for name in files:
                entry = next(n for n in packed.namelist() if n.endswith('/converter/' + name))
                with packed.open(entry) as incoming, (models / name).open('xb') as target:
                    shutil.copyfileobj(incoming, target)
                (models / name).chmod(0o600)
        manifest = {'source': CHECKPOINT, 'source_commit': COMMIT, 'archive_sha256': digest,
                    'sha256': {n: hashlib.sha256((models / n).read_bytes()).hexdigest() for n in files}}
        (models / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        print('Pesos oficiais instalados. Hashes registrados no manifesto local; teste uma prévia antes de usar.')
    finally:
        if downloaded:
            archive.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
