# Estúdio de Reels — pipeline e CLI

Módulo **local e offline** para transformar gravações existentes de gameplay em MP4 vertical, sem reescrever o Auto Posts. A CLI `python -m app.reels` da Fase 1 permanece disponível. A Fase 2 já oferece [geração pelo painel web](reels-web.md); geração/publicação agendada e Meta Reels pertencem à Fase 3.

## Arquitetura existente e extensão escolhida

| Componente existente | Responsabilidade | Como foi preservado |
| --- | --- | --- |
| `app/main.py` | FastAPI, painel, autenticação, sessão e endpoints | Fase 1 sem novas rotas; Fase 2 adiciona rotas privadas e supervisor, preservando as rotas anteriores |
| `app/db.py` | SQLite, posts de imagem, identidade, eventos e automação | Tabelas e registros anteriores mantidos; o novo repositório usa `Database.connect()` |
| `app/publisher.py` / `app/automation.py` | Fila assíncrona e rotina de publicação de imagem | Não recebem vídeos nem executam FFmpeg; o render não bloqueia seu event loop |
| `app/meta.py` | Graph API para publicação de imagens | Integração existente preservada; publicação de Reels não implementada |
| `.data/media` | JPEGs públicos para a Meta | Gameplays e Reels não entram nessa pasta nem são expostos por StaticFiles |
| Testes anteriores | 21 testes funcionais | Mantidos, sem remover ou enfraquecer assertions |

`app/reels/library.py` cria, de forma aditiva, `reel_assets`, `reel_jobs` e `reel_job_events` no mesmo `marketing.sqlite3`. Não altera a marca existente nem ativa a automação. O render ocorre em processo CLI separado e trava apenas outro render do Estúdio, não o worker de posts de imagem. A CLI executa o job sincronamente e registra progresso no SQLite. A [fila web da Fase 2](reels-web.md) usa um processo filho por job e reutiliza o mesmo renderizador.

### Pipeline da Fase 1

1. Copiar MP4/MOV/WebM para a biblioteca privada, sem modificar o original.
2. Calcular SHA-256 por streaming e medir streams/duração com ffprobe; importações repetidas reutilizam o registro.
3. Selecionar apenas gravações com os temas declarados, planejar cortes de até 5 segundos e salvar os intervalos de origem.
4. Montar roteiro pt-BR por templates locais, sem datas de lançamento, lore ou recursos inventados.
5. Sintetizar frases em português offline e medir cada WAV. Os tempos de legenda vêm dessas medições, não de estimativa pelo número de caracteres.
6. Normalizar os cortes, aplicar fades de até 120 ms, zoom suave opcional, títulos e legendas ASS. Misturar voz e trilha local opcional.
7. Validar o resultado antes de marcar o job como `ready` e disponibilizar `deliverables/reel.mp4` no disco local.

Não há visão computacional para identificar cidades, magia ou personagens. **Os temas são declarações suas sobre o que está visível na gravação.** Não marque cenas que não existem. Um tema solicitado sem gravação correspondente falha; falta de duração também falha, sem repetir trechos para completar o vídeo. Um roteiro fornecido por `--script-file` é de sua autoria e precisa da sua revisão factual.

## Instalar no Ubuntu 24.04

Requisitos: Python 3.12, `venv`, FFmpeg com libx264/AAC/libass e eSpeak NG. Não é necessária GPU, driver especial, conta PixVerse, chave de IA ou API paga.

No checkout atualizado do repositório:

```bash
cd auto-dev-marketing
bash scripts/install-reels.sh
.venv/bin/python -m app.reels doctor
```

O instalador usa os pacotes oficiais `ffmpeg`, `espeak-ng` e `python3-venv` via APT, solicitando `sudo` apenas se faltarem ferramentas. Depois reutiliza `scripts/install.sh` e o ambiente virtual existente. Não lê, sobrescreve ou cria valores de `.env`. Para instalar manualmente:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg espeak-ng python3-venv
bash scripts/install.sh
```

### Voz padrão: eSpeak NG

`--tts espeak` utiliza a voz `pt-br`, velocidade 165 palavras/minuto. É inteiramente offline, pequena e rápida, mas sua qualidade é robótica. A narração é gerada em frases, normalizada em WAV mono de 48 kHz e posicionada na timeline sem cortar palavras ou acelerar a fala para caber. Se um roteiro ultrapassar a duração escolhida, o job falha com a duração medida; reduza o texto ou aumente o Reel.

### Piper opcional, em CPU

O adaptador aceita o Piper atual e um modelo **pt_BR já baixado**, com `.onnx` e `.onnx.json` locais. Não há download durante a renderização nem uso de `--cuda`.

```bash
.venv/bin/python -m pip install -r requirements-reels-piper.txt
mkdir -p .data/reels/models
.venv/bin/python -m piper.download_voices pt_BR-faber-medium --data-dir .data/reels/models
```

Esse download inicial precisa de Internet. Use o utilitário oficial, preserve a verificação TLS e confira a licença e o MODEL_CARD da voz antes de uso promocional. Depois passe `--tts piper --piper-model .data/reels/models/pt_BR-faber-medium.onnx`. Também é possível definir `REELS_PIPER_MODEL` no ambiente. Uma escolha explícita de Piper nunca é trocada silenciosamente por eSpeak. O teste de geração real desta entrega usa eSpeak; a inferência de uma voz Piper específica depende da instalação do modelo.

Referência consultada: [CLI oficial do Piper](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/CLI.md). O idioma é verificado no JSON da voz. Não há clonagem de voz.

## Gerar o primeiro Reel a partir do seu gameplay

Separe uma gravação real com pelo menos **15 segundos utilizáveis**. MP4, MOV e WebM são aceitos; o original permanece intacto. Rode no diretório do projeto:

```bash
set -euo pipefail

