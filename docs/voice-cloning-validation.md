# Validação da extensão Minha Voz

Data: 22/10/2026. Referências usadas foram sintéticas, sem gravações pessoais do usuário ou de terceiros. Nenhum áudio foi enviado para serviços externos. Não houve publicação real nem alteração de credenciais.

| Verificação executada | Resultado |
| --- | --- |
| Suíte completa após a extensão | **88 testes, 87 passaram e 1 ignorado**, 293,632 s. Todos os 76 testes anteriores passaram. |
| Novos testes | 12: 11 passaram; conversão real ignorada pela ausência dos pesos oficiais. |
| Perfis/upload | Consentimento obrigatório, WAV/MP3 reais, formato, silêncio, duração, tamanho, limite de cinco perfis, originais/normalizados privados e exclusão. |
| Segurança | Autenticação/origem, ID validado, recusa de symlink, diretórios 0700, arquivos 0600, ausência de diretório público, metadados sem caminhos de máquina. |
| Jobs | Criação e cancelamento de prévia, exclusão bloqueada durante jobs, derivados removidos sem apagar outro perfil ou MP4 cuja remoção não foi solicitada. |
| Falhas do motor | Modelo ausente não cria job nem troca de voz silenciosamente; retorno de falta de memória, morte por sinal, erro de modelo e timeout tratados. Conversão simulada nesses testes. |
| Cancelamento de processo | Subprocesso local de teste encerrou com o grupo correspondente; processo independente preservado. Teste dirigido adicional passou em 3,263 s. |
| Render com opção Minha Voz | MP4 H.264/AAC e SRT com tempos medidos foram gerados usando **conversor substituído por fixture eSpeak**; comprova o encaixe no render, não a clonagem. |
| Navegador Minha Voz | Importação WAV, MediaRecorder com entrada de fala sintética, WebM real, consentimento, players privados, upload, dois perfis, exclusão, aprovação obrigatória, mobile e logout passaram. |
| Navegador legado | Criação, edição, aprovação, agendamento, cancelamento, simulação e seis telas desktop/mobile passaram novamente. |
| Navegador da Fase 2 | Upload/progresso, roteiro, música, render real, reprodução 1080×1920, download, SRT, cancelamento e mobile passaram novamente. |
| Navegador do Estúdio completo | Prévia Kokoro real, oito presets, análise, cortes, blur/dissolve, música/SFX, render, download, agendamento, aprovação/simulação e configurações passaram novamente; não é teste de clonagem. |
| Ambiente isolado | Instalado e importado: Python 3.12.14, Torch 2.5.1+cpu, CUDA ausente, OpenVoice na revisão fixada; `pip check` sem incompatibilidades. |
| Diagnóstico | Identificou corretamente dependências instaladas e pesos ausentes. |
| Sintaxe | Python `compileall`, JavaScript `node --check`, shell `bash -n` e `git diff --check` passaram. |

O teste do navegador encontrou e motivou a correção para WebM de MediaRecorder sem duração no cabeçalho: a duração é medida após decodificação limitada a 61 segundos. Uma fixture de tom estacionário também foi substituída por fala sintética no microfone de teste, pois o cancelamento de ruído do navegador pode suprimir tons; a validação de áudio silencioso continua coberta e não foi relaxada.

## Bloqueio externo e critério de conclusão

O servidor de pesos indicado na documentação oficial é:

`https://myshell-public-repo-host.s3.amazonaws.com/openvoice/checkpoints_v2_0417.zip`

O acesso foi recusado pelo proxy deste ambiente, **403 Forbidden**. A execução completa do instalador terminou com erro explícito ao baixar os pesos, depois de conferir o ambiente isolado; o modo `--runtime-only` terminou com sucesso. O código e a licença upstream puderam ser consultados; o checkout e as dependências CPU foram instalados. **Não há checkpoint local e não foi executada uma conversão neural real OpenVoice.**

Consequentemente, continuam **PENDENTES DE VALIDAÇÃO REAL**:

- Compatibilidade do checkpoint com esta combinação de dependências.
- Conversão Kokoro pt-BR → OpenVoice V2 com saída inteligível.
- Semelhança, naturalidade e pronúncia usando referência autorizada do usuário.
- Reprodução e render completo com essa conversão neural, sem substitutos de teste.
- Tempo de geração e pico de memória do modelo no Acer/Ryzen/12 GB.

Não foi medido tempo de clonagem real. Os 293,632 s são da suíte, não da síntese. O código registra duração/performance quando uma conversão real consegue terminar.

Após obter o ZIP oficial e instalar o motor, execute o teste que **falha**, em vez de ignorar, se o modelo faltar:

```bash
VOICE_CLONE_REQUIRE_REAL=1 .venv/bin/python -m unittest tests.test_voice_cloning.VoiceCloningTests.test_real_conversion_when_official_weights_available -v
```

O teste usa referência sintética autorizada e frase nova. Depois cadastre sua referência e ouça a prévia. Só então valide a qualidade e o Reel real. **O recurso não é declarado integralmente concluído enquanto esses critérios dependerem de um modelo não testado.**

[Instalação, operação, licenças e solução de problemas](voice-cloning.md).
