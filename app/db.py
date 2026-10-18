from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import uuid


def now_iso():
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "marketing.sqlite3"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS posts (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, caption TEXT NOT NULL,
                    image TEXT NOT NULL, alt_text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft', scheduled_at TEXT,
                    approved_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    published_at TEXT, media_id TEXT, container_id TEXT,
                    error TEXT, source TEXT NOT NULL DEFAULT 'local',
                    delivery_mode TEXT
                );
                CREATE INDEX IF NOT EXISTS posts_queue ON posts(status, scheduled_at);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, post_id TEXT,
                    action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS automation_runs (
                    slot TEXT PRIMARY KEY, status TEXT NOT NULL,
                    post_id TEXT, detail TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
            """)
            db.execute("INSERT OR IGNORE INTO settings VALUES ('brand', ?)", (json.dumps({
                "name": "Auto Posts", "segment": "Marketing digital",
                "audience": "Profissionais de marketing digital, social media e empreendedores", "tone": "Próximo e profissional",
                "color": "#7454e9", "cta": "Fale com a gente pelo direct.",
                "signature": "Fernando Vaccari Pickhardt--Dev--Web",
            }),))
            db.execute("INSERT OR IGNORE INTO settings VALUES ('automation', ?)", (json.dumps({
                'enabled': False, 'time': '10:00', 'days': [0, 2, 4],
                'topics': ['Planejamento de conteúdo para marketing digital', 'Como conversar com seu público', 'Consistência no Instagram'],
                'objective': 'educate', 'approved_at': None, 'mode': None,
            }),))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def brand(self):
        with self.connect() as db:
            return json.loads(db.execute("SELECT value FROM settings WHERE key='brand'").fetchone()[0])

    def save_brand(self, brand):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE settings SET value=? WHERE key='brand'", (json.dumps(brand),))
            automation = json.loads(db.execute("SELECT value FROM settings WHERE key='automation'").fetchone()[0])
            automation.update(enabled=False, approved_at=None)
            db.execute("UPDATE settings SET value=? WHERE key='automation'", (json.dumps(automation),))
            self.event(db, None, 'brand_updated', 'Identidade alterada; rotina automática desativada para nova aprovação')

    def automation(self):
        with self.connect() as db:
            return json.loads(db.execute("SELECT value FROM settings WHERE key='automation'").fetchone()[0])

    def save_automation(self, config):
        with self.connect() as db:
            db.execute("UPDATE settings SET value=? WHERE key='automation'", (json.dumps(config),))
            self.event(db, None, 'automation_updated', 'Rotina ativada' if config['enabled'] else 'Rotina desativada')

    def claim_run(self, slot):
        with self.connect() as db:
            result = db.execute("INSERT OR IGNORE INTO automation_runs VALUES (?, 'running', NULL, '', ?, ?)", (slot, now_iso(), now_iso()))
            return result.rowcount == 1

    def attach_run(self, slot, post_id):
        with self.connect() as db:
            db.execute('UPDATE automation_runs SET post_id=?,updated_at=? WHERE slot=?', (post_id, now_iso(), slot))

    def finish_run(self, slot, status, post_id=None, detail=''):
        with self.connect() as db:
            db.execute('UPDATE automation_runs SET status=?,post_id=COALESCE(?,post_id),detail=?,updated_at=? WHERE slot=?',
                       (status, post_id, detail, now_iso(), slot))
            self.event(db, post_id, 'automation_' + status, detail)

    def automation_runs(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM automation_runs ORDER BY created_at DESC LIMIT 20')]

    @staticmethod
    def event(db, post_id, action, detail=""):
        db.execute("INSERT INTO events(post_id,action,detail,created_at) VALUES (?,?,?,?)",
                   (post_id, action, detail, now_iso()))

    def create(self, title, caption, image, alt_text, source):
        post_id, now = uuid.uuid4().hex, now_iso()
        with self.connect() as db:
            db.execute("""INSERT INTO posts(id,title,caption,image,alt_text,source,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,?,?)""", (post_id, title, caption, image, alt_text, source, now, now))
            self.event(db, post_id, "created", "Rascunho criado")
        return self.get(post_id)

    def get(self, post_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
            return dict(row) if row else None

    def posts(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM posts ORDER BY created_at DESC")]

    def events(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 50")]

    def edit(self, post_id, fields):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            post = db.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
            if not post:
                raise KeyError(post_id)
            if post['status'] not in {"draft", "scheduled", "failed"}:
                raise ValueError("Esta publicação não pode ser editada. Crie um novo rascunho.")
            for key, value in fields.items():
                if key not in {"title", "caption", "alt_text", "image"}:
                    raise ValueError("Campo inválido")
                db.execute(f"UPDATE posts SET {key}=? WHERE id=?", (value, post_id))
            db.execute("""UPDATE posts SET status='draft',scheduled_at=NULL,approved_at=NULL,
                          container_id=NULL,error=NULL,delivery_mode=NULL,updated_at=? WHERE id=?""", (now_iso(), post_id))
            self.event(db, post_id, "edited", "Alterações salvas; aprovação anterior removida")
        return self.get(post_id)

    def schedule(self, post_id, when, mode):
        with self.connect() as db:
            result = db.execute("""UPDATE posts SET status='scheduled', scheduled_at=?, approved_at=?,
                updated_at=?, error=NULL, delivery_mode=? WHERE id=? AND status IN ('draft','failed','scheduled')""",
                (when, now_iso(), now_iso(), mode, post_id))
            if not result.rowcount:
                raise ValueError("Publicação indisponível para agendamento.")
            self.event(db, post_id, "scheduled", when)
        return self.get(post_id)

    def cancel(self, post_id):
        with self.connect() as db:
            result = db.execute("""UPDATE posts SET status='draft',scheduled_at=NULL,approved_at=NULL,
                delivery_mode=NULL,updated_at=? WHERE id=? AND status='scheduled'""", (now_iso(), post_id))
            if not result.rowcount:
                raise ValueError("Somente agendamentos pendentes podem ser cancelados.")
            self.event(db, post_id, "cancelled", "Agendamento cancelado")
        return self.get(post_id)

    def claim(self, post_id, mode, due=False):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if due:
                where = "status='scheduled' AND approved_at IS NOT NULL AND scheduled_at<=? AND delivery_mode=?"
                params = (now_iso(), mode)
            else:
                where = "status IN ('draft','failed')"
                params = ()
            result = db.execute(f"""UPDATE posts SET status='publishing',approved_at=?,updated_at=?,
                error=NULL,delivery_mode=? WHERE id=? AND {where}""",
                (now_iso(), now_iso(), mode, post_id, *params))
            if not result.rowcount:
                return None
            self.event(db, post_id, "claimed", mode)
        return self.get(post_id)

    def finish(self, post_id, status, error=None, media_id=None):
        with self.connect() as db:
            db.execute("""UPDATE posts SET status=?, error=?, media_id=COALESCE(?,media_id),
                published_at=?,updated_at=? WHERE id=? AND status='publishing'""",
                (status, error, media_id, now_iso() if status in {"published", "simulated"} else None,
                 now_iso(), post_id))
            self.event(db, post_id, status, error or media_id or "")

    def save_container(self, post_id, container_id):
        with self.connect() as db:
            db.execute("UPDATE posts SET container_id=?,updated_at=? WHERE id=?", (container_id, now_iso(), post_id))

    def due(self, mode):
        with self.connect() as db:
            return [row[0] for row in db.execute("""SELECT id FROM posts WHERE status='scheduled'
                AND approved_at IS NOT NULL AND scheduled_at<=? AND delivery_mode=? ORDER BY scheduled_at LIMIT 10""",
                (now_iso(), mode))]

    def recover_interrupted(self):
        with self.connect() as db:
            db.execute("UPDATE automation_runs SET status='review_required',detail='Rotina interrompida; confira os registros',updated_at=? WHERE status='running'", (now_iso(),))
            rows = db.execute("SELECT id FROM posts WHERE status='publishing'").fetchall()
            for row in rows:
                db.execute("UPDATE posts SET status='review_required',error=?,updated_at=? WHERE id=?",
                    ("Processo interrompido. Confira a conta do Instagram antes de criar outra publicação.", now_iso(), row[0]))
                self.event(db, row[0], "review_required", "Reinício durante envio")
