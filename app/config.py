from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import os
import re


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    mode: str = "demo"
    timezone: str = "America/Sao_Paulo"
    meta_token: str = ""
    instagram_id: str = ""
    public_url: str = ""
    password: str = ""
    api_version: str = "v25.0"
    ai_key: str = ""
    ai_model: str = "gpt-4o-mini"
    scheduler_seconds: float = 15
    reels_upload_mb: int = 512
    reels_music_mb: int = 64
    reels_storage_mb: int = 8192
    reels_min_free_mb: int = 1024
    reels_threads: int = 4
    reels_queue_limit: int = 3
    reels_timeout_seconds: int = 900
    reels_file_limit_mb: int = 512

    @property
    def delivery_key(self):
        return 'demo' if self.mode == 'demo' else 'live:' + self.instagram_id

    @classmethod
    def from_env(cls):
        return cls(
            data_dir=Path(os.getenv("DATA_DIR", ".data")).resolve(),
            mode=os.getenv("APP_MODE", "demo"),
            timezone=os.getenv("APP_TIMEZONE", "America/Sao_Paulo"),
            meta_token=os.getenv("META_ACCESS_TOKEN", ""),
            instagram_id=os.getenv("INSTAGRAM_ACCOUNT_ID", ""),
            public_url=os.getenv("PUBLIC_BASE_URL", "").rstrip("/"),
            password=os.getenv("APP_PASSWORD", ""),
            api_version=os.getenv("META_API_VERSION", "v25.0"),
            ai_key=os.getenv("AI_API_KEY", ""),
            ai_model=os.getenv("AI_MODEL", "gpt-4o-mini"),
            reels_upload_mb=int(os.getenv('REELS_UPLOAD_MB', '512')),
            reels_music_mb=int(os.getenv('REELS_MUSIC_MB', '64')),
            reels_storage_mb=int(os.getenv('REELS_STORAGE_MB', '8192')),
            reels_min_free_mb=int(os.getenv('REELS_MIN_FREE_MB', '1024')),
            reels_threads=int(os.getenv('REELS_THREADS', '4')),
            reels_queue_limit=int(os.getenv('REELS_QUEUE_LIMIT', '3')),
            reels_timeout_seconds=int(os.getenv('REELS_TIMEOUT_SECONDS', '900')),
            reels_file_limit_mb=int(os.getenv('REELS_FILE_LIMIT_MB', '512')),
        )

    def validate(self):
        if not 1 <= self.reels_threads <= 8 or not 1 <= self.reels_queue_limit <= 10:
            raise ValueError('REELS_THREADS deve ser 1–8 e REELS_QUEUE_LIMIT, 1–10.')
        if min(self.reels_upload_mb, self.reels_music_mb, self.reels_storage_mb,
               self.reels_timeout_seconds, self.reels_file_limit_mb) <= 0 or self.reels_min_free_mb < 0:
            raise ValueError('Os limites de Reels devem ser positivos; a reserva de disco pode ser zero.')
        if self.mode not in {"demo", "live"}:
            raise ValueError("APP_MODE deve ser demo ou live.")
        ZoneInfo(self.timezone)
        if not re.fullmatch(r"v\d+\.\d+", self.api_version):
            raise ValueError("META_API_VERSION inválida.")
        if self.mode == "live":
            missing = [name for name, value in {
                "META_ACCESS_TOKEN": self.meta_token,
                "INSTAGRAM_ACCOUNT_ID": self.instagram_id,
                "PUBLIC_BASE_URL": self.public_url,
                "APP_PASSWORD": self.password,
            }.items() if not value]
            if missing:
                raise ValueError("Modo real requer: " + ", ".join(missing))
            if not self.instagram_id.isdecimal():
                raise ValueError("INSTAGRAM_ACCOUNT_ID deve ser numérico.")
            url = urlparse(self.public_url)
            if url.scheme != "https" or not url.hostname or url.username or url.password or url.path not in {"", "/"} or url.query or url.fragment:
                raise ValueError("PUBLIC_BASE_URL deve ser uma origem HTTPS pública, sem caminho.")
            if url.hostname in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("A Meta precisa de uma URL pública para buscar as imagens.")
            if len(self.password) < 12:
                raise ValueError("APP_PASSWORD deve conter pelo menos 12 caracteres.")
