# PRODUCTION-PLAN.md — Django Shopman

> Plano completo para levar o Shopman a produção com excelência.
> Benchmarks: iFood, Shopify, Take.app, padarias artesanais premium (Levain, Tartine).
> Princípio: confiar no Core, evoluir o App. Cada WP dimensionado para uma sessão do Claude Code.

---

## Diagnóstico

O Core está sólido: 8 apps independentes, ~1.532 testes, Protocol/Adapter bem executado, security gates (G1-G12), transações atômicas, idempotência. **Não mexemos no Core salvo necessidade comprovada.**

O App (shopman-app) tem storefront funcional end-to-end, dashboard operacional, API REST, 912 testes. Mas há gaps significativos entre o estado atual e um produto production-grade. Este plano os endereça sistematicamente.

**Pré-requisito**: Executar IMPROVEMENTS-PLAN (WP-1 a WP-3) antes deste plano. São 3 bugs e limpeza de design que devem estar resolvidos.

---

## Status Geral

| WP | Área | Status | Estimativa |
|----|------|--------|------------|
| P0 | Infraestrutura & Deploy | ⬚ Pendente | 1 sessão |
| P1 | Segurança para Produção | ⬚ Pendente | 1 sessão |
| P2 | Robustez Operacional | ⬚ Pendente | 1 sessão |
| P3 | Storefront — Fundação UX | ⬚ Pendente | 2 sessões |
| P4 | Storefront — Catálogo & Busca | ⬚ Pendente | 1 sessão |
| P5 | Storefront — Checkout & Pagamento | ⬚ Pendente | 1 sessão |
| P6 | Storefront — Tracking & Pós-venda | ⬚ Pendente | 1 sessão |
| P7 | Storefront — Conta & Fidelidade | ⬚ Pendente | 1 sessão |
| P8 | Admin — Dashboard & Operação | ⬚ Pendente | 1 sessão |
| P9 | Admin — Gestão de Pedidos & POS | ⬚ Pendente | 1 sessão |
| P10 | Notificações & Comunicação | ⬚ Pendente | 1 sessão |
| P11 | Canal WhatsApp | ⬚ Pendente | 1 sessão |
| P12 | Canal Marketplace (iFood) | ⬚ Pendente | 1 sessão |
| P13 | PWA, Performance & SEO | ⬚ Pendente | 1 sessão |
| P14 | Compliance (LGPD) & Legal | ⬚ Pendente | 1 sessão |
| P15 | Testes E2E & Stress | ⬚ Pendente | 1 sessão |
| P16 | Polimento Final & Launch Checklist | ⬚ Pendente | 1 sessão |

---

## WP-P0: Infraestrutura & Deploy

**Objetivo**: Base técnica para rodar em produção com confiança. Sem isso, nada mais importa.

### 0.1 Dockerfile & docker-compose

- `Dockerfile` multi-stage: build (collectstatic, pip install) → runtime (gunicorn, slim image).
- `docker-compose.yml` com 4 serviços: `web` (gunicorn), `postgres` (15-alpine), `redis` (7-alpine), `worker` (opcional, para tarefas async futuras).
- `.dockerignore`: excluir `.git`, `__pycache__`, `media/`, `db.sqlite3`, `.env`.
- Volume nomeado para `media/` e `postgres_data/`.
- Entrypoint script: `migrate → collectstatic → gunicorn`.
- Healthcheck no container web: `curl -f http://localhost:8000/health/`.

### 0.2 Settings por ambiente

- **Estrutura**: `project/settings/base.py`, `dev.py`, `production.py`, `test.py`.
- `base.py`: tudo que é comum (INSTALLED_APPS, middleware, AUTH_BACKENDS).
- `production.py`: `DEBUG=False`, `SECURE_*` headers, PostgreSQL, Redis, Sentry, S3.
- `dev.py`: `DEBUG=True`, SQLite, console email, sem HTTPS.
- `test.py`: in-memory SQLite, console email, sem throttling.
- Variável `DJANGO_SETTINGS_MODULE` controla qual settings carregar.
- `.env.example` documentado com todas as variáveis (sem valores reais).

### 0.3 PostgreSQL

- `DATABASE_URL` via `dj-database-url`.
- Connection pooling: `django-db-connection-pool` ou pgBouncer no docker-compose.
- `CONN_MAX_AGE = 600` para reuso de conexões.

### 0.4 Redis

- Cache backend: Redis nativo do Django (`django.core.cache.backends.redis.RedisCache`) em `CACHES["default"]`.
- Session backend: `django.contrib.sessions.backends.cache`.
- Rate limiting backend: mesmo Redis (database 1).

### 0.5 Static files

- `whitenoise` middleware para servir estáticos em produção.
- `STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"`.
- Cache headers automáticos com hash no filename.
- Alternativa futura: CloudFront CDN (se escala justificar).

### 0.6 Media files

- **Fase 1**: volume local + nginx servindo `/media/`.
- **Fase 2** (quando escalar): `django-storages` + S3 + CloudFront.
- Image processing: `Pillow` para resize/crop no upload (max 1200px, WebP).

### 0.7 Gunicorn

- `gunicorn project.wsgi:application --workers 4 --bind 0.0.0.0:8000 --timeout 30`.
- Workers = `2 × CPU + 1`.
- `--access-logfile -` para stdout (capturado pelo Docker).

### 0.8 Nginx (se VPS)

- Reverse proxy → gunicorn.
- SSL via Let's Encrypt (certbot).
- Serve `/static/` e `/media/` diretamente.
- Gzip, security headers, rate limiting de camada HTTP.
- Config template em `deploy/nginx.conf`.

### 0.9 CI/CD

- **GitHub Actions**: `.github/workflows/ci.yml`.
  - `test`: `make test` em Python 3.11+, PostgreSQL service container.
  - `lint`: `make lint` (ruff).
  - `build`: Docker build + push para registry (GitHub Container Registry).
  - `deploy-staging`: auto-deploy em merge para `main`.
  - `deploy-production`: manual trigger (ou tag `v*`).
- Matriz: Python 3.11, 3.12.

### 0.10 Backups

- Script `deploy/backup.sh`: `pg_dump` comprimido → S3 (ou local com rotação 30 dias).
- Cron diário no host (ou task no container).
- Teste mensal de restore documentado em `deploy/RESTORE.md`.

### Arquivos a criar

```
deploy/
├── Dockerfile
├── docker-compose.yml
├── docker-compose.prod.yml
├── entrypoint.sh
├── nginx.conf
├── backup.sh
├── RESTORE.md
├── .env.example
project/settings/
├── __init__.py
├── base.py
├── dev.py
├── production.py
├── test.py
.github/workflows/
└── ci.yml
```

### Testes

- `make test` passa em CI com PostgreSQL.
- `docker-compose up` levanta toda a stack local.
- Health check responde 200.

---

## WP-P1: Segurança para Produção

**Objetivo**: Eliminar toda vulnerabilidade que bloqueie uso real com dados reais de clientes.

### 1.1 HTTPS & Headers

Em `production.py`:
```python
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31_536_000  # 1 ano
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
```

### 1.2 Content Security Policy

- Instalar `django-csp`.
- Configurar directives:
  - `default-src: 'self'`
  - `script-src: 'self' cdn.jsdelivr.net js.stripe.com` (HTMX, Alpine, Stripe)
  - `style-src: 'self' 'unsafe-inline' cdn.jsdelivr.net fonts.googleapis.com` (Tailwind inline)
  - `img-src: 'self' data: *.stripe.com`
  - `font-src: 'self' fonts.gstatic.com`
  - `connect-src: 'self' api.stripe.com`
  - `frame-src: js.stripe.com`
  - `frame-ancestors: 'none'`
- Report-URI para coletar violações.

### 1.3 Session Security

- `SESSION_COOKIE_AGE = 7200` (2h para storefront).
- `SESSION_EXPIRE_AT_BROWSER_CLOSE = False` (carrinho preservado).
- Session rotation em login: `request.session.cycle_key()` em `auth.py` após verificação OTP.
- Middleware para limitar sessões simultâneas por customer (max 3 dispositivos).

### 1.4 Admin Security

