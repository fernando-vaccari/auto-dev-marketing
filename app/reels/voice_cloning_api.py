"""Rotas privadas de Minha Voz, sob a autenticação/origem já existente em /api/reels."""
import asyncio
import json
from pathlib import Path
import re
import shutil
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from .tools import ReelError
from . import voice_cloning as cloning


class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    profile_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')


def router(service):
    api = APIRouter(prefix='/my-voice')
    root = cloning.private_root(service.library.root / 'voice-cloning')
    library = service.library

    @api.get('')
    def listing():
        return {'profiles': cloning.profiles(root), 'default_profile_id': service.preferences.get('my_voice', {}).get('profile_id'),
                'runtime': cloning.runtime_status(), 'limit_bytes': cloning.MAX_BYTES}

    @api.put('/default')
    def select(body: Selection):
        if body.profile_id:
            cloning.read_profile(root, body.profile_id)
        service.preferences.set('my_voice', {'profile_id': body.profile_id})
        return {'profile_id': body.profile_id}

    @api.post('', status_code=201)
    async def upload(request: Request, filename: str, name: str = 'Minha Voz', consent: bool = False):
        if not consent:
            raise HTTPException(422, 'Confirme a autorização de uso da voz.')
        if len(filename) > 120 or not re.fullmatch(r'[\w .-]+', filename) or filename.startswith('.'):
            raise HTTPException(422, 'Nome de arquivo inválido.')
        suffix = Path(filename).suffix.lower()
        if suffix not in cloning.EXTENSIONS:
            raise HTTPException(422, 'Use WAV/MP3 ou uma gravação de áudio do navegador.')
        try:
            length = int(request.headers.get('content-length', '0'))
        except ValueError:
            length = 0
        if not 0 < length <= cloning.MAX_BYTES:
            raise HTTPException(413, 'A amostra precisa ter conteúdo e até 20 MiB.')
        temporary = root / ('upload-' + uuid.uuid4().hex + suffix)
        # Mesma trava das outras importações: limita espaço reservado e pedidos simultâneos.
        import fcntl
        with (library.root / 'upload.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise HTTPException(409, 'Outro upload está em andamento.') from None
            service.require_space(2 * length + 12 * 1024 * 1024)
            count = 0
            try:
                with temporary.open('xb') as target:
                    temporary.chmod(0o600)
                    async for chunk in request.stream():
                        count += len(chunk)
                        if count > length:
                            raise HTTPException(413, 'Tamanho do upload inconsistente.')
                        target.write(chunk)
                if count != length:
                    raise HTTPException(422, 'Upload incompleto.')
                task = asyncio.create_task(asyncio.to_thread(cloning.create_profile, root, temporary, name=name, consent=consent))
                try:
                    return await asyncio.shield(task)
                except asyncio.CancelledError:
                    await task
                    raise
            finally:
                temporary.unlink(missing_ok=True)

    @api.get('/{identifier}/audio')
    def audio(identifier: str):
        cloning.read_profile(root, identifier)
        return FileResponse(cloning.profile_dir(root, identifier) / 'reference.wav', media_type='audio/wav')

    @api.delete('/{identifier}')
    def delete(identifier: str, delete_exports: bool = False):
        with cloning.profile_lock(root):
            directory = cloning.profile_dir(root, identifier)
            with library.db.connect() as db:
                jobs = [dict(row) for row in db.execute('SELECT id,status,config_json FROM reel_jobs')
                        if json.loads(row['config_json']).get('clone_profile_id') == identifier]
                if any(job['status'] in {'queued','rendering'} for job in jobs):
                    raise HTTPException(409, 'Cancele ou aguarde os jobs deste perfil antes de excluí-lo.')
                for job in jobs:
                    target = library.root / 'jobs' / job['id']
                    if target.is_symlink() or not target.resolve().is_relative_to((library.root / 'jobs').resolve()):
                        raise ReelError('Diretório de job inválido.')
                    config = json.loads(job['config_json'])
                    if delete_exports or config.get('_task') == 'voice_preview':
                        if target.is_dir():
                            shutil.rmtree(target)
                        db.execute("UPDATE reel_jobs SET status='failed',stage='voice_deleted',output_path=NULL,error=? WHERE id=?",
                                   ('Arquivos removidos a pedido do usuário ao excluir o perfil de voz.',job['id']))
                    elif target.is_dir():
                        (target / 'narration.wav').unlink(missing_ok=True)
                        speech = target / 'speech'
                        if speech.is_symlink():
                            speech.unlink()
                        elif speech.is_dir():
                            shutil.rmtree(speech)
            shutil.rmtree(directory)
            if service.preferences.get('my_voice', {}).get('profile_id') == identifier:
                service.preferences.set('my_voice', {'profile_id': None})
        return {'deleted': True, 'exports_deleted': delete_exports}

    return api
