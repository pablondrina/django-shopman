# DJANGO-HEADLESS-PLAN — desacoplar a loja (Nuxt no apex `/`)

> **Prompt auto-contido.** Tornar o Django **headless** (backend de API/admin/operador,
> sem servir páginas de cliente) e a **loja Nuxt** a superfície de cliente, acessada em
> `/` no domínio de produção. Arquitetura aprovada pelo Pablo (2026-06-17).

## Decisão de arquitetura (aprovada)

**Desacoplado por domínio** (não domínio único com prefixos — isso vira gambiarra por
causa da colisão da `/api` do BFF):

| Superfície | Domínio (prod) | O quê |
|---|---|---|
| **Loja** (Nuxt) | apex, ex. `nelson.com` **em `/`** | superfície de cliente |
| **Backend** (Django) | `api.nelson.com` | API REST + webhooks de pagamento |
| **Admin/Operador** (Django Unfold) | `admin.nelson.com` | gestão, KDS, produção, fechamento |
| **PDV** (Nuxt) | `pos.nelson.com` | caixa |

O **BFF** (`server/api/v1/[...path].ts`, `server/api/auth/[...path].ts` + `djangoProxy.ts`)
das superfícies Nuxt é a ponte correta: o navegador só fala com o próprio host; o servidor
Nuxt proxia para `api.` por baixo (CSRF/cookie resolvidos server-side, sem CORS). **Manter.**

Por que NÃO domínio único: o BFF serve `/api/v1` e `/api/auth`; o Django também tem `/api/*`;
o PDV também proxia `/api/v1`. Na raiz tudo colide (loop do proxy + PDV no BFF errado). Em
subdomínios a colisão evapora (cada superfície só tem o próprio `/api`).

## Princípio do refactor

"Headless" ≠ apagar páginas. É **reapontar todo gerador de link de cliente** para a loja
Nuxt, atrás de **uma fonte única** (`SHOPMAN_STOREFRONT_BASE_URL`), e só então aposentar as
páginas Django legadas. Errar um link de **pagamento/notificação** = cliente com botão
quebrado — por isso é tela-a-tela, testado, nunca no susto.

## Estado atual (branch `refactor/django-headless`)

- ✅ **Passo 1 — fonte única** (commit `7e4d6a3d`): `settings.SHOPMAN_STOREFRONT_BASE_URL`
  (env, default = `WHATSAPP_STOREFRONT_URL` → `SHOPMAN_DOMAIN`) +
  `shopman/shop/services/storefront_links.py` com os **caminhos CANÔNICOS da loja Nuxt**
  (`/tracking/{ref}`, `/pedido/{ref}/pagamento`, `/product/{sku}`, `/menu`, `/cart`,
  `/account`, …) e builders de URL absoluta. Testado (`test_storefront_links.py`).
  **Cutover de domínio = 1 knob:** `SHOPMAN_STOREFRONT_BASE_URL=https://nelson.com`.
- ✅ **Reapontados (seguros):** `admin/shop.py` (preview da loja → `home_url()`),
  `handlers/_stock_receivers.py::_cart_url` (→ `cart_url()`). Teste de stock-receiver
  atualizado para o novo contrato (`/cart`, base = `SHOPMAN_STOREFRONT_BASE_URL`).
- ✅ **Passo 2 — projeção de pagamento + magic links (interino):**
  - `shop/projections/payment_status.py` desacoplado de `reverse("storefront:…")`:
    `status_url` → `/api/v1/payment/{ref}/status/` (endpoint que sobrevive, mesmo path que a
    view da API já sobrescreve); `redirect_url` + hrefs `track_order` → `order_tracking_url`;
    hrefs `retry_payment` → `order_payment_url`. **Confirmado** que o Nuxt NÃO renderiza
    `promise.actions` (a página usa `payment.actions` [só mock_confirm em DEBUG, `/api/v1/…`],
    `payment.tracking_url` e `payment.checkout_url`; `status_url`/`redirect_url` são
    sobrescritos pela própria view da API com paths Nuxt) — repoint é seguro p/ a superfície
    viva e remove o acoplamento que quebraria ao aposentar as URLs do storefront.
  - `shop/services/notification.py` (fallback) → `storefront_links.order_payment_url(ref)`.
  - Testes ajustados: `test_access_urls`, `test_projections_payment`, `test_web_payment`
    (legado, assert sem trailing slash), `test_availability_plan_e2e` (cart_url no contrato
    `SHOPMAN_STOREFRONT_BASE_URL` — herança vermelha do Passo 1).