- **2FA**: `django-otp` + TOTP para todos os admin users.
- **Obscurecer path**: admin em `/gestao/` ao invés de `/admin/`.
- **Rate limiting**: `django-axes` — bloquear IP após 5 tentativas falhas em 15min.
- **Audit log**: `django-auditlog` para rastrear toda ação admin (create, update, delete).
- **Session timeout admin**: `SESSION_COOKIE_AGE` separado para admin (30min via middleware).

### 1.5 Webhook Hardening

- **EFI**: Remover opção `SKIP_SIGNATURE` completamente. Em dev, usar mock backend.
- **Ambos (EFI + Stripe)**: Validar timestamp do webhook (rejeitar se > 5min atrás).
- **IP whitelist**: Middleware que restringe `/webhooks/*` a IPs conhecidos dos gateways.
- **Idempotency**: Verificar `PaymentIntent.gateway_id` antes de processar (já existe parcialmente).
- **Rate limit**: Max 60 webhooks/min por gateway.

### 1.6 Rate Limiting Granular

Além do DRF throttle genérico (120/min anon):
- **Login/OTP**: 3 requests/10min por phone (já existe, manter).
- **Checkout**: 10 submits/hora por session.
- **Coupon**: 5 tentativas/10min por session.
- **API catalog**: 300/min por IP (público, mas com limite).
- **Cart operations**: 60/min por session.
- **Search**: 30/min por IP.
- Retornar headers `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After`.

### 1.7 Secrets Validation

- Guard em `production.py`: se `SECRET_KEY` contém "dev" ou "not-for-production", `raise ImproperlyConfigured`.
- Validar que `DATABASE_URL` aponta para PostgreSQL (não SQLite).
- Validar que `EFI_WEBHOOK_TOKEN`, `STRIPE_WEBHOOK_SECRET` estão configurados.

### 1.8 API Authentication

- **Storefront API**: Session-based (já funciona para logged-in users).
- **Integração externa**: API key via header `X-API-Key` (modelo `APIKey` com hash, owner, scopes, expiry).
- **Admin API** (futuro): OAuth2 com `django-oauth-toolkit`.
- Permissions por endpoint:
  - Catalog: `AllowAny` (público).
  - Cart/Checkout: `IsAuthenticated` ou session válida.
  - Account: `IsAuthenticated`.
  - Tracking: por `order.ref` (sem auth, mas com rate limit).

### Arquivos

- `project/settings/production.py` — headers, sessions, guards.
- `channels/middleware.py` — novo: session limit, admin timeout, webhook IP filter.
- `channels/api/authentication.py` — novo: APIKeyAuthentication.
- `channels/api/throttling.py` — novo: throttle classes por endpoint.
- `shopman/webhooks.py` — remover SKIP_SIGNATURE, adicionar timestamp validation.
- `requirements/production.txt` — django-csp, django-otp, django-axes, django-auditlog.

### Testes

- `test_production_settings_reject_dev_secret` — settings guard funciona.
- `test_webhook_rejects_stale_timestamp` — webhook > 5min rejeitado.
- `test_webhook_rejects_wrong_ip` — IP fora da whitelist rejeitado.
- `test_session_rotation_on_login` — session key muda após OTP verificado.
- `test_admin_locked_after_5_failures` — django-axes funciona.
- `test_api_key_authentication` — API key válida e inválida.
- `test_csp_headers_present` — response contém Content-Security-Policy.

---

## WP-P2: Robustez Operacional

**Objetivo**: O sistema não falha silenciosamente. Erros são detectados, logados, e o operador é alertado.

### 2.1 Error Tracking (Sentry)

- `sentry-sdk[django]` em production.
- `SENTRY_DSN` via env var.
- Configurar: `traces_sample_rate=0.1`, `send_default_pii=False`.
- Tags automáticos: `channel`, `order_ref`, `customer_ref`.
- Breadcrumbs para HTMX requests.

### 2.2 Structured Logging

- `python-json-logger` para formato JSON em produção.
- Cada log inclui: `timestamp`, `level`, `logger`, `message`, `request_id`, `customer_ref`.
- Middleware `RequestIDMiddleware`: gera UUID por request, injeta no log context.
- Log levels:
  - `ERROR`: exceções não tratadas, payment failures.
  - `WARNING`: rate limit atingido, stock conflict.
  - `INFO`: order created, payment captured, notification sent.
  - `DEBUG`: desligado em produção.

### 2.3 Health Check

- View `GET /health/` retorna JSON:
  ```json
  {"status": "ok", "database": "ok", "redis": "ok", "version": "1.0.0"}
  ```
- Checa: database connection, Redis ping, disk space (media).
- Status 200 se tudo ok, 503 se qualquer falha.
- Usado pelo Docker healthcheck e load balancer.

### 2.4 Custom Error Pages

- `templates/404.html` — branded, com link para menu e busca.
- `templates/500.html` — branded, com mensagem amigável e link para contato.
- `templates/503.html` — manutenção programada.
- Todas usam inline CSS (sem dependência de static files que podem estar indisponíveis).
- Mobile-responsive.

### 2.5 Error Handling em Views

- Decorator `@graceful_error` para views do storefront:
  - Captura exceções, loga com Sentry, retorna página amigável.
  - Em HTMX requests, retorna partial com mensagem de erro.
- Mensagens de erro específicas e acionáveis:
  - "Produto indisponível" → "Este produto está esgotado. Veja alternativas:"
  - "Telefone inválido" → "Use o formato (11) 99999-9999"
  - Rate limit → "Muitas tentativas. Tente novamente em X segundos." (com countdown)

### 2.6 HTMX Error Recovery

- Handler global `htmx:responseError` no `base.html`:
  - 4xx → toast com mensagem.
  - 5xx → toast "Algo deu errado. Tente novamente." + botão retry.
  - Network error → toast "Sem conexão. Verifique sua internet."
- `htmx:timeout` → retry automático (1x) antes de mostrar erro.
- Retry button em todas as mensagens de erro.

### 2.7 Monitoring Dashboard (Admin)

- Widget no dashboard admin: "System Health" com status de DB, Redis, últimos erros Sentry.
- Alertas por email para operador quando: payment fail, stock discrepancy, webhook rejection.

### Arquivos

- `channels/middleware.py` — adicionar RequestIDMiddleware.
- `channels/web/decorators.py` — novo: @graceful_error.
- `channels/web/views/health.py` — novo.
- `channels/web/templates/404.html`, `500.html`, `503.html` — novos.
- `channels/web/templates/partials/error_toast.html` — novo.
- `project/settings/production.py` — Sentry config, logging config.

### Testes

- `test_health_check_ok` — tudo saudável = 200.
- `test_health_check_db_down` — DB indisponível = 503.
- `test_404_page_renders` — URL inexistente retorna 404 branded.
- `test_500_page_renders` — erro interno retorna 500 branded.
- `test_htmx_error_returns_toast` — request HTMX com erro retorna partial.
- `test_request_id_in_logs` — log contém request_id.

---

## WP-P3: Storefront — Fundação UX

**Objetivo**: Toda página do storefront atinge qualidade visual de padaria artesanal premium, com a praticidade de um iFood. Este WP cobre a base que todos os outros WPs de storefront usam.

### 3.1 Design System

Criar fundação visual consistente — não um framework, mas convenções claras:

- **Tipografia**: Self-hosted variable fonts (não Google Fonts CDN).
  - Display: serif elegante (tipo Playfair Display) para títulos e nome da loja.
  - Body: sans-serif clean (tipo Inter) para texto e UI.
  - `@font-face` em `base.css` com `font-display: swap`.
- **Cores**: Manter sistema OKLCH existente (5 tokens) mas documentar uso:
  - Primary: CTAs, links, badges ativos.
  - Secondary: backgrounds, cards, hover states.
  - Accent: alertas, promoções, badges especiais.
  - Neutral/Neutral Dark: texto, bordas, sombras.
- **Spacing & Layout**: grid de 4px. Paddings consistentes: `p-4` (16px) em mobile, `p-6` (24px) em desktop.
- **Elevação**: 3 níveis de sombra (cards, drawers, modals).
- **Radius**: `rounded-xl` (12px) para cards, `rounded-full` para badges/pills.
- **Motion**: transições de 200ms ease-out. Entrada: fade + slide-up. Saída: fade-out.

### 3.2 Tailwind — Produção

