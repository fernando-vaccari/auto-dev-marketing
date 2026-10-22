"""Empacota somente o código e a documentação, sem estado ou credenciais."""
from pathlib import Path
import hashlib
import os
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
FILES = {'.dockerignore', '.env.example', '.gitignore', 'Dockerfile', 'README.md', 'compose.yaml',
         'requirements-integrations.txt','requirements-reels-kokoro.txt','requirements.in', 'requirements.txt', 'requirements-dev.txt', 'requirements-reels-piper.txt'}
DIRECTORIES = {'.github', 'app', 'deploy', 'docs', 'scripts', 'tests', 'roblox'}
MEDIA_SUFFIXES = {'.mp4', '.mov', '.webm', '.wav', '.mp3', '.m4a', '.ogg', '.flac', '.aac', '.onnx','.bin','.mkv'}


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / 'artifacts' / 'auto-posts.zip'
    target.parent.mkdir(parents=True, exist_ok=True)
    paths = [ROOT / filename for filename in FILES]
    for name in DIRECTORIES:
        for directory, children, files in os.walk(ROOT / name):
            children[:] = [child for child in children if child not in {'__pycache__', '.data', '.cache', '.venv', '.git'}]
            paths.extend(Path(directory) / file for file in files if not file.endswith('.pyc') and not file.startswith('.env'))
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            if path.is_file() and not path.is_symlink() and path.suffix.lower() not in MEDIA_SUFFIXES:
                archive.write(path, 'auto-posts/' + path.relative_to(ROOT).as_posix())
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(f'{digest}  {target.name}\n')
    print(f'Pacote criado: {target} ({target.stat().st_size} bytes)')


if __name__ == '__main__':
    main()
