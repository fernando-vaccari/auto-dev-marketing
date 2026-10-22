"""Kokoro-82M ONNX local: pt-BR, CPU, sem download durante inferência."""
import importlib.util
from pathlib import Path
import wave

from .tools import ReelError

VOICES={'pf_dora':'Dora · pt-BR','pm_alex':'Alex · pt-BR','pm_santa':'Santa · pt-BR'}
_cache={}


def available(directory):
    directory=Path(directory) if directory else None
    return bool(directory and (directory/'kokoro-v1.0.onnx').is_file() and (directory/'voices-v1.0.bin').is_file()
                and importlib.util.find_spec('kokoro_onnx'))


def generate(text, output, *, directory, voice='pf_dora', threads=4):
    if voice not in VOICES or not available(directory):
        raise ReelError('Voz neural indisponível. Instale Kokoro local e os modelos verificados pelo instalador.')
    import numpy as np
    import onnxruntime as rt
    rt.disable_telemetry_events()
    from kokoro_onnx import Kokoro
    key=(str(Path(directory).resolve()),threads)
    if key not in _cache:
        options=rt.SessionOptions();options.intra_op_num_threads=threads;options.inter_op_num_threads=1
        options.execution_mode=rt.ExecutionMode.ORT_SEQUENTIAL
        session=rt.InferenceSession(str(Path(directory)/'kokoro-v1.0.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
        _cache[key]=Kokoro.from_session(session,str(Path(directory)/'voices-v1.0.bin'))
    engine=_cache[key]
    if voice not in engine.get_voices():raise ReelError('A voz escolhida não existe no pacote de modelos instalado.')
    audio,rate=engine.create(text,voice=voice,speed=1.0,lang='pt-br',trim=True)
    if not len(audio) or not np.isfinite(audio).all():raise ReelError('A voz neural gerou áudio vazio ou inválido.')
    with wave.open(str(output),'wb') as target:
        target.setparams((1,2,int(rate),0,'NONE','not compressed'))
        target.writeframes((np.clip(audio,-.98,.98)*32767).astype('<i2').tobytes())