- **Remover CDN**. Instalar Tailwind localmente:
  - `package.json` com `tailwindcss`, `@tailwindcss/forms`, `@tailwindcss/typography`.
  - `tailwind.config.js` com content paths, extend colors (design tokens), custom fonts.
  - `npx tailwindcss -i ./static/src/input.css -o ./static/css/output.css --minify`.
  - Build step no `Makefile` e no `Dockerfile`.
- CSS de ~400KB CDN → ~15KB otimizado.
- Purge automático de classes não usadas.

### 3.3 Componentes Base (Partials Reutilizáveis)

Criar biblioteca de partials HTMX-ready:

- `_button.html` — variantes: primary, secondary, outline, danger, disabled, loading.
  - Loading state: ícone spinner + texto "Processando...". Atributo `hx-disabled-elt="this"`.
- `_input.html` — label, input, erro inline, hint. Variantes: text, tel, email, textarea.
  - Validação visual: borda verde (válido), vermelha (inválido), com ícone.
- `_toast.html` — success, error, warning, info. Auto-dismiss em 5s. Dismissível por swipe/click.
  - `aria-live="assertive"` para erros, `"polite"` para info.
- `_modal.html` — overlay + content, focus trap (Alpine), close em Esc e click fora.
  - `role="dialog"`, `aria-modal="true"`, `aria-labelledby`.
- `_badge.html` — status badges reutilizáveis (disponível, preparando, esgotado, etc.).
- `_card.html` — produto card com imagem, nome, preço, badge, CTA.
- `_empty_state.html` — ilustração + mensagem + CTA. Usado em: carrinho vazio, sem pedidos, sem resultados.
- `_skeleton.html` — loading skeleton para cards, listas, textos.
- `_breadcrumb.html` — navegação contextual.

### 3.4 Acessibilidade (WCAG 2.1 AA)

- **Skip link**: já existe `#main-content` — adicionar `<main id="main-content">` no `base.html`.
- **ARIA labels**: em todo botão icon-only (cart, menu, share, close).
- **ARIA live regions**: toast notifications, cart badge, payment status, search results count.
- **Focus management**:
  - Modal: focus trap via Alpine (`x-trap`).
  - Drawer: focus no primeiro elemento ao abrir, retorna ao trigger ao fechar.
  - HTMX swap: `hx-on::after-swap="this.querySelector('[autofocus]')?.focus()"`.
- **Keyboard navigation**:
  - Tab order lógico em toda página.
  - `Enter` e `Space` em botões e links.
  - `Escape` fecha modais e drawers.
  - Arrow keys em steppers de quantidade.
- **Contraste**: verificar todos os tokens OKLCH contra WCAG AA (4.5:1 para texto, 3:1 para UI).
- **Reduced motion**: `@media (prefers-reduced-motion)` desabilita animações.

### 3.5 Imagens — Pipeline de Otimização

- Upload hook em `Product` (via `post_save` signal ou override `save()`):
  - Resize para max 800px largura.
  - Gerar variantes: thumbnail (200px), card (400px), detail (800px).
  - Converter para WebP (com fallback JPEG).
  - Armazenar dimensões (width, height) para evitar layout shift.
- Template helper `{% product_image product size="card" %}` que gera `<img>` com:
  - `srcset` para 1x e 2x.
  - `width` e `height` explícitos.
  - `loading="lazy"` (exceto above-the-fold).
  - `alt="{{ product.name }}"`.
  - Fallback para placeholder ilustrado (não emoji).
- Placeholder: SVG branded com ícone de pão/café (não emoji).

### 3.6 Base Template — Rewrite

Reescrever `base.html` para fundação production-grade:

- `<head>`: meta charset, viewport, theme-color, description, canonical, OG tags, favicon.
- Fonts self-hosted com preload.
- Tailwind CSS (build local).
- Alpine.js + HTMX com config:
  - `htmx.config.timeout = 15000` (15s).
  - `htmx.config.defaultSwapStyle = "innerHTML"`.
  - Handler global para `htmx:responseError`, `htmx:sendError`, `htmx:timeout`.
- Header responsivo: logo, busca (expandível), cart badge, user menu.
- Footer: links úteis, contato, redes sociais, powered by.
- Toast container fixo (top-right mobile, bottom-right desktop).
- Cookie consent banner (ver P14).

### Arquivos

- `static/src/input.css` — novo: Tailwind input com @layer, custom utilities.
- `tailwind.config.js` — novo.
- `package.json` — novo.
- `channels/web/templates/base.html` — rewrite.
- `channels/web/templates/components/` — novo diretório: _button, _input, _toast, _modal, _badge, _card, _empty_state, _skeleton, _breadcrumb.
- `channels/web/templatetags/storefront.py` — novo: product_image, format_money, availability_badge.
- `channels/web/static/fonts/` — Inter, Playfair Display (ou similar).
- `channels/web/static/img/placeholder.svg` — novo.
- `Makefile` — adicionar `make css` (Tailwind build).

### Testes

- `test_base_template_has_meta_tags` — viewport, description, OG.
- `test_base_template_has_skip_link` — skip navigation funciona.
- `test_toast_has_aria_live` — toast acessível.
- `test_modal_has_focus_trap` — modal captura foco.
- `test_product_image_generates_srcset` — template tag gera srcset.
- `test_tailwind_build_succeeds` — `make css` não falha.

---

## WP-P4: Storefront — Catálogo & Busca

**Objetivo**: Cliente encontra o que quer em 3 segundos. Menu intuitivo, busca eficaz, filtros úteis. Benchmark: iFood (categorias sticky) + Levain (fotografia que dá fome).

### 4.1 Menu — Layout Redesign

- **Hero section** (topo): banner da loja com foto hero, nome, tagline, horário de funcionamento.
  - Se dentro do horário → badge "Aberto agora".
  - Se fora → "Abre às XX:XX" com próximo horário.
  - Se promoção ativa → destaque com countdown.
- **Collection pills** (sticky): barra horizontal de coleções, scroll horizontal em mobile.
  - Active state: fill com cor primary.
  - Scroll-to-section com offset para header sticky.
  - IntersectionObserver para highlight automático ao scrollar.
  - **Fallback sem JS**: links âncora simples funcionam.
- **Product grid**:
  - Cards com: foto (aspect-ratio 4:3), nome, descrição curta (1 linha truncada), preço, badge de disponibilidade.
  - **Quick-add**: botão "+" no card adiciona direto (sem ir para PDP). Stepper aparece após primeiro add.
  - Grid responsivo: 1 col (< 375px), 2 cols (mobile), 3 cols (tablet), 4 cols (desktop).
  - Lazy loading: IntersectionObserver carrega cards fora da viewport.
- **Seção "Feitos Ontem"** (D-1): se channel permite, seção separada com badge "50% off" e visual distinto.
- **Empty collection**: mensagem contextual "Nenhum produto nesta categoria ainda."

### 4.2 Busca — Upgrade Significativo

**Barra de busca**:
- Mobile: ícone no header → expande para barra full-width com animação slide-down.
- Desktop: barra visível no header com ícone de lupa.
- Placeholder: "Buscar pães, doces, cafés...".

**Busca server-side** (HTMX):
- Debounce 300ms (via `hx-trigger="keyup changed delay:300ms"`).
- Endpoint `GET /busca/?q=...` retorna partial com resultados.
- `SearchView` melhorado:
  - TrigramSimilarity do PostgreSQL para fuzzy matching (com fallback `icontains` para SQLite em dev).
  - Busca em: `product.name`, `product.description`, `collection.name`.
  - Ordenação por relevância (trigram score).
  - Limite: 20 resultados.
  - Se 0 resultados: "Nenhum resultado para 'X'. Veja nossas sugestões:" + produtos populares.
- **Resultado**: mesmos product cards do grid (reutiliza `_card.html`).

### 4.3 Product Detail Page (PDP)

- **Galeria**: imagem principal grande (aspect 1:1) + thumbnails se houver múltiplas fotos.
- **Info**: nome (h1, serif), preço grande, badge de disponibilidade, descrição (prose), ingredientes/alérgenos (se houver).
- **CTA**: botão "Adicionar ao carrinho" sticky em mobile (fixed bottom).
  - Se indisponível: "Indisponível" (disabled) + seção "Produtos similares" abaixo.
  - Se D-1: "Adicionar (produto do dia anterior)" + badge "-50%".
