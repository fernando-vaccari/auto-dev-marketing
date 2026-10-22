# Continuidade — Auto Posts completo

Solicitação de 22/10/2026. As Fases 1/2 foram preservadas. Não foram alterados .env, credenciais existentes ou arquivos pessoais. Nenhuma publicação real foi autorizada/executada nesta tarefa.

## Implementação entregue

- Agendamentos persistentes com slots por data/hora/índice, dias/quantidade/origem, roteiros novos opcionais, política manual/aprovação/automática, pausa/edição/exclusão/execução e recuperação.
- OBS websocket oficial com autenticação, consulta de capacidades (SetRecordDirectory requer 5.3+), captura assistida e importação privada, inclusive remux MKV com limpeza do temporário.
- Pacote Luau com câmeras, marcadores, foco/FOV/duração, restauração da interface e oito exemplos configuráveis sem mapa fictício.
- Kokoro-82M ONNX pt-BR em CPU, licenças documentadas, pesos externos com SHA-256, prévia, velocidade/volume seguros e ajuste de roteiro por síntese real medida.
- Oito presets cinematográficos, correção leve de cor, dissolve/fade, fundo desfocado, títulos/legendas animados, música com ducking e efeitos próprios.
- Análise amostrada de movimento/nitidez/exposição/variedade, histórico de intervalos e revisão de cortes, sem alegar compreensão semântica.
- API oficial Meta de Reels por sessão resumível e upload local, processamento, aprovação, simulação, histórico e bloqueio de duplicação/ambiguidade, com autorização revalidada antes da publicação.
- Painel em português com resumo, criação, trailers, biblioteca, voz, captura, automações, Instagram e configurações; limites persistentes e limpeza segura.
- Instalador, comandos iniciar/testar/diagnosticar, CI ampliada, documentação e ZIP somente de código.

## Evidências e pendências

[Relatório detalhado](validacao-sistema-completo.md): suíte de 76 testes; suíte Ubuntu 24.04 com 75 testes e rodada posterior de 24 integrações/segurança, sem rede e com limite de 2 GiB; três scripts de navegador; fontes Luau compilados. Consultar o relatório para distinguir cada execução.

Pendentes de validação real: Roblox Studio com os marcadores do jogo, OBS gravando gameplay verdadeiro, conta/aplicativo/token/permissões Meta e envio explicitamente autorizado. Não tratar fixtures RGB, simulador websocket ou MockTransport como validação real. Não habilitar publicação real ou clonar voz em futuras tarefas de teste.

[Guia do usuário](auto-posts-completo.md). A execução pode ser continuada dessas pendências externas sem refazer o projeto. Os arquivos de modelos permanecem fora do Git. O draft de instalação/startup do ambiente foi atualizado; salvar o draft não publica snapshot nem implanta o aplicativo.
