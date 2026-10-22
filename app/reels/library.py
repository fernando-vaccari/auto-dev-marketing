from pathlib import Path
import hashlib
import json
import os
import tempfile
import unicodedata
import uuid

from ..db import Database, now_iso
from .tools import ReelError, probe

THEMES = {'gameplay', 'cidades', 'cavernas', 'demonios', 'npcs', 'batalhas', 'magia', 'exploracao'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.webm'}
MUSIC_EXTENSIONS = {'.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac'}


def normalize_themes(values):
    tags = set()
    for value in values:
        for item in value.split(','):
            normalized = ''.join(char for char in unicodedata.normalize('NFKD', item.strip().lower()) if not unicodedata.combining(char))
            if normalized:
                if normalized not in THEMES:
                    raise ReelError(f'Tema desconhecido: {item}. Use: {", ".join(sorted(THEMES))}.')
                tags.add(normalized)
    return sorted(tags)


class ReelLibrary:
    """Adiciona tabelas ao SQLite existente, sem modificar posts ou credenciais."""

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir).resolve()
        self.db = Database(self.data_dir)
        self.root = self.data_dir / 'reels'
        self.imports = self.root / 'imports'
        self.imports.mkdir(parents=True, exist_ok=True)
        (self.root / 'jobs').mkdir(exist_ok=True)
        with self.db.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS reel_assets (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, original_name TEXT NOT NULL,
                    relative_path TEXT NOT NULL, sha256 TEXT NOT NULL,
                    tags_json TEXT NOT NULL, metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, UNIQUE(kind, sha256)
                );
                CREATE TABLE IF NOT EXISTS reel_jobs (
                    id TEXT PRIMARY KEY, status TEXT NOT NULL, progress INTEGER NOT NULL,
                    stage TEXT NOT NULL, config_json TEXT NOT NULL, output_path TEXT,
                    error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reel_job_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                    stage TEXT NOT NULL, progress INTEGER NOT NULL, detail TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            ''')
            db.execute('BEGIN IMMEDIATE')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(reel_jobs)')}
            if 'origin' not in columns:
                db.execute("ALTER TABLE reel_jobs ADD COLUMN origin TEXT NOT NULL DEFAULT 'cli'")
            if 'cancel_requested' not in columns:
                db.execute('ALTER TABLE reel_jobs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0')

    @staticmethod
    def asset_dict(row):
        if not row:
            return None
        value = dict(row)
        value['tags'] = json.loads(value.pop('tags_json'))
        value['metadata'] = json.loads(value.pop('metadata_json'))
        return value

    def asset(self, asset_id, kind=None):
        with self.db.connect() as db:
            value = self.asset_dict(db.execute('SELECT * FROM reel_assets WHERE id=?', (asset_id,)).fetchone())
        if not value or (kind and value['kind'] != kind):
            raise ReelError(f'Mídia não encontrada ou tipo incorreto: {asset_id}')
        return value

    def asset_path(self, asset, verify=False):
        path = (self.root / asset['relative_path']).resolve()
        if not path.is_relative_to(self.imports.resolve()) or not path.is_file():
            raise ReelError('A cópia privada da mídia não está disponível.')
        if verify:
            digest = hashlib.sha256()
            with path.open('rb') as file:
                while chunk := file.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != asset['sha256']:
                raise ReelError('A cópia importada foi modificada ou corrompida. Importe novamente o arquivo original.')
        return path

    def assets(self, kind=None):
        with self.db.connect() as db:
            rows = db.execute('SELECT * FROM reel_assets WHERE (? IS NULL OR kind=?) ORDER BY created_at', (kind, kind))
            return [self.asset_dict(row) for row in rows]

    def import_media(self, source, kind='video', tags=(), original_name=None):
        path = Path(source).expanduser().resolve()
        suffix = path.suffix.lower()
        if kind not in {'video', 'music', 'effect'}:
            raise ReelError('Tipo de mídia inválido.')
        if not path.is_file() or suffix not in (VIDEO_EXTENSIONS if kind == 'video' else MUSIC_EXTENSIONS):
            raise ReelError('Informe um arquivo local MP4/MOV/WebM para vídeo, ou MP3/WAV/OGG/FLAC/M4A/AAC para trilha.')
        tags = normalize_themes(tags) if kind == 'video' else []
        descriptor, temporary = tempfile.mkstemp(dir=self.imports, suffix=suffix)
        temporary = Path(temporary)
        try:
            digest = hashlib.sha256()
            with path.open('rb') as original, os.fdopen(descriptor, 'wb') as copied:
                while chunk := original.read(1024 * 1024):
                    copied.write(chunk)
                    digest.update(chunk)
            metadata = probe(temporary)
            stream_type = 'video' if kind == 'video' else 'audio'
            streams = [stream for stream in metadata['streams'] if stream['codec_type'] == stream_type]
            if not streams:
                raise ReelError(f'O arquivo não contém stream de {stream_type}.')
            if kind == 'video':
                if not any(name in metadata['format'].split(',') for name in ('mov', 'mp4', 'matroska', 'webm')):
                    raise ReelError('O conteúdo não é um contêiner MP4/MOV/WebM válido.')
                if streams[0].get('width', 0) > 7680 or streams[0].get('height', 0) > 7680:
                    raise ReelError('Importe gravações com até 7680 pixels por dimensão.')
            sha = digest.hexdigest()
            with self.db.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                existing = self.asset_dict(db.execute('SELECT * FROM reel_assets WHERE kind=? AND sha256=?', (kind, sha)).fetchone())
                if existing:
                    merged = sorted(set(existing['tags']) | set(tags))
                    stored = (self.root / existing['relative_path']).resolve()
                    if not stored.is_relative_to(self.imports.resolve()):
                        raise ReelError('Caminho privado inválido no registro de mídia.')
                    # Também restaura uma cópia privada perdida/corrompida a partir do original verificado.
                    os.replace(temporary, stored)
                    db.execute('UPDATE reel_assets SET tags_json=? WHERE id=?', (json.dumps(merged), existing['id']))
                    existing['tags'] = merged
                    return existing
                filename = sha + suffix
                os.replace(temporary, self.imports / filename)
                asset_id = uuid.uuid4().hex
                db.execute('INSERT INTO reel_assets VALUES (?,?,?,?,?,?,?,?)', (
                    asset_id, kind, original_name or path.name, 'imports/' + filename, sha,
                    json.dumps(tags or (['gameplay'] if kind == 'video' else [])), json.dumps(metadata), now_iso()))
            return self.asset(asset_id)
        finally:
            temporary.unlink(missing_ok=True)

    def create_job(self, config, origin='cli', queue_limit=None):
        job_id = uuid.uuid4().hex
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if queue_limit is not None:
                count = db.execute("SELECT COUNT(*) FROM reel_jobs WHERE origin='web' AND status IN ('queued','rendering')").fetchone()[0]
                if count >= queue_limit:
                    raise ReelError('A fila de Reels está cheia. Aguarde um render terminar.')
            db.execute("""INSERT INTO reel_jobs(id,status,progress,stage,config_json,created_at,updated_at,origin)
                          VALUES (?,'queued',0,'queued',?,?,?,?)""",
                       (job_id, json.dumps(config, ensure_ascii=False), now_iso(), now_iso(), origin))
        return job_id

    def begin_job(self, job_id):
        with self.db.connect() as db:
            result = db.execute("UPDATE reel_jobs SET status='rendering',updated_at=? WHERE id=? AND status='queued' AND cancel_requested=0", (now_iso(), job_id))
            if not result.rowcount:
                raise ReelError('O job não está disponível para renderização.')

    def update_job(self, job_id, status, stage, progress, detail='', output_path=None, error=None):
        with self.db.connect() as db:
            db.execute('UPDATE reel_jobs SET status=?,stage=?,progress=?,output_path=?,error=?,updated_at=? WHERE id=?',
                       (status, stage, progress, output_path, error, now_iso(), job_id))
            db.execute('INSERT INTO reel_job_events(job_id,stage,progress,detail,created_at) VALUES (?,?,?,?,?)',
                       (job_id, stage, progress, detail, now_iso()))

    def jobs(self, job_id=None):
        with self.db.connect() as db:
            rows = db.execute('SELECT * FROM reel_jobs WHERE (? IS NULL OR id=?) ORDER BY created_at DESC LIMIT 100', (job_id, job_id))
            result = []
            for row in rows:
                value = dict(row)
                value['config'] = json.loads(value.pop('config_json'))
                value['events'] = [dict(event) for event in db.execute('SELECT stage,progress,detail,created_at FROM reel_job_events WHERE job_id=? ORDER BY id', (value['id'],))]
                result.append(value)
            return result

    def recover_interrupted(self):
        with self.db.connect() as db:
            ids = [row[0] for row in db.execute("SELECT id FROM reel_jobs WHERE status='rendering'")]
        for job_id in ids:
            self.update_job(job_id, 'failed', 'interrupted', 0, error='Renderização interrompida. Inicie um novo job; nenhum envio foi realizado.')