- **Quantidade**: stepper (−/+) com input editável.
- **Notes** (opcional): campo de observações para o item ("sem cobertura", "fatiar", etc.).
- **Seção similares**: sempre mostrar 3-4 produtos da mesma coleção.
- **Breadcrumb**: Menu > [Coleção] > [Produto].
- **Structured data**: JSON-LD `Product` schema (name, image, price, availability, brand).

### 4.4 Floating Cart Bar

- **Posição**: fixed bottom em mobile, fixed bottom-right em desktop.
- **Conteúdo**: ícone carrinho + quantity badge + total formatado + "Ver carrinho".
- **Animação**: slide-up ao adicionar primeiro item, bounce no badge a cada adição.
- **Interação**: click abre cart drawer (sheet de baixo em mobile).
- **Oculto**: quando carrinho vazio.

### Arquivos

- `channels/web/views/catalog.py` — rewrite MenuView, SearchView, ProductDetailView.
- `channels/web/templates/menu.html` — rewrite completo.
- `channels/web/templates/product_detail.html` — rewrite.
- `channels/web/templates/partials/search_results.html` — novo.
- `channels/web/templates/components/_card.html` — product card component.
- `channels/web/templates/components/_floating_cart.html` — redesign.
- `channels/web/templatetags/storefront.py` — json_ld_product.

### Testes

- `test_menu_renders_collections_and_products` — página lista tudo.
- `test_search_fuzzy_matching` — "pao" encontra "pão francês".
- `test_search_no_results_shows_suggestions` — 0 resultados → sugestões.
- `test_pdp_shows_alternatives_when_sold_out` — sold out → similares.
- `test_pdp_json_ld_schema` — structured data correto.
- `test_quick_add_from_menu` — HTMX add do card funciona.
- `test_floating_cart_bar_visible_with_items` — aparece quando há itens.

---

## WP-P5: Storefront — Checkout & Pagamento

**Objetivo**: Checkout rápido, seguro, sem fricção. Benchmark: Take.app (simplicidade) + iFood (transparência). Conversão é prioridade.

### 5.1 Cart Drawer — Redesign

- **Abertura**: sheet de baixo em mobile (slide-up 80vh), drawer lateral em desktop.
- **Conteúdo por item**: foto (thumb), nome, preço unitário, stepper (−/+), subtotal, botão remover (ícone X).
- **Coupon**: campo com botão "Aplicar". Feedback inline: "Cupom aplicado! -R$ X,XX" (verde) ou "Cupom inválido" (vermelho).
- **Resumo**: subtotal, desconto, total. Sempre visível (sticky bottom dentro do drawer).
- **CTA**: "Continuar para checkout" — botão primary grande.
- **HTMX**: toda interação (qty, remove, coupon) via HTMX swaps. Sem reload.
- **Animações**: item remove com fade-out + collapse. Item add com slide-in.

### 5.2 Checkout Flow — Simplificação

**Redesign para single-page com seções colapsáveis** (não multi-step):

1. **Seção Identificação**:
   - Se logado: mostrar nome + phone + "Não é você? Trocar conta".
   - Se não logado: campo phone + botão "Verificar". OTP inline (sem navegar para outra página).
   - OTP: 6 dígitos, auto-advance entre inputs, auto-submit quando completo.
   - Timer de reenvio: countdown de 60s, depois "Reenviar código".
   - Device trust: checkbox "Lembrar este dispositivo" (explica o que faz).

2. **Seção Entrega/Retirada**:
   - Toggle: "Retirar na loja" | "Delivery" (se canal suporta).
   - Se retirada: mostrar endereço da loja + mapa pequeno + horário de funcionamento.
   - Se delivery:
     - Endereços salvos como cards selecionáveis (radio visual).
     - "Adicionar novo endereço" → form inline (não modal).
     - CEP auto-fill: ao digitar CEP, buscar ViaCEP e preencher rua/bairro/cidade.
     - Complemento e referência como campos opcionais.
     - Taxa de entrega calculada e exibida em tempo real.

3. **Seção Pagamento**:
   - Cards visuais para método: PIX (ícone + "Desconto de X%"), Cartão (ícone de card).
   - Se PIX: nenhum campo adicional (será gerado após confirmar).
   - Se Cartão: Stripe Elements inline (card number, expiry, CVC). Minimalista.
   - Métodos salvos: mostrar últimos 4 dígitos + bandeira. "Usar este cartão".

4. **Seção Observações** (opcional, colapsada):
   - Textarea: "Alguma observação para o pedido?".

5. **Resumo fixo** (sidebar desktop / bottom sheet mobile):
   - Lista de items com qty e preço.
   - Subtotal, desconto, frete (se delivery), total.
   - CTA: "Confirmar Pedido — R$ XX,XX".
   - Ao clicar: loading state no botão, disable form.

### 5.3 Payment Flow — PIX

- Após confirmar pedido com PIX:
  - Redirect para `/pedido/{ref}/pagamento/`.
  - **QR Code** grande e centralizado (SVG, não imagem).
  - **Copia-e-cola**: botão "Copiar código PIX" com feedback "Copiado!".
  - **Timer**: countdown visual de expiração (15 min default).
  - **Status**: polling HTMX a cada 3s.
    - Pending → ícone aguardando + "Aguardando pagamento..."
    - Confirmed → ícone check verde + "Pagamento confirmado!" + redirect automático para tracking em 3s.
    - Expired → "PIX expirado" + botão "Gerar novo PIX".
    - Failed → mensagem de erro + botão "Tentar novamente".
  - **Max polling**: 300 tentativas (15 min). Após isso, mostra mensagem + botão manual.

### 5.4 Payment Flow — Cartão

- Stripe Elements renderizado inline na seção de pagamento.
- Validação client-side (Stripe.js): feedback visual de campo válido/inválido.
- Submit: loading state, Stripe confirma payment intent client-side.
- Sucesso: redirect para tracking.
- Falha: mensagem específica ("Cartão recusado", "Saldo insuficiente", "Tente outro cartão").
- 3D Secure: handled por Stripe automaticamente (popup).

### 5.5 Post-Checkout

- **Redirect**: para `/pedido/{ref}/` (tracking).
- **Confetti** (sutil): animação CSS de confetti/sparkles por 2s na confirmação.
- **Email**: enviado automaticamente (handler já existe).
- **WhatsApp** (se canal ativo): mensagem com resumo + link de tracking.

### Arquivos

- `channels/web/templates/cart_drawer.html` — rewrite.
- `channels/web/templates/checkout.html` — rewrite (single-page).
- `channels/web/templates/partials/checkout_*.html` — seções: identity, delivery, payment, summary.
- `channels/web/templates/payment.html` — rewrite (PIX + Card).
- `channels/web/views/checkout.py` — refactor para single-page.
- `channels/web/views/payment.py` — melhorar polling, add retry.
- `channels/web/static/js/checkout.js` — Alpine component para checkout state.

### Testes

- `test_checkout_single_page_renders_all_sections` — todas seções visíveis.
- `test_checkout_otp_inline` — OTP funciona sem redirect.
- `test_checkout_address_autofill_cep` — CEP preenche campos.
- `test_pix_polling_detects_confirmation` — status muda para confirmed.
- `test_pix_expired_shows_retry` — expirado mostra botão gerar novo.
- `test_card_payment_stripe_elements` — Stripe Elements renderiza.
- `test_checkout_logged_in_prefills` — dados do customer preenchidos.
- `test_checkout_summary_updates_on_change` — total recalculado em tempo real.

---

## WP-P6: Storefront — Tracking & Pós-Venda

**Objetivo**: Cliente acompanha o pedido com a confiança de um iFood. Operador atualiza status e cliente é notificado instantaneamente.

### 6.1 Order Tracking Page

- **URL**: `/pedido/{ref}/` (sem auth, por ref — como iFood).
- **Header**: ref do pedido, data, nome da loja.
- **Timeline visual** (vertical stepper):
  - Cada status = step com ícone, título, hora, descrição.
  - Status atual = destacado (cor primary, ícone animado pulse).
  - Futuros = cinza claro.
  - Passados = check verde.
  - Steps: Recebido → Confirmado → Preparando → Pronto → Entregue/Retirado.
