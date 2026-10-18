# Validação executada

Entrega da Auto Posts em 18 de outubro de 2026. Ambiente Linux x86_64, Python 3.12.14, Node.js 24.19.0.

| Verificação | Resultado observado |
| --- | --- |
| Instalação com versões fixadas | Concluída; repetição idempotente, `pip check` sem dependências quebradas |
| Testes funcionais e de integração | **21 executados, 21 aprovados**, nenhum pulado; bancos temporários e HTTP simulado |
| Scheduler real em background | Executou ocorrência aprovada e preservou estados |
| Rotina recorrente | Criou texto, JPEG e simulou envio; uma execução por dia, revogação ao editar marca, erros sem repetição |
| Navegador Chromium | Criação, edição, aprovação, agendamento, cancelamento, simulação e ativação/desativação da rotina aprovados |
| Layout | Seis telas verificadas no desktop e em 390 px; sem transbordamento horizontal e sem erros JavaScript |
| Sintaxe de JavaScript | Ambos os scripts passaram em `node --check` |
| Docker | Imagem construída e executada como usuário 10001; login, geração de JPEG e simulação funcionaram |
| Persistência em container | Conteúdo simulado continuou disponível após reiniciar o container com volume |
| Deploy | Compose interpretado; Caddyfile validado pelo Caddy |
| Instância de desenvolvimento | `/health` respondeu `status: ok`; três rascunhos presentes e rotina desativada |

O build Docker dentro desta nuvem precisou usar o proxy existente com resolução de seu hostname e a CA pública do ambiente montada como segredo de build `pip_ca`. Nenhuma verificação TLS ou de checksum foi desativada. Essa adaptação não incorpora credenciais nem a CA à imagem final. Em hospedagem comum, o Dockerfile usa as CAs padrão do sistema.

As capturas `screenshots/desktop.png` e `screenshots/mobile.png` mostram os rascunhos de demonstração, sem publicação real.

## Não executado ou ainda pendente

- Criação de conta/VM na Oracle, DNS DuckDNS e emissão de certificado para um domínio real.
- Configuração de credenciais Meta, validação das permissões efetivas e envio real à conta Instagram.
- Chamadas reais de IA; os testes desse cliente usam respostas simuladas. O fluxo gratuito não usa IA externa.
- Execução do workflow no GitHub Actions; o resultado dos testes locais não comprova o resultado de uma execução remota.
- Publicação do snapshot do ambiente pela plataforma ou restauração em uma nova tarefa.

A aprovação dos testes demonstra a aplicação em demonstração e o comportamento esperado com a API simulada. Não comprova a conectividade, as permissões, as cotas ou a publicação de uma conta Meta real. O guia `cloud-free.md` explica as etapas externas restantes.
