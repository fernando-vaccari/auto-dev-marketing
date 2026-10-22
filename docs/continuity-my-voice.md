# Continuidade — Minha Voz

Extensão isolada sobre o sistema completo em `c49baeb`. Não modificar Instagram, OBS, agendamentos, seleção de cenas ou autenticação para continuar esta tarefa.

Implementados: perfis privados com consentimento, upload/gravação pelo navegador, validação bounded de áudio, CRUD, player privado, adaptador OpenVoice V2 + Kokoro pt-BR, subprocesso CPU em `.venv-voiceclone`, integração na fila/prévias/render existentes, cancelamento, exclusão de derivados, seleção padrão aprovada, diagnóstico, instalador e documentação. Código upstream fixado em `74a1d147b17a8c3092dd5430504bd83ef6c7eb23`; licença MIT declarada para código e pesos. Voz-base existente Kokoro, não MeloTTS sem português.

Suíte: 88 testes, 87 passaram e 1 ignorado. Navegador Minha Voz, painel original e Fase 2 passaram. Ambiente isolado CPU instalado/importado, sem alterar `.venv` principal.

Bloqueio: download oficial de pesos OpenVoice negado com 403 pelo proxy. Não há clonagem neural real validada; não há benchmark de latência/RAM, tampouco comprovação de semelhança. Não substituir isso por mocks nem afirmar conclusão plena.

Próximo passo independente do código: obter `checkpoints_v2_0417.zip` da URL oficial em rede autorizada, executar instalador com `--checkpoint-archive`, diagnóstico e teste com `VOICE_CLONE_REQUIRE_REAL=1`, depois avaliar referência própria autorizada no navegador. Não publicar ou enviar áudio para serviços externos. [Guia](voice-cloning.md) e [evidências](voice-cloning-validation.md).
