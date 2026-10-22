-- São referências configuráveis a marcadores de câmera, não mapas ou cenas geradas.
-- Crie/associe cada marcador real em Workspace/AutoPostsCameras antes de executar.
local names={"Cidade medieval","Castelo","Floresta","Caverna","Combate","Magia","NPC","Exploração"}
local ids={"cidade","castelo","floresta","caverna","combate","magia","npc","exploracao"}
local sequences={}
for index,name in ipairs(names) do
    sequences[index]={id=ids[index],name=name,hideUI=true,points={
        {camera="AutoPostsCameras/"..ids[index].."_inicio",duration=5,fov=65,cut=true},
        {camera="AutoPostsCameras/"..ids[index].."_fim",duration=10,fov=55},
    }}
end
-- Para foco móvel: acrescente focus="Pasta/PersonagemReal" no ponto.
-- Para panorama: pan=25. Sobrevoo/travelling: posicione marcadores reais no trajeto.
return sequences
