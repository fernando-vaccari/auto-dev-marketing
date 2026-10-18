"""Rotina recorrente com autorização explícita por configuração e modo."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import asyncio

from .content import generate_content, render_image


def next_run(settings, config, after=None):
    if not config['enabled'] or config.get('target') != settings.delivery_key:
        return None
    zone = ZoneInfo(settings.timezone)
    now = after or datetime.now(timezone.utc)
    local = now.astimezone(zone)
    hour, minute = map(int, config['time'].split(':'))
    for delta in range(8):
        date = local.date() + timedelta(days=delta)
        candidate = datetime(date.year, date.month, date.day, hour, minute, tzinfo=zone)
        if date.weekday() in config['days'] and candidate > now:
            return candidate.astimezone(timezone.utc).isoformat()
    return None


class Automation:
    def __init__(self, settings, db, publisher):
        self.settings, self.db, self.publisher = settings, db, publisher

    async def tick(self, now=None):
        config = self.db.automation()
        if not config['enabled'] or config.get('target') != self.settings.delivery_key or not config['approved_at']:
            return
        now = now or datetime.now(timezone.utc)
        local = now.astimezone(ZoneInfo(self.settings.timezone))
        hour, minute = map(int, config['time'].split(':'))
        due = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if local.weekday() not in config['days'] or local < due or due < datetime.fromisoformat(config['approved_at']):
            return
        slot = f"{self.settings.mode}:{local.date().isoformat()}"
        if not self.db.claim_run(slot):
            return
        post = None
        try:
            brand = self.db.brand()
            topic = config['topics'][local.date().toordinal() % len(config['topics'])]
            content = await generate_content(self.settings, brand, topic, config['objective'])
            # Uma alteração/desativação durante a geração revoga a autorização antes do envio.
            current = self.db.automation()
            if current != config:
                self.db.finish_run(slot, 'cancelled', detail='Rotina alterada durante a geração')
                return
            image = await asyncio.to_thread(render_image, self.settings.data_dir / 'media', brand, content['title'])
            post = self.db.create(image=image, **content)
            self.db.attach_run(slot, post['id'])
            if self.db.automation() != config:
                self.db.finish_run(slot, 'cancelled', post['id'], 'Rotina desativada; rascunho mantido')
                return
            result = await self.publisher.publish(post['id'])
            self.db.finish_run(slot, result['status'], post['id'], result['error'] or '')
        except asyncio.CancelledError:
            self.db.finish_run(slot, 'review_required', post['id'] if post else None, 'Rotina interrompida; confira os registros')
            raise
        except Exception:
            self.db.finish_run(slot, 'failed', post['id'] if post else None,
                               'Não foi possível concluir a rotina. Confira geração, credenciais e conexão. Sem reenvio automático.')