- **Card de resumo**: items, quantidades, total pago. Colapsável.
- **Estimativa de tempo**:
  - Se `preparing`: "Previsão: pronto às XX:XX" (baseado em crafting work order ETA).
  - Se `ready`: "Pronto para retirada!" (destaque grande).
  - Se `dispatched`: "A caminho! Previsão: XX:XX".
- **Contato**: botão WhatsApp para falar com a loja (link `wa.me/{phone}`).
- **Cancelamento**: botão "Cancelar pedido" visível apenas se status permite (new, confirmed).
  - Confirmação modal: "Tem certeza? Essa ação não pode ser desfeita."
  - Após cancelar: status atualiza, reembolso processado (handler já existe).

### 6.2 Real-time Updates

- **HTMX polling**: a cada 10s, atualiza timeline + status.
  - `hx-trigger="every 10s"` no container principal.
  - Servidor retorna partial com status atualizado.
  - Se status terminal (completed, cancelled): parar polling (`hx-trigger="none"`).
- **Transição suave**: quando status muda, slide-down no novo step + highlight animation.

### 6.3 Order Confirmation Page

- **Após checkout**: landing page com:
  - "Pedido recebido!" com ícone check grande.
  - Resumo do pedido.
  - Estimativa de tempo.
  - Link de tracking (copiável).
  - "Enviamos uma confirmação para seu WhatsApp/email."
  - CTA secundário: "Voltar ao menu".

### 6.4 Pós-venda

- **Reorder**: botão "Pedir novamente" no tracking de pedidos completados.
  - Adiciona mesmos items ao carrinho (verificando disponibilidade).
  - Se algo indisponível: aviso + sugestão de alternativas.
- **Avaliação** (simples): após `delivered`, mostrar "Como foi seu pedido?" com 5 estrelas.
  - Salvar em `Order.data["rating"]` (não precisa de modelo novo).
  - Opcional: campo de comentário (max 500 chars).

### Arquivos

- `channels/web/templates/tracking.html` — rewrite com timeline.
- `channels/web/templates/order_confirmation.html` — rewrite.
- `channels/web/templates/partials/order_timeline.html` — novo.
- `channels/web/templates/partials/order_actions.html` — novo (cancel, reorder, rate).
- `channels/web/views/tracking.py` — adicionar cancel, reorder, rate.

### Testes

- `test_tracking_page_shows_timeline` — timeline renderiza com status atual.
- `test_tracking_polling_updates_status` — polling retorna status novo.
- `test_cancel_order_from_tracking` — botão cancela e atualiza.
- `test_reorder_adds_items_to_cart` — reorder funciona.
- `test_rating_saved_on_order` — avaliação salva em data.
- `test_tracking_stops_polling_on_terminal` — completed/cancelled não faz polling.

---

## WP-P7: Storefront — Conta & Fidelidade

**Objetivo**: Cliente tem controle sobre sua conta e engaja com programa de fidelidade. Benchmark: Shopify (account management) + padarias artesanais (experiência boutique).

### 7.1 Account Page — Redesign

- **Layout**: sidebar (desktop) / tabs (mobile) com seções:
  - Meus Pedidos
  - Meus Dados
  - Endereços
  - Fidelidade
  - Dispositivos
- **Meus Pedidos**:
  - Lista com: ref, data, status badge, total, nº items.
  - Filtros: "Todos", "Ativos", "Concluídos" (pills).
  - Click → vai para tracking page.
  - Empty state: "Nenhum pedido ainda. Conheça nosso menu!" + CTA.
- **Meus Dados**:
  - Nome (editável inline).
  - Phone (exibido, não editável — é o identificador).
  - Email (editável, com verificação).
  - "Excluir minha conta" (ver P14 LGPD).
- **Endereços**:
  - Cards com: label (Casa, Trabalho), endereço formatado, badge "Principal".
  - Editar, excluir, definir como principal.
  - Adicionar novo (form inline, mesmo do checkout).
  - Empty state: "Nenhum endereço salvo. Adicione um no checkout!"

### 7.2 Loyalty Section

- **Card de pontos**: visual tipo cartão fidelidade.
  - Tier atual (badge + cor): Bronze, Prata, Ouro, Platina.
  - Pontos acumulados: número grande + "pontos".
  - Progresso para próximo tier: barra de progresso.
  - "Próximo tier: Ouro (faltam X pontos)".
- **Stamps** (se habilitado): grid visual de carimbos (ex: "10 pães = 1 grátis").
  - Carimbos preenchidos vs. vazios.
  - Animação ao ganhar carimbo.
- **Histórico de pontos**: lista com data, operação (+/-), pontos, origem (pedido ref).
- **Resgate**: "Usar pontos no próximo pedido" toggle (salva preferência).

### 7.3 Dispositivos

- **Lista**: nome do dispositivo (User-Agent parsed), data de trust, IP parcial.
- **Revogar**: botão "Remover" por dispositivo.
- **Explicação**: "Dispositivos confiáveis não precisam de código de verificação."

### 7.4 Auth Flow — Polish

- **Login page redesign**:
  - Minimalista: logo da loja, campo de phone, botão "Entrar".
  - Subtext: "Enviaremos um código para seu WhatsApp."
  - Link: "Primeira vez? É automático, não precisa cadastrar."
- **OTP page**: 6 dígitos separados, auto-advance, paste-friendly.
  - Timer de reenvio com countdown.
  - "Não recebeu? Enviar por SMS" (fallback explícito).
- **Magic link**: email com design branded (template HTML).

### Arquivos

- `channels/web/templates/account.html` — rewrite com tabs/sidebar.
- `channels/web/templates/partials/account_orders.html` — lista de pedidos.
- `channels/web/templates/partials/account_profile.html` — dados pessoais.
- `channels/web/templates/partials/account_addresses.html` — endereços.
- `channels/web/templates/partials/account_loyalty.html` — novo.
- `channels/web/templates/partials/account_devices.html` — redesign.
- `channels/web/templates/login.html` — redesign.
- `channels/web/templates/partials/otp_input.html` — novo (6 dígitos component).
- `channels/web/views/account.py` — expandir com loyalty, address edit, order filters.

### Testes

- `test_account_shows_orders_with_filters` — filtros funcionam.
- `test_account_loyalty_shows_tier_and_points` — loyalty card correto.
- `test_account_edit_name` — nome atualizado.
- `test_account_add_address` — endereço adicionado.
- `test_account_edit_address` — endereço editado.
- `test_account_delete_device` — dispositivo revogado.
- `test_otp_6_digit_input` — OTP aceita 6 dígitos corretamente.

---

## WP-P8: Admin — Dashboard & Operação

**Objetivo**: Operador gerencia tudo do Unfold admin com eficiência de Shopify POS. Dashboard é a home. Benchmark: Shopify (actionable insights) + iFood Merchant (queue management).

### 8.1 Dashboard — Upgrade

Adicionar ao dashboard existente (493 linhas):

- **KPIs com comparação**: cada KPI mostra valor atual + variação vs. ontem/semana passada.
  - "Pedidos hoje: 47 (+12% vs. ontem)". Seta verde/vermelha.
- **Ticket médio**: total / nº pedidos.
- **Tempo médio de preparo**: calculado de `confirmed → ready` (se crafting integrado).
- **Pedidos pendentes de ação**:
  - Card de alerta: "3 pedidos aguardando confirmação" → link direto.
  - "2 pagamentos PIX pendentes" → link.
- **Estoque D-1**: tabela de produtos que vencem hoje (já existe, manter).
- **Chart de vendas por hora**: barras por hora do dia atual (útil para padaria ver pico).
- **Auto-refresh**: HTMX polling a cada 60s nos widgets dinâmicos.

### 8.2 Customização do Admin

- **Cores/branding**: Unfold theme com cores da loja (lê de `Shop.design_tokens`).
- **Navegação**: reestruturar sidebar:
  - Dashboard (home)
  - Pedidos (com badge de pendentes)
  - Cardápio (produtos, coleções, listagens)
  - Estoque (posições, movimentações, alertas)
  - Produção (receitas, ordens de produção)
  - Clientes (customers, grupos, loyalty)
  - Promoções (promoções, cupons)
  - Financeiro (day closing, relatórios)
  - Configurações (loja, canais, integrações)

### 8.3 Quick Actions

