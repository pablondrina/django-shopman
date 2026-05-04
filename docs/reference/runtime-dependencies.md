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

SQLite continua permitido para desenvolvimento leve, mas qualquer teste marcado
como concorrente pode ser pulado nesse modo. Um release nao pode usar uma rodada
SQLite como prova de robustez operacional.

Variavel:

```env
DATABASE_URL=postgres://shopman:shopman@localhost:5432/shopman
```

## Redis

Redis e o cache compartilhado do Shopman. Ele e usado para:

- `django-ratelimit` em login, OTP, checkout e APIs publicas;
- caches operacionais curtos, como disponibilidade, geocode, shop singleton e
  rules engine;
- token EFI em cache com TTL;
- health/readiness de cache em ambiente com `REDIS_URL`;
- fanout SSE multi-worker do `django-eventstream`.

Quando `REDIS_URL` esta definido, `config/settings.py` configura:

- `CACHES["default"]` com `django.core.cache.backends.redis.RedisCache`;
- `EVENTSTREAM_REDIS` derivado da mesma URL, para que `send_event` alcance
  listeners conectados a qualquer worker.

Variavel:

```env
REDIS_URL=redis://localhost:6379/0
```

`rediss://` e aceito para ambientes gerenciados com TLS.

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
