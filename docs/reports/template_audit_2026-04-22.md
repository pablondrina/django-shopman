# Auditoria Completa de Templates — 2026-04-22

**Escopo:** 56 templates storefront + 19 templates backstage  
**Critérios:** Convenções CLAUDE.md, uso de projeções, omotenashi-first > mobile-first > whatsapp-first, Penguin UI (Tailwind v4 + Alpine.js), simplicidade/robustez/elegância, gambiarras ocultas

---

## Resumo Executivo

75 templates auditados. A grande maioria está limpa e alinhada com as convenções. Os problemas concentram-se em **3 categorias**:

1. **Alpine v2 API em backstage** — `__x.$data` quebrado silenciosamente no Alpine v3
2. **`fetch()` onde deveria ser HTMX** — padrão repetido em 6 templates de cart/produto/tracking
3. **Templates órfãos e tokens Tailwind v3** — 5 arquivos com vocabulário visual obsoleto

**Contagem de achados:** 5 P0 (quebrado/crítico), 10 P1 (violação de convenção), 8 P2 (qualidade/polish), 4 P3 (cosmético)

---

## P0 — CRÍTICO (comportamento quebrado ou silenciosamente errado)

### P0-1: `__x.$data` no POS e KDS (Alpine v2 morta)

**Arquivos:**
- `pos/index.html` linhas 389, 395: `document.querySelector('#pos-sangria-modal').__x.$data.open = true`
- `kds/partials/kds_js.html` linha 49: `el.__x.$data.elapsed = serverElapsed`

**Problema:** `__x.$data` é API interna do Alpine v2 que não existe no v3. No POS, os modais de sangria e fechamento de caixa **não abrem**. No KDS, o timer de elapsed **não sincroniza** após swap HTMX.

**Fix:** Usar `Alpine.$data(el)` (Alpine v3 API pública) ou `$dispatch` para comunicação entre componentes.

### P0-2: `OrderConfirmationView` bypassa projeção inteiramente

**Arquivo:** `storefront/views/tracking.py` → `OrderConfirmationView.get()`

**Problema:** Passa `order` (ORM model cru) direto ao template. Monta `enriched_items`, calcula ETA e `share_text` inline no view. O `PROJECTION-UI-PLAN` listava `OrderConfirmationProjection` — nunca foi criada.

**Impacto:** Template acopla em atributos do model; lógica de formatação duplicada; sem contrato tipado.

### P0-3: `_build_tracking_context()` — 130 linhas de código morto

**Arquivo:** `storefront/views/tracking.py`

**Problema:** Função de ~130 linhas que duplica exatamente a projeção `order_tracking.py`. Nunca é chamada. Lixo que confunde e aumenta superfície de manutenção.

### P0-4: `checkout_order_summary.html` — tokens Penguin v3 inteiros

**Arquivo:** `storefront/partials/checkout_order_summary.html`

**Problema:** Template inteiro usa vocabulário v3: `text-foreground`, `bg-warning-light`, `font-heading`, `text-muted-foreground`. Renderiza com fallbacks CSS mas não é canônico Penguin v4. Também faz comparação crua de `delivery_fee_q` no template.

### P0-5: `quick_reorder.html` — form POST sem HTMX, sem loading state

**Arquivo:** `storefront/partials/quick_reorder.html`

**Problema:** `<form method="post">` que faz full page reload. Sem `hx-post`, sem indicador de loading, sem feedback ao usuário. Em um contexto omotenashi (reorder rápido), é a pior experiência possível.

---

## P1 — VIOLAÇÃO DE CONVENÇÃO (funciona mas fere regras)

### P1-1: `fetch()` em vez de HTMX para cart operations (6 templates)

**Arquivos:**
- `product_detail.html` (2 fetch calls)
- `order_tracking.html` (1 fetch para rating)
- `_catalog_item_grid.html` (1 fetch)
- `availability_preview.html` (1 fetch)
- `stock_error_modal.html` (1 fetch)

**Nota:** Os fetch() em `_cart_page_content.html` e `cart_drawer.html` são **exceção documentada** — comentário explica que `htmx.ajax` causa crash no settle phase quando o source element é destruído pelo reload cascata. Esses estão OK.

**Problema nos demais:** Regra CLAUDE.md: "HTMX: toda comunicação com servidor". Os fetch() em product_detail e tracking não têm a mesma justificativa técnica.

### P1-2: `document.getElementById` em 12+ locais

**Arquivos e contextos:**
- `base.html` linha 140: logout form submit
- `checkout.html` linha 184: logout form submit (duplicado)
- `_bottom_nav.html` linha 36: badge sync (justificado — lê elemento vivo após swap)
- `auth_verify_code.html` linhas 54-55: countdown timer (deveria ser Alpine)
- `_catalog_item_grid.html`, `availability_preview.html`, `product_detail.html`, `stock_error_modal.html`: modal de erro de estoque
- `kds/partials/kds_js.html` linha 32: grid reference
- `pedidos/partials/pedidos_js.html` linhas 22, 25, 48: grid + cards
- `pedidos/index.html` linha 71: `Alpine.$data(document.getElementById(...))`

