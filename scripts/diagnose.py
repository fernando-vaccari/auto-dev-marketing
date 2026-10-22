"""Diagnóstico local, sem ler valores de credenciais nem chamar Meta/OBS."""
from pathlib import Path
import importlib.util
import json
import os
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.reels.tools import doctor
from app.reels.voices import available

root=Path(os.getenv('DATA_DIR','.data')).resolve()
root.mkdir(parents=True,exist_ok=True)
report=doctor()
report.update(kokoro_local=available(root/'reels/models/kokoro'),obs_instalado=bool(shutil.which('obs')),
    obs_websocket=bool(importlib.util.find_spec('websockets')),cofre=bool(importlib.util.find_spec('cryptography')),
    autenticacao_configurada=bool(os.getenv('APP_PASSWORD')),disco_livre_mib=shutil.disk_usage(root).free//1048576,
    captura_real='PENDENTE DE VALIDAÇÃO REAL',publicacao_real='PENDENTE DE VALIDAÇÃO REAL')
print(json.dumps(report,ensure_ascii=False,indent=2))