- **Marcar pedido como pronto**: botão em destaque na lista de pedidos em `processing`.
- **Confirmar pedido**: botão na lista de pedidos `new`.
- **Reimprimir comprovante**: ação no pedido individual.
- **Adicionar alerta de estoque**: ação rápida ao ver produto com estoque baixo.

### Arquivos

- `shop/dashboard.py` — expandir widgets.
- `shop/admin.py` — reestruturar navegação.
- `project/settings/base.py` — UNFOLD config atualizada.
- `shopman/admin/` — quick actions nos ModelAdmins de Order.

### Testes

- `test_dashboard_kpis_with_comparison` — KPIs mostram variação.
- `test_dashboard_pending_orders_alert` — alerta de pedidos pendentes.
- `test_dashboard_auto_refresh` — HTMX polling nos widgets.
- `test_quick_action_mark_ready` — botão muda status.

---

## WP-P9: Admin — Gestão de Pedidos & POS

**Objetivo**: Fluxo de atendimento presencial (balcão) e gestão completa de pedidos remotos. Operador faz tudo sem sair do admin.

### 9.1 Order List — Enhanced

- **Filtros rápidos** (pills): Novos, Confirmados, Preparando, Prontos, Todos.
- **Busca**: por ref, nome do cliente, phone.
- **Indicadores visuais**: badge colorido por status, ícone por canal (web, WhatsApp, iFood, balcão).
- **Bulk actions**: confirmar múltiplos pedidos, marcar múltiplos como pronto.
- **Sort**: por data (padrão), por total, por status.

### 9.2 Order Detail — Enhanced

- **Header**: ref, status badge, canal, data/hora, cliente (com link).
- **Timeline**: mesma timeline do storefront (status history).
- **Items**: tabela com produto, qty, preço unitário, subtotal.
- **Pagamento**: status do pagamento, método, valor.
- **Ações contextuais**:
  - `new` → Confirmar / Cancelar.
  - `confirmed` → Iniciar preparo.
  - `processing` → Marcar pronto.
  - `ready` → Marcar retirado/entregue.
  - Qualquer status não-terminal → Adicionar nota interna.
- **Notas internas**: lista de notas do operador (não visíveis para cliente).

### 9.3 POS Mode (Balcão)

- **Vista simplificada** para atendente no balcão:
  - Grid de produtos com botão de add rápido (tap).
  - Carrinho lateral com items, quantidade, total.
  - Seleção de cliente: por phone (busca rápida) ou "Cliente avulso".
  - Forma de pagamento: Dinheiro, PIX, Cartão.
  - Botão "Fechar venda" → cria order, gera fiscal (se configurado).
- **Implementação**: view custom no admin (não template storefront).
- **URL**: `/gestao/pos/` (dentro do admin).
- **Atalhos de teclado**: F1-F12 para categorias, Enter para confirmar, Esc para cancelar item.

### 9.4 Day Closing (Fechamento do Dia)

- **Wizard**: step-by-step no admin.
  - Step 1: Resumo de vendas (por canal, por método de pagamento).
  - Step 2: Conferência de estoque (quants vs. físico).
  - Step 3: Registrar sobras/perdas.
  - Step 4: Confirmar fechamento → gera `DayClosing` record.
- **PDF**: gerar relatório do dia para impressão (ver P14 ou depois).

### Arquivos

- `shopman/admin/order_admin.py` — enhanced order admin.
- `shopman/admin/pos_view.py` — novo: POS mode.
- `shopman/admin/day_closing_view.py` — novo: wizard de fechamento.
- `channels/web/templates/admin/pos.html` — novo: template POS.
- `channels/web/templates/admin/day_closing.html` — novo.

### Testes

- `test_order_list_filters_by_status` — filtros funcionam.
- `test_order_detail_actions_per_status` — ações corretas por status.
- `test_pos_create_order` — POS cria pedido.
- `test_pos_keyboard_shortcuts` — atalhos funcionam.
- `test_day_closing_wizard` — fechamento gera DayClosing.

---

## WP-P10: Notificações & Comunicação

**Objetivo**: Cliente nunca fica no escuro. Cada mudança de status gera notificação no canal certo. Benchmark: iFood (proativo, contextual) + Take.app (WhatsApp-native).

### 10.1 Email Templates — Completar e Redesign

Templates HTML branded para todos os eventos:

| Evento | Template | Status |
|--------|----------|--------|
| `order_placed` | Pedido recebido — resumo + link tracking | ✅ Existe |
| `order_confirmed` | Pedido confirmado — estimativa de tempo | ✅ Existe |
| `order_processing` | Em preparo — atualização | ✅ Existe |
| `order_ready` | Pronto! Venha buscar / aguarde entrega | ✅ Existe |
| `order_dispatched` | Saiu para entrega — tracking link | ⬚ Criar |
| `order_delivered` | Entregue — pedir avaliação | ⬚ Criar |
| `order_cancelled` | Cancelado — motivo + reembolso info | ⬚ Criar |
| `payment_confirmed` | Pagamento confirmado | ⬚ Criar |
| `payment_refunded` | Reembolso processado | ⬚ Criar |
| `loyalty_earned` | Pontos ganhos — saldo atualizado | ⬚ Criar |
| `loyalty_tier_up` | Subiu de tier — parabéns! | ⬚ Criar |

**Design de email**:
- Logo da loja no header.
- Cores da loja (design tokens).
- CTA button (link de tracking).
- Footer: endereço, contato, unsubscribe.
- Responsivo (< 600px).
- Plain text fallback.

### 10.2 WhatsApp Notifications

- Integrar com `ManychatBackend` (já existe) ou WhatsApp Business API.
- Templates de mensagem aprovados para:
  - Pedido recebido.
  - Pedido pronto.
  - Pagamento confirmado.
- Link de tracking no corpo da mensagem.

### 10.3 Push Notifications (PWA)

- Service worker: registrar subscription.
- Backend: `webpush` (django-webpush).
- Eventos que geram push:
  - Pedido confirmado.
  - Pedido pronto.
  - Promoção ativa (se opt-in).
- Permission request: após primeiro pedido (não no primeiro visit).

### 10.4 Notification Preferences

- Em "Minha Conta" → "Notificações":
  - Toggle por canal: Email, WhatsApp, Push.
  - Toggle por tipo: Pedidos, Promoções.
- Salvar em `Customer.data["notification_preferences"]`.

### Arquivos

- `channels/templates/notifications/` — 7 novos templates.
- `shopman/backends/notification_email.py` — registrar novos eventos.
- `shopman/backends/notification_push.py` — novo backend.
- `channels/web/views/account.py` — notification preferences.
- `channels/web/templates/partials/account_notifications.html` — novo.

### Testes

- `test_email_order_cancelled_sent` — email de cancelamento enviado.
- `test_email_payment_refunded_sent` — email de reembolso enviado.
- `test_whatsapp_order_ready_sent` — WhatsApp de pronto enviado.
- `test_push_notification_order_confirmed` — push enviado.
- `test_notification_preferences_respected` — canal desativado não envia.

---

## WP-P11: Canal WhatsApp

**Objetivo**: Cliente faz pedido inteiro via WhatsApp, como na Take.app. Canal mais natural para padarias brasileiras.

### 11.1 Arquitetura

- **ChannelConfig preset**: `whatsapp()` em `presets.py`.
  - Confirmation: optimistic (auto-confirm).
  - Payment: PIX (link enviado no chat).
  - Notifications: WhatsApp (no canal).
  - Pipeline: simplificado (stock → payment → notification).

### 11.2 Integration Options

- **Opção A**: Manychat (já existe backend) — flow builder visual, menor controle.
- **Opção B**: WhatsApp Business API direta (Twilio/Meta Cloud API) — controle total.
- **Recomendação**: suportar ambos via backend abstrato.

### 11.3 Flow

1. Cliente envia "Oi" ou clica em link → Mensagem de boas-vindas + link para cardápio web.
2. Cliente navega cardápio no storefront mobile (PWA) e faz checkout selecionando WhatsApp.
3. Pedido criado com `channel=whatsapp`.
4. Confirmação e updates via WhatsApp (backend existing).
5. PIX: link de pagamento enviado no chat.
6. Tracking: link enviado no chat.

### 11.4 Webhook Receiver

