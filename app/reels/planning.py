from dataclasses import asdict, dataclass
import math

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
    tts: str = 'auto'
    piper_model: str | None = None
    script: str | None = None
    fit: str = 'contain'
    zoom: float = 0.02
    threads: int = 4
    music_volume: float = 0.12

    def validate(self):
        if type(self.duration) is not int or not 15 <= self.duration <= 60:
            raise ReelError('A duração deve ser um número inteiro entre 15 e 60 segundos.')
        if not self.asset_ids or len(self.asset_ids) > 30 or len(set(self.asset_ids)) != len(self.asset_ids):
            raise ReelError('Escolha de 1 a 30 vídeos importados, sem IDs repetidos.')
        if not self.title.strip() or len(self.title) > 80:
            raise ReelError('O título deve conter de 1 a 80 caracteres.')
        if self.fit not in {'contain', 'crop'}:
            raise ReelError('Enquadramento inválido: escolha contain ou crop.')
        if not math.isfinite(self.zoom) or not 0 <= self.zoom <= 0.06:
            raise ReelError('O zoom deve ficar entre 0 e 0.06.')
        if type(self.threads) is not int or not 1 <= self.threads <= 8:
            raise ReelError('Escolha de 1 a 8 threads; o padrão recomendado é 4.')
        if not math.isfinite(self.music_volume) or not 0 <= self.music_volume <= 0.3:
            raise ReelError('O volume da trilha deve ficar entre 0 e 0.3.')
        if self.tts not in {'auto', 'espeak', 'piper'}:
            raise ReelError('Narração inválida: escolha auto, espeak ou piper.')
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
    cursors = {asset['id']: 0 for asset in selected}
    remaining = required
    cuts = []
    timeline = 0
    while remaining:
        for asset in selected:
            asset_id = asset['id']
            frames = min(5 * fps, capacities[asset_id] - cursors[asset_id], remaining)
            if not frames:
                continue
            cuts.append({'asset_id': asset_id, 'source_start': cursors[asset_id] / fps,
                         'duration': frames / fps, 'frames': frames, 'timeline_start': timeline / fps,
                         'tags': asset['tags']})
            cursors[asset_id] += frames
            remaining -= frames
            timeline += frames
            if not remaining:
                break
    return {'version': 1, 'title': options.title, 'duration': options.duration, 'fps': fps,
            'width': 1080, 'height': 1920, 'themes': themes, 'cuts': cuts,
            'sources': [{'id': asset['id'], 'sha256': asset['sha256'], 'original_name': asset['original_name'],
                         'relative_path': asset['relative_path'], 'metadata': asset['metadata']} for asset in selected],
            'script': options.script.strip() if options.script else make_script(themes, options.duration),
            'script_source': 'user' if options.script else 'local_template',
            'scene_evidence': 'user_declared_tags', 'fit': options.fit, 'zoom': options.zoom,
            'source_audio': 'muted', 'publishing_enabled': False}
