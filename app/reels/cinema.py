"""Presets de efeitos leves e parâmetros seguros para FFmpeg/ASS."""
PRESETS={
 'legacy':dict(name='Edição clássica',cut=5,transition='fade',contrast=1,saturation=1,brightness=0,zoom=.02,caption='cinematic',accent='#FFFFFF',music=.12,vignette=False,sharp=0),
 'medieval_epico':dict(name='Medieval épico',cut=3.5,transition='fade',contrast=1.06,saturation=.94,brightness=-.01,zoom=.025,caption='cinematic',accent='#F0CF91',music=.14,vignette=True,sharp=.2),
 'fantasia':dict(name='Fantasia cinematográfica',cut=4,transition='dissolve',contrast=1.03,saturation=1.07,brightness=0,zoom=.02,caption='cinematic',accent='#D7C9FF',music=.12,vignette=True,sharp=.15),
 'misterio':dict(name='Mistério',cut=5,transition='dissolve',contrast=1.05,saturation=.85,brightness=-.015,zoom=.015,caption='minimal',accent='#C8D4E8',music=.10,vignette=True,sharp=.1),
 'combate':dict(name='Combate',cut=2,transition='fade',contrast=1.06,saturation=1.04,brightness=0,zoom=.03,caption='gamer',accent='#FFD084',music=.14,vignette=False,sharp=.25),
 'exploracao':dict(name='Exploração',cut=5.5,transition='dissolve',contrast=1.02,saturation=1.04,brightness=.005,zoom=.018,caption='modern',accent='#CFEBD5',music=.10,vignette=False,sharp=.1),
 'diario':dict(name='Diário de desenvolvimento',cut=5,transition='fade',contrast=1.01,saturation=1,brightness=0,zoom=.008,caption='minimal',accent='#FFFFFF',music=.08,vignette=False,sharp=0),
 'atualizacao':dict(name='Atualização do jogo',cut=3.5,transition='fade',contrast=1.03,saturation=1.03,brightness=0,zoom=.015,caption='modern',accent='#D2C1FF',music=.10,vignette=False,sharp=.1),
 'trailer_curto':dict(name='Trailer curto para Instagram',cut=2.5,transition='fade',contrast=1.04,saturation=1.02,brightness=0,zoom=.025,caption='gamer',accent='#E7D5FF',music=.12,vignette=True,sharp=.15),
}
CAPTIONS={
 'cinematic':dict(size=43,outline=2,shadow=1,bold=True,margin=340),
 'gamer':dict(size=48,outline=3,shadow=2,bold=True,margin=350),
 'modern':dict(size=44,outline=2,shadow=1,bold=True,margin=320),
 'minimal':dict(size=38,outline=1,shadow=0,bold=False,margin=300),
}
SCRIPT_STYLES={'epico','misterioso','empolgante','informativo','diario','curiosidade','atualizacao'}


def preset(options):return PRESETS[options.preset]


def grade(options):
    p=preset(options)
    filters=[]
    if options.preset!='legacy':
        filters.append(f"eq=contrast={p['contrast']}:saturation={p['saturation']}:brightness={p['brightness']}")
        if p['sharp']:filters.append(f"unsharp=3:3:{p['sharp']}:3:3:0")
        if p['vignette']:filters.append('vignette=angle=PI/7')
    return filters