**Regra:** "NUNCA document.getElementById em templates. Usar $refs, x-data, $store."

### P1-3: `htmx.ajax()` imperativo no backstage

**Arquivos:**
- `pedidos/partials/card.html` linha 112: reject button via `htmx.ajax('POST', ...)`
- `pedidos/partials/card.html` linha 125: lazy detail via `htmx.ajax('GET', ...)`  
- `pedidos/partials/pedidos_js.html` linha 82: filter reload

**Regra:** HTMX declarativo nos atributos HTML. Imperativo só quando não há alternativa.

### P1-4: Forms `method="post"` sem HTMX no backstage

**Arquivos:**
- `pos/index.html` linha 297: cash close form (full page reload)
- `pos/cash_open.html` linha 17: cash open form
- `gestao/producao/index.html` linhas 10, 59: filter GET + bulk create POST
- `gestao/fechamento/index.html` linha 22: closing form

**Problema:** Full page reloads onde HTMX daria feedback instantâneo com loading states.

### P1-5: `auth_verify_code.html` — IIFE vanilla JS para countdown

**Arquivo:** `storefront/partials/auth_verify_code.html`

**Problema:** Countdown timer implementado com `document.getElementById` + `setInterval` em IIFE vanilla. Deveria ser componente Alpine com `x-data`, `x-text`, `x-show`.

### P1-6: `_tokens.html` — classList.toggle para dark mode

**Arquivo:** `storefront/partials/_tokens.html` linha 27

**Problema:** `h.classList.toggle('dark', isDark)` — manipulação direta de classe. Contexto: bootstrap de dark mode antes do Alpine carregar. **Pode ser exceção legítima** (precisa rodar antes do Alpine para evitar flash).

### P1-7: `pedidos/index.html` — camel modifier inconsistente

**Arquivo:** `pedidos/index.html`

**Problema:** `@htmx:after-swap.window` sem `.camel` modifier. Em `card.html` o padrão correto (`@htmx:after-swap.camel.window`) é usado. Inconsistência.

### P1-8: `base.html` — CSRF header em event listener global

**Arquivo:** `storefront/base.html` linha 404

**Detalhes:** `document.querySelector('meta[name="csrf-token"]').content` no handler global `htmx:configRequest`. Funciona, mas é o único `document.querySelector` que deveria existir (necessário para HTMX global config). **Aceitável como exceção.**

### P1-9: Projeção `hero.py` — inversão de dependência

**Arquivo:** `storefront/projections/hero.py`

**Problema:** Projeção importa de `views._helpers` — inversão da direção de dependência (projeção deveria ser importada pelo view, não o contrário). Além disso, `_hero_data()` não é chamada por nenhum view.

### P1-10: HTML hardcoded no view de produção

**Arquivo:** `backstage/views/production.py` — `bulk_create_work_orders()`

**Problema:** Constrói strings HTML com classes Tailwind direto no view Python. Template deveria renderizar isso.

---

## P2 — QUALIDADE / POLISH (funciona, mas abaixo do padrão)

### P2-1: Tokens Tailwind v3 em 4 templates

**Arquivos:**
- `access_link_invalid.html` — `text-foreground`, `text-h3`, `rounded-lg`, `text-muted-foreground`, inline `rgb(var(--primary))`
- `device_list.html` — `text-muted-foreground`, `text-error`, `bg-background/50`
- `_design_tokens_no_alpine.html` — `classList.add('dark')` (v3 bootstrap)
- `pos/partials/shift_summary.html` — shadcn token classes

**Fix:** Migrar para vocabulário Penguin v4.

### P2-2: `availability_preview.html` — duplicação de stepper

**Arquivo:** `storefront/partials/availability_preview.html`

**Problema:** Duplica integralmente a lógica de stepper/set() de `_catalog_item_grid.html`. Consome dicts crus de `_annotate_products()` em vez de projeção tipada. Item dict contém `"product": <Product ORM>`.

### P2-3: `account.py` — redundância Customer + projection

**Arquivo:** `storefront/views/account.py`

**Problema:** Passa `"account": projection` E `"customer": customer` (ORM cru) ao template. Todos os campos necessários já existem na projeção. Templates têm dois caminhos de acesso ao mesmo dado.

### P2-4: Views backstage passam raw Shop/KDSInstance

**Arquivos:**
- `backstage/views/kds.py`: `"instance": instance` (raw KDSInstance) + `"shop": shop`
- `backstage/views/orders.py`: `"shop": shop`
- `backstage/views/pos.py`: `"cash_session": cash_session` (raw CashRegisterSession)

