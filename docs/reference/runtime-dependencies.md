# Runtime dependencies

Este arquivo e a fonte canonica para banco, cache, realtime e limites de
ambiente do Django Shopman.

## Decisao

Sim: **vamos usar Redis**.

Contrato atual:

- **Desenvolvimento canonico**: PostgreSQL 16 + Redis 7 via `docker-compose.yml`
  e `make up`.
- **Staging/producao**: PostgreSQL 16+ e Redis 7+ sao obrigatorios.
- **SQLite/LocMem**: fallback local para scripts, exploracao rapida e ambientes
  sem Docker. Nao serve como evidencia de release.
- **Celery/Django Tasks**: nao fazem parte do contrato atual. Directives rodam
  pelo command `process_directives`; se uma fila externa entrar depois, sera
  uma decisao explicita. No bump para Django 6, avaliar o framework nativo de
  Tasks antes de escolher Celery, lembrando que Django Tasks nao fornece worker
  de execucao por si so.
- **Django 6**: manter o runtime alinhado com APIs nativas do Django quando
  existirem. Redis usa `django.core.cache.backends.redis.RedisCache`; nao ha
  dependencia de pacote externo para cache Redis. `django-ratelimit 4.1` ainda emite um warning de
  allowlist para esse backend, silenciado no settings depois do check proprio
  `SHOPMAN_E006`.

## PostgreSQL

PostgreSQL e necessario para o contrato de comercio real porque os caminhos
criticos dependem de locking transacional:

- estoque: holds, deduct, release e prevencao de oversell;
- pagamento: capture/refund com `select_for_update`;
- producao: work orders e compromissos;
- checkout: idempotencia e concorrencia entre sessoes.
- webhooks: replay guard duravel via `orderman.IdempotencyKey` e unicidade
  `channel_ref + external_ref` para pedidos de marketplace.

SQLite continua permitido para desenvolvimento leve, mas qualquer teste marcado
como concorrente pode ser pulado nesse modo. Um release nao pode usar uma rodada
SQLite como prova de robustez operacional.

Variavel:

```env
DATABASE_URL=postgres://shopman:shopman@localhost:5432/shopman
```

## Redis

Redis e o cache compartilhado do Shopman. Ele e usado para:

- `django-ratelimit` em login, OTP, checkout, carrinho, CEP e APIs publicas;
- caches operacionais curtos, como disponibilidade, geocode, shop singleton e
  rules engine;
- token EFI em cache com TTL;
- health/readiness de cache em ambiente com `REDIS_URL`;
- fanout SSE multi-worker do `django-eventstream`.

Quando `REDIS_URL` esta definido, `config/settings.py` configura:

- `CACHES["default"]` com `django.core.cache.backends.redis.RedisCache`;
- `EVENTSTREAM_REDIS` derivado da mesma URL, para que `send_event` alcance
  listeners conectados a qualquer worker.

`django-eventstream` usa `shopman.shop.eventstream.ShopmanChannelManager`:

- `stock-*` e publico e contem apenas disponibilidade por canal;
- `order-*` exige usuario ligado ao pedido ou staff;
- `backstage-*` exige staff.

Webhooks usam o banco, nao Redis, como camada canonica de idempotencia:

- Stripe: id do evento assinado, com hash do payload como fallback;
- EFI PIX: `endToEndId` como chave primaria de replay, com `txid` como fallback;
- iFood: `order_id`/`order_code` como chave de replay e `Order.external_ref`
  unico dentro do canal.

Variavel:

```env
REDIS_URL=redis://localhost:6379/0
```

`rediss://` e aceito para ambientes gerenciados com TLS.

## Gate runtime

O gate canônico de segurança/confiabilidade para ambiente real é:

```bash
make test-runtime
```

Para quem nao quer tocar em Docker localmente, o caminho canonico e deixar o
CI executar esse target e buildar a imagem de deploy. O workflow
`.github/workflows/runtime-gate.yml` sobe PostgreSQL 16 e Redis 7 como services
do GitHub Actions, roda a suite completa, builda `Dockerfile` e entao executa
`make test-runtime`. O desenvolvedor nao precisa rodar comandos Docker na
maquina local.

Esse target roda `scripts/check_runtime_gate.py` antes dos testes. Ele falha
fechado quando:

- `DATABASE_URL` nao esta definido ou nao aponta para PostgreSQL;
- o banco nao responde a uma query real;
- `REDIS_URL` nao esta definido;
- o cache default nao usa `django.core.cache.backends.redis.RedisCache`;
- o cache Redis nao completa set/get/delete;
- `EVENTSTREAM_REDIS` nao esta configurado para fanout SSE multi-worker.

Depois do preflight, `scripts/run_runtime_tests.py` executa o subconjunto de
stress de seguranca/confiabilidade e falha se qualquer teste for pulado. O
subconjunto cobre concorrencia de estoque, invariantes de quantidade, Payman,
Craftsman, checkout concorrente, rate limit em Redis, acesso a pedidos,
permissoes SSE, replay de webhooks, deploy checks e health/readiness.

Em 2026-05-05, o workflow `Runtime Gate` do PR #3 passou com:

- `Quality + deploy contract`: `ruff`, migrations check, `check --deploy` e
  suite completa;
- `Docker deploy image`: build real do `Dockerfile` no GitHub Actions;
- `PostgreSQL + Redis runtime stress gate`: `make test-runtime` em services
  reais do GitHub Actions.

Para stress HTTP complementar, com o servidor ja rodando e seed aplicado:

```bash
make load-test HOST=http://localhost:8000 USERS=100 RATE=10 TIME=60s
```

## Checks obrigatorios

`python manage.py check --deploy` deve falhar em producao quando:

- `DATABASE_URL` nao aponta para PostgreSQL;
- `REDIS_URL` nao configura cache Redis;
- adapters de pagamento reais nao estao configurados;
- tokens/segredos de webhooks estao ausentes;
- `DOORMAN_ACCESS_LINK_API_KEY` esta ausente fora de `DEBUG`;
- `DJANGO_SECRET_KEY`, hosts ou dominios estao inseguros.

SQLite em `DEBUG=true` segue como warning (`SHOPMAN_W001`) para manter ergonomia
local. SQLite fora de `DEBUG` e erro bloqueante (`SHOPMAN_E007`).

## Topologia minima

Para piloto real:

```text
reverse proxy/HTTPS
  -> Django ASGI/Daphne workers
       -> PostgreSQL
       -> Redis
       -> payment/notification gateways
```

Redis nao substitui o banco e nao e fila principal. Ele e infraestrutura
compartilhada para limites, cache e realtime.

## Deploy encapsulado

O repositorio inclui `Dockerfile` e compose profiles para app/worker/release,
mas o operador deve usar os wrappers:

```bash
make deploy-check
make deploy-up
make deploy-logs
make deploy-down
```

`make up` continua subindo apenas PostgreSQL + Redis para desenvolvimento. O
profile de app so entra pelos targets `deploy-*`.
