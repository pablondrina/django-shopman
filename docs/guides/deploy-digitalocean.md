# Deploy DigitalOcean

Este guia é o caminho canônico para subir o Shopman na DigitalOcean sem o
operador chamar Docker manualmente. O alvo inicial é `shopman-staging` na App
Platform, com web ASGI, worker de diretivas, job de release, PostgreSQL e cache
Valkey compatível com Redis.

## Decisão

Use DigitalOcean App Platform para aplicação/worker/job e DigitalOcean Managed
Databases para PostgreSQL e Valkey. Valkey não deve ser tratado como banco
`dev` implícito no App Platform; o blueprint referencia clusters gerenciados
nomeados para manter staging alinhado ao contrato de produção.

Fontes oficiais usadas para este contrato:

- App spec YAML, Dockerfile, workers, jobs e bindable variables:
  <https://docs.digitalocean.com/products/app-platform/reference/app-spec/>
- Variáveis de ambiente e secrets:
  <https://docs.digitalocean.com/products/app-platform/how-to/use-environment-variables/>
- Bancos no App Platform:
  <https://docs.digitalocean.com/products/app-platform/how-to/manage-databases/>
- Valkey como substituto Redis-compatible do Managed Caching:
  <https://docs.digitalocean.com/products/databases/valkey/>

## Blueprint

O arquivo `.do/app.yaml` define:

- `web`: Daphne ASGI em `config.asgi:application`;
- `directive-worker`: `python manage.py process_directives --watch`;
- `release`: job `PRE_DEPLOY` com `check --deploy` e migrations;
- `postgres`: PostgreSQL 16 gerenciado (`shopman-staging-postgres`);
- `cache`: Valkey 8 gerenciado (`shopman-staging-cache`), exposto ao Django via `REDIS_URL`;
- instância Nelson ativa via `SHOPMAN_INSTANCE_APPS`, `SHOPMAN_CUSTOMER_STRATEGY_MODULES`
  e `SHOPMAN_INSTANCE_MODIFIERS`;
- health checks em `/ready/` e liveness em `/health/`.

O blueprint usa `git.repo_clone_url` público para dispensar autorização manual
da GitHub App da DigitalOcean no primeiro staging. Enquanto isso estiver assim,
redeploys devem ser acionados explicitamente com `doctl apps update --spec ...`
ou pelo painel. Para deploy automático por push, autorize a GitHub App da
DigitalOcean e troque os blocos `git` por `github`.

O `Dockerfile` já compila CSS e agora roda `collectstatic` no build. O runtime
serve `/static/` por WhiteNoise, então App Platform não precisa de volume
compartilhado entre release job e web para CSS/admin/assets.

## Segredos Obrigatórios

Antes do primeiro deploy com `DJANGO_DEBUG=false`, crie estas variáveis como
encrypted runtime variables no nível do app:

```env
DJANGO_SECRET_KEY=<segredo forte>
DOORMAN_ACCESS_LINK_API_KEY=<segredo forte>
EFI_WEBHOOK_TOKEN=<token webhook sandbox/produção>
IFOOD_WEBHOOK_TOKEN=<token webhook sandbox/produção>
MANYCHAT_WEBHOOK_SECRET=<segredo HMAC webhook>
```

O blueprint define `DOORMAN_MESSAGE_SENDER_CLASS=shopman.doorman.senders.EmailSender`
para permitir staging técnico sem token ManyChat real e falhar fechado no OTP por
telefone. Para piloto público, `MANYCHAT_API_TOKEN` é obrigatório: ele é diferente
de `MANYCHAT_WEBHOOK_SECRET` e ativa a cadeia WhatsApp-first (`ManyChat -> SMS ->
email`) usada pelo login do storefront.

Em planos PostgreSQL pequenos, mantenha:

```env
DATABASE_CONN_MAX_AGE=0
```

Isso fecha conexões ao fim de cada request e evita saturar o limite de conexões
do Managed PostgreSQL durante browser QA, SSE, health checks e jobs. Se o
ambiente crescer, reavalie com pool de conexões ou plano maior antes de subir
`CONN_MAX_AGE`.

Para exercitar gateways sandbox reais, adicione também:

```env
EFI_CLIENT_ID=<sandbox>
EFI_CLIENT_SECRET=<sandbox>
EFI_CERTIFICATE_PATH=<path no container ou estratégia de secret file>
EFI_PIX_KEY=<sandbox>
STRIPE_PUBLISHABLE_KEY=<sandbox>
STRIPE_SECRET_KEY=<sandbox>
STRIPE_WEBHOOK_SECRET=<sandbox>
MANYCHAT_API_TOKEN=<sandbox/staging>
MANYCHAT_SUBSCRIBER_RESOLVER=shopman.guestman.contrib.manychat.resolver.ManychatSubscriberResolver.resolve
IFOOD_MERCHANT_ID=<sandbox/staging>
```

