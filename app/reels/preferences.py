"""Configuração local privada: não altera .env nem credenciais preexistentes."""
import json
import os
from pathlib import Path
import tempfile
import threading

from .tools import ReelError


class Preferences:
    def __init__(self, library):self.library=library
    def get(self,key,default=None):
        with self.library.db.connect() as db:
            row=db.execute('SELECT value FROM settings WHERE key=?',('reels:'+key,)).fetchone()
        return json.loads(row[0]) if row else default
    def set(self,key,value):
        with self.library.db.connect() as db:
            db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('reels:'+key,json.dumps(value,ensure_ascii=False)))


class Secrets:
    """Fernet em repouso; chave local 0600. Nunca retorna tokens nos endpoints GET."""
    def __init__(self, root):
        self.lock=threading.RLock()
        self.root=root/'secrets';self.root.mkdir(mode=0o700,exist_ok=True)
        self.path=self.root/'credentials.enc';self.key=self.root/'key'
    def cipher(self):
        try:from cryptography.fernet import Fernet
        except ImportError:raise ReelError('Instale requirements-integrations.txt para salvar credenciais locais.') from None
        try:fd=os.open(self.key,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        except FileExistsError:pass
        else:
            with os.fdopen(fd,'wb') as file:file.write(Fernet.generate_key())
        return Fernet(self.key.read_bytes())
    def read(self):
        if not self.path.exists():return {}
        try:return json.loads(self.cipher().decrypt(self.path.read_bytes()))
        except Exception:raise ReelError('Não foi possível abrir o cofre local de credenciais.') from None
    def get(self,key,default=''):
        with self.lock:return self.read().get(key,default)
    def set(self,key,value):
        with self.lock:
            values=self.read();values[key]=value
            encoded=self.cipher().encrypt(json.dumps(values).encode())
            fd,temp=tempfile.mkstemp(dir=self.root)
            try:
                with os.fdopen(fd,'wb') as file:file.write(encoded)
                os.replace(temp,self.path)
            finally:Path(temp).unlink(missing_ok=True)
