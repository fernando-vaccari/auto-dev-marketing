# Validação da Fase 2

Validação executada em 22/10/2026 sobre a extensão do Auto Posts existente. Nenhum acesso à Meta, publicação, chave de IA, modelo generativo ou gameplay real foi usado. As capturas são padrões sintéticos gerados com FFmpeg; a trilha é um tom de teste. Não representam cenas do futuro RPG.

| Verificação executada | Resultado |
| --- | --- |
| Suíte original antes da extensão | 41 testes passaram |
| Suíte completa final, Python 3.12 / FFmpeg 7.1.5 / eSpeak NG local | **49 testes passaram**, 62,578 s; sem skips/falhas |
| Mesma suíte no Ubuntu 24.04, Python 3.12 / FFmpeg 6.1.1 / eSpeak NG 1.51 | **49 testes passaram**, 60,860 s; sem skips/falhas |
| Contêiner Ubuntu de teste | Rede `none`, 4 CPUs, 2 GiB de RAM; exit 0, sem OOM |
| `scripts/reels_browser_smoke.py`, Chromium | Login, upload com progresso, vídeo selecionado, roteiro editado, trilha opcional, render real e reprodução 1080×1920/15 s passaram |
| Mesmo teste de navegador | MP4 baixado e integralmente decodificado pelo FFmpeg; roteiro/SRT exibidos; cancelamento, logout e layout de 390 px passaram; zero erros JS |
| `scripts/browser_smoke.py`, Chromium | Criação/edição/aprovação/agendamento/cancelamento/simulação/automação e as 6 telas anteriores desktop/mobile passaram; zero erros JS |
| Sintaxe JS e Python | `node --check` em app.js/login.js/reels.js e `compileall` passaram |
| Dependências Python | `pip check`: sem requisitos quebrados |
| Proxy existente | `caddy validate` aprovou o limite específico de upload, mantendo 9 MB nas outras rotas |
| Diff | `git diff --check` passou |

Os oito novos testes de contrato/integração cobrem todas as rotas sem sessão (401), Estúdio sem senha (503), proteção de origem (403), importação de vídeo e música com inspeção real, nomes/caminhos/controles Unicode inválidos, conteúdo falso, tamanhos declarados/excedidos/incompletos, cleanup, upload simultâneo e quota. Também verificam validação de planejamento, fila cheia, progresso/eventos, cancelamento idempotente, leitura de textos, download por caminhos fixos, HTTP Range e rejeição de symlink para fora da área privada.

O teste real do supervisor verifica um PID diferente do servidor, disponibilidade de `/health` durante o render, saída H.264/AAC vertical, decodificação completa, legendas e roteiro utilizados. Depois cancela um job pendente e outro em execução, confere que o worker terminou e que um processo independente permanece vivo. Outro teste cobre tempo limite, encerramento do servidor e recuperação de jobs interrompidos. As variáveis sensíveis do painel/Meta/IA não são repassadas ao filho.

Foi encontrada e corrigida durante a validação uma disputa entre o erro transitório do worker e a classificação de timeout/cancelamento do supervisor. Agora o supervisor controla o estado final das interrupções dos jobs web; o comportamento da CLI permanece coberto pelos testes anteriores.

O contêiner Ubuntu é um ambiente de teste reutilizado com dependências oficiais já instaladas e código final copiado para `/project`, não uma nova imagem de implantação do Compose. O teste de navegador foi executado no ambiente atual com Chromium instalado. A CI foi ampliada para executar ambos os scripts no Ubuntu 24.04; a execução remota da CI depende do GitHub e não é considerada comprovada por estes resultados locais.

Não foram comprovados: desempenho no Ryzen 7 5700U físico, voz de um modelo Piper real, compatibilidade com todo codec/arquivo fornecido por terceiros, garantia rígida de quota/RAM, publicação ou aprovação do arquivo pela Meta. O padrão de voz testado é eSpeak NG em pt-BR. Não há exclusão pelo painel, retry automático nem retomada de render parcial. A biblioteca e o renderizador da Fase 1 permanecem reutilizados; fases 3 e 4 não foram implementadas.

[Instalação, uso pelo navegador e limites configuráveis](reels-web.md).