`MANYCHAT_OTP_FLOW_NS` é opcional. Sem ele, o OTP usa
`/fb/sending/sendContent` para mensagem direta; com ele, usa
`/fb/sending/sendFlow` para disparar uma automação ManyChat. Para piloto real em
WhatsApp, valide no ManyChat se o contato estará dentro da janela de 24 horas; se
não estiver, use uma automação com template aprovado para mensagem fora da janela.

Sem os segredos obrigatórios, o release job falha fechado. Sem as credenciais
dos gateways, o `make smoke-gateways-sandbox` permanece bloqueado por
credenciais, como esperado.

## Primeiro Deploy

Quando houver token temporário da DigitalOcean, a execução operacional será:

```bash
doctl auth init --context shopman-staging
doctl auth switch --context shopman-staging
doctl projects create --name "Shopman Staging" --purpose "Web Application" --environment Staging
doctl databases create shopman-staging-postgres --engine pg --version 16 --region nyc3 --size db-s-1vcpu-1gb --num-nodes 1 --wait
doctl databases create shopman-staging-cache --engine valkey --version 8 --region nyc3 --size db-s-1vcpu-1gb --num-nodes 1 --wait
doctl databases db create <postgres-id> shopman
doctl databases user create <postgres-id> shopman
doctl apps spec validate .do/app.yaml
doctl apps create --spec .do/app.yaml --project-id <project-id> --wait
```

O usuário `shopman` precisa ter permissão de criação no schema `public` do banco
`shopman`; sem isso o release job passa em `check --deploy`, mas falha em
`migrate` com `permission denied for schema public`.

Se o app já existir:

```bash
doctl apps update <app-id> --spec .do/app.yaml --update-sources --wait
```

Depois do deploy:

```bash
make release-readiness-strict json=1
make smoke-gateways-sandbox json=1
```

O primeiro comando ainda só fica verde para release real depois de anexarmos
evidência manual/física de QA Omotenashi e pré-produção. O segundo só fica verde
quando EFI, Stripe, iFood e ManyChat estiverem com sandbox/staging reais.

## Bootstrap de Dados e Admin

Para staging técnico inicial, rode o seed Nelson uma única vez antes de qualquer
dado real existir. O seed cria um superuser técnico `admin`, mas fora de DEBUG
ele exige `ADMIN_PASSWORD` forte e falha fechado se a senha estiver ausente ou
óbvia.

Fluxo canônico:

```bash
ADMIN_PASSWORD=<senha-forte-temporaria> python manage.py seed --flush
SHOPMAN_ADMIN_PASSWORD=<senha-forte-do-dono> python manage.py bootstrap_admin \
  --username pablo \
  --email pablo@example.com \
  --deactivate-seed-admin
```

Depois que staging tiver dados de piloto, não use `seed --flush`; recriar o
dataset passa a ser uma operação destrutiva deliberada. Para DigitalOcean App
Platform, execute o bootstrap via console/job temporário e remova as senhas do
ambiente do app depois da execução.

Execução real de 2026-05-06:

- `bootstrap-staging` rodou como job `POST_DEPLOY`, executando `seed --flush`
  e `bootstrap_admin`;
- usuário `pablo` ficou como superuser nominal e `admin` técnico foi desativado;
- a senha de `pablo` foi guardada fora do repo em
  `~/.shopman/shopman-staging-admin-2026-05-06.txt`;
- a API recusou a remoção do componente temporário com `403`, então ele foi
  neutralizado para `python manage.py check --deploy`, sem envs secretas.
  Remova o componente no painel ou com um token que permita apagar componentes
  da App Platform.

## Domínio

Comece pela URL `.ondigitalocean.app`. Quando o staging estiver saudável,
adicione o domínio definitivo, por exemplo:

```text
staging.seudominio.com.br
```

Ao adicionar domínio próprio, confirme que:

- `DJANGO_ALLOWED_HOSTS` inclui o domínio;
- `CSRF_TRUSTED_ORIGINS` inclui `https://...`;
- `SHOPMAN_DOMAIN` e `WHATSAPP_STOREFRONT_URL` apontam para a URL pública;
- o domínio está como `PRIMARY` na App Platform.

## Media

Arquivos estáticos ficam resolvidos pelo build + WhiteNoise. Arquivos de mídia
enviados por usuários/admin ainda não devem depender do filesystem efêmero da
App Platform para piloto público. Para comércio real, a próxima decisão é:
DigitalOcean Spaces/S3-compatible storage ou outro storage persistente para
`MEDIA_ROOT`.

Até essa decisão, staging técnico deve usar apenas assets versionados/seedados
ou aceitar que uploads manuais sejam descartáveis.

## Critério de Pronto

Staging técnico está pronto quando:

1. App Platform deploya `web`, `directive-worker` e `release` sem erro.
2. `/health/` e `/ready/` respondem 200.
3. `make release-readiness` não reporta falhas locais.
4. `make release-readiness-strict` aponta somente bloqueios externos reais.

Piloto público só fica pronto quando:

1. Gateways sandbox/staging passam em `make smoke-gateways-sandbox`.
2. QA Omotenashi físico/staging está registrado.
3. Media persistente está decidido e configurado se houver upload real.
4. PostgreSQL e Valkey estão em plano gerenciado adequado para o risco do piloto.