- ✅ **Passo 2 — magic links MIGRADOS de verdade (sem legado, sem interino):**
  decisão do Pablo: projeto novo em pré-lançamento, zero legado a manter. O magic link
  agora **nasce, é consumido e estabelece sessão no domínio da LOJA (Nuxt)**:
  - **Builders** (`access_urls.py`) reescritos: link = `storefront_links` base + `/a?t=<token>`
    (domínio da loja, sem `next` na query). O **destino vem da metadata do token** server-side
    (`order_ref`/`action`/`next`) → zero superfície de open-redirect. Assinatura enxuta:
    `build_*_access_url(customer, order_ref)` (caíram `request_or_shop`/`next_url`/`_resolve_domain`).
  - **Página Nuxt** `app/pages/a.vue` (rota `/a`): faz `POST /api/auth/access/` (BFF →
    `/api/v1/auth/access/`), seta o cookie no host da loja, e `navigateTo(redirect)`.
  - **Endpoint** `storefront/api/auth.py::AccessLinkExchangeView` (`POST /api/v1/auth/access/`):
    troca token→sessão (reusa `shop.services.access`), grava `origin_channel`, concede acesso ao
    pedido, e devolve `{session, redirect}` derivado da metadata (`path_order_payment`/
    `path_order_tracking`/`path_order_history`/`next` relativo/`/account`).
  - **Ponte ManyChat** (doorman Core, `views/access_link.py`): `access/create/` agora emite o
    link da loja via novo setting `DOORMAN.ACCESS_LINK_ENTRY_URL` (= `SHOPMAN_STOREFRONT_BASE_URL`)
    e **dobra o `next` na metadata** (validado relativo) em vez de query param.
  - **Legado REMOVIDO:** `storefront/views/access.py` (`/a/`), `AccessLinkLoginView`
    (`/auth/access/<token>/`), `shop/services/auth.exchange_access_link`,
    `templates/.../access_link_invalid.html`, e os testes legados (portados p/ o endpoint novo).
  - **Verificado ao vivo** (preview 3000): `/a?t=token-inválido` → 400 no Django → estado de erro
    amigável na loja, integrado ao shell. `make test` verde (2142 passed).

## Geradores de link de cliente AINDA a reapontar (mapeados)

1. ✅ **`shop/projections/payment_status.py`** — feito no Passo 2.
2. ✅ **`shop/services/notification.py`** — feito no Passo 2 (fallback → `order_payment_url`).
3. ✅ **`shop/services/access_urls.py` + magic links** — MIGRADOS de verdade no Passo 2 (acima).
   Cross-domain resolvido: link da loja + sessão no host da loja via BFF.
4. ✅ **`storefront/presentation/catalog.py` `detail_url`** — era código morto (zero consumidores);
   removido no Passo 3.
5. ✅ **`storefront/services/catalog.py` sitemap** — `sitemap_urls` removido no Passo 3 (Nuxt serve
   o próprio `sitemap.xml`/`robots.txt`).

## ✅ Passo 3 — páginas Django de cliente APOSENTADAS (commit `37e34d12`)

