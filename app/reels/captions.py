import textwrap


def timestamp(seconds, ass=False):
    # Inteiros evitam produzir 00:00:60,000 nas fronteiras de minuto.
    scale = 100 if ass else 1000
    ticks = round(seconds * scale)
    hours, ticks = divmod(ticks, 3600 * scale)
    minutes, ticks = divmod(ticks, 60 * scale)
    whole, fraction = divmod(ticks, scale)
    return f'{hours}:{minutes:02d}:{whole:02d}.{fraction:02d}' if ass else f'{hours:02d}:{minutes:02d}:{whole:02d},{fraction:03d}'


def ass_text(text):
    # A entrada nunca vira tags ASS ou expressões FFmpeg.
    text = text.replace('\\', '／').replace('{', '(').replace('}', ')')
    return r'\N'.join(textwrap.wrap(' '.join(text.split()), width=39))


def write_captions(directory, narration, *, title, duration, signature=''):
    cues = narration['cues']
    srt = []
    for index, cue in enumerate(cues, 1):
        srt.append(f"{index}\n{timestamp(cue['start'])} --> {timestamp(cue['end'])}\n{cue['text']}\n")
    (directory / 'captions.srt').write_text('\n'.join(srt), encoding='utf-8')
    ass = '''[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,DejaVu Sans,42,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80101010,-1,0,0,0,100,100,0,0,3,2,0,2,100,100,360,1
Style: Title,DejaVu Sans,56,&H00FFFFFF,&H00FFFFFF,&H00202020,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,8,80,80,150,1
Style: Credit,DejaVu Sans,24,&H00EADCD3,&H00FFFFFF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,2,0,8,90,90,430,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    end = timestamp(duration, ass=True)
    ass += f'Dialogue: 0,0:00:00.00,{end},Title,,0,0,0,,{ass_text(title)}\n'
    if signature:
        ass += f'Dialogue: 0,0:00:00.00,{end},Credit,,0,0,0,,{ass_text(signature)}\n'
    for cue in cues:
        ass += f"Dialogue: 1,{timestamp(cue['start'], ass=True)},{timestamp(cue['end'], ass=True)},Caption,,0,0,0,,{ass_text(cue['text'])}\n"
    (directory / 'captions.ass').write_text(ass, encoding='utf-8')
