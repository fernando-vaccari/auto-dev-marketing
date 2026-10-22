# Fase 1 — evidências de validação

Validado em 22 de outubro de 2026. O checkout inicial estava limpo em `559867c`. A alteração remota `691b1e8`, que ativa proxy headers, foi incorporada por fast-forward antes de implementar o módulo. Nenhum arquivo de credenciais foi lido, sobrescrito ou incluído no Git.

## Resultados

| Verificação | Resultado |
| --- | --- |
| Baseline existente | 21 testes anteriores passaram antes da implementação |
| Suíte ampliada | 41 testes passaram, sem pulos: 21 anteriores + 20 do módulo |
| Ubuntu 24.04 x86_64 | Suíte completa e instalador executados com FFmpeg 6.1.1 e eSpeak NG 1.51 da distribuição |
| Limites do container de teste | 4 CPUs, 2 GiB de RAM, sem rede, sem GPU; saída 0, sem encerramento por falta de memória |
| Formatos de entrada | MP4, MOV e WebM reais gerados como fixtures, com resoluções e taxas de quadros diferentes |
| Render com trilha | 15 s, 1080×1920, H.264/yuv420p, 30 fps, AAC estéreo de 48 kHz e `faststart` |
| Render sem trilha | Recorte central sem zoom, 15 s e 450 frames; voz e vídeo exportados corretamente |
| Integridade do MP4 | Decodificação integral com FFmpeg sem erros; `moov` antes de `mdat` |
| Roteiros e narração | Voz pt-BR real medida para templates de 15, 30, 45 e 60 s, sem acelerar/cortar fala |
| Legendas | SRT e ASS usam os mesmos intervalos medidos dos WAVs; tags ASS de entrada são neutralizadas |
| Persistência | Biblioteca deduplicada por SHA-256, cópias privadas verificadas antes do render e reimportação restaura cópia corrompida |
| Falhas e concorrência | Dependência ausente gera job com erro; trava impede segundo render; recuperação marca jobs interrompidos |
| Preservação | Testes verificam marca, posts e automação existentes após abrir as novas tabelas |
| Empacotamento/Git | Vídeos, trilhas e ONNX ignorados; o pacote de código não contém mídias geradas ou credenciais |
| Verificações auxiliares | `pip check`, sintaxe JavaScript e sintaxe Bash sem erros |

O render de teste visível foi criado por `scripts/reels_smoke.py`, com padrões coloridos e texto explícito de teste, num banco separado em `.data/reels-smoke`. Ele foi inspecionado visualmente e não representa imagens de um jogo Roblox. Não há gameplay real fornecido nesta tarefa.

## Como repetir

Em Ubuntu 24.04:

```bash
bash scripts/install-reels.sh
REELS_REQUIRE_TOOLS=1 .venv/bin/python -m unittest discover -v
.venv/bin/python scripts/reels_smoke.py
```

A instalação inicial precisa de Internet para os pacotes oficiais. O processamento e os testes de mídia não dependem de rede, APIs de IA ou credenciais Meta. O teste em container montou somente a CA pública do ambiente durante o build para manter HTTPS verificável; nenhuma verificação TLS, assinatura APT ou checksum foi desligada. A etapa de testes rodou com a rede desabilitada.

Também houve execução na máquina de desenvolvimento Debian 13, com FFmpeg 7.1.5 e eSpeak NG 1.52. O eSpeak dessa máquina foi extraído de pacotes obtidos pelos índices APT oficiais assinados, num diretório local, pois o ambiente não dispõe de `sudo`. Essa adaptação não é necessária no Ubuntu com os pacotes instalados normalmente.

## Limites da evidência

- Não é um benchmark no Ryzen 7 5700U/Vega 8; os testes usam fixtures pequenas e não comprovam tempo real ou pico de memória de qualquer gravação 4K/8K.
- O eSpeak foi exercitado de ponta a ponta. O Piper possui testes do contrato de invocação, configuração pt_BR e tratamento de falta de modelo, mas não foi executado com uma voz ONNX real nesta entrega.
- A página Estúdio de Reels, uploads HTTP, preview/download autenticados e fila de render do painel pertencem à Fase 2.
- Os horários 12h30/19h30, de segunda a sábado, são apenas um exemplo de configuração desativada para a Fase 3. Nenhuma aprovação de publicação foi criada.
- Não houve chamada real da API Meta para publicar Reels. A documentação vigente da publicação oficial precisa ser verificada antes dessa implementação.
- O resultado local/container não comprova o resultado do GitHub Actions; a CI foi configurada para exigir os testes de mídia no Ubuntu 24.04.
