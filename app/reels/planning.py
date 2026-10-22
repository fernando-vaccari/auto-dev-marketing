from dataclasses import asdict, dataclass
import math
import re
from .cinema import PRESETS, CAPTIONS, SCRIPT_STYLES

from .library import normalize_themes
from .tools import ReelError

THEME_LINES = {
    'gameplay': 'Confira estas capturas reais de gameplay.',
    'cidades': 'Veja as cidades medievais nestas capturas.',
    'cavernas': 'As cavernas aparecem nestas gravações do projeto.',
    'demonios': 'Veja os demônios registrados neste gameplay.',
    'npcs': 'Conheça os NPCs mostrados nestas capturas.',
    'batalhas': 'Confira as batalhas registradas neste gameplay.',
    'magia': 'A magia aparece nestes trechos gravados.',
    'exploracao': 'Acompanhe estes registros de exploração do mundo.',
}


@dataclass(frozen=True)
class RenderOptions:
    asset_ids: tuple[str, ...]
    duration: int = 30
    title: str = 'RPG medieval em desenvolvimento'
    themes: tuple[str, ...] = ()
    music_id: str | None = None
    effect_id: str | None = None
    effect_volume: float = .10
    tts: str = 'auto'
    piper_model: str | None = None
    script: str | None = None
    fit: str = 'contain'
    zoom: float = 0.02
    threads: int = 4
    music_volume: float = 0.12
    voice_id: str = 'pf_dora'
    kokoro_dir: str | None = None
    voice_speed: float = 1.0
    voice_volume: float = 1.0
    auto_shorten: bool = True
    preset: str = 'legacy'
    caption_style: str = 'preset'
    caption_font: str = 'DejaVu Sans'
    caption_size: int = 42
    caption_color: str = '#FFFFFF'
    caption_outline: int = 2
    caption_shadow: int = 1
    caption_position: str = 'bottom'
    caption_animation: bool = True
    highlight_words: tuple[str, ...] = ()
    selection: str = 'sequential'
    avoid_reuse: bool = True
    cuts_override: tuple[dict, ...] | None = None
    script_style: str = 'informativo'
    game_name: str = ''
    confirmed_facts: tuple[str, ...] = ()
    cta: str = 'Acompanhe o desenvolvimento.'
    variation: int = 0

    def validate(self):
        if type(self.duration) is not int or not 15 <= self.duration <= 60:
            raise ReelError('A duração deve ser um número inteiro entre 15 e 60 segundos.')
        if not self.asset_ids or len(self.asset_ids) > 30 or len(set(self.asset_ids)) != len(self.asset_ids):
            raise ReelError('Escolha de 1 a 30 vídeos importados, sem IDs repetidos.')
        if not self.title.strip() or len(self.title) > 80:
            raise ReelError('O título deve conter de 1 a 80 caracteres.')
        if self.preset not in PRESETS or self.caption_style not in {*CAPTIONS,'preset'} or self.script_style not in SCRIPT_STYLES:
            raise ReelError('Preset ou estilo inválido.')
        if self.selection not in {'sequential','quality'} or self.caption_font not in {'DejaVu Sans','DejaVu Sans Bold'}:
            raise ReelError('Seleção ou fonte inválida.')
        if not 28 <= self.caption_size <= 64 or not 0 <= self.caption_outline <= 5 or not 0 <= self.caption_shadow <= 4 or self.caption_position not in {'bottom','center','top'} or not re.fullmatch(r'#[A-Fa-f0-9]{6}',self.caption_color):
            raise ReelError('Configuração de legenda inválida.')
        if len(self.game_name)>80 or len(self.cta)>100 or len(self.confirmed_facts)>5 or any(len(f)>180 for f in self.confirmed_facts) or len(self.highlight_words)>5 or any(not re.fullmatch(r'[\wÀ-ÿ]{1,24}',w) for w in self.highlight_words):
            raise ReelError('Informações ou destaques excedem os limites.')
        if self.fit not in {'contain', 'crop', 'blur'}:
            raise ReelError('Enquadramento inválido: escolha contain ou crop.')
        if not math.isfinite(self.zoom) or not 0 <= self.zoom <= 0.06:
            raise ReelError('O zoom deve ficar entre 0 e 0.06.')
        if type(self.threads) is not int or not 1 <= self.threads <= 8:
            raise ReelError('Escolha de 1 a 8 threads; o padrão recomendado é 4.')
        if not math.isfinite(self.music_volume) or not 0 <= self.music_volume <= 0.3:
            raise ReelError('O volume da trilha deve ficar entre 0 e 0.3.')
        if not math.isfinite(self.effect_volume) or not 0 <= self.effect_volume <= .3:
            raise ReelError('Volume de efeito inválido.')
        if self.tts not in {'auto', 'espeak', 'piper', 'kokoro'}:
            raise ReelError('Narração inválida: escolha auto, espeak ou piper.')
        if self.voice_id not in {'pf_dora','pm_alex','pm_santa'} or not .85 <= self.voice_speed <= 1.15 or not .5 <= self.voice_volume <= 1.5:
            raise ReelError('Voz, velocidade ou volume inválidos.')
        if self.script is not None and (not self.script.strip() or len(self.script) > 3000):
            raise ReelError('O roteiro deve conter de 1 a 3000 caracteres.')

    def to_dict(self):
        return asdict(self)


