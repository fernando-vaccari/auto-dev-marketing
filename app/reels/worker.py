"""Um processo/sessão Linux por job web, reutilizando o renderizador da Fase 1."""
import argparse
import ctypes
import os
import resource
import signal

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
    config['asset_ids'] = tuple(config['asset_ids'])
    config['themes'] = tuple(config['themes'])
    try:
        ReelStudio(library).render(RenderOptions(**config), job_id=args.job_id)
        return 0
    except KeyboardInterrupt:
        # O supervisor decide entre cancelamento e interrupção do servidor.
        return 130
    except ReelError as error:
        library.update_job(args.job_id, 'failed', 'failed', 0, error=str(error))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
