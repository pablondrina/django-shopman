# Deploy

Este guia define o caminho operacional simples para staging/piloto. Docker e
compose ficam encapsulados nos targets `make deploy-*`; o operador nao precisa
chamar comandos Docker diretamente.

## Contrato

- Aplicacao: imagem `Dockerfile` com Python 3.12, assets Tailwind compilados e
  ASGI via Daphne.
- Banco: PostgreSQL 16+.
- Cache/realtime: Redis 7+ ou Valkey Redis-compatible usando o backend nativo
  `django.core.cache.backends.redis.RedisCache`.
- Worker leve: `python manage.py process_directives --watch`.
- Release step: `check --deploy`, `migrate` e `collectstatic`.
- Estáticos: `collectstatic` roda no build da imagem; WhiteNoise serve
  `/static/` no runtime.

Nao ha `django-redis`, Celery ou broker adicional neste contrato.

## Arquivos

- `Dockerfile`: imagem da aplicacao.
- `docker-compose.yml`: Postgres/Redis por default; app, worker e release em
  profiles para nao alterar o fluxo de desenvolvimento.
- `.env.example`: variaveis base. Copie para `.env` e substitua os segredos.
- `Makefile`: wrappers `deploy-*`.
- `.do/app.yaml`: blueprint DigitalOcean App Platform para staging sem segredos.

## Comandos

```bash
cp .env.example .env
# edite .env: DJANGO_DEBUG=false, segredo forte, hosts e tokens reais
make deploy-check
make deploy-up
```

`make deploy-up` executa:

1. build da imagem;
2. subida de PostgreSQL/Redis;
3. release one-shot (`check --deploy`, migrations e `collectstatic`);
4. subida do web ASGI e do directive worker.

Para acompanhar ou parar:

```bash
make deploy-logs
make deploy-ps
make deploy-down
```

## Variaveis Minimas

Para qualquer ambiente publico:

```env
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=<segredo forte>
DJANGO_ALLOWED_HOSTS=loja.example.com
CSRF_TRUSTED_ORIGINS=https://loja.example.com
DATABASE_URL=postgres://...
REDIS_URL=redis://... ou rediss://...
DOORMAN_ACCESS_LINK_API_KEY=<segredo>
EFI_WEBHOOK_TOKEN=<segredo>
IFOOD_WEBHOOK_TOKEN=<segredo>
MANYCHAT_API_TOKEN=<segredo>
MANYCHAT_WEBHOOK_SECRET=<segredo>
SHOPMAN_PIX_ADAPTER=shopman.shop.adapters.payment_efi
SHOPMAN_CARD_ADAPTER=shopman.shop.adapters.payment_stripe
```

`manage.py check --deploy` falha fechado quando esses itens obrigatorios nao
estao configurados para producao.

## Static e Media

`collectstatic` grava em `STATIC_ROOT` (`/app/staticfiles` no container) durante
o build da imagem. WhiteNoise serve `/static/` no runtime; CDN/reverse proxy
pode ser adicionado depois, mas nao é requisito para App Platform.

`MEDIA_ROOT` permanece em `/app/media` no container local. Em App Platform esse
filesystem é efêmero; piloto publico com uploads reais precisa de storage
externo persistente, como DigitalOcean Spaces/S3-compatible.

## Gates

Antes de abrir trafego:

```bash
make deploy-check
make test-runtime
```

No PR, o workflow `Runtime Gate` builda a imagem Docker e executa PostgreSQL +
Redis reais no GitHub Actions, entao esse gate nao depende de Docker instalado
na maquina local.

## Limites

Este compose e uma topologia minima para staging/piloto. Em producao final,
manter os mesmos contratos, mas decidir provedor, TLS/reverse proxy,
backup/restore, logs, monitoramento de webhooks e estrategia de rollbacks.

Para DigitalOcean App Platform, use o guia dedicado:
[`deploy-digitalocean.md`](deploy-digitalocean.md).
