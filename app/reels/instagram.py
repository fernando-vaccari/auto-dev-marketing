"""API oficial: Facebook Login for Business + sessão resumível, sem URLs públicas locais.
Referência consultada: developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/content-publishing/
"""
import asyncio
from dataclasses import replace
from pathlib import Path
import re

import httpx

from ..meta import MetaClient,MetaError
from ..db import now_iso
from .tools import ReelError,probe


class ProcessingPending(MetaError):pass


class ReelMetaClient(MetaClient):
    async def create_reel(self,caption):
        value=await self.request('POST',f'{self.settings.instagram_id}/media',
            {'media_type':'REELS','upload_type':'resumable','caption':caption})
        return self.identifier(value)

    async def upload_reel(self,identifier,path):
        if not re.fullmatch(r'\d+',identifier):raise MetaError('Identificador de contêiner inválido.')
        path=Path(path);size=path.stat().st_size
        async def chunks():
            with path.open('rb') as source:
                while data:=await asyncio.to_thread(source.read,1024*1024):yield data
        try:
            async with httpx.AsyncClient(transport=self.transport,timeout=httpx.Timeout(180,connect=20)) as client:
                response=await client.post(f'https://rupload.facebook.com/ig-api-upload/{self.settings.api_version}/{identifier}',
                    headers={'Authorization':f'OAuth {self.settings.meta_token}','offset':'0','file_size':str(size),
                             'Content-Length':str(size),'Content-Type':'application/octet-stream'},content=chunks())
            result=response.json()
            if response.is_error or not isinstance(result,dict) or result.get('success') is not True:
                raise MetaError('A Meta recusou a transferência do vídeo. Confira permissões e requisitos do aplicativo.')
        except (httpx.HTTPError,ValueError):
            raise MetaError('A transferência do vídeo falhou ou excedeu o tempo limite. Nenhuma publicação foi solicitada.') from None

    async def finish_reel(self,identifier):
        for attempt in range(self.poll_attempts):
            data=await self.request('GET',identifier,{'fields':'status_code'})
            state=data.get('status_code')
            if state=='FINISHED':break
            if state=='PUBLISHED':raise MetaError('O contêiner já consta como publicado; confira a conta antes de repetir.',uncertain=True)
            if state in {'ERROR','EXPIRED'}:raise MetaError('A Meta não conseguiu processar o vídeo ou o contêiner expirou.')
            if state not in {'IN_PROGRESS'}:raise MetaError('Estado de processamento desconhecido. Confira a Meta.')
            await asyncio.sleep(self.poll_seconds)
        else:raise ProcessingPending('O vídeo ainda está sendo processado pela Meta.')
        value=await self.request('POST',f'{self.settings.instagram_id}/media_publish',{'creation_id':identifier},publishing=True)
        return self.identifier(value,publishing=True)