Django headless de verdade. **Removido:** `storefront/views/` inteiro, `storefront/urls.py`,
`storefront/templates/` (61 templates), `context_processors.py`; `config/urls.py` perdeu o
`include("storefront.urls")`; settings perderam `WelcomeGateMiddleware` + os context processors de
storefront. **SSE de cliente** (`sku_state`/`order_events`) some com as views; **`_sse_emitters` e o
SSE de operador (backstage) ficam** (separados). **Extraído p/ manter a API:**
`get_authenticated_customer` → `storefront/identity.py`; `omotenashi_qa` (backstage) → links de
cliente via `storefront_links`. **MANTIDOS** (a API que o BFF consome): `storefront/api/`,
`services/`, `projections/`, `presentation/`, `intents/`, `models/`, `cart.py`, `identity.py`,
`ChannelParamMiddleware`. **Testes:** removidos os de página (`test_web_*`, guardrails de
template/asset, omotenashi partials/cold-strings, SSE trigger guard); contratos vivos PORTADOS p/
a API/serviço (acesso a pedido, magic link, rate limiting, persist_address, home reorder);
`cart_session` fixture usa `PUT /api/v1/cart/skus/`. `make test` verde (**1792 passed**).

**Investigado e RESOLVIDO/decidido:**
- ✅ `make lint` verde: dívida de import-sort pré-existente corrigida (commit `chore(lint)`); Admin
  canônico passa.
- ⚠️ **`shop/templates/components/` + `storefront/static/` NÃO são órfãos — são COMPARTILHADOS com o
  backstage** (ex.: `gestor/base.html` e `kds_customer/board.html` carregam
  `storefront/css/output-gestor.css`; `_badge.html` é usado pelo admin/gestor). **Ficam.** Separar
  o que é só-cliente do build compartilhado é delicado e de baixo valor.
- ⚠️ **`_sse_emitters.py` está VIVO p/ o operador** — `_on_order_changed`/`_on_payment_changed`
  emitem `backstage-orders-update` (SSE do operador) junto com `order-{ref}`/`stock-{ref}` (canais de
  cliente agora sem assinante, no-op barato). **Fica.** Remover só os emits de cliente é frágil e ~zero
  benefício.

**Follow-ups remanescentes (não bloqueiam):**
- e2e Playwright (`shop/tests/e2e/test_storefront_e2e.py`, `importorskip`→skip; cenários 01/02/06 de
  cliente) e `shop/tests/load/locustfile.py` ainda batem em rotas legadas — **reescrever contra a loja
  Nuxt/API** (esforço próprio; não afeta `make test`).
- **Fase 1 (deploy/subdomínios)** — código JÁ pronto: `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` e
  `SHOPMAN_STOREFRONT_BASE_URL` são todos env-driven (`config/settings.py`). Falta só o deploy +
  DNS + DO App Platform (outward-facing, do Pablo).

## Ordem & gates

`make test` verde a cada passo. ✅ Reapontar (itens 1–5) → ✅ aposentar SSE/templates/páginas →
✅ limpar testes → ✅ `make test` → **falta: deploy staging e verificar API + admin + operador +
PDV + notificações 100%.**

## Fase 1 — subdomínios (depois do headless, na virada de domínio)

- DO App Platform: domínios `api.`/`admin.`/`pos.` + apex → componentes (ingress por host,
  ou apps separados). Apex → `thing-storefront` (loja) com `NUXT_APP_BASE_URL=/`.
- BFFs (`thing-storefront`, `pos-uithing`) `NUXT_DJANGO_BASE_URL` → `https://api.nelson.com`.
- `SHOPMAN_STOREFRONT_BASE_URL=https://nelson.com` (vira todos os links de cliente).
- CSRF/cookies: ver `djangoProxy.ts` (set referer/origin = origem do djangoBaseUrl;
  `CSRF_TRUSTED_ORIGINS` precisa incluir os hosts). Cookie de sessão fica no host da loja via
  o BFF (host-only). Testar checkout/login end-to-end.

## Referências

- Fonte única: `shopman/shop/services/storefront_links.py` (+ `SHOPMAN_STOREFRONT_BASE_URL`).
- BFF: `surfaces/storefront-uithing-nuxt/server/utils/djangoProxy.ts`.
- URLs Django: `config/urls.py`, `shopman/storefront/urls.py`.
- Memória: deploy/staging em `project_pos_staging_deploy`.
