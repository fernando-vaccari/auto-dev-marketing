"""Fila web de um único render, sem FFmpeg no processo/event loop do FastAPI."""
from pathlib import Path
import asyncio
import fcntl
import os
import shutil
import signal
import sys
import time

from .library import ReelLibrary
from .tools import ReelError

MIB = 1024 * 1024


class ReelService:
    def __init__(self, settings):
        self.settings = settings
        self.library = ReelLibrary(settings.data_dir)
        self.task = None
        self.lock = None
        self.current = None
        self.closing = False
        self.control = asyncio.Lock()
        (self.library.root / 'uploads').mkdir(exist_ok=True)
        (self.library.root / 'worker-logs').mkdir(exist_ok=True)

    def storage(self):
        used = 0
        for directory, children, files in os.walk(self.library.root, followlinks=False):
            children[:] = [name for name in children if not (Path(directory) / name).is_symlink()]
            for name in files:
                try:
                    path = Path(directory) / name
                    if not path.is_symlink():
                        used += path.stat().st_size
                except FileNotFoundError:
                    pass
        return {'used_bytes': used, 'limit_bytes': self.settings.reels_storage_mb * MIB,
                'free_bytes': shutil.disk_usage(self.library.root).free,
                'reserve_bytes': self.settings.reels_min_free_mb * MIB}

    def require_space(self, additional=0):
        usage = self.storage()
        if usage['used_bytes'] + additional > usage['limit_bytes']:
            raise ReelError('Limite de armazenamento do Estúdio atingido. Remova arquivos antigos antes de continuar.')
        if usage['free_bytes'] < usage['reserve_bytes'] + additional:
            raise ReelError('Disco sem espaço suficiente, preservando a reserva configurada.')
        return usage

    async def start(self):
        self.lock = (self.library.root / 'web-supervisor.lock').open('a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            self.lock = None
            raise RuntimeError('Já existe um supervisor web de Reels usando este DATA_DIR.') from None
        self.closing = False
        # Nunca utiliza PIDs persistidos para sinalizar processos de outra instância.
        with self.library.db.connect() as db:
            old = [row[0] for row in db.execute("SELECT id FROM reel_jobs WHERE origin='web' AND status='rendering'")]
        for job_id in old:
            self.library.update_job(job_id, 'failed', 'interrupted', 0,
                                    error='O servidor reiniciou durante o render. Crie um novo job.')
        self.task = asyncio.create_task(self._run())

    @staticmethod
    async def terminate(process):
        if process.returncode is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(asyncio.shield(process.wait()), timeout=3)
        except asyncio.TimeoutError:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()

    async def close(self):
        self.closing = True
        if self.current:
            job_id, process = self.current
            await self.terminate(process)
            job = self.library.jobs(job_id)[0]
            if not job['cancel_requested'] and job['status'] != 'ready':
                self.library.update_job(job_id, 'failed', 'interrupted', job['progress'],
                                        error='O servidor foi encerrado durante o render.')
        if self.task:
            await self.task
            self.task = None
        if self.lock:
            self.lock.close()
            self.lock = None

    async def cancel(self, job_id):
        async with self.control:
            job = self.library.jobs(job_id)[0]
            if job['origin'] != 'web':
                raise ReelError('Somente jobs iniciados pelo painel podem ser cancelados pelo painel.')
            if job['status'] == 'cancelled':
                return
            if job['status'] not in {'queued', 'rendering'}:
                raise ReelError('Este job já terminou e não pode ser cancelado.')
            with self.library.db.connect() as db:
                db.execute('UPDATE reel_jobs SET cancel_requested=1 WHERE id=?', (job_id,))
            process = self.current[1] if self.current and self.current[0] == job_id else None
            if process:
                await self.terminate(process)
            self.library.update_job(job_id, 'cancelled', 'cancelled', job['progress'], detail='Cancelado pelo usuário.')

    def child_environment(self):
        allowed = {'PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'TZ', 'REELS_FFMPEG', 'REELS_FFPROBE',
                   'REELS_ESPEAK_NG', 'REELS_PIPER', 'REELS_PIPER_MODEL'}
        result = {key: value for key, value in os.environ.items() if key in allowed}
        result.update(PYTHONUNBUFFERED='1', OMP_NUM_THREADS=str(self.settings.reels_threads),
                      OPENBLAS_NUM_THREADS=str(self.settings.reels_threads))
        return result

    async def _run(self):
        while not self.closing:
            with self.library.db.connect() as db:
                row = db.execute("SELECT id FROM reel_jobs WHERE origin='web' AND status='queued' AND cancel_requested=0 ORDER BY created_at LIMIT 1").fetchone()
            if not row:
                await asyncio.sleep(.3)
                continue
            job_id = row[0]
            try:
                await self._execute(job_id)
            except Exception:
                job = self.library.jobs(job_id)[0]
                if job['status'] in {'queued', 'rendering'} and not job['cancel_requested']:
                    self.library.update_job(job_id, 'failed', 'failed', job['progress'],
                                            error='O supervisor não conseguiu concluir o job. Consulte a configuração local.')

    async def _execute(self, job_id):
        self.require_space(128 * MIB)
        async with self.control:
            job = self.library.jobs(job_id)[0]
            if job['cancel_requested'] or job['status'] != 'queued' or self.closing:
                return
            command = [sys.executable, '-m', 'app.reels.worker', '--data-dir', str(self.settings.data_dir),
                       '--job-id', job_id, '--parent-pid', str(os.getpid()),
                       '--file-limit', str(self.settings.reels_file_limit_mb * MIB)]
            log = (self.library.root / 'worker-logs' / f'{job_id}.log').open('wb')
            try:
                process = await asyncio.create_subprocess_exec(*command, cwd=Path(__file__).resolve().parents[2],
                    env=self.child_environment(), start_new_session=True, stdin=asyncio.subprocess.DEVNULL,
                    stdout=log, stderr=log)
            except BaseException:
                log.close()
                raise
            self.current = (job_id, process)
        waiting = asyncio.create_task(process.wait())
        started = time.monotonic()
        reason = None
        try:
            while process.returncode is None:
                try:
                    await asyncio.wait_for(asyncio.shield(waiting), timeout=1)
                except asyncio.TimeoutError:
                    try:
                        await asyncio.to_thread(self.require_space)
                    except ReelError as error:
                        reason = str(error)
                    if time.monotonic() - started > self.settings.reels_timeout_seconds:
                        reason = 'Tempo máximo de renderização atingido.'
                    if reason or self.closing:
                        await self.terminate(process)
            job = self.library.jobs(job_id)[0]
            if job['cancel_requested']:
                self.library.update_job(job_id, 'cancelled', 'cancelled', job['progress'], detail='Cancelado pelo usuário.')
            elif reason:
                self.library.update_job(job_id, 'failed', 'failed', job['progress'], error=reason)
            elif job['status'] not in {'ready', 'failed'}:
                self.library.update_job(job_id, 'failed', 'failed', job['progress'],
                                        error='O processo de render terminou sem uma saída válida.')
        finally:
            if process.returncode is None:
                await self.terminate(process)
            await waiting
            log.close()
            if self.current and self.current[0] == job_id:
                self.current = None