- Endpoint para receber mensagens do WhatsApp Cloud API.
- Parse de mensagens: pedido novo, consulta de status, cancelamento.
- Chatbot simples para FAQs (horário, endereço, cardápio).

### Arquivos

- `shopman/presets.py` — adicionar `whatsapp()`.
- `shopman/backends/notification_whatsapp.py` — expandir para 2-way.
- `shopman/webhooks.py` — adicionar WhatsApp webhook receiver.
- `channels/web/views/checkout.py` — suporte a channel=whatsapp no checkout.

### Testes

- `test_whatsapp_preset_configured` — preset tem campos corretos.
- `test_whatsapp_order_receives_confirmation` — WhatsApp enviado.
- `test_whatsapp_webhook_parses_message` — webhook processa mensagem.

---

## WP-P12: Canal Marketplace (iFood)

**Objetivo**: Receber pedidos do iFood e processar dentro do Shopman. Pedido iFood vira pedido Shopman com todos os benefícios (estoque, fiscal, tracking interno).

### 12.1 Arquitetura

- **ChannelConfig preset**: `marketplace()` em `presets.py` (já existe base).
  - Confirmation: immediate (iFood confirma).
  - Payment: external (iFood processa).
  - Stock: hold automático.
  - Pipeline: stock → fulfillment → notification (interna para operador).

### 12.2 iFood Integration

- **Webhook receiver**: endpoint para events do iFood (PLACED, CONFIRMED, CANCELLED, DISPATCHED).
- **Polling** (se webhook não disponível): check de novos pedidos a cada 30s.
- **Mapeamento**: iFood product ID → Shopman SKU (tabela de mapeamento ou `ExternalIdentity`).
- **Order creation**: iFood order → Shopman Session → Shopman Order.

### 12.3 Operator Visibility

- Pedidos iFood aparecem no dashboard com ícone/badge "iFood".
- Operador aceita/recusa dentro do admin (ação → callback para iFood API).
- Timeline do pedido: eventos iFood mapeados para status Shopman.

### 12.4 Stock Sync

- Ao criar hold no Shopman, opcional: atualizar disponibilidade no iFood.
- Ao esgotar: pausar item no iFood.

### Arquivos

- `shopman/backends/marketplace_ifood.py` — novo: iFood backend.
- `shopman/webhooks.py` — adicionar iFood webhook.
- `shopman/management/commands/ifood_poll.py` — novo: polling command.
- `shopman/admin/` — badge iFood em order list.

### Testes

- `test_ifood_webhook_creates_order` — webhook cria pedido.
- `test_ifood_sku_mapping` — produto iFood mapeado corretamente.
- `test_ifood_stock_sync` — estoque reflete no iFood.
- `test_ifood_order_visible_in_admin` — pedido com badge iFood.

---

## WP-P13: PWA, Performance & SEO

**Objetivo**: Storefront carrega em < 2s em 3G, indexa bem no Google, e funciona como app no celular. Benchmark: Lighthouse 90+ em todas as categorias.

### 13.1 PWA Enhancement

- **Manifest completo**: name, short_name, icons (192, 512, maskable), theme_color, background_color, display: standalone, orientation: portrait, shortcuts.
- **Shortcuts**: "Ver cardápio", "Meus pedidos" (acessíveis do ícone do app).
- **Install prompt**: banner customizado após segunda visita (não intrusivo).
- **Splash screen**: animação suave com logo.
- **Offline**:
  - Cache de assets estáticos (CSS, JS, fonts, icons).
  - Cache do cardápio (última versão visitada).
  - Offline page com: "Sem conexão" + "Último cardápio visitado" (se cacheado).
  - Queue de ações offline: "Adicionar ao carrinho" salvo → sincroniza quando online.

### 13.2 Performance

- **Tailwind build** (já em P3): ~15KB vs ~400KB CDN.
- **Fonts**: preload + font-display: swap + subset (latin + latin-ext).
- **Images**: WebP, srcset, lazy loading, explicit dimensions (já em P3).
- **Critical CSS**: inline styles para above-the-fold no `base.html`.
- **HTMX + Alpine**: bundles minificados, self-hosted (não CDN).
- **HTTP caching**:
  - Estáticos: `Cache-Control: public, max-age=31536000, immutable` (via whitenoise hash).
  - HTML: `Cache-Control: no-cache` (sempre fresh).
  - API: `Cache-Control: private, max-age=0`.
- **Preconnect**: `dns-prefetch` + `preconnect` para Stripe, Google Fonts (se mantidos).
- **Target**: LCP < 2.5s, FID < 100ms, CLS < 0.1.

### 13.3 SEO

- **Meta tags por página**: title, description, canonical, og:title, og:description, og:image, og:url.
- **Structured data (JSON-LD)**:
  - `LocalBusiness` na home (nome, endereço, horário, logo, rating).
  - `Product` no PDP (name, image, price, availability, brand).
  - `BreadcrumbList` em toda página com breadcrumb.
  - `WebSite` com SearchAction (busca).
  - `ItemList` no menu (lista de produtos).
- **Sitemap dinâmico**: `/sitemap.xml` com: home, coleções, produtos, como funciona.
- **Robots.txt**: allow all, block admin.
- **Alt text**: `{{ product.name }}` em todas as imagens.
- **URLs amigáveis**: `/produto/{sku}/` (já está bom).
- **Target**: Rich snippets no Google para produtos.

### 13.4 Analytics

- **Google Analytics 4**: via Google Tag Manager (configurable, off por padrão).
- **Events**: `page_view`, `add_to_cart`, `begin_checkout`, `purchase`, `search`.
- **Conversion tracking**: checkout completion rate.
- **Consentimento**: só ativa após aceite de cookies (P14).

### Arquivos

- `channels/web/views/pwa.py` — expandir manifest, service worker.
- `channels/web/templates/base.html` — meta tags, preconnect, critical CSS.
- `channels/web/templatetags/seo.py` — novo: json_ld helpers.
- `channels/web/templates/offline.html` — redesign com cardápio cacheado.
- `channels/web/static/sw.js` — rewrite service worker.

### Testes

- `test_lighthouse_performance_score` — Lighthouse via CI (puppeteer).
- `test_manifest_complete` — manifest tem todos os campos.
- `test_json_ld_product` — PDP tem structured data.
- `test_json_ld_local_business` — home tem LocalBusiness.
- `test_sitemap_includes_products` — sitemap dinâmico.
- `test_meta_tags_per_page` — cada página tem title + description.

---

## WP-P14: Compliance (LGPD) & Legal

**Objetivo**: Conformidade legal para operar no Brasil com dados de clientes.

### 14.1 Páginas Legais

- **Termos de Uso** (`/termos/`): template com conteúdo configurável (campo em `Shop.data` ou arquivo markdown).
- **Política de Privacidade** (`/privacidade/`): idem.
- **Política de Cookies** (`/cookies/`): idem.
- Links no footer de toda página.
- Checkbox no checkout: "Li e aceito os Termos de Uso e Política de Privacidade" (obrigatório).

### 14.2 Cookie Consent

- **Banner**: bottom da tela, não intrusivo.
  - "Usamos cookies para melhorar sua experiência. [Aceitar] [Configurar] [Recusar]".
  - Configurar: toggles para Essenciais (sempre on), Analytics, Marketing.
- **Implementação**: Alpine.js local (sem lib externa).
  - Salvar preferência em cookie `consent` (não localStorage).
  - Só ativar GA4/GTM após aceite de Analytics.

### 14.3 Direitos do Titular (LGPD)

- **Acesso aos dados**: endpoint `GET /minha-conta/meus-dados/exportar/` → JSON ou CSV com todos os dados do customer.
- **Retificação**: edição de dados na conta (já existe).
- **Eliminação**: "Excluir minha conta" →
  - Modal de confirmação: "Isso apagará seus dados permanentemente. Pedidos anteriores serão anonimizados."
  - Fluxo: anonimizar Customer (nome → "Anonimizado", phone → hash, email → null), manter Orders com ref para auditoria.
  - Período de carência: 30 dias para cancelar exclusão.
- **Portabilidade**: mesmo endpoint de exportação.

### 14.4 Data Retention

- Addresses não utilizadas há 12 meses: auto-delete (management command).
- Sessions expiradas (> 30 dias sem order): auto-delete.
- VerificationCodes expirados: auto-delete diariamente.
- Logs de acesso: rotação de 90 dias.

