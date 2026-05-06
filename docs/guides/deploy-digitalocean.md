# Deploy DigitalOcean

Este guia é o caminho canônico para subir o Shopman na DigitalOcean sem o
operador chamar Docker manualmente. O alvo inicial é `shopman-staging` na App
Platform, com web ASGI, worker de diretivas, job de release, PostgreSQL e cache
Valkey compatível com Redis.

## Decisão

Use DigitalOcean App Platform para aplicação/worker/job e banco gerenciado pelo
próprio App Platform no staging técnico. Para piloto público ou produção,
converta/associe PostgreSQL e Valkey gerenciados com backup, janela de
manutenção e alertas.

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
- `postgres`: PostgreSQL 16 para staging;
- `cache`: Valkey, exposto ao Django via `REDIS_URL`;
- health checks em `/ready/` e liveness em `/health/`.

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
MANYCHAT_API_TOKEN=<sandbox/staging>
MANYCHAT_WEBHOOK_SECRET=<segredo HMAC webhook>
```

Para exercitar gateways sandbox reais, adicione também:

```env
EFI_CLIENT_ID=<sandbox>
EFI_CLIENT_SECRET=<sandbox>
EFI_CERTIFICATE_PATH=<path no container ou estratégia de secret file>
EFI_PIX_KEY=<sandbox>
STRIPE_PUBLISHABLE_KEY=<sandbox>
STRIPE_SECRET_KEY=<sandbox>
STRIPE_WEBHOOK_SECRET=<sandbox>
MANYCHAT_OTP_FLOW_NS=<flow namespace>
IFOOD_MERCHANT_ID=<sandbox/staging>
```

Sem os segredos obrigatórios, o release job falha fechado. Sem as credenciais
dos gateways, o `make smoke-gateways-sandbox` permanece bloqueado por
credenciais, como esperado.

## Primeiro Deploy

Quando houver token temporário da DigitalOcean, a execução operacional será:

```bash
doctl auth init
doctl apps create --spec .do/app.yaml
```

Se o app já existir:

```bash
doctl apps update <app-id> --spec .do/app.yaml
```

Depois do deploy:

```bash
make release-readiness-strict json=1
make smoke-gateways-sandbox json=1
```

O primeiro comando ainda só fica verde para release real depois de anexarmos
evidência manual/física de QA Omotenashi e pré-produção. O segundo só fica verde
quando EFI, Stripe, iFood e ManyChat estiverem com sandbox/staging reais.

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
