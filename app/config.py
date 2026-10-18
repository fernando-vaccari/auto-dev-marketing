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
        )

    def validate(self):
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