### Arquivos

- `channels/web/views/legal.py` — novo: TermsView, PrivacyView, CookiesView.
- `channels/web/views/account.py` — data export, account deletion.
- `channels/web/templates/legal/` — novo: terms.html, privacy.html, cookies.html.
- `channels/web/templates/components/_cookie_consent.html` — novo.
- `shopman/management/commands/cleanup_expired_data.py` — novo.
- `channels/web/templates/checkout.html` — checkbox de termos.

### Testes

- `test_terms_page_renders` — página de termos acessível.
- `test_cookie_consent_banner` — banner renderiza.
- `test_data_export_contains_customer_data` — export completo.
- `test_account_deletion_anonymizes` — dados anonimizados.
- `test_checkout_requires_terms_acceptance` — checkout falha sem checkbox.

---

## WP-P15: Testes E2E & Stress

**Objetivo**: Confiança total no sistema antes do launch. Nenhum caminho crítico sem cobertura.

### 15.1 Testes E2E (Playwright)

Happy paths completos:

1. **Fluxo completo de compra** (web): menu → add → cart → checkout → PIX → confirmação → tracking.
2. **Fluxo com login**: checkout → OTP → verificação → address → payment → order.
3. **Fluxo de reorder**: account → histórico → reorder → checkout.
4. **Fluxo admin**: login → dashboard → ver pedido → confirmar → preparar → pronto.
5. **Fluxo POS**: admin → POS → add items → selecionar cliente → fechar venda.

Edge cases:

6. **Produto esgota durante checkout**: outro cliente compra último item.
7. **PIX expira**: customer não paga em 15 min.
8. **Sessão expira**: customer volta depois de horas.
9. **Duplo click no submit**: idempotency protege.
10. **Rate limit no OTP**: customer tenta muitas vezes.

### 15.2 Load Testing (Locust)

- **Cenários**:
  - 100 clientes simultâneos navegando menu.
  - 50 checkouts simultâneos.
  - 20 pagamentos PIX simultâneos.
  - Dashboard admin com 10 operadores.
- **Targets**:
  - P95 response time < 500ms.
  - P99 < 2s.
  - Zero erros em fluxo normal.
  - Suportar 500 pedidos/dia (padaria média).

### 15.3 Security Testing

- **OWASP ZAP**: scan automatizado das URLs públicas.
- **Manual**: testar CSRF, XSS, injection nos forms.
- **Webhook spoofing**: enviar webhook falso, verificar rejeição.

### 15.4 Accessibility Testing

- **Axe-core**: scan automatizado de toda página.
- **Manual**: navegação via teclado em todo o checkout.
- **Screen reader**: testar com NVDA/VoiceOver nos flows principais.

### Arquivos

- `tests/e2e/` — novo diretório.
- `tests/e2e/test_purchase_flow.py` — Playwright.
- `tests/e2e/test_admin_flow.py` — Playwright.
- `tests/load/` — novo.
- `tests/load/locustfile.py` — Locust scenarios.
- `tests/security/` — novo.

### Testes

- Todos os 10 cenários E2E passam.
- Load test: P95 < 500ms com 100 concurrent.
- OWASP ZAP: zero high-severity findings.
- Axe-core: zero violations em páginas principais.

---

## WP-P16: Polimento Final & Launch Checklist

**Objetivo**: Últimos ajustes, verificação cruzada, e preparação para go-live.

### 16.1 Cross-Browser Testing

- Chrome (desktop + mobile).
- Safari (iOS — crítico para Brasil).
- Firefox.
- Samsung Internet (popular no Brasil).
- Verificar: layout, fonts, forms, HTMX, Alpine, Stripe Elements.

### 16.2 Content & Copy

- Revisão de todo texto user-facing (português correto, tom amigável).
- Mensagens de erro: específicas, acionáveis, sem jargão técnico.
- Empty states: encorajadores, com CTA.
- Loading states: texto contextual ("Buscando produtos...", "Processando pagamento...").

### 16.3 Favicon & Branding

- Favicon em múltiplos tamanhos (16, 32, 180 apple-touch, 192, 512).
- OG image default (1200x630) para shares sociais.
- Twitter Card image.

### 16.4 DNS & SSL

- Configurar domínio.
- SSL via Let's Encrypt ou Cloudflare.
- Redirect www → non-www (ou vice-versa).
- Verificar HSTS preload.

### 16.5 Launch Checklist

```
Infraestrutura:
[ ] PostgreSQL rodando, backups configurados
[ ] Redis rodando (sessions, cache)
[ ] Gunicorn com workers adequados
[ ] Nginx ou load balancer configurado
[ ] SSL ativo, HSTS habilitado
[ ] Domínio apontando corretamente
[ ] Docker compose funcional
[ ] CI/CD pipeline rodando

Segurança:
[ ] SECRET_KEY rotacionado
[ ] DEBUG = False
[ ] ALLOWED_HOSTS restrito
[ ] CSP headers ativos
[ ] Admin com 2FA
[ ] Admin path obscurecido
[ ] Webhook signatures validando
[ ] Rate limits ativos
[ ] Session security configurada

Aplicação:
[ ] Seed data removido / dados reais inseridos
[ ] Produtos cadastrados com fotos reais
[ ] Coleções organizadas
[ ] Horário de funcionamento configurado
[ ] Promoções ativas configuradas
[ ] Canais habilitados (web, WhatsApp)
[ ] Email transacional configurado (SES/Mailgun)
[ ] PIX configurado (EFI produção)
[ ] Stripe configurado (se card)
[ ] Notificações testadas end-to-end

Qualidade:
[ ] Testes E2E passando
[ ] Load test: P95 < 500ms
[ ] Lighthouse: 90+ em todas as categorias
[ ] Axe-core: zero violations
[ ] OWASP ZAP: zero high findings
[ ] Cross-browser testado

Legal:
[ ] Termos de Uso publicados
[ ] Política de Privacidade publicada
[ ] Cookie consent implementado
[ ] LGPD compliance verificado

Operacional:
[ ] Operador treinado no admin
[ ] Sentry configurado
[ ] Alertas de email para operador
[ ] Backup testado (restore funciona)
[ ] Runbook de incidentes documentado
```

---

## Ordem de Execução Recomendada

```
Fase 1 — Fundação (obrigatório antes de tudo)
  P0: Infraestrutura & Deploy
  P1: Segurança para Produção
  P2: Robustez Operacional

Fase 2 — Storefront Excellence
  P3: Fundação UX (design system, Tailwind, componentes, acessibilidade)
  P4: Catálogo & Busca
  P5: Checkout & Pagamento
  P6: Tracking & Pós-Venda
  P7: Conta & Fidelidade

Fase 3 — Operador & Admin
  P8: Dashboard & Operação
  P9: Gestão de Pedidos & POS

Fase 4 — Comunicação & Canais
  P10: Notificações & Comunicação
  P11: Canal WhatsApp
  P12: Canal Marketplace (iFood)

Fase 5 — Polish & Launch
  P13: PWA, Performance & SEO
  P14: Compliance (LGPD) & Legal
  P15: Testes E2E & Stress
  P16: Polimento Final & Launch Checklist
```

**Dependências**:
- P3 antes de P4-P7 (componentes base usados em tudo).
- P0-P1 antes de P15 (precisa de infra para testes de carga).
- P10 pode rodar em paralelo com P8-P9.
- P14 pode rodar em paralelo com P13.
- P16 sempre por último.

---

## Princípios Transversais

1. **Core é sagrado**: não alteramos core apps salvo bug comprovado. A implementação no App que se adapta.
2. **HTMX para servidor, Alpine para DOM**: sem exceção. Sem jQuery, sem onclick inline.
3. **Mobile-first**: toda feature é desenhada primeiro para tela de 375px.
4. **Testes acompanham**: nenhuma feature sem teste. O test list de cada WP é obrigatório.
5. **Incremental**: cada WP é deployable independentemente. Nenhum WP depende de outro WP da mesma fase (exceto P3).
6. **Zero residuals**: renomear completamente, sem aliases, sem "formerly X".
7. **Centavos com _q**: sem exceção em valores monetários.
8. **Portuguese-first**: toda UI em pt-BR. Código e logs em inglês.
