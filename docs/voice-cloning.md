# Minha Voz — clonagem local opcional

Esta extensão altera apenas a opção de narração. Dora/Kokoro, Piper, eSpeak, renderizador, autenticação, arquivos de gameplay, captura, Instagram e regras existentes continuam disponíveis. Nenhuma gravação pessoal ou modelo é incluído no Git. Não há API paga nem clonagem via serviço externo.

**Estado da entrega:** cadastro, gravação de navegador, validação, privacidade e integração estão implementados. **A conversão neural real está PENDENTE DE VALIDAÇÃO REAL**, porque o acesso aos pesos oficiais OpenVoice V2 foi recusado pelo proxy deste ambiente (403). Não confunda o teste do render com conversor simulado com prova de clonagem. Não houve medição de tempo ou avaliação de semelhança com um modelo carregado.

## Modelo, idioma e licenças

Motor escolhido para integração: **OpenVoice V2, conversor de timbre, sobre a voz-base Kokoro Dora pt-BR**. Não usamos MeloTTS como voz-base: a lista nativa do V2 tem inglês, espanhol, francês, chinês, japonês e coreano, sem português. O projeto documenta conversão entre idiomas, incluindo idiomas não vistos; isso permite avaliar a conversão sobre áudio pt-BR já sintetizado, mas não comprova a qualidade desta combinação sem ouvir uma conversão real.

A base Kokoro já existente sintetiza de fato português brasileiro; OpenVoice converte esse áudio usando a referência. A referência não é transcrita, não é necessária gravação de cada roteiro e não existe treinamento demorado. Pronúncia, ritmo e pausas vêm sobretudo de Dora; a conversão busca aproximar o timbre, não promete reprodução perfeita da voz, sotaque ou emoção. O usuário precisa ouvir a prévia antes de adotar o perfil.

Fontes verificadas em 22/10/2026:

- [README oficial OpenVoice](https://github.com/myshell-ai/OpenVoice/blob/74a1d147b17a8c3092dd5430504bd83ef6c7eb23/README.md): V1 e V2 sob MIT, inclusive uso comercial, e idiomas nativos.
- [Uso oficial e checkpoint V2](https://github.com/myshell-ai/OpenVoice/blob/74a1d147b17a8c3092dd5430504bd83ef6c7eb23/docs/USAGE.md).
- [Código do conversor](https://github.com/myshell-ai/OpenVoice/blob/74a1d147b17a8c3092dd5430504bd83ef6c7eb23/openvoice/api.py): `device='cpu'`, extração de referência e conversão.
- [MIT OpenVoice incluída](licenses/OpenVoice-MIT.txt). Pesos V2 são declarados MIT pelo autor; a descarga bloqueada não foi inspecionada localmente.
- Base Kokoro: pesos Apache 2.0, integração ONNX MIT. [Licenças e documentação anteriores](auto-posts-completo.md#voz-neural-escolhida-e-licenças). PyTorch usa BSD; dependências auxiliares mantêm seus termos próprios. Não redistribuímos esses binários.

Não foram escolhidos XTTS (licença dos pesos exige análise distinta do uso comercial) nem uma voz-base sem pt-BR apenas para obter uma demonstração. OpenVoice + Kokoro é uma implementação candidata testável; a naturalidade final permanece pendente. Use somente sua voz ou referência fornecida com autorização explícita para este uso.

## Instalar apenas o motor de clonagem

O ambiente principal encontrado nesta tarefa foi **Python 3.12.14**, não 3.14. O instalador preserva a versão principal e `.venv`, `.env`, bancos, vídeos e credenciais. O motor tem **`.venv-voiceclone` separado**, Python 3.10–3.12, Torch 2.5.1 **CPU**, NumPy 1.26.4 e Librosa 0.10.2.post1. Não instala CUDA, ASR, Gradio, OpenAI ou um servidor público. Dependências antigas completas do OpenVoice não são instaladas no FastAPI.

No Ubuntu 24.04, Python 3.12 e seu módulo venv devem estar disponíveis. Se necessário, instale `python3.12-venv` pelo gerenciador do sistema. FFmpeg e a voz Kokoro do Auto Posts devem estar preparados.

```bash
cd auto-dev-marketing
bash scripts/install-voice-cloning.sh
```

Para selecionar outro Python compatível já instalado, sem alterar o Python principal:

```bash
VOICE_CLONE_PYTHON=python3.11 bash scripts/install-voice-cloning.sh
```

O script instala somente o ambiente isolado, fixa a revisão upstream e recusa substituir um checkout modificado ou modelos diferentes. Internet é necessária apenas na instalação. A aplicação continua funcionando sem esse motor; o painel explica que a clonagem está indisponível enquanto os pesos faltarem.

URL de pesos usada pelo instalador, conforme documentação oficial:

```text
https://myshell-public-repo-host.s3.amazonaws.com/openvoice/checkpoints_v2_0417.zip
```

Se a URL não for acessível, obtenha **esse ZIP oficial**, conforme as regras de acesso da sua rede, e informe o arquivo local:

```bash
bash scripts/install-voice-cloning.sh --checkpoint-archive /caminho/checkpoints_v2_0417.zip
```

Não use checkpoints de desconhecidos. O instalador lê somente dois membros esperados do ZIP, sem extrair caminhos arbitrários: `converter/config.json` e `converter/checkpoint.pth`. Registra SHA-256 do ZIP e de cada arquivo no manifesto privado. Os hashes são conferidos em cada conversão. **O hash inicial é registrado após o download por TLS; não é uma assinatura nem uma verificação independente contra hash publicado pelo autor.** O carregamento usa `torch.load(weights_only=True)`, sem aceitar objetos Python arbitrários de pickle.

Preparar somente código/dependências, sem habilitar o recurso:

```bash
bash scripts/install-voice-cloning.sh --runtime-only
```

Nenhuma instalação baixa modelos durante um render. A integração não usa o construtor upstream que baixa `wavmark`: inicializa explicitamente o conversor sem esse componente, sem alterar a fonte upstream. Não implementa marca d'água acústica; o histórico identifica o motor usado.

## Diagnosticar e iniciar

```bash
.venv/bin/python scripts/diagnose_voice_cloning.py
bash scripts/auto-posts iniciar
```

O diagnóstico informa Python principal/isolado, CPU, memória disponível, importação Torch/OpenVoice, ausência de CUDA, arquivos e integridade dos modelos. Sai com código 2 quando o motor não está pronto. Não lê nem transmite as amostras. Se sua instalação usa outro executável Python principal, use-o no diagnóstico sem substituir `.venv`.

Painel local: **http://127.0.0.1:8000**. Preserve o carregamento do seu `.env`/`APP_PASSWORD` conforme o [guia do sistema](auto-posts-completo.md). Microfone requer contexto seguro: localhost no mesmo computador ou HTTPS, além de permissão explícita no navegador.

## Cadastrar e usar a voz

1. Entre no painel e abra **Estúdio de Reels → Minha Voz**.
2. Confirme que é sua voz ou que tem autorização. Dê um nome ao perfil.
3. Grave pelo microfone e encerre a gravação, ou importe WAV/MP3. Há reprodução antes de salvar. O navegador grava WebM/Opus, Ogg/Opus ou áudio MP4 conforme suporte.
4. Use de **6 a 60 segundos**, até **20 MiB**, preferencialmente 15–30 segundos de fala limpa. Evite música, eco e outras pessoas falando. Clique **Validar e salvar amostra**. A barra informa envio; a validação acontece depois.
5. Escolha o perfil, digite a frase e clique **Gerar prévia com Minha Voz**. O botão permanece indisponível sem o motor instalado. A síntese entra na mesma fila sequencial dos Reels e pode ser cancelada.
6. Ouça, marque a aprovação e clique **Usar Minha Voz nos próximos Reels**. Essa escolha é persistente para novas criações no navegador. **Não muda jobs, regras ou agendamentos anteriores.** Há opção de voltar à voz padrão.
7. Em **Criar Reel**, importe/selecione gameplay real, confira que o motor é **Minha Voz**, ajuste roteiro/duração e gere normalmente. O perfil é escolhido em Minha Voz. O render usa o mesmo processamento de duração real, normalização, legendas e montagem existente. Não corta palavras nem acelera automaticamente a fala.

Para utilizar uma voz comum novamente, selecione Dora/Piper/eSpeak no formulário. Se Minha Voz falhar, o job mostra erro; não troca silenciosamente a voz por Dora. A prévia aprova o perfil e sua qualidade; o Reel realiza uma **nova síntese do seu roteiro**, não reutiliza o áudio da frase de teste.

A validação recusa vídeo, várias faixas, conteúdo inválido, excesso de tamanho, duração insuficiente/excessiva e silêncio/nível insuficiente. Decodifica no máximo 61 segundos para medir a duração, inclusive em WebM sem duração no cabeçalho. Normaliza para WAV mono 24 kHz e remove silêncio das bordas. Música/ruído/identidade do falante não são reconhecidos semanticamente; os avisos não substituem ouvir a referência.

## Privacidade, exclusão e limites

- Amostra original, WAV normalizado e metadados: `DATA_DIR/reels/voice-cloning/<id>/`, diretórios 0700 e arquivos 0600. São no máximo cinco perfis. O áudio original permanece local.
- Todas as rotas estão sob `/api/reels/my-voice`, com a autenticação e proteção de origem existentes. Arquivos são buscados por ID validado, nunca por caminho enviado no navegador. Não há montagem pública desses diretórios.
- Modelos/código pesado: `.venv-voiceclone`, ignorado pelo Git. Amostras e estado também são ignorados mesmo em um `DATA_DIR` personalizado. O ZIP de distribuição contém apenas código/documentação.
- **Excluir perfil** remove referência, original e narrações intermediárias associadas, inclusive prévias. Bloqueia exclusão enquanto houver jobs na fila/em execução; cancele-os primeiro.
- MP4s prontos podem conter sua voz. São preservados por padrão; marque **excluir também os Reels prontos** para removê-los junto com o perfil. Gameplays importados e outros perfis permanecem intactos. Históricos registram a remoção; cópias que você já baixou/publicou não são apagadas remotamente.
- Uma síntese de clonagem por vez, limite de threads herdado do Estúdio (padrão 4), processos de prioridade reduzida na fila existente. Conversor é carregado por frase e liberado ao encerrar o subprocesso. Isso reduz retenção de RAM e pode aumentar bastante o tempo de geração.
- Processo isolado sem CUDA e sem conexão de rede via sockets Python, sem tokens/proxies/senhas herdados, limite de 8 GiB de espaço de endereçamento e 240 s por frase. Esses limites podem causar erro em vez de travar o sistema; não representam um benchmark de memória física.
- Cancelamento usa o grupo do job existente. O conversor permanece nesse grupo e recebe sinal se o pai morrer. Não encerra processos independentes.
- `voice-cloning-performance.jsonl` no diretório do job registra segundos reais de síntese, duração de áudio e threads quando há sucesso. Não há valor de desempenho real nesta entrega, pois faltam pesos. Falta de memória, timeout ou modelo inválido interrompem o job com erro.

Não houve teste físico no Acer/Ryzen/Vega. A importação CPU do motor foi testada em Python 3.12, com Torch sem CUDA. Nenhuma garantia de qualidade, latência, consumo de RAM ou compatibilidade de pesos é dada sem executar a prévia real nesse equipamento.

## Testes e solução de problemas

```bash
.venv/bin/python -m unittest tests.test_voice_cloning -v
.venv/bin/python -m unittest discover -v
# Com Playwright/Chromium de desenvolvimento:
.venv/bin/python scripts/my_voice_browser_smoke.py
# Exigir conversão REAL, falhando se os pesos estiverem ausentes:
VOICE_CLONE_REQUIRE_REAL=1 .venv/bin/python -m unittest tests.test_voice_cloning.VoiceCloningTests.test_real_conversion_when_official_weights_available -v
```

O teste real usa uma referência **sintética Dora**, sem voz de terceiros, para verificar processamento de uma frase nova com OpenVoice. Mesmo se passar, não mede semelhança com sua voz: isso exige sua referência autorizada e escuta. Sem pesos o teste fica explicitamente ignorado, ou falha se `VOICE_CLONE_REQUIRE_REAL=1`.

- **403 no modelo:** o ambiente não tem acesso à URL oficial; o restante do Auto Posts continua operante. Obtenha o ZIP oficial em rede autorizada ou mantenha Dora. Não há contorno automático de restrições.
- **Python 3.14:** não remova sua `.venv`; escolha Python 3.12/3.11 exclusivamente para o instalador isolado.
- **Microfone ausente:** confira localhost/HTTPS, permissão e dispositivo; WAV/MP3 permanece alternativa.
- **Silêncio ou voz baixa:** regrave sem música/ruído. Gravações curtas após remoção das bordas podem ser recusadas.
- **Memória/timeout:** feche programas, reduza o texto ou volte a Dora. Não são iniciadas várias conversões em paralelo.
- **Falha de importação/hash:** rode o diagnóstico; preserve arquivos existentes e confira o manifesto. O instalador não sobrescreve modelos divergentes ou checkout modificado.

Resultados executados desta mudança serão registrados em [validação de Minha Voz](voice-cloning-validation.md), distinguindo testes simulados e conversão real.