# Substitua somente este caminho pelo arquivo já gravado no seu computador.
GAMEPLAY="/caminho/para/seu-gameplay.mp4"

VIDEO_ID=$(.venv/bin/python -m app.reels import "$GAMEPLAY" --tags gameplay |
  .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

# Primeiro revise o plano e o roteiro; esta ação não renderiza nem publica.
.venv/bin/python -m app.reels plan --asset "$VIDEO_ID" --duration 15

# Gere o MP4 completo em CPU.
.venv/bin/python -m app.reels render \
  --asset "$VIDEO_ID" \
  --duration 15 \
  --title "Meu RPG medieval em desenvolvimento" \
  --tts espeak \
  --threads 4
```

A saída JSON informa `output`, apontando para:

```text
.data/reels/jobs/<JOB_ID>/deliverables/reel.mp4
```

Esse é o arquivo pronto para visualizar localmente com VLC ou outro player e revisar antes de qualquer publicação. Nesta fase não há botão no painel, download HTTP ou envio ao Instagram.

Para vários vídeos, repita `--asset ID` em `plan` e `render`. A soma das durações deve atender ao tempo final; os cortes alternam entre fontes e não reutilizam os mesmos intervalos. Informe `--duration` de **15 a 60**, em segundos inteiros.

Temas reconhecidos: `gameplay`, `cidades`, `cavernas`, `demonios`, `npcs`, `batalhas`, `magia`, `exploracao`. A importação aceita acentos. Por exemplo, se sua gravação realmente mostra cidades e exploração, use `--tags cidades,exploração` e depois `--themes cidades` no render. Usar somente `gameplay` produz uma descrição genérica da gravação.

### Trilha fornecida por você

Importe um arquivo de áudio que tenha autorização para usar, sem confundir música do gameplay com trilha licenciada:

```bash
TRILHA_ID=$(.venv/bin/python -m app.reels import "/caminho/trilha.wav" --kind music |
  .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

.venv/bin/python -m app.reels render --asset "$VIDEO_ID" --duration 30 \
  --title "Diário de desenvolvimento do meu RPG" --tts espeak \
  --music "$TRILHA_ID" --music-volume 0.12
```

Este exemplo de 30 segundos exige pelo menos 30 segundos de gravações selecionadas. Trilhas curtas são repetidas explicitamente até o fim do vídeo, com fade de entrada/saída. A voz é normalizada e a música recebe volume fixo baixo, não ducking automático. O áudio original do gameplay é **silenciado** nesta primeira versão. Sem trilha, a saída contém narração e silêncio nos intervalos.

### Enquadramento e custo de render

- Padrão `--fit contain`: preserva o enquadramento inteiro, sem distorção, em um fundo escuro vertical. É a opção mais conservadora para HUD de gameplay horizontal.
- `--fit crop`: preenche a tela com recorte central. Não há rastreamento de personagem ou identificação automática de HUD; confira o resultado.
- `--zoom 0.02`: zoom progressivo de até aproximadamente 2% por corte; `--zoom 0` desliga o efeito.
- Quatro threads de FFmpeg por padrão, uma thread de filtros e apenas um job por biblioteca. `--threads 2` reduz a carga. Nenhuma aceleração Radeon/CUDA é exigida.
- Saída fixa 1080×1920, 30 fps, H.264 High nível 4.1, yuv420p, AAC estéreo de 48 kHz/192 kbps e `faststart`. Duração e codecs são conferidos por ffprobe.
- Os intermediários usam H.264 para limitar disco/RAM. Há uma normalização por corte e uma codificação final; não é uma operação de cópia sem perda. A velocidade real depende da gravação e deve ser medida no Ryzen 7 5700U; não há garantia de tempo real.

O projeto é direcionado a Ryzen 7 5700U/Vega 8/12 GB, mas a validação não mede diretamente esse equipamento. Não há carregamento de todos os vídeos na RAM, renders concorrentes ou modelo de vídeo generativo.

## Roteiro próprio e legendas

Crie um `.txt` UTF-8 e use `--script-file /caminho/roteiro.txt`. O texto aparece em `script.txt`, é falado e vira legenda por frases. O SRT e o ASS são derivados dos mesmos tempos medidos, com até duas linhas por legenda em condições normais. Isso não é alinhamento de palavra a palavra ou transcrição de áudio arbitrário. Não geramos legendas para a fala que já exista no gameplay nesta fase.

Todos os jobs guardam `plan.json` com hashes e intervalos de origem, `script.txt`, `narration.json`, `narration.wav`, `captions.srt`, `captions.ass`, `commands.json`, `render.log` e `report.json`. O MP4 só recebe status pronto após validação. Os comandos usam listas de argumentos, não shell com texto do roteiro.

## Biblioteca, progresso e falhas

```bash
.venv/bin/python -m app.reels list
.venv/bin/python -m app.reels list --kind music
.venv/bin/python -m app.reels jobs
.venv/bin/python -m app.reels jobs --id ID_DO_JOB
```

O progresso é impresso em JSON no stderr e registrado por etapa no SQLite. O resultado final sai em JSON no stdout. Erros têm código de saída 2 e interrupção pelo usuário, 130. Jobs com falha mantêm histórico e logs. Após interrupção abrupta, o próximo render, depois de obter a trava, marca jobs antigos em execução como interrompidos. Não há reenvio ou nova tentativa automática.

Gameplays e entregáveis ficam sob `DATA_DIR/reels`, fora das rotas públicas atuais. Reutilize o `DATA_DIR` do painel; `--data-dir /outro/local` deve vir **antes** do subcomando. Não mova nem exclua `.data` inteira, que também contém seu banco e a chave de sessão. Intermediários ocupam espaço e não são apagados automaticamente; faça backup e inspecione antes de removê-los.

## Reel de teste sem material gravado

Para verificar instalação e render antes de importar gameplay:

```bash
.venv/bin/python scripts/reels_smoke.py
```

O script gera padrões de teste e uma trilha de tom simples, explicitamente identificados como **sintéticos, não cenas do Roblox**. Usa um banco separado em `.data/reels-smoke`. Não é conteúdo promocional real. Sem gravações suas, não há Reel real do jogo a produzir.

## Testes

```bash
REELS_REQUIRE_TOOLS=1 .venv/bin/python -m unittest discover -v
.venv/bin/python -m pip check
node --check app/web/app.js
node --check app/web/login.js
```

`REELS_REQUIRE_TOOLS=1` faz a suíte falhar se FFmpeg/eSpeak não estiverem disponíveis. Sem essa variável, somente os testes de integração de mídia podem ser pulados por ferramentas ausentes, com a condição relatada pelo unittest. Os testes geram MP4/MOV/WebM temporários; nenhum gameplay ou MP4 de saída precisa ser versionado. A CI instala as ferramentas gratuitas e exige esses testes.

[Resultados de validação da Fase 1](reels-validation.md): inclui testes no Ubuntu 24.04 com rede desabilitada e os limites do que foi comprovado.

## Limites e próximas fases

- **Fase 1 entregue:** biblioteca, roteiro local, voz offline, legendas, montagem, exportação, progresso/falhas e CLI.
- **Fase 2 entregue:** nova página no painel, importação autenticada, edição das configurações, fila de render fora do processo ASGI e download/preview autenticados.
- **Fase 3:** dois horários diários, **12h30 e 19h30**, de segunda a sábado, em `America/Sao_Paulo`. `docs/examples/reels-schedule.example.json` é apenas contrato futuro desativado. A rotina atual de imagens tem uma ocorrência por dia; não se deve reutilizar sua chave única por data para duas publicações de Reels. Serão necessários slots por data, horário, modo e conta, aprovação explícita e verificação da documentação oficial vigente da Meta antes de implementar o envio de vídeo.
- **Fase 4:** importar cenas cinematográficas e um manifesto de planos exportados do Roblox Studio em plataforma suportada, mantendo referências aos arquivos reais e seus intervalos. Nenhuma cena que ainda não foi gravada será inventada pelo pipeline. **Não se pressupõe Roblox Studio nativo no Ubuntu.** O Ubuntu executa este módulo de edição sobre arquivos já capturados ou exportados.

Nenhuma configuração de credencial é alterada pelo Estúdio. Não crie uma chamada Meta de Reels aproveitando apenas os parâmetros de imagem existentes. A compatibilidade de arquivo verificada pelo FFmpeg não equivale à aprovação de publicação pela Meta.
