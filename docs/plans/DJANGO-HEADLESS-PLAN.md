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
4. **`storefront/presentation/catalog.py:114`** (`detail_url` → `storefront:product_detail`) —
   "convenience for templates". Confirmar se a API/Nuxt usa; se não, é legado (tem fallback).
5. **`storefront/services/catalog.py`** (sitemap Django reverse `storefront:home/menu/…`) — o
   Nuxt já serve o próprio `sitemap.xml`/`robots.txt`. Aposentar o sitemap Django.

## Aposentar (depois que os links acima apontarem para o Nuxt)

- **SSE legado** (`storefront:sku_state`, `order_events`, `stock_events`) — o Nuxt NÃO usa
  EventSource. Remover views + rotas + `test_sse_emitters.py`.
- **Templates Django de cliente** (`shop/templates/components/_header.html`, `_bottom_nav.html`,
  `_focus_overlay.html` referenciam `storefront:`) — só os usam as páginas legadas. Aposentar
  junto. (Confirmar que o admin/operador NÃO os usa.)
- **Páginas legadas** `shopman/storefront/urls.py` — remover `path("", include("shopman.
  storefront.urls"))` do `config/urls.py`. A ponte de auth do magic link já NÃO depende mais de
  páginas Django (o `/a/` Django foi removido; quem consome é a loja Nuxt + `/api/v1/auth/access/`).
  **MANTER** `storefront/api/`, `storefront/services/`, `storefront/projections/` (a API que o BFF
  consome).
- **Testes legados** de web-view (`storefront/tests/test_web_views*`) — remover/quarentenar.

## Ordem & gates

`make test` verde a cada passo. Reapontar (itens 1–5) → aposentar SSE/templates/páginas →
limpar testes → `make test` → deploy staging e verificar **API + admin + operador + PDV +
notificações** 100%.

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
