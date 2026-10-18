# Implantar Auto Posts sem mensalidade

Arquitetura: **VM Oracle Cloud Always Free + Docker Compose + DuckDNS + Caddy**. O app utiliza templates locais para texto e JPEG; nenhuma chave de IA é necessária. O banco e as imagens ficam no volume persistente do Docker.

Este roteiro não cria uma conta, não contrata recursos e não garante disponibilidade de uma oferta gratuita. Use somente recursos identificados como **Always Free** e verifique o resumo de custos antes de concluir. Cadastro pode exigir cartão para verificação. A Oracle pode limitar capacidade e recuperar instâncias ociosas. Não há garantia de execução ininterrupta em uma oferta gratuita.

Referências oficiais: [Oracle Free Tier](https://www.oracle.com/cloud/free/) · [Recursos Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm) · [DuckDNS](https://www.duckdns.org/) · [Docker no Ubuntu](https://docs.docker.com/engine/install/ubuntu/) · [Caddy HTTPS](https://caddyserver.com/docs/automatic-https).

## 1. Conta e servidor

Crie sua conta na Oracle e selecione uma VM Ubuntu LTS elegível para Always Free, com volume e rede dentro das cotas gratuitas. Use uma chave SSH própria. Não habilite upgrade pago. Guarde a chave no seu computador; não a envie pelo chat nem a coloque no repositório.

Anote o IPv4 público do servidor. Na lista de segurança/NSG da rede Oracle, permita TCP 80 e 443 para o serviço web. Restrinja TCP 22 ao seu IP sempre que possível. Não exponha a porta 8000 ou portas de banco. Ajuste também o firewall do sistema, se estiver ativo, preservando o acesso SSH.

## 2. Endereço gratuito

No DuckDNS, crie um subdomínio gratuito e aponte-o para o IPv4 da VM. Você não precisa comprar domínio. Se o IP da VM mudar, atualize o registro antes de continuar os envios. O token DuckDNS deve permanecer privado; o app não precisa dele.

## 3. Transferir os arquivos

Use o arquivo `auto-posts.zip` disponível na raiz do repositório, baixe pelo botão **Code → Download ZIP** ou clone `fernando-vaccari/auto-dev-marketing`. Depois, envie os arquivos ao servidor por SCP/SFTP.

Extraia o pacote e entre na pasta que contém `compose.yaml`. Em Ubuntu, prepare o Docker pela documentação oficial. Outra opção é usar os pacotes da distribuição, quando disponíveis:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 unzip
sudo systemctl enable --now docker
```

Para transferir um ZIP do seu computador, use `scp -i /caminho/da/sua-chave auto-posts.zip ubuntu@IP_DA_VM:~/` e depois `unzip auto-posts.zip` e `cd auto-posts`. Substitua os marcadores pelos dados reais. A validação desta tarefa usa Linux x86_64; outras arquiteturas exigem verificar a disponibilidade das dependências.

## 4. Iniciar em demonstração

Crie um `.env` privado no diretório do projeto:

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Preencha `APP_DOMAIN` com o subdomínio DuckDNS e `APP_PASSWORD` com uma senha própria de pelo menos 12 caracteres. Mantenha `APP_MODE=demo` e `AI_API_KEY` vazia. O Compose usa `APP_DOMAIN` para configurar `PUBLIC_BASE_URL` automaticamente.

```bash
sudo docker compose up -d --build
sudo docker compose ps
```

O Caddy solicita o certificado HTTPS automaticamente quando DNS e portas estão corretos. Acesse seu subdomínio pelo navegador e entre com a senha configurada. Em **Minha marca**, confira **Auto Posts**, o público de marketing digital e a assinatura **Fernando Vaccari Pickhardt--Dev--Web**.

Crie um rascunho, revise, aprove e simule. Ative uma rotina em demonstração para conferir o comportamento. Nenhuma dessas ações publica na conta real.

## 5. Conectar o Instagram

Prepare uma conta profissional vinculada a uma Página e um app Meta com as permissões oficiais. O README detalha o fluxo de Facebook Login e a obtenção do ID. Insira `META_ACCESS_TOKEN` e `INSTAGRAM_ACCOUNT_ID` no `.env` privado, altere `APP_MODE=live` e recrie o serviço:

```bash
sudo docker compose up -d
```

**Nunca envie tokens ou senhas pelo chat.** Na tela **Integração**, verifique a conta conectada. Faça um primeiro envio aprovado e confira a publicação no Instagram. Depois, autorize novamente os agendamentos e a rotina para esse modo e essa conta. A validação real só termina após essa conferência.

O token Meta é usado apenas no servidor; não aparece nas respostas de configuração do painel. As imagens JPEG são públicas para a Meta, com nomes aleatórios e sem listagem. Conteúdos que não devem ficar públicos não devem ser enviados a este fluxo.

## 6. Manter os dados

O volume `app_data` conserva banco, imagens e chave de sessão ao recriar os containers. Não use `docker compose down -v`, que apaga volumes. Faça backups para um local sob seu controle. Para um backup consistente, pare o serviço de aplicação durante a cópia ou use o mecanismo de backup do SQLite.

Confira periodicamente o estado da VM, a elegibilidade gratuita, DNS, validade do token e histórico de erros. Uma VM parada não publica. Na volta, os posts agendados vencidos são processados; a rotina recorrente recupera apenas a ocorrência do dia atual.

## O que permanece sob sua responsabilidade

Criar as contas Oracle, DuckDNS e Meta, validar eventual cartão, selecionar recursos gratuitos disponíveis, configurar DNS/rede e fornecer o acesso à conta Instagram. A implantação externa e a publicação real não são comprovadas pelos testes locais. Se a Oracle não disponibilizar capacidade gratuita, não migre para um plano pago sem decidir isso conscientemente; mantenha o projeto em demonstração enquanto escolhe outra hospedagem compatível.