class ReelPublishing:
    def __init__(self,service):
        self.service=service;self.library=service.library;self.client_factory=None
    def recover(self):
        with self.library.db.connect() as db:
            db.execute("UPDATE reel_deliveries SET status='review_required',error='Servidor reiniciou durante uma operação externa. Confira o Instagram antes de repetir.',updated_at=? WHERE status='processing'",(now_iso(),))

    def configuration(self):
        configured=self.service.preferences.get('instagram',{})
        return {'account_id':configured.get('account_id') or self.service.settings.instagram_id,
                'app_id':configured.get('app_id',''),'api_version':configured.get('api_version',self.service.settings.api_version),
                'mode':configured.get('mode','demo'),'enabled':configured.get('enabled',False),'business_login_confirmed':configured.get('business_login_confirmed',False),
                'permissions_confirmed':configured.get('permissions_confirmed',False),'revision':configured.get('revision',0)}

    def token(self):return self.service.secrets.get('meta_token') or self.service.settings.meta_token

    @property
    def mode(self):
        config=self.configuration()
        return 'demo' if config['mode']=='demo' else f"live:{config['account_id']}:{config['revision']}"

    def client(self):
        if self.client_factory:return self.client_factory()
        config=self.configuration()
        if not config['account_id'] or not self.token():raise ReelError('Configure a conta profissional e o token no Instagram.')
        settings=replace(self.service.settings,instagram_id=config['account_id'],meta_token=self.token(),api_version=config['api_version'])
        return ReelMetaClient(settings,poll_attempts=3,poll_seconds=2)

    def history(self):
        with self.library.db.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM reel_deliveries ORDER BY created_at DESC LIMIT 100')]

    def register(self,identifier,policy='manual'):
        job=self.library.jobs(identifier)
        if not job or job[0]['status']!='ready' or job[0]['config'].get('_task'):
            raise ReelError('Escolha um Reel pronto para configurar a publicação.')
        with self.library.db.connect() as db:
            db.execute("INSERT OR IGNORE INTO reel_deliveries(job_id,policy,approved,status,mode,created_at,updated_at) VALUES (?,?,0,'awaiting_approval',?,?,?)",(identifier,policy,self.mode,now_iso(),now_iso()))

    def approve(self,identifier,approved,authorize_live=False):
        found=next((d for d in self.history() if d['job_id']==identifier),None)
        if not found:raise ReelError('Publicação não encontrada.')
        if found['status'] in {'published','simulated','processing','review_required'}:
            raise ReelError('Este envio já terminou ou precisa de conferência manual; não será repetido.')
        if approved and self.library.jobs(identifier)[0]['status']!='ready':
            raise ReelError('Aguarde o Reel ficar pronto e revise antes de aprovar.')
        if approved and self.configuration()['mode']=='live' and not authorize_live:
            raise ReelError('Confirme explicitamente o envio real desta publicação.')
        with self.library.db.connect() as db:
            db.execute("UPDATE reel_deliveries SET approved=?,status=?,mode=?,error=NULL,updated_at=? WHERE job_id=?",
                       (int(approved),'queued' if approved else 'awaiting_approval',self.mode,now_iso(),identifier))

    def state(self,identifier,status,**values):
        allowed={'container_id','media_id','error'}
        assignments=['status=?','updated_at=?'];arguments=[status,now_iso()]
        for key,value in values.items():
            if key not in allowed:raise ValueError('Campo de publicação inválido.')
            assignments.append(key+'=?');arguments.append(value)
        with self.library.db.connect() as db:
            db.execute('UPDATE reel_deliveries SET '+','.join(assignments)+' WHERE job_id=?',(*arguments,identifier))

    def automatic_authorized(self,delivery):
        for rule in self.service.automation.schedules():
            if rule['id']==delivery['schedule_id'] and rule['revision']==delivery['revision']:
                c=rule['config'];return c['enabled'] and c['policy']=='automatic' and c.get('auto_authorized',False)
        return False

    async def tick(self):
        for delivery in self.history():
            identifier=delivery['job_id']
            jobs=self.library.jobs(identifier)
            if not jobs:continue
            job=jobs[0]
            if delivery['status']=='awaiting_render':
                if job['status'] in {'failed','cancelled'}:
                    self.state(identifier,'failed',error='A geração do Reel não foi concluída.');continue
                if job['status']!='ready':continue
                self.state(identifier,'awaiting_approval');delivery['status']='awaiting_approval'
            if delivery['policy']=='automatic' and delivery['status']=='awaiting_approval' and self.automatic_authorized(delivery):
                self.state(identifier,'queued');delivery['status']='queued'
            if delivery['status'] not in {'queued','waiting'}:continue
            if job['status']!='ready':continue
            if delivery['mode']!=self.mode:
                self.state(identifier,'review_required',error='Modo, conta ou configuração alterados. É necessária conferência e nova autorização.');continue
            if delivery['policy']=='automatic' and not delivery['approved'] and not self.automatic_authorized(delivery):
                self.state(identifier,'awaiting_approval',error='Regra pausada ou alterada; a autorização automática não é mais válida.');continue
            if not delivery['approved'] and delivery['policy']!='automatic':continue
            with self.library.db.connect() as db:
                claimed=db.execute("UPDATE reel_deliveries SET status='processing',updated_at=? WHERE job_id=? AND status IN ('queued','waiting')",(now_iso(),identifier)).rowcount
            if not claimed:continue
            try:
                if self.configuration()['mode']=='demo':
                    self.state(identifier,'simulated',media_id=None,error=None);return
                config=self.configuration()
                if not (config['enabled'] and config['business_login_confirmed'] and config['permissions_confirmed']):
                    raise ReelError('Publicação real desativada ou requisitos oficiais não confirmados.')
                directory=self.library.root/'jobs'/identifier
                expected=self.library.root.resolve()/'jobs'/identifier
                path=(directory/'deliverables/reel.mp4').resolve()
                if directory.resolve()!=expected or not path.is_relative_to(expected) or not path.is_file():
                    raise ReelError('Arquivo privado do Reel indisponível.')
                await asyncio.to_thread(probe,path)
                client=self.client()
                container=delivery['container_id']
                if not container:
                    await client.account()
                    await client.request('GET',f"{config['account_id']}/content_publishing_limit",{'fields':'quota_usage,config'})
                    caption=job['config'].get('title','')+'\n'+job['config'].get('cta','')
                    container=await client.create_reel(caption)
                    self.state(identifier,'processing',container_id=container)
                    await client.upload_reel(container,path)
                media=await client.finish_reel(container)
                self.state(identifier,'published',media_id=media,error=None)
            except ProcessingPending as error:self.state(identifier,'waiting',error=str(error))
            except MetaError as error:self.state(identifier,'review_required' if error.uncertain else 'failed',error=str(error))
            except ReelError as error:self.state(identifier,'failed',error=str(error))
            except Exception:self.state(identifier,'review_required',error='Falha inesperada em operação externa; confira o Instagram antes de repetir.')
            return
