"""API autenticada. Nunca monta a biblioteca privada como StaticFiles."""
import asyncio
import fcntl
import os
from pathlib import Path
import re
import unicodedata
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from zoneinfo import ZoneInfo
from datetime import datetime, timezone

from .library import VIDEO_EXTENSIONS, MUSIC_EXTENSIONS, normalize_themes
from .planning import RenderOptions, build_plan
from .speech import choose_voice
from .tools import ReelError
from .service import MIB


class Creation(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    asset_ids: list[str] = Field(default_factory=list, max_length=30)
    title: str = Field(min_length=1, max_length=80)
    duration: int = Field(ge=15, le=60, strict=True)
    themes: list[str] = Field(default_factory=list, max_length=8)
    script: str | None = Field(default=None, max_length=3000)
    tts: str = Field(default='espeak', pattern='^(espeak|piper)$')
    music_id: str | None = None
    fit: str = Field(default='contain', pattern='^(contain|crop)$')
    zoom: float = Field(default=.02, ge=0, le=.06, allow_inf_nan=False)


class ScheduleConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(default='Reels do RPG', min_length=1, max_length=80)
    enabled: bool = False
    days: list[int] = Field(default=[0,1,2,3,4,5],min_length=1,max_length=7)
    times: list[str] = Field(default=['12:30','19:30'],min_length=1,max_length=4)
    timezone: str = 'America/Sao_Paulo'
    quantity: int = Field(default=1,ge=1,le=3)
    policy: str = Field(default='approval',pattern='^(manual|approval|automatic)$')
    auto_authorized: bool = False
    grace_minutes: int = Field(default=30,ge=1,le=120)
    template: Creation

    @model_validator(mode='after')
    def valid(self):
        if len(set(self.days)) != len(self.days) or any(day not in range(7) for day in self.days):
            raise ValueError('Dias inválidos ou repetidos.')
        if len(set(self.times)) != len(self.times) or any(not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',t) for t in self.times):
            raise ValueError('Horários inválidos ou repetidos.')
        try:
            ZoneInfo(self.timezone)
        except (KeyError, ValueError):
            raise ValueError('Fuso horário inválido.') from None
        if self.policy == 'automatic' and not self.auto_authorized:
            raise ValueError('A política automática exige autorização explícita.')
        return self


class OBSConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    port: int = Field(default=4455,ge=1024,le=65535)
    password: str | None = Field(default=None,max_length=1024)

class CaptureConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    input_name: str = Field(min_length=1,max_length=200)
    scene_name: str = Field(min_length=1,max_length=200)
    sequence: str = Field(default='Exploração',max_length=80)
    themes: list[str] = Field(default=['gameplay'],max_length=8)
    duration: int = Field(default=30,ge=5,le=120)
    lead_seconds: int = Field(default=5,ge=0,le=15)
    directory: str = Field(default='gravacoes',pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    game_confirmed: bool = False


def router(service):
    api = APIRouter(prefix='/api/reels')
    library, settings = service.library, service.settings

    def asset_view(asset):
        return {key: asset[key] for key in ('id', 'kind', 'original_name', 'tags', 'metadata', 'created_at')} | {
            'size_bytes': library.asset_path(asset).stat().st_size}

    def get_job(job_id):
        if not re.fullmatch('[a-f0-9]{32}', job_id):
            raise HTTPException(404, 'Job não encontrado.')
        jobs = library.jobs(job_id)
        if not jobs:
            raise HTTPException(404, 'Job não encontrado.')
        return jobs[0]

    def job_view(job):
        value = {key: job[key] for key in ('id', 'status', 'stage', 'progress', 'error', 'events', 'created_at', 'updated_at', 'origin')}
        value['config'] = {key: val for key, val in job['config'].items() if key != 'piper_model'}
        value['video_url'] = f"/api/reels/jobs/{job['id']}/video" if job['status'] == 'ready' else None
        return value

    def options(body):
        values = body.model_dump()
        values.update(asset_ids=tuple(body.asset_ids), themes=tuple(body.themes),
                      threads=settings.reels_threads, piper_model=os.getenv('REELS_PIPER_MODEL') if body.tts == 'piper' else None)
        return RenderOptions(**values)

    @api.get('/capture/config')
    def obs_config():
        return service.preferences.get('obs',{'port':4455}) | {'password_configured':bool(service.secrets.get('obs_password')),'mode':'assisted'}

    @api.put('/capture/config')
    def obs_save(body: OBSConfig):
        service.preferences.set('obs',{'port':body.port})
        if body.password is not None:service.secrets.set('obs_password',body.password)
        return {'saved':True}

    @api.get('/capture/status')
    def capture_status():
        return service.capture.status()

    @api.get('/capture/history')
    def capture_history():
        values=service.capture.history()
        for value in values:value.pop('config_json',None)
        return values

    @api.post('/capture/start',status_code=201)
    def capture_start(body: CaptureConfig):
        config=body.model_dump();config['themes']=normalize_themes(config['themes'])
        return service.capture.start(config)

    @api.post('/capture/{identifier}/stop')
    def capture_stop(identifier: str):
        return service.capture.finish(identifier)

    @api.get('/capture/package')
    def capture_package():
        return FileResponse(Path(__file__).resolve().parents[2]/'roblox'/'AutoPostsCapture.rbxmx',filename='AutoPostsCapture.rbxmx')

    @api.get('/schedules')
    def schedules():
        result = service.automation.schedules()
        for item in result:
            item.pop('config_json', None)
            item['config']['template'].pop('piper_model',None)
        return result

    @api.post('/schedules', status_code=201)
    def schedule_create(body: ScheduleConfig):
        config = body.model_dump()
        config['template'] = options(body.template).to_dict()
        return {'id':service.automation.save(config)}

    @api.put('/schedules/{identifier}')
    def schedule_edit(identifier: str, body: ScheduleConfig):
        if not any(item['id']==identifier for item in service.automation.schedules()):
            raise HTTPException(404,'Agendamento não encontrado.')
        config=body.model_dump(); config['template']=options(body.template).to_dict()
        return {'id':service.automation.save(config,identifier)}

    @api.delete('/schedules/{identifier}')
    def schedule_delete(identifier: str):
        service.automation.delete(identifier)
        return {'deleted':True}

    @api.post('/schedules/{identifier}/run')
    def schedule_run(identifier: str):
        found=next((s for s in service.automation.schedules() if s['id']==identifier),None)
        if not found: raise HTTPException(404,'Agendamento não encontrado.')
        slot='manual:'+uuid.uuid4().hex
        job=service.automation.enqueue(found['config'],slot=slot,schedule_id=identifier,revision=found['revision'])
        return {'job_id':job,'slot':slot}

    @api.get('/schedule-history')
    def schedule_history():
        return service.automation.history()

    @api.get('/config')
    def config():
        voices = []
        for name in ('espeak', 'piper'):
            try:
                choose_voice(name, os.getenv('REELS_PIPER_MODEL'))
                voices.append(name)
            except ReelError:
                pass
        return {'video_limit_bytes': settings.reels_upload_mb * MIB,
                'music_limit_bytes': settings.reels_music_mb * MIB, 'storage': service.storage(),
                'voices': voices, 'publishing_enabled': False}

    @api.get('/assets')
    def assets():
        return [asset_view(asset) for asset in library.assets()]

    @api.post('/assets', status_code=201)
    async def upload(request: Request, filename: str, kind: str = 'video', tags: str = 'gameplay'):
        filename = unicodedata.normalize('NFKC', filename)
        if not filename or len(filename) > 180 or any(c in filename for c in '/\\:') or any(unicodedata.category(c) in {'Cc', 'Cf'} for c in filename):
            raise HTTPException(422, 'Nome de arquivo inválido.')
        suffix = Path(filename).suffix.lower()
        if kind not in {'video', 'music'} or suffix not in (VIDEO_EXTENSIONS if kind == 'video' else MUSIC_EXTENSIONS):
            raise HTTPException(422, 'Formato não permitido.')
        normalized = normalize_themes([tags]) if kind == 'video' else []
        try:
            size = int(request.headers.get('content-length', '0'))
        except ValueError:
            size = 0
        if size <= 0:
            raise HTTPException(411, 'Informe Content-Length positivo.')
        limit = (settings.reels_upload_mb if kind == 'video' else settings.reels_music_mb) * MIB
        if size > limit:
            raise HTTPException(413, 'Arquivo excede o limite configurado.')
        lock = (library.root / 'upload.lock').open('a')
        temporary = library.root / 'uploads' / (uuid.uuid4().hex + suffix)
        try:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise HTTPException(409, 'Outro upload está em andamento.') from None
            try:
                await asyncio.to_thread(service.require_space, size * 2)
            except ReelError as error:
                raise HTTPException(507, str(error)) from None
            received = 0
            with temporary.open('xb') as target:
                async for chunk in request.stream():
                    received += len(chunk)
                    if received > size or received > limit:
                        raise HTTPException(413, 'Upload excedeu o tamanho declarado.')
                    await asyncio.to_thread(target.write, chunk)
            if received != size:
                raise HTTPException(422, 'Upload incompleto.')
            # Se o cliente desconectar, aguarda a cópia privada antes de remover o temporário.
            task = asyncio.create_task(asyncio.to_thread(library.import_media, temporary, kind, normalized, filename))
            try:
                asset = await asyncio.shield(task)
            except asyncio.CancelledError:
                await task
                raise
            return asset_view(asset)
        finally:
            temporary.unlink(missing_ok=True)
            lock.close()

    @api.post('/plan')
    def plan(body: Creation):
        value = build_plan(library, options(body))
        value.pop('sources', None)
        return value

    @api.post('/jobs', status_code=202)
    def create(body: Creation):
        opts = options(body)
        build_plan(library, opts)
        choose_voice(opts.tts, opts.piper_model)
        if opts.music_id:
            library.asset(opts.music_id, 'music')
        service.require_space(128 * MIB)
        job_id = library.create_job(opts.to_dict(), origin='web', queue_limit=settings.reels_queue_limit)
        return job_view(get_job(job_id))

    @api.get('/jobs')
    def jobs():
        return [job_view(job) for job in library.jobs()]

    @api.get('/jobs/{job_id}')
    def job(job_id: str):
        return job_view(get_job(job_id))

    @api.post('/jobs/{job_id}/cancel')
    async def cancel(job_id: str):
        get_job(job_id)
        await service.cancel(job_id)
        return job_view(get_job(job_id))

    def private_file(job_id, relative, ready=False):
        job = get_job(job_id)
        if ready and job['status'] != 'ready':
            raise HTTPException(409, 'O Reel ainda não está pronto.')
        directory = library.root / 'jobs' / job_id
        path = (directory / relative).resolve()
        # Verifica toda a cadeia: também recusa um diretório de job substituído por symlink.
        expected = library.root.resolve() / 'jobs' / job_id
        if directory.resolve() != expected or not path.is_relative_to(expected) or not path.is_file():
            raise HTTPException(404, 'Arquivo indisponível.')
        return path

    @api.get('/jobs/{job_id}/video')
    def video(job_id: str):
        return FileResponse(private_file(job_id, 'deliverables/reel.mp4', True), media_type='video/mp4')

    @api.get('/jobs/{job_id}/download')
    def download(job_id: str):
        return FileResponse(private_file(job_id, 'deliverables/reel.mp4', True), media_type='video/mp4', filename=f'reel-{job_id[:8]}.mp4')

    @api.get('/jobs/{job_id}/texts')
    def texts(job_id: str):
        get_job(job_id)
        result = {}
        for key, name in (('script', 'script.txt'), ('captions', 'captions.srt')):
            try:
                path = private_file(job_id, name)
            except HTTPException as error:
                if error.status_code == 404:
                    result[key] = ''
                    continue
                raise
            if path.stat().st_size > 100_000:
                raise HTTPException(413, 'Texto excede o limite.')
            result[key] = path.read_text(encoding='utf-8')
        return result

    return api
