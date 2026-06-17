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

## Geradores de link de cliente AINDA a reapontar (mapeados)

1. **`shop/projections/payment_status.py`** (consumida pelo Nuxt!) — `reverse("storefront:
   order_payment")` (≈ l.419, l.473) e `reverse("storefront:payment_status_partial")` (l.146).
   ⚠️ **SUTILEZA:** `surfaces/storefront-uithing-nuxt/app/pages/pedido/[ref]/pagamento.vue:90`
   faz `$fetch(apiPath(action.href))` esperando `{redirect_url}` — ou seja, ALGUM `action.href`
   é consumido como **chamada de API**, não link de página. **Entender o handling por `kind`
   (link/external/mutation) no Nuxt ANTES de mexer.** O Nuxt já tem a própria página de
   pagamento (`/pedido/[ref]/pagamento`) e o próprio polling via `/api/v1`; provavelmente
   esses URLs Django são vestigiais para navegação, mas confirmar o uso do `apiPath`.
2. **`shop/services/notification.py`** (l.301/306, fallback `/pedido/{ref}/pagamento/`) —
   trocar o fallback por `storefront_links.order_payment_url(ref)`. O caminho PRIMÁRIO usa
   `build_payment_access_url`/`build_tracking_access_url` (magic link) → ver item 3.
3. **`shop/services/access_urls.py`** (magic links `/a/?t=&next=/pedido/{ref}/…`) —
   ⚠️ **SUTILEZA (cross-domain):** em subdomínios, um magic link que cai no Django (`api.`)
   seta o cookie em `api.`, mas o cliente aterrissa na loja (`nelson.com`) onde o cookie não
   existe. **Magic-link precisa MIGRAR de feature:** o link aponta para uma rota da LOJA Nuxt
   (ex. `nelson.com/a/<token>`) que chama `/api/auth/...` (BFF) e estabelece a sessão no
   domínio da loja. É feature nova (rota Nuxt + endpoint de API), não só repoint. Interino
   (staging single-domain): magic link no `/a/` Django segue funcionando; trocar só os
   `next_url` para os caminhos Nuxt de `storefront_links`.
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
  storefront.urls"))` do `config/urls.py`. **MANTER** o que vira ponte de auth do magic link
  (`/a/`, `/auth/access/<token>/`) até a migração do item 3, e **MANTER** `storefront/api/`,
  `storefront/services/`, `storefront/projections/` (a API que o BFF consome).
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
