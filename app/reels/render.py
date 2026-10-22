from contextlib import contextmanager
from pathlib import Path
import fcntl
import json
import shutil
import time

from .captions import write_captions
from .planning import build_plan
from .cinema import grade
from .analysis import analyze, metrics, record_usage
from .speech import synthesize_fitting
from .tools import ReelError, doctor, executable, probe, run


@contextmanager
def render_lock(root):
    with (root / 'render.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ReelError('Já existe um Reel sendo renderizado neste diretório. Aguarde antes de iniciar outro.') from None
        yield


class ReelStudio:
    def __init__(self, library, progress=None):
        self.library = library
        self.progress = progress or (lambda value: None)

    def render(self, options, job_id=None):
        supervised = job_id is not None
        options.validate()
        with render_lock(self.library.root):
            self.library.recover_interrupted()
            job_id = job_id or self.library.create_job(options.to_dict())
            self.library.begin_job(job_id)
            directory = self.library.root / 'jobs' / job_id
            commands = []
            started = time.monotonic()

            def update(stage, percent, detail=''):
                self.library.update_job(job_id, 'rendering', stage, percent, detail)
                self.progress({'job_id': job_id, 'stage': stage, 'progress': percent, 'detail': detail})

            def ffmpeg(args, timeout=180):
                command = [executable('ffmpeg'), '-nostdin', '-hide_banner', '-v', 'error', '-y'] + [str(value) for value in args]
                commands.append(command)
                (directory / 'commands.json').write_text(json.dumps(commands, ensure_ascii=False, indent=2))
                return run(command, cwd=directory, timeout=timeout, log=directory / 'render.log')

            try:
                directory.mkdir()
                update('preflight', 2)
                capabilities = doctor()
                if not capabilities['ffmpeg']['available'] or not capabilities['ffprobe']['available']:
                    raise ReelError('FFmpeg e ffprobe são obrigatórios. Execute o instalador do Estúdio de Reels.')
                if not all(capabilities['filters'].values()) or not all(capabilities['encoders'].values()):
                    raise ReelError('Esta instalação do FFmpeg precisa de libx264, AAC, libass, zoompan e filtros de áudio.')
                if options.selection == 'quality':
                    for asset_id in options.asset_ids:
                        if not metrics(self.library, asset_id):
                            update('analysis', 5, 'Analisando movimento, exposição e nitidez; sem compreensão semântica')
                            analyze(self.library, asset_id)
                plan = build_plan(self.library, options)
                music = self.library.asset(options.music_id, 'music') if options.music_id else None
                assets = {asset_id: self.library.asset(asset_id, 'video') for asset_id in options.asset_ids}
                paths = {key: self.library.asset_path(value, verify=True) for key, value in assets.items()}
                music_path = self.library.asset_path(music, verify=True) if music else None
                effect = self.library.asset(options.effect_id, 'effect') if options.effect_id else None
                effect_path = self.library.asset_path(effect,verify=True) if effect else None
                (directory / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
                (directory / 'script.txt').write_text(plan['script'] + '\n', encoding='utf-8')
                update('narration', 8, 'Gerando voz local por frases, sem rede')
                narration = synthesize_fitting(plan['script'], directory, engine=options.tts,
                                       model=options.kokoro_dir if options.tts in {'kokoro','my_voice'} else options.piper_model,
                                       duration=options.duration, threads=options.threads, voice_id=options.voice_id,
                                       speed=options.voice_speed, volume=options.voice_volume, auto_shorten=options.auto_shorten,
                                       clone_profile_id=options.clone_profile_id,clone_root=options.clone_root)
                plan['script'] = narration['text']
                (directory / 'script.txt').write_text(plan['script'] + '\n', encoding='utf-8')
                (directory / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
                (directory / 'narration.json').write_text(json.dumps(narration, ensure_ascii=False, indent=2))
                write_captions(directory, narration, title=options.title, duration=options.duration,
                               signature=self.library.db.brand().get('signature', ''), options=options)
                from .voices import _cache
                _cache.clear()
                import gc
                gc.collect()
                font_dir = directory / 'fonts'
                font_dir.mkdir()
                for font in (Path(__file__).parents[1] / 'web' / 'fonts').glob('*.ttf'):
                    shutil.copyfile(font, font_dir / font.name)
                segments = []
                for index, cut in enumerate(plan['cuts']):
                    update('cuts', 20 + int(50 * index / len(plan['cuts'])), f"Corte {index + 1}/{len(plan['cuts'])}")
                    filters = ['fps=30']
                    if options.fit == 'contain':
                        filters += ['scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2',
                                    'pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x11111b']
                    elif options.fit == 'blur':
                        filters += ['split[bgin][fgin];[bgin]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=8:1,scale=1080:1920[back];[fgin]scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2[front];[back][front]overlay=(W-w)/2:(H-h)/2:shortest=1']
                    else:
                        filters += ['scale=1080:1920:force_original_aspect_ratio=increase:force_divisible_by=2', 'crop=1080:1920']
                    filters += ['setsar=1', 'format=yuv420p', 'tpad=stop_mode=clone:stop_duration=0.1']
                    if options.zoom:
                        filters.append(f"zoompan=z='1+{options.zoom}*on/{cut['frames']}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=1080x1920:fps=30")
                    filters += grade(options)
                    fade = min(.12, cut['duration'] / 4)
                    if plan['transition'] == 'fade':
                        filters += [f"fade=t=in:st=0:d={fade:.3f}", f"fade=t=out:st={max(0, cut['duration'] - fade):.4f}:d={fade:.3f}"]
                    target = f'cut-{index:03d}.mp4'
                    ffmpeg(['-threads', options.threads, '-ss', f"{cut['source_start']:.6f}", '-protocol_whitelist', 'file,pipe',
                            '-i', paths[cut['asset_id']], '-map', '0:v:0', '-an', '-sn', '-dn', '-filter_threads', '1',
                            '-vf', ','.join(filters), '-frames:v', cut['frames'], '-r', '30',
                            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20', '-pix_fmt', 'yuv420p',
                            '-threads', options.threads, target], timeout=max(180, cut['duration'] * 30))
                    segments.append(f"file '{target}'")
                (directory / 'cuts.ffconcat').write_text('ffconcat version 1.0\n' + '\n'.join(segments) + '\n')
                update('compositing', 75, 'Montando títulos, legendas, voz e trilha')
                args=[];graph=[]
                if plan['transition']=='dissolve' and len(plan['cuts'])>1:
                    for index in range(len(plan['cuts'])):
                        args += ['-threads','1','-i',f'cut-{index:03d}.mp4']
                    previous='0:v'
                    for index in range(1,len(plan['cuts'])):
                        offset=plan['cuts'][index]['timeline_start']
                        target=f'x{index}'
                        graph.append(f'[{previous}][{index}:v]xfade=transition=fade:duration={plan["overlap"]}:offset={offset}[{target}]')
                        previous=target
                    video_source=previous;voice_index=len(plan['cuts'])
                else:
                    args=['-threads',options.threads,'-f','concat','-safe','1','-i','cuts.ffconcat']
                    video_source='0:v';voice_index=1
                args+=['-i','narration.wav']
                graph += [f'[{video_source}]ass=filename=captions.ass:fontsdir=fonts,format=yuv420p[v]',
                          f'[{voice_index}:a]aresample=48000,asplit=2[voice][side]']
                if music:
                    args += ['-stream_loop','-1','-protocol_whitelist','file,pipe','-i',music_path]
                    graph += [f'[{voice_index+1}:a]atrim=duration={options.duration},asetpts=PTS-STARTPTS,aresample=48000,loudnorm=I=-24:TP=-4:LRA=9,volume={options.music_volume},afade=t=in:d=1,afade=t=out:st={options.duration-1}:d=1[bgm]',
                              '[bgm][side]sidechaincompress=threshold=0.025:ratio=8:attack=20:release=350[ducked]',
                              '[voice][ducked]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:level=false[a]']
                else:
                    graph += ['[side]anullsink','[voice]alimiter=limit=0.95:level=false[a]']
                if effect:
                    effect_index=voice_index+1+(1 if music else 0)
                    args+=['-protocol_whitelist','file,pipe','-i',effect_path]
                    graph=[chain.replace('[a]','[bed]') for chain in graph]
                    points=[cut['timeline_start'] for cut in plan['cuts'][1:]][:12] or [0]
                    labels=''.join(f'[s{i}]' for i in range(len(points)))
                    graph.append(f'[{effect_index}:a]atrim=duration=0.8,aresample=48000,volume={options.effect_volume},afade=t=out:st=0.5:d=0.3,asplit={len(points)}{labels}')
                    for i,point in enumerate(points):graph.append(f'[s{i}]adelay={round(point*1000)}:all=1[fx{i}]')
                    inputs='[bed]'+''.join(f'[fx{i}]' for i in range(len(points)))
                    graph.append(f'{inputs}amix=inputs={len(points)+1}:duration=first:normalize=0,alimiter=limit=0.95:level=false[a]')
                args += ['-filter_complex_threads', '1', '-filter_complex', ';'.join(graph), '-map', '[v]', '-map', '[a]',
                         '-t', options.duration, '-r', '30', '-c:v', 'libx264', '-profile:v', 'high', '-level:v', '4.1',
                         '-preset', 'veryfast', '-crf', '23', '-maxrate', '10M', '-bufsize', '20M', '-pix_fmt', 'yuv420p',
                         '-threads', options.threads, '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
                         '-map_metadata', '-1', '-movflags', '+faststart', 'reel.partial.mp4']
                ffmpeg(args, timeout=max(300, options.duration * 30))
                update('validation', 95)
                metadata = probe(directory / 'reel.partial.mp4')
                videos = [stream for stream in metadata['streams'] if stream['codec_type'] == 'video']
                audios = [stream for stream in metadata['streams'] if stream['codec_type'] == 'audio']
                if not videos or not audios or (videos[0].get('width'), videos[0].get('height')) != (1080, 1920) or videos[0].get('codec_name') != 'h264' or videos[0].get('pix_fmt') != 'yuv420p' or audios[0].get('codec_name') != 'aac' or videos[0].get('avg_frame_rate') != '30/1' or audios[0].get('sample_rate') != '48000' or audios[0].get('channels') != 2 or abs(metadata['duration'] - options.duration) > .1:
                    raise ReelError('O arquivo renderizado não passou na validação de resolução, duração ou codecs.')
                # Decodificação completa detecta corrupção além dos metadados.
                ffmpeg(['-i','reel.partial.mp4','-f','null','-'],timeout=max(120,options.duration*5))
                deliverables = directory / 'deliverables'
                deliverables.mkdir()
                target = deliverables / 'reel.mp4'
                (directory / 'reel.partial.mp4').replace(target)
                report = {'job_id': job_id, 'output': str(target), 'metadata': metadata,
                          'elapsed_seconds': round(time.monotonic() - started, 2), 'tts': narration['engine'],
                          'threads': options.threads, 'gpu_used': False, 'network_used': False,
                          'publishing_enabled': False, 'source_audio': 'muted',
                          'transitions': plan['transition'], 'intermediates_kept': True}
                (directory / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
                relative = str(target.relative_to(self.library.root))
                record_usage(self.library,job_id,plan['cuts'])
                self.library.update_job(job_id, 'ready', 'ready', 100, output_path=relative)
                self.progress({'job_id': job_id, 'stage': 'ready', 'progress': 100})
                return report
            except BaseException as exc:
                message = 'Renderização interrompida pelo usuário.' if isinstance(exc, KeyboardInterrupt) else str(exc)
                if not (supervised and isinstance(exc, KeyboardInterrupt)):
                    self.library.update_job(job_id, 'failed', 'failed', 0, error=message)
                if isinstance(exc, (ReelError, KeyboardInterrupt)):
                    raise
                raise ReelError(f'Falha interna no job {job_id}. Consulte o histórico e render.log: {type(exc).__name__}') from None
