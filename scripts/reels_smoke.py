"""Render verificável com padrões sintéticos, nunca anunciado como gameplay real."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.reels.library import ReelLibrary
from app.reels.planning import RenderOptions
from app.reels.render import ReelStudio
from app.reels.tools import ReelError, executable, run


def main():
    parser = argparse.ArgumentParser(description='Gerar um Reel de teste SINTÉTICO, sem Roblox ou publicação.')
    parser.add_argument('--data-dir', type=Path, default=ROOT / '.data' / 'reels-smoke')
    args = parser.parse_args()
    directory = args.data_dir.resolve()
    fixtures = directory / 'synthetic-inputs'
    fixtures.mkdir(parents=True, exist_ok=True)
    library = ReelLibrary(directory)
    sources = []
    for name, size, fps, codec in [('synthetic.mp4', '640x360', 24, 'libx264'),
                                    ('synthetic.mov', '180x320', 30, 'libx264'),
                                    ('synthetic.webm', '320x180', 25, 'libvpx-vp9')]:
        path = fixtures / name
        if not path.exists():
            run([executable('ffmpeg'), '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', f'testsrc2=size={size}:rate={fps}',
                 '-t', '6', '-an', '-c:v', codec, '-threads', '2', '-pix_fmt', 'yuv420p', path])
        sources.append(library.import_media(path, tags=['gameplay']))
    music = fixtures / 'synthetic-tone.wav'
    if not music.exists():
        run([executable('ffmpeg'), '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=220:sample_rate=48000', '-t', '2', music])
    track = library.import_media(music, kind='music')
    def progress(value):
        print(json.dumps(value, ensure_ascii=False), file=sys.stderr, flush=True)
    # Roteiro explícito evita chamar padrões de teste de capturas reais do Roblox.
    script = ('Este é um teste sintético do Estúdio de Reels. As cores e formas não são cenas do Roblox. '
              'Use seus próprios vídeos para produzir o primeiro conteúdo do jogo.')
    result = ReelStudio(library, progress).render(RenderOptions(tuple(asset['id'] for asset in sources), duration=15,
                title='TESTE SINTÉTICO — NÃO É GAMEPLAY ROBLOX', script=script, music_id=track['id'], tts='espeak'))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ReelError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
