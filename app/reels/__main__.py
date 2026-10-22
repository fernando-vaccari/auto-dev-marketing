"""CLI local: python -m app.reels --help. Nenhuma rota de publicação."""
from pathlib import Path
import argparse
import json
import os
import sys

from .library import ReelLibrary
from .planning import RenderOptions, build_plan
from .render import ReelStudio
from .tools import ReelError, doctor


def parser():
    root = argparse.ArgumentParser(description='Estúdio de Reels — Fase 1, totalmente local e sem publicação.')
    root.add_argument('--data-dir', default=os.getenv('DATA_DIR', '.data'), help='Mesmo DATA_DIR do painel (padrão: .data).')
    commands = root.add_subparsers(dest='command', required=True)
    commands.add_parser('doctor', help='Verificar FFmpeg, filtros e ferramentas de voz locais.')
    ingest = commands.add_parser('import', help='Copiar e registrar vídeo ou trilha na biblioteca privada.')
    ingest.add_argument('file', type=Path)
    ingest.add_argument('--kind', choices=['video', 'music'], default='video')
    ingest.add_argument('--tags', action='append', default=[], help='Temas realmente visíveis, separados por vírgulas.')
    listing = commands.add_parser('list', help='Listar os arquivos importados e seus IDs.')
    listing.add_argument('--kind', choices=['video', 'music'])
    jobs = commands.add_parser('jobs', help='Consultar progresso, falhas e histórico de jobs.')
    jobs.add_argument('--id')
    for command in ('plan', 'render'):
        task = commands.add_parser(command, help='Revisar o plano sem renderizar.' if command == 'plan' else 'Gerar MP4 local, sem publicar.')
        task.add_argument('--asset', action='append', required=True, help='ID de vídeo importado; repita para vários vídeos.')
        task.add_argument('--duration', type=int, default=30)
        task.add_argument('--title', default='RPG medieval em desenvolvimento')
        task.add_argument('--themes', action='append', default=[])
        task.add_argument('--music', help='ID de trilha importada pelo usuário.')
        task.add_argument('--tts', choices=['auto', 'espeak', 'piper'], default='auto')
        task.add_argument('--piper-model', default=os.getenv('REELS_PIPER_MODEL'))
        task.add_argument('--script-file', type=Path, help='Roteiro próprio em UTF-8, até 3000 caracteres.')
        task.add_argument('--fit', choices=['contain', 'crop'], default='contain')
        task.add_argument('--zoom', type=float, default=.02)
        task.add_argument('--threads', type=int, default=4)
        task.add_argument('--music-volume', type=float, default=.12)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == 'doctor':
            value = doctor()
        else:
            library = ReelLibrary(args.data_dir)
            if args.command == 'import':
                value = library.import_media(args.file, kind=args.kind, tags=args.tags)
            elif args.command == 'list':
                value = library.assets(args.kind)
            elif args.command == 'jobs':
                value = library.jobs(args.id)
            else:
                script = None
                if args.script_file:
                    if args.script_file.stat().st_size > 20000:
                        raise ReelError('O arquivo de roteiro é muito grande.')
                    script = args.script_file.read_text(encoding='utf-8')
                options = RenderOptions(tuple(args.asset), duration=args.duration, title=args.title,
                                        themes=tuple(args.themes), music_id=args.music, tts=args.tts,
                                        piper_model=args.piper_model, script=script, fit=args.fit,
                                        zoom=args.zoom, threads=args.threads, music_volume=args.music_volume)
                if args.command == 'plan':
                    value = build_plan(library, options)
                else:
                    def progress(event):
                        print(json.dumps(event, ensure_ascii=False), file=sys.stderr, flush=True)
                    value = ReelStudio(library, progress=progress).render(options)
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    except (ReelError, OSError, UnicodeError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(json.dumps({'error': 'Renderização interrompida; consulte jobs.'}), file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