**Problema:** Projeções existem mas models crus são passados em paralelo.

### P2-5: `history.html` — template órfão/duplicado

**Arquivo:** `storefront/history.html`

**Problema:** Duplicata de `order_history.html` sem projeção, com strings hardcoded e breadcrumb pattern antigo. Verificar se alguma rota aponta para ele — se não, deletar.

### P2-6: Hardcoded strings que deveriam ser omotenashi copy

**Arquivos:**
- `closing_awareness.html`: "Ultimos" (falta acento: "Últimos")
- `shop_status_badge.html`: strings de status hardcoded
- `urgency_badge.html`: textos de urgência hardcoded
- `birthday_banner.html`: mensagem de aniversário hardcoded

**Fix:** Mover para `OmotenashiCopy` keys.

### P2-7: `menu.html` — URL hardcoded em Alpine

**Arquivo:** `storefront/menu.html` linha 146

**Problema:** `/produto/` hardcoded dentro de JavaScript Alpine. Deveria ser injetado via `data-url` ou template tag `{% url %}`.

### P2-8: `checkout.html` — hx-indicator órfão

**Arquivo:** `storefront/checkout.html` linha 415

**Problema:** `hx-indicator` em botão dentro de `<form method="post">` sem `hx-post`. O spinner nunca dispara.

---

## P3 — COSMÉTICO

### P3-1: `prototype_menu.html` — template de protótipo em produção
Provavelmente sobra de desenvolvimento. Se não é usado em nenhuma rota, deletar.

### P3-2: `MutationObserver` em `_bottom_nav.html`
Não está na lista de exceções documentadas (IntersectionObserver, geolocation, clipboard, service worker). Funciona, mas a convenção deveria listá-lo explicitamente.

### P3-3: Navigator.vibrate ausente no KDS/Pedidos
Alertas sonoros existem, mas `navigator.vibrate()` para feedback háptico em tablet não está implementado. Seria omotenashi para operadores.

### P3-4: Context processor injeta `Shop` ORM cru globalmente
`storefront/context_processors.py` → `shop()` injeta `storefront` como `Shop` model. Deliberado e funcional, mas significa que todos os templates têm acesso direto a atributos do ORM sem contrato tipado. Aceitar como design decision documentada.

---

## Padrões Positivos (o que está BEM)

- **Projeções tipadas** usadas corretamente em 90%+ dos surfaces (cart, checkout, tracking, KDS board, POS, order queue)
- **HTMX polling** correto (innerHTML, intervalos razoáveis, hx-trigger="every Ns")
- **Dark mode tokens** consistentes na maioria dos templates
- **Touch targets** respeitados (min 44px) em storefront e backstage
- **SSE integration** correta para stock updates
- **OmotenashiCopy** bem integrado nos templates de alto tráfego (tracking, confirmation, home, PIX)
- **Empty states** presentes na maioria das listas
- **Loading states** via `hx-indicator` + `hx-on::before-request` na maioria dos forms HTMX
- **fetch() documentado** em cart templates com justificativa técnica legítima (htmx.ajax crash)
- **Mobile-first layout** consistente com Tailwind responsive utilities

---

## Recomendação de Plano de Ação

**Bloco A (P0 — fazer agora):**
1. Fix `__x.$data` → `Alpine.$data()` no POS e KDS (3 ocorrências, 30 min)
2. Criar `OrderConfirmationProjection` e eliminar code morto em tracking.py (~2h)
3. Migrar `checkout_order_summary.html` para tokens Penguin v4 (1h)
4. Converter `quick_reorder.html` para `hx-post` com loading state (30 min)

**Bloco B (P1 — próxima iteração):**
5. Converter fetch() → HTMX em product_detail, order_tracking rating (1.5h)
6. Refatorar `auth_verify_code.html` countdown para Alpine (30 min)
7. Substituir `document.getElementById` por `$refs` onde possível (1h)
8. Converter forms backstage para HTMX (producao, fechamento, POS cash) (2h)
9. Limpar `hero.py` (deletar ou corrigir dependência) (15 min)
10. Mover HTML de `bulk_create_work_orders` para template (30 min)

**Bloco C (P2 — polish):**
11. Migrar 4 templates com tokens v3 para Penguin v4 (1.5h)
12. Extrair stepper compartilhado de catalog_item_grid/availability_preview (1h)
13. Remover redundância Customer/projection em account.py (30 min)
14. Deletar `history.html` e `prototype_menu.html` se órfãos (15 min)
15. Mover hardcoded strings para OmotenashiCopy keys (1h)
16. Fix URL hardcoded e hx-indicator órfão em menu/checkout (15 min)

**Estimativa total:** ~12h de trabalho, priorizável em 3 blocos independentes.
