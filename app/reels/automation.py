"""Slots persistentes: uma reserva transacional por data, hora, regra e revisão."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import json
import uuid

from .planning import RenderOptions, build_plan
from .speech import choose_voice
from .tools import ReelError
from ..db import now_iso


class ReelAutomation:
    def __init__(self, service):
        self.service, self.library = service, service.library
        with self.library.db.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS reel_schedules (
                    id TEXT PRIMARY KEY, revision INTEGER NOT NULL, config_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reel_slots (
                    slot TEXT PRIMARY KEY, schedule_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    status TEXT NOT NULL, job_id TEXT, detail TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reel_deliveries (
                    job_id TEXT PRIMARY KEY, policy TEXT NOT NULL, approved INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL, container_id TEXT, media_id TEXT, error TEXT,
                    schedule_id TEXT, revision INTEGER, mode TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
            ''')
            # Um job de geração em andamento fica ligado ao slot antes de soltar a transação.
            db.execute("UPDATE reel_slots SET status='failed',detail='Reserva interrompida antes de criar o job.',updated_at=? WHERE status='claiming'", (now_iso(),))

    def schedules(self):
        with self.library.db.connect() as db:
            return [dict(row) | {'config': json.loads(row['config_json'])} for row in db.execute('SELECT id,revision,config_json,created_at,updated_at FROM reel_schedules ORDER BY created_at')]

    def save(self, config, identifier=None):
        identifier = identifier or uuid.uuid4().hex
        with self.library.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT revision FROM reel_schedules WHERE id=?', (identifier,)).fetchone()
            revision = row[0]+1 if row else 1
            db.execute('''INSERT INTO reel_schedules VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                          revision=excluded.revision,config_json=excluded.config_json,updated_at=excluded.updated_at''',
                       (identifier, revision, json.dumps(config, ensure_ascii=False), now_iso(), now_iso()))
        return identifier

    def delete(self, identifier):
        with self.library.db.connect() as db:
            db.execute('DELETE FROM reel_schedules WHERE id=?', (identifier,))

    def history(self):
        with self.library.db.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM reel_slots ORDER BY created_at DESC LIMIT 100')]

    def enqueue(self, config, *, slot, schedule_id=None, revision=None):
        with self.library.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute("INSERT OR IGNORE INTO reel_slots VALUES (?,?,?,'claiming',NULL,'',?,?)",
                              (slot, schedule_id or '', revision or 0, now_iso(), now_iso())).rowcount:
                return None
            try:
                values = dict(config['template'])
                values['cuts_override']=None
                if config.get('regenerate_script',True):values['script']=None
                sequence=db.execute('SELECT COUNT(*) FROM reel_slots WHERE schedule_id=?',(schedule_id or '',)).fetchone()[0]-1
                values['variation']=(values.get('variation',0)+sequence)%100000
                if config.get('library_mode','selected')=='all' or not values.get('asset_ids'):
                    requested = set(values.get('themes', []))
                    values['asset_ids'] = [a['id'] for a in self.library.assets('video') if not requested or requested.intersection(a['tags'])][-30:]
                values['threads']=self.service.settings.reels_threads
                options = RenderOptions(**values)
                build_plan(self.library, options)
                choose_voice(options.tts, options.kokoro_dir if options.tts == 'kokoro' else options.piper_model)
                self.service.require_space(128*1024*1024)
                count = db.execute("SELECT COUNT(*) FROM reel_jobs WHERE origin='web' AND status IN ('queued','rendering')").fetchone()[0]
                if count >= self.service.settings.reels_queue_limit:
                    raise ReelError('Fila cheia neste horário; o slot não será duplicado.')
                identifier = uuid.uuid4().hex
                stamp = now_iso()
                db.execute("INSERT INTO reel_jobs(id,status,progress,stage,config_json,created_at,updated_at,origin) VALUES (?,'queued',0,'queued',?,?,?,'web')",
                           (identifier,json.dumps(options.to_dict(),ensure_ascii=False),stamp,stamp))
                db.execute("UPDATE reel_slots SET status='queued',job_id=?,updated_at=? WHERE slot=?", (identifier,stamp,slot))
                db.execute("INSERT INTO reel_deliveries(job_id,policy,approved,status,schedule_id,revision,mode,created_at,updated_at) VALUES (?,?,0,'awaiting_render',?,?,?,?,?)",
                           (identifier,config['policy'],schedule_id,revision,self.service.publishing.mode,stamp,stamp))
                return identifier
            except (ReelError, ValueError, TypeError) as error:
                db.execute("UPDATE reel_slots SET status='failed',detail=?,updated_at=? WHERE slot=?", (str(error)[:500],now_iso(),slot))
                return None

    def tick(self, now=None):
        now = now or datetime.now(timezone.utc)
        for schedule in self.schedules():
            config = schedule['config']
            if not config['enabled']:
                continue
            local = now.astimezone(ZoneInfo(config['timezone']))
            if local.weekday() not in config['days']:
                continue
            for clock in config['times']:
                hour, minute = map(int, clock.split(':'))
                due = local.replace(hour=hour,minute=minute,second=0,microsecond=0)
                # Apenas a janela recente: evita disparar vários dias de publicações antigas.
                if not 0 <= (local-due).total_seconds() <= config.get('grace_minutes',30)*60:
                    continue
                for index in range(config['quantity']):
                    slot = f"{schedule['id']}:{local.date()}:{clock}:{index}"
                    self.enqueue(config,slot=slot,schedule_id=schedule['id'],revision=schedule['revision'])
        with self.library.db.connect() as db:
            db.execute("UPDATE reel_slots SET status=COALESCE((SELECT status FROM reel_jobs WHERE id=reel_slots.job_id),status),updated_at=? WHERE job_id IS NOT NULL AND status IN ('queued','rendering')", (now_iso(),))
