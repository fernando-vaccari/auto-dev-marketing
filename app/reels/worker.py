"""Um processo/sessão Linux por job web, reutilizando o renderizador da Fase 1."""
import argparse
import ctypes
import os
import resource
import signal
import json
from .speech import synthesize_fitting
from .captions import write_captions

from .library import ReelLibrary
from .planning import RenderOptions
from .render import ReelStudio
from .tools import ReelError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--parent-pid', required=True, type=int)
    parser.add_argument('--file-limit', type=int, required=True)
    args = parser.parse_args()
    if os.getsid(0) != os.getpid():
        raise SystemExit('O worker deve ser iniciado pelo supervisor em uma sessão própria.')

    def interrupted(signum, frame):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        # Só esta sessão contém o Python e os subprocessos deste job.
        os.killpg(os.getpgrp(), signal.SIGTERM)
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        raise SystemExit('Não foi possível proteger o worker contra morte do servidor.')
    if os.getppid() != args.parent_pid:
        return 130
    os.nice(5)  # Prioridade menor para preservar a interação com o painel/desktop.
    resource.setrlimit(resource.RLIMIT_FSIZE, (args.file_limit, args.file_limit))
    library = ReelLibrary(args.data_dir)
    jobs = library.jobs(args.job_id)
    if not jobs or jobs[0]['origin'] != 'web' or jobs[0]['status'] != 'queued':
        return 2
    config = jobs[0]['config']
    kind = config.pop('_task', 'reel')
    config['asset_ids'] = tuple(config['asset_ids'])
    config['themes'] = tuple(config['themes'])
    try:
        options = RenderOptions(**config)
        if kind == 'analysis':
            from .analysis import analyze
            library.begin_job(args.job_id)
            directory=library.root/'jobs'/args.job_id;directory.mkdir()
            results={}
            for index,identifier in enumerate(options.asset_ids):
                library.update_job(args.job_id,'rendering','analysis',int(90*index/len(options.asset_ids)))
                results[identifier]=analyze(library,identifier)
            (directory/'analysis.json').write_text(json.dumps(results))
            library.update_job(args.job_id,'ready','ready',100)
        elif kind == 'voice_preview':
            library.begin_job(args.job_id)
            directory=library.root/'jobs'/args.job_id;directory.mkdir()
            library.update_job(args.job_id,'rendering','narration',10,'Gerando prévia local')
            result=synthesize_fitting(options.script,directory,engine=options.tts,
                model=options.kokoro_dir if options.tts=='kokoro' else options.piper_model,
                duration=options.duration,threads=options.threads,voice_id=options.voice_id,
                speed=options.voice_speed,volume=options.voice_volume,auto_shorten=options.auto_shorten)
            (directory/'script.txt').write_text(result['text'],encoding='utf-8')
            (directory/'narration.json').write_text(json.dumps(result,ensure_ascii=False))
            write_captions(directory,result,title=options.title,duration=options.duration)
            library.update_job(args.job_id,'ready','ready',100,output_path=str((directory/'narration.wav').relative_to(library.root)))
        else:
            ReelStudio(library).render(options, job_id=args.job_id)
        return 0
    except KeyboardInterrupt:
        # O supervisor decide entre cancelamento e interrupção do servidor.
        return 130
    except ReelError as error:
        library.update_job(args.job_id, 'failed', 'failed', 0, error=str(error))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