def make_script(themes, duration):
    # Usa apenas os temas declarados pelo usuário, sem inventar lore, lançamento ou funcionalidades.
    intro = 'Um RPG medieval está em desenvolvimento no Roblox.'
    outro = 'Acompanhe os próximos registros deste projeto.'
    # Margem para sílabas e pausas de vozes pt-BR, verificada com áudio real.
    budget = max(22, int((duration - 3) * 1.65))
    lines = [intro]
    for theme in themes:
        line = THEME_LINES[theme]
        if len((' '.join(lines + [line, outro])).split()) <= budget:
            lines.append(line)
    if len(lines) == 1:
        lines.append(THEME_LINES[themes[0]])
    extras = [
        'O projeto ainda está em desenvolvimento. Estas imagens são registros do que foi capturado, não uma promessa de lançamento.',
        'Qual destes trechos você quer acompanhar nos próximos vídeos? Compartilhe sua opinião e participe desta jornada de desenvolvimento.',
    ]
    for extra in extras:
        if len((' '.join(lines + [extra, outro])).split()) <= budget:
            lines.append(extra)
    return ' '.join(lines + [outro])


def build_plan(library, options):
    options.validate()
    assets = [library.asset(asset_id, 'video') for asset_id in options.asset_ids]
    themes = normalize_themes(options.themes) or sorted({tag for asset in assets for tag in asset['tags']})
    known = {tag for asset in assets for tag in asset['tags']}
    missing = set(themes) - known
    if missing:
        raise ReelError('Não há gravações importadas com estes temas: ' + ', '.join(sorted(missing)))
    selected = [asset for asset in assets if set(asset['tags']) & set(themes)]
    fps = 30
    capacities = {asset['id']: math.floor(asset['metadata']['duration'] * fps) for asset in selected}
    required = options.duration * fps
    if sum(capacities.values()) < required:
        raise ReelError(f'As gravações selecionadas têm {sum(capacities.values()) / fps:.2f}s utilizáveis; importe pelo menos {options.duration}s. Não repetimos ou inventamos cenas para completar o vídeo.')
    cut_frames=round(PRESETS[options.preset]['cut']*fps)
    transition=PRESETS[options.preset]['transition']
    overlap=6 if transition=='dissolve' else 0

    def allocate(budget):
        if options.selection=='quality':
            from .analysis import select
            return select(library,selected,budget,cut_frames,avoid_reuse=options.avoid_reuse)
        cursors={asset['id']:0 for asset in selected};remaining=budget;result=[]
        while remaining:
            for asset in selected:
                identifier=asset['id'];frames=min(cut_frames,capacities[identifier]-cursors[identifier],remaining)
                if not frames:continue
                result.append({'asset_id':identifier,'source_start':cursors[identifier]/fps,'duration':frames/fps,'frames':frames,'tags':asset['tags']})
                cursors[identifier]+=frames;remaining-=frames
                if not remaining:break
        return result

    cuts=allocate(required);warning=''
    if overlap:
        for attempt in range(6):
            budget=required+overlap*(len(cuts)-1)
            if budget>sum(capacities.values()):
                overlap=0;transition='fade';warning='Sem margem real para sobreposição: usamos fade e preservamos a duração.';cuts=allocate(required);break
            try:newcuts=allocate(budget)
            except ReelError:
                overlap=0;transition='fade';cuts=allocate(required);break
            if len(newcuts)==len(cuts):cuts=newcuts;break
            cuts=newcuts
        else:
            overlap=0;transition='fade';cuts=allocate(required)
    if overlap and any(c['frames']<=2*overlap for c in cuts):
        overlap=0;transition='fade';cuts=allocate(required)
    if options.cuts_override:
        cuts=[]
        for value in options.cuts_override:
            identifier=value['asset_id'];start=float(value['source_start']);length=float(value['duration'])
            if identifier not in capacities or not math.isfinite(start+length) or start<0 or length<=0 or round((start+length)*fps)>capacities[identifier]:
                raise ReelError('Um corte revisado ultrapassa a gravação disponível.')
            cuts.append({'asset_id':identifier,'source_start':round(start*fps)/fps,'frames':round(length*fps),'duration':round(length*fps)/fps})
        if sum(c['frames'] for c in cuts)-overlap*(len(cuts)-1)!=required:
            raise ReelError('A soma dos cortes revisados e transições deve corresponder à duração escolhida.')
        for index,cut in enumerate(cuts):
            for previous in cuts[:index]:
                if previous['asset_id']==cut['asset_id'] and max(previous['source_start'],cut['source_start'])<min(previous['source_start']+previous['duration'],cut['source_start']+cut['duration']):
                    raise ReelError('Os cortes revisados não podem repetir o mesmo intervalo.')
    timeline=0
    for cut in cuts:
        cut['timeline_start']=timeline/fps
        timeline+=cut['frames']-overlap
    script=options.script.strip() if options.script else make_script(themes, options.duration)
    if not options.script and (options.game_name or options.script_style!='informativo' or options.confirmed_facts):
        from .scripts import promotional_script
        script=promotional_script(themes,options)
    return {'version': 1, 'title': options.title, 'duration': options.duration, 'fps': fps,
            'width': 1080, 'height': 1920, 'themes': themes, 'cuts': cuts,
            'sources': [{'id': asset['id'], 'sha256': asset['sha256'], 'original_name': asset['original_name'],
                         'relative_path': asset['relative_path'], 'metadata': asset['metadata']} for asset in selected],
            'script': script,
            'script_source': 'user' if options.script else 'local_template',
            'scene_evidence': 'user_declared_tags', 'fit': options.fit, 'zoom': options.zoom,
            'source_audio': 'muted', 'publishing_enabled': False, 'transition':transition,'overlap':overlap/fps,'warning':warning,'preset':options.preset}
