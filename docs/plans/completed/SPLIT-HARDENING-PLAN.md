# SPLIT-HARDENING-PLAN — Tornar o split autoritativo

> Baseado na análise crítica de 2026-04-20 + verificação do estado atual.
> Objetivo: eliminar toda ambiguidade residual do split shop/storefront/backstage.

## Estado verificado (2026-04-21)

| Achado | Status | Ação |
|--------|--------|------|
| Templates/statics duplicados em shop/ | **71 templates + 13 statics duplicados confirmados** | WP-H1 |
| shop/ importa backstage diretamente (sem adapter) | **10 imports diretos em 6 arquivos de produção** | WP-H2 |
| Docstrings/loggers referenciam `shopman.shop.web` | **33 ocorrências em 21 arquivos** | WP-H3 |
| Tests de storefront/backstage vivem em shop/tests/ | **test_web.py, test_flow_s6.py, test_admin.py parcial** | WP-H3 |
| Guardrails não cobrem storefront/backstage | **test_no_deep_kernel_imports.py varre só shop/** | WP-H4 |
| Views gordos (checkout 1012L, _helpers 627L) | **Confirmado** | WP-H5, WP-H6 |

### Achados descartados

| Achado | Motivo |
|--------|--------|
| "Split topológico, não semântico" (handlers/__init__.py monolítico) | É o design correto: shop é orquestrador, registrar handlers no boot é sua responsabilidade. 32k linhas em shop é esperado para orquestrar 8 kernels. |
| "storefront/backstage AppConfigs minimalistas" | Camadas de apresentação não precisam de boot complexo. A autoridade está nos imports, não no AppConfig. |
| account.py 620L | São 12 views pequenas (10-30L cada). 620L é razoável. |
| catalog.py projection 640L | Projection completa e bem estruturada. Tamanho adequado. |

---

## Plano de Execução

### Wave 1 — 5 WPs paralelos (sem dependência entre si)

---

#### WP-H1: Purgar templates/statics duplicados de shop/

**Problema:** 71 templates de superfície + 13 statics duplicados sob `shopman/shop/`. Com `APP_DIRS=True` e shop antes em `INSTALLED_APPS`, Django resolve do lugar antigo → shadowing silencioso.

**Escopo:**
- Deletar `shopman/shop/templates/storefront/` (55 arquivos)
- Deletar `shopman/shop/templates/kds/` (6 arquivos)
- Deletar `shopman/shop/templates/pedidos/` (6 arquivos)
- Deletar `shopman/shop/templates/pos/` (4 arquivos)
- Deletar `shopman/shop/templates/gestao/` (3 arquivos)
- Deletar `shopman/shop/static/storefront/` (5 arquivos: css, js)
- Deletar `shopman/shop/static/img/` (2 arquivos)
- Deletar `shopman/shop/static/icon-*` (4 arquivos)
- Deletar `shopman/shop/static/js/gestures.js`
- **Manter:** `shopman/shop/templates/components/` (18 shared) + `shopman/shop/templates/admin/` (3)

**Verificação:** `make test` green — templates resolvem do app correto.

**Complexidade:** Baixa — só deletar. ~84 arquivos.

---

#### WP-H2: Criar adapters KDS + Alert, eliminar imports diretos shop→backstage

**Problema:** shop/ importa diretamente de `shopman.backstage.models` em 6 arquivos de produção (10 imports). Os adapters `kds.py` e `alert.py` foram planejados mas nunca criados. O adapter de promotion já existe e funciona como referência.

**Imports diretos a eliminar (produção, excluindo tests/):**

```
shop/services/kds.py          → KDSInstance, KDSTicket (3 imports)
shop/handlers/kds_dispatch.py  → KDSInstance, KDSTicket (1 import)
shop/kds_utils.py              → KDSInstance, KDSTicket (1 import)
shop/handlers/confirmation.py  → OperatorAlert (1 import)
shop/handlers/notification.py  → OperatorAlert (1 import)
shop/handlers/stock_alerts.py  → OperatorAlert (1 import)
shop/lifecycle.py              → OperatorAlert (1 import)
shop/management/commands/refresh_oven.py → KDSTicket (1 import)
```

**Criar:**
1. `shopman/shop/adapters/kds.py` — wraps KDSInstance/KDSTicket CRUD (criar ticket, listar, marcar done, buscar por order, etc.)
2. `shopman/shop/adapters/alert.py` — wraps OperatorAlert creation/query (criar alerta, escalar, buscar ativos)
3. Atualizar os 6 arquivos para usar `from shopman.shop.adapters import kds as kds_adapter` / `alert as alert_adapter`
4. **Também corrigir** `shopman/shop/adapters/pricing.py` L9: mover `from shopman.storefront.models import Promotion` para lazy import (module-level import em adapter é funcional mas inconsistente com o padrão dos outros adapters)

**Referência de padrão:** `shopman/shop/adapters/promotion.py` — lazy imports dentro de cada função.

**Verificação:** `make test` green + `grep -rn 'from shopman\.backstage' shopman/shop/ --include='*.py' | grep -v /tests/` retorna zero.

**Complexidade:** Média — 2 novos adapters + atualizar 6-7 arquivos.

---

#### WP-H3: Corrigir referências stale + redistribuir tests

**Problema A — Docstrings/loggers:** 33 referências a `shopman.shop.web` em 21 arquivos. Inclui 4 loggers com nomes antigos.

**Problema B — Tests mal-localizados:** `shop/tests/test_web.py` testa URLs e views de storefront/backstage. `shop/tests/test_flow_s6.py` testa `storefront._helpers._shop_status`. Devem estar nos tests das respectivas apps.

**Escopo A — Docstrings (21 arquivos):**
- `storefront/views/payment.py` — logger `shopman.shop.web.payment` → `shopman.storefront.views.payment`
- `storefront/views/devices.py` — logger `shopman.shop.web.devices` → `shopman.storefront.views.devices`
- `storefront/views/bridge.py` — logger `shopman.shop.web.bridge` → `shopman.storefront.views.bridge`
- `storefront/views/auth.py` — logger `shopman.shop.web.auth` → `shopman.storefront.views.auth`
- `backstage/projections/*.py` (6 arquivos) — docstrings referenciam `shopman.shop.web.views.*`
- `storefront/projections/*.py` (8 arquivos) — docstrings referenciam `shopman.shop.web.views.*`
- `shop/webhooks/urls.py` — 3 ocorrências (estes são imports reais de shop.webhooks, corretos — só confirmar)

**Escopo B — Redistribuir tests:**
- Mover classes de `shop/tests/test_web.py`:
  - `TestStorefrontURLs`, `TestHomeViewXFrame`, `TestViewImports`, `TestCheckoutUsesService`, `TestOrderCancelUsesService`, `TestTemplatetagsBridge`, `TestAPIBridge` → `storefront/tests/test_urls.py`
  - `TestWebhookURLs`, `TestWebhookImports` → ficam em `shop/tests/` (webhooks são de shop)
- Mover `test_flow_s6.py` (testa `_shop_status`) → `storefront/tests/test_shop_status.py`
- Após mover, deletar `shop/tests/test_web.py` se ficou vazio (ou renomear para test_webhooks.py se só sobrou webhook)

**Verificação:** `make test` green + `grep -rn 'shopman\.shop\.web' shopman/ | grep -v __pycache__` retorna só shop/webhooks/ (que é correto).

**Complexidade:** Baixa-Média — edições simples em muitos arquivos + 2 movimentações de test.

---

#### WP-H5: Emagrecer _helpers.py (627L → ~370L)

**Problema:** `storefront/views/_helpers.py` é um catchall de helpers de apresentação. Funções de shop status, hero, allergen info e carrier tracking não são "view helpers" — são projections ou services.

**Extrações:**
1. `_shop_status()` + `_format_opening_hours()` + `DAY_NAMES_PT` + `DAY_ORDER` (128 linhas) → `storefront/projections/shop_status.py`
   - São read models puros (consultam Shop.opening_hours, retornam dicts imutáveis)
2. `_hero_data()` (83 linhas) → `storefront/projections/hero.py`
   - É um builder de projection (consulta Promotion, Product, popular_skus)
3. `_allergen_info()` (23 linhas) → `storefront/projections/product_detail.py` (já existe, adicionar)
4. `_carrier_tracking_url()` + `CARRIER_TRACKING_URLS` (18 linhas) → `storefront/projections/order_tracking.py` (já existe, adicionar)

**Fica em _helpers.py (~375L):**
- `_get_channel_listing_ref`, `_get_price_q`, `_get_availability` — core pricing/availability
- `_line_item_is_d1` — D1 check
- `_to_storefront_avail`, `_storefront_availability_state`, `_availability_badge` — availability mapping
- `_promo_matches_for_vitrine`, `_best_auto_promotion_discount_q` — promo matching
- `_annotate_products` — product annotation (core function, 136L)

**Atualizar imports em:** views que usam as funções extraídas (home.py, info.py, catalog.py, tracking.py).

**Verificação:** `make test` green + `wc -l storefront/views/_helpers.py` < 400.

**Complexidade:** Média — 4 extrações + atualizar imports em ~6 views.

---

#### WP-H6: Emagrecer checkout.py (1012L → ~650L)

**Problema:** `CheckoutView` concentra validação, construção de contexto de address picker, e lógica de repricing — responsabilidades que devem ser services.

**Extrações:**
1. `_address_picker_context()` (78 linhas) → `storefront/services/address_picker.py`
   - Usado também em `account.py` (`_account_picker_context` é ~90% igual) → unificar
   - Criar `build_address_picker_context(addresses, *, form_data=None, preselected_id=None)` genérico
   - `_account_picker_context()` em account.py chama com `addresses=[]`
2. Métodos de validação de `CheckoutView` → `storefront/services/checkout_validation.py`:
   - `_validate_checkout_form` (23L)
   - `_validate_preorder` (36L)
   - `_validate_slot` (49L)
   - `_is_closed_date` (28L)
   - `_check_repricing` (43L)
   - `_check_cart_stock` (60L)
   - `_get_session_held_qty` (14L)
   - Total: ~253 linhas → service dedicado

**Fica em checkout.py (~650L):**
- `CheckoutView.get`, `CheckoutView.post` (fluxo principal)
- `_checkout_page_context` (contexto do GET)
- `_render_with_errors`
- `_get_payment_methods`, `_resolve_payment_method`, `_payment_method_available`, `_parse_address_data`
- `CheckoutOrderSummaryView`, `SimulateIFoodView`

**Verificação:** `make test` green + `wc -l storefront/views/checkout.py` < 700.

**Complexidade:** Média — 2 extrações + unificação do address picker + atualizar imports.

---

### Wave 2 — após Wave 1 (depende de WP-H2)

---

#### WP-H4: Testes arquiteturais — enforcement automatizado

**Problema:** A regra de dependência (`storefront → shop ← backstage`, sem cross-surface, shop só via adapters) existe como convenção mas não é enforçada por CI.

**Depende de:** WP-H2 (sem os adapters criados, os testes falhariam por violações existentes)

**Criar `shopman/shop/tests/test_architecture.py`:**

1. **test_no_cross_surface_imports** — storefront nunca importa backstage, backstage nunca importa storefront
   - Scan `shopman/storefront/**/*.py` para `from shopman.backstage` e `import shopman.backstage`
   - Scan `shopman/backstage/**/*.py` para `from shopman.storefront` e `import shopman.storefront`
   - Zero violations

2. **test_shop_imports_surfaces_only_via_adapters** — shop nunca importa storefront/backstage exceto em adapters/
   - Scan `shopman/shop/**/*.py` excluindo `shop/adapters/` e `shop/tests/`
   - Procurar `from shopman.(storefront|backstage)` e `import shopman.(storefront|backstage)`
   - Zero violations

3. **test_no_deep_kernel_imports_all_apps** — expandir o teste existente
   - `FRAMEWORK_ROOT` → scan shop/, storefront/, backstage/ (não só shop/)
   - Reusa `DEEP_IMPORT_RE` existente

4. **test_no_template_shadowing** — detectar templates duplicados
   - Listar templates de cada app dir
   - Detectar se dois apps registram o mesmo template path
   - Whitelist: `components/` (shared by design)

**Verificação:** `make test` green (todos os 4 novos testes passam).

**Complexidade:** Média — 4 novos testes, ~150 linhas.

---

## Paralelismo

```
Wave 1 (paralelo):
  WP-H1 ─── Purgar templates/statics duplicados
  WP-H2 ─── Criar adapters KDS + Alert
  WP-H3 ─── Fix docstrings + redistribuir tests
  WP-H5 ─── Emagrecer _helpers.py
  WP-H6 ─── Emagrecer checkout.py

Wave 2 (após WP-H2):
  WP-H4 ─── Testes arquiteturais
```

## Estimativa

| WP | Arquivos tocados | Complexidade |
|----|-----------------|-------------|
| WP-H1 | ~84 deletados | Baixa |
| WP-H2 | 2 novos + 7 editados | Média |
| WP-H3 | ~23 editados + 2 movidos | Baixa-Média |
| WP-H4 | 1 novo + 1 editado | Média |
| WP-H5 | 2 novos + ~8 editados | Média |
| WP-H6 | 2 novos + 2 editados | Média |
