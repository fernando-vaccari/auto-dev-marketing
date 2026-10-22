# Validação e limites — sistema completo

Data: **22/10/2026**. Os arquivos de vídeo são fixtures locais sintéticas identificadas como testes, não cenas do futuro RPG. Nenhum token de produção foi configurado ou alterado, nenhum conteúdo foi publicado e nenhum serviço pago foi contratado.

## Evidências executadas

| Verificação | Resultado |
| --- | --- |
| Base anterior à extensão | 49 testes existentes preservados |
| Suíte completa ampliada, Python 3.12 / FFmpeg 7.1.5 | **76 testes passaram**, 217,436 s, sem falhas ou skips |
| Suíte no Ubuntu 24.04 / FFmpeg 6.1.1 / eSpeak 1.51 | **75 testes passaram**, 259,054 s, sem falhas ou skips |
| Atualizações finais no Ubuntu 24.04 | **24 testes de integração/segurança passaram**, 28,252 s; incluem o teste adicional MKV, voz neural longa, OBS 5.3, regras e autorização Meta |
| Recursos/rede no Ubuntu de teste | 4 CPUs, limite de 2 GiB de RAM, rede `none`; processo encerrou com sucesso, sem OOM |
| Oito presets novos | Todos renderizados em 1080×1920/30 fps com MP4 H.264/AAC; duração e decodificação integral verificadas |
| Voz neural | Kokoro ONNX real, Dora pt-BR; SHA-256 dos dois arquivos conferido |
| Roteiro longo de 15 s | Síntese real excedeu o limite, texto foi reduzido e ressintetizado; mais de uma tentativa, fala final até 14 s e nenhuma aceleração automática |
| OBS simulado | Websocket v5 local real no transporte, desafio de autenticação, requests correlacionados, seleção de fonte/cena, gravação simulada e importação de arquivo inspecionado com FFmpeg/ffprobe |
| Arquivo MKV | Remux por cópia de streams, importação MP4, original preservado e temporário removido |
| Meta simulada | Criação REELS/resumable, upload binário, processamento, publicação, ID, limite/credencial/permissão/timeout, erro ambíguo e prevenção de duplicação |
| Autorização Meta | Pausa/alteração de regra/configuração impede aproveitar autorização anterior; checagem adicional imediatamente antes do pedido de publicação |
| Navegador completo | Voz neural, preset, blur/dissolve, música/SFX, análise, cortes revisados, render, reprodução, download, regra desativada, execução/cancelamento, aprovação/simulação, limites, pacote Luau e limpeza passaram |
| Navegador da Fase 2 | Login/upload/progresso/seleção/roteiro/trilha/render/player/download/SRT/cancelamento/logout passaram |
| Navegador do painel original | Criação, edição, aprovação, agendamento, cancelamento, simulação, rotina de imagens e seis telas desktop/mobile passaram |
| Prévia privada de mídia | Cinco testes dirigidos finais passaram; vídeo por ID autenticado, resposta Range 206 e reprodução de trecho revisado no navegador |
| Responsividade | Oito seções do Estúdio verificadas em largura de 390 px, sem overflow horizontal ou erros JavaScript |
| Luau | Quatro fontes compilados com `luau-compile`; pacote XML reconstruído por script |
| Instalação | `bash scripts/auto-posts instalar` executado com sucesso e repetível neste ambiente usando ferramentas de sistema já disponíveis |
| Dependências/sintaxe | `pip check`, `compileall`, sintaxe shell e `node --check` passaram |

A rodada completa no Ubuntu precedeu o último teste de remux. Os testes dirigidos posteriores validaram o código atualizado de captura, voz, segurança, regras e Meta. A síntese neural e o fluxo de mídia funcionaram sem internet no contêiner. Isso não é um benchmark do notebook físico nem prova de captura de um jogo usando o hardware do usuário.

O instalador reconheceu o wrapper eSpeak oficial já preparado no ambiente de desenvolvimento, sem desativar TLS/checksums. No computador Ubuntu novo, o mesmo fluxo usa os pacotes oficiais via APT. O OBS real não está instalado neste ambiente; sua instalação administrativa e configuração gráfica permanecem ações no equipamento do usuário. A opção `--com-obs` foi documentada, mas não foi executada contra um desktop real aqui.

A CI foi ampliada para instalar os modelos verificados, exigir testes de mídia/voz e executar os três testes de navegador no Ubuntu 24.04. **A execução remota da CI não é comprovada por estes resultados locais.**

## Critérios de conclusão

