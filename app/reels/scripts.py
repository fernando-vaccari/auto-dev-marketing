"""Templates de estilo; fatos declarados pelo usuário, sem inventar lore ou lançamento."""
from .planning import THEME_LINES
INTRO={
 'epico':['Uma jornada está tomando forma.','Cada gravação revela um novo passo.'],
 'misterioso':['O que estas gravações revelam?','Há mais para observar nestas capturas.'],
 'empolgante':['Veja os novos registros do projeto!','Novas capturas, novos detalhes para acompanhar!'],
 'informativo':['Confira estas gravações do projeto.','Veja o registro mais recente do desenvolvimento.'],
 'diario':['Mais um registro do nosso desenvolvimento.','Hoje compartilhamos uma etapa do projeto.'],
 'curiosidade':['Qual detalhe chamou sua atenção?','O que você percebe nestes registros?'],
 'atualizacao':['Estas são as capturas desta atualização.','Confira os registros mais recentes do projeto.'],
}

def promotional_script(themes,options):
    opening=INTRO[options.script_style][options.variation%2]
    name=(options.game_name+': ') if options.game_name else ''
    # As versões curtas serão verificadas novamente com áudio real, em até quatro tentativas.
    lines=[name+opening,THEME_LINES[themes[options.variation%len(themes)]]]
    lines.extend(options.confirmed_facts[:min(3,max(1,options.duration//15))])
    lines.append(options.cta)
    return ' '.join(lines)
