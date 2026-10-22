"""Instala arquivos de um release fixo, com SHA-256 verificado; nunca roda no render."""
from pathlib import Path
import argparse
import hashlib
import os
import httpx

FILES={
 'kokoro-v1.0.onnx':'beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a',
 'voices-v1.0.bin':'bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d'}

def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as source:
        while block:=source.read(1024*1024):value.update(block)
    return value.hexdigest()

def install(data_dir):
    root=Path(data_dir).resolve()/'reels'/'models'/'kokoro';root.mkdir(parents=True,exist_ok=True)
    for name,expected in FILES.items():
        path=root/name
        if path.exists():
            if digest(path)!=expected:raise RuntimeError(f'{name} difere do release verificado; nenhum arquivo existente foi sobrescrito.')
            print(name+': já verificado');continue
        temporary=path.with_suffix(path.suffix+'.download')
        try:
            with httpx.stream('GET','https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/'+name,
                              follow_redirects=True,timeout=120) as response:
                response.raise_for_status()
                with temporary.open('xb') as destination:
                    for chunk in response.iter_bytes(1024*1024):destination.write(chunk)
            if digest(temporary)!=expected:raise RuntimeError('Checksum incorreto; download recusado.')
            temporary.replace(path);print(name+': instalado e verificado')
        finally:temporary.unlink(missing_ok=True)
    return root

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir',default=os.getenv('DATA_DIR','.data'))
    print(install(parser.parse_args().data_dir))