| Requisito | Estado e evidência |
| --- | --- |
| Interface e importação | Implementadas e testadas em navegador, com autenticação |
| Biblioteca privada | Metadados, temas editáveis, múltipla seleção, trilhas e efeitos; acesso por ID |
| Narração neural pt-BR | Implementada com Kokoro CPU; voz Dora realmente sintetizada |
| Prévia e nova narração | Jobs separados, player de áudio e novos pedidos pela interface |
| Duração e sincronização | Medição de WAV, redução limitada do texto, SRT/ASS derivados dos tempos reais |
| Presets/legendas | Oito presets renderizados; animação por frase e destaque visual, sem falso alinhamento por palavra |
| Música com ducking | Sidechain, fades, normalização/volume e limiter testados em renders |
| MP4 1080×1920 | Codecs, fps, duração e integridade conferidos |
| Câmeras Luau | Pacote, marcadores e oito exemplos implementados; **PENDENTE DE VALIDAÇÃO REAL NO STUDIO** |
| OBS/importação automática | Protocolo e fluxo implementados/testados por simulador com arquivo real; **PENDENTE DE VALIDAÇÃO REAL COM OBS E GAMEPLAY** |
| Agendamentos/aprovação | SQLite, duas horas, dias/quantidade/origem/política, CRUD, idempotência, pausa e reinício testados |
| Integração Meta | Fluxo oficial e erros testados com MockTransport; **PENDENTE DE VALIDAÇÃO REAL EM CONTA COMPATÍVEL** |
| Histórico e falhas | Jobs, eventos, slots, capturas e publicações; estados ambíguos bloqueiam reenvio |
| Instalação/documentação | Scripts e guias presentes, cofre criptografado, ferramentas/modelos versionados por referência/hash |
| Recursos anteriores | 49 testes anteriores preservados e executados na suíte ampliada |

Não há uma declaração de “100% validado em produção”: os estados externos acima continuam pendentes.

## Segurança exercitada

- Rotas do Estúdio sem sessão retornam 401; sem senha configurada o Estúdio retorna 503. Origens indevidas são recusadas.
- Upload testa nomes/caminhos/controles inválidos, conteúdo falso, tamanhos inconsistentes, quota e concorrência, com limpeza dos temporários.
- Preview, texto, pacote e MP4 exigem sessão; download usa caminho fixo e recusa symlink para fora da área privada. Range permite seek.
- Credenciais são somente de escrita via API, ficam criptografadas em arquivo 0600 com chave 0600 e não entram no SQLite ou respostas GET.
- Processo de render recebe ambiente reduzido, sem token Meta, senha do painel ou chave de IA. Cancelamento encerra somente seu grupo e preserva um processo independente usado como sentinela no teste.
- OBS não interrompe gravação alheia. Captura e render compartilham uma trava. Instância reiniciada não usa registros antigos para enviar StopRecord.
- Limpeza preserva originais, entregáveis e textos. Configuração de limites não consegue modificar senha/autenticação.
- Publicação em demonstração não cria cliente externo. Timeout ambíguo ou reinício durante envio exigem conferência manual, sem retry automático.

## Dependências e limitações externas

1. **Roblox Studio:** instalar em plataforma oficialmente suportada, inserir pacote, associar marcadores/objetos reais e validar a restauração de câmera/UI dentro do jogo. Compilação Luau não substitui esse teste.
2. **Captura:** instalar OBS compatível com obs-websocket 5.3+ e preparar uma fonte de vídeo real. O jogo aberto e a sequência pronta são confirmações humanas; não há disparo remoto Luau→localhost comprovado. No Ubuntu, a disponibilidade de uma fonte que mostre o ambiente Roblox precisa ser preparada e testada pelo usuário.
3. **Meta:** conta profissional, aplicativo compatível com Facebook Login for Business, token, permissões/revisão e autorização de um envio real. Não usamos conta de produção nesta tarefa. Leitura de conta não valida publicação.
4. **Modelo/voz:** Dora foi a voz efetivamente usada nos testes de síntese. Alex e Santa são seleções do pacote upstream e devem ser ouvidas pelo usuário. Piper permanece opcional, sem voz/licença individual recomendada ou teste de síntese real nesta entrega.
5. **Qualidade visual:** os testes sintéticos verificam execução técnica dos efeitos, não o resultado artístico de cenas reais. Associações semânticas vêm das tags declaradas; o seletor usa heurísticas visuais.
6. **Operação:** não há OAuth self-service, renovação automática de token, retomada byte a byte de upload, alinhamento por palavra, retomada de render parcial ou disparo automático de novas câmeras. Históricos exibem até 100 registros recentes; limpeza de intermediários é manual e os originais não são apagados.
7. **Hardware:** não houve benchmark físico do Acer/Ryzen/Vega. Não há quota rígida de RAM/filesystem, apesar dos limites de threads, fila, arquivo, tempo e espaço monitorado.

[Guia completo de instalação/operação](auto-posts-completo.md) · [Referências oficiais e licenças](referencias-tecnicas.md).
