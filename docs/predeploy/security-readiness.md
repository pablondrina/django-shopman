# Security Readiness Checklist

Estado em 2026-04-26. Este documento prepara a fase posterior de deploy sem
definir provedor, topologia, domínio ou processo operacional.

## Bloqueadores Automatizados

Antes de qualquer ambiente público, rodar:

```bash
python manage.py check --deploy
ruff check .
pytest -q
```

`manage.py check --deploy` já bloqueia:

- `SHOPMAN_E001`: `DJANGO_SECRET_KEY` ausente ou igual ao segredo de desenvolvimento.
- `SHOPMAN_E002`: `DJANGO_ALLOWED_HOSTS` vazio ou com `*` em produção.
- `SHOPMAN_E003`: adapter de pagamento `pix` ou `card` apontando para mock em produção.
- `SHOPMAN_E004`: webhook EFI ou iFood sem token.
- `SHOPMAN_E005`: webhook ManyChat sem segredo HMAC.
- `SHOPMAN_E006`: cache compartilhado Redis ausente em produção.
- `SHOPMAN_E007`: SQLite fora de `DEBUG`.

Warnings que precisam de decisão antes do go-live:

- `SHOPMAN_W001`: SQLite em fallback local/debug. Produção falha como `SHOPMAN_E007`.
- `SHOPMAN_W002`: notification adapter console fora de `DEBUG`.
- `SHOPMAN_W003`: canal fiscal ativo sem adapter fiscal.
- `SHOPMAN_W004`: `Listing.ref` sem `Channel.ref` correspondente.
- `SHOPMAN_W005`: backend contextual de pricing do Offerman não configurado.

## Variáveis Obrigatórias

Base Django:

- `DJANGO_DEBUG=false`
- `DJANGO_SECRET_KEY=<valor forte e único>`
- `DJANGO_ALLOWED_HOSTS=<domínios separados por vírgula>`
- `CSRF_TRUSTED_ORIGINS=https://<domínio>[,...]`
- `DATABASE_URL=<postgresql>`
- `REDIS_URL=<redis ou rediss>`

Pagamentos e webhooks:

- `STRIPE_SECRET_KEY` e `STRIPE_WEBHOOK_SECRET`, se cartão estiver ativo.
- `EFI_CLIENT_ID`, `EFI_CLIENT_SECRET`, `EFI_WEBHOOK_TOKEN`, se Pix EFI estiver ativo.
- `IFOOD_WEBHOOK_TOKEN`, se iFood estiver ativo.

Mensageria e autenticação externa:

- `DOORMAN_ACCESS_LINK_API_KEY`, se access links chat→web estiverem expostos.
- `MANYCHAT_API_TOKEN`, se WhatsApp via ManyChat enviar mensagens.
- `MANYCHAT_WEBHOOK_SECRET`, se webhooks ManyChat estiverem expostos.
- `WHATSAPP_VERIFY_TOKEN`, se endpoint WhatsApp direto for ativado.

## Segurança HTTP

Com `DEBUG=false`, `config/settings.py` ativa:

- `SESSION_COOKIE_SECURE=True`
- `CSRF_COOKIE_SECURE=True`
- `SECURE_HSTS_SECONDS=31536000`
- `SECURE_HSTS_INCLUDE_SUBDOMAINS=True`
- `SECURE_HSTS_PRELOAD=True`
- `SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https")`
- `SECURE_CONTENT_TYPE_NOSNIFF=True`
- `SECURE_REFERRER_POLICY="strict-origin-when-cross-origin"`

Antes do go-live, confirmar no ambiente:

- O proxy envia `X-Forwarded-Proto=https`.
- Cookies `sessionid` e `csrftoken` chegam com `Secure`.
- HSTS só é ligado depois de confirmar domínio HTTPS final e subdomínios.
- CSP permite apenas origens realmente usadas por Stripe, Google Maps e APIs necessárias.

## Superfícies Públicas

Storefront:

- Login/OTP tem rate limiting via `django-ratelimit`.
- Links de acesso usam tokens de Doorman com uso único, expiração e criação
  autenticada por `DOORMAN_ACCESS_LINK_API_KEY` fora de `DEBUG`.
- URLs de pedido (`/pedido/<ref>/`, pagamento, status, cancelamento,
  confirmacao e reorder) nao devem ser publicas por `ref`: exigem sessao
  autorizada, cliente autenticado correspondente ou staff.
- SSE `order-*` segue a mesma regra de acesso do pedido; `stock-*` permanece
  publico porque transmite disponibilidade por canal, sem dados pessoais.
- Trusted device usa cookie assinado por token hash e pode ser revogado.
- Checkout simulado de iFood é `DEBUG` only e retorna 404 fora de debug.

Backstage:

- Páginas de operador devem continuar protegidas por autenticação/permissões.
- SSE `backstage-*` exige staff via `ShopmanChannelManager`.
- Ações POS/KDS/produção devem seguir delegando para `shop.services`.
- Revisar permissões dos grupos seedados antes de expor `/gestor/`.

Webhooks:

- EFI rejeita token ausente/incorreto.
- iFood rejeita token ausente/incorreto.
- ManyChat exige HMAC quando `MANYCHAT_WEBHOOK_SECRET` está configurado.
- Stripe depende de `STRIPE_WEBHOOK_SECRET` para validação de assinatura.

## Dados Sensíveis

Não logar:

- OTP/códigos de verificação.
- Tokens de acesso, webhook ou device trust.
- Segredos de pagamento.
- Payload completo de pagamento quando contiver identificadores sensíveis.

Já existem testes contra vazamento de OTP em senders. Antes do deploy, rodar
busca manual:

```bash
rg 'print\\(|logger\\.(debug|info|warning|error).*token|logger\\.(debug|info|warning|error).*secret|logger\\.(debug|info|warning|error).*code' shopman packages
```

## Operação Mínima Pré-Deploy

Ainda fora do escopo desta fase, mas precisa estar decidido antes de produção:

- Backup e restore testado para PostgreSQL.
- Redis provisionado e validado para cache, rate limit e SSE multi-worker.
- Estratégia de coleta de logs.
- Monitoramento de webhooks falhos.
- Processo para rotacionar `DJANGO_SECRET_KEY` e tokens externos.
- Processo para rodar migrations e seed inicial.
- Domínios finais para Storefront, Backstage e webhooks.

## Critério De Pronto

Um ambiente está pronto para teste público quando:

- `python manage.py check --deploy` roda sem erros.
- `ruff check .` passa.
- `pytest -q` passa.
- `DJANGO_DEBUG=false` no ambiente.
- Webhooks expostos têm token/assinatura configurados.
- Backstage exige autenticação em todas as rotas sensíveis.
- Checkout real usa adapters reais para métodos habilitados.
- `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` contêm somente domínios reais.
