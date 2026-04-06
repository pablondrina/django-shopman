# WP-S2: Component System — Rebuild do Zero

## Contexto

WP-S0 (bugs) e WP-S1 (design tokens OKLCH) concluídos. O sistema de tokens está funcional: CSS variables semânticas, dark mode via `.dark` class + JS auto-detect, Tailwind mapeado. Agora: reconstruir TODOS os componentes do zero, inspirados em Penguin UI (estrutura/ARIA) e Oxbow UI (visual/e-commerce).

## Referências

- **Penguin UI** (https://penguinui.com) — Primitivos acessíveis: ARIA roles, focus traps, keyboard nav, Alpine.js patterns
- **Oxbow UI** (https://oxbowui.com) — Visual e-commerce: product cards, cart, checkout. Estética clean: rounded-xl, shadow-sm→md hover, transitions, group-hover:scale-105 em imagens
- **STOREFRONT-PLAN.md** na raiz — plano geral WP-S0 a WP-S6

## Abordagem

Copy-paste e adaptação em Django templates. Sem libs externas (convenção do projeto). Cada componente é `{% include %}` com parâmetros via `with`. Frontend: HTMX ↔ servidor, Alpine.js ↔ DOM (convenção CLAUDE.md).

## Ordem: Primitivos → E-commerce → Estrutura

### Fase 1: Primitivos (Penguin-inspired)

Reescrever do zero cada arquivo em `framework/shopman/templates/components/`.

| # | Componente | Arquivo | Params | ARIA |
|---|-----------|---------|--------|------|
| 1 | **Button** | `_button.html` | variant(primary/secondary/outline/ghost/destructive), size(sm/md/lg), disabled, loading, icon_only, type, href, label, icon, full_width, hx_*, x_click, css_class, aria_label | focus-visible:ring |
| 2 | **Input** | `_input.html` | name, label, type, placeholder, error, hint, required, icon, x_model, inputmode, maxlength, x_mask | aria-describedby, aria-invalid, aria-required |
| 3 | **Badge** | `_badge.html` | variant(default/success/warning/error/info/outline/d1/sold_out), size(sm/md), text | aria-label se info-only |
| 4 | **Toast** | polir `$store.toast` em `base.html` | Manter Alpine store. Polir: ícones SVG (success/error/warning/info), auto-dismiss 4s, role=alert aria-live=assertive | role=alert |
| 5 | **Modal/Bottom Sheet** | `_bottom_sheet.html` | store_name, title, max_width, show_handle | role=dialog, aria-modal, focus trap (first focusable on open, restore on close), ESC |
| 6 | **Toggle** | `_toggle.html` | name, label, checked, x_model, disabled | role=switch, aria-checked |
| 7 | **Stepper** | `_stepper.html` | value, min, max, name, x_model, aria_label, hx_post, hx_target, compact | aria-label nos botões +/-, aria-valuenow/min/max, long-press acceleration |
| 8 | **Radio Cards** | `_radio_cards.html` | name, options, selected, x_model, cols | role=radiogroup, role=radio, aria-checked, keyboard arrows |

**Deletar** após reescrita:
- `_button_inner.html` (inlined no novo `_button.html`)
- `_toast.html` (substituído por $store.toast em base)

### Fase 2: E-commerce (Oxbow-inspired)

Reescrever em `framework/shopman/templates/storefront/partials/`.

| # | Componente | Arquivo | Descrição |
|---|-----------|---------|-----------|
| 9 | **Product Card** | `product_card.html` | Reescrever: imagem com aspect-square + object-cover + group-hover:scale-105, badges (D-1, sold_out), preço com strikethrough, botão add com HTMX. Featured variant (col-span-2). Skeleton loading. `aria-label="Adicionar {nome} ao carrinho"`. Corrigir `bg-error-light0` → `bg-error-light`. |
| 10 | **Product Card Skeleton** | `product_card_skeleton.html` | Placeholder com animate-pulse, aspect-square |
| 11 | **Cart Item** | `cart_item.html` | **MERGE** cart_item + cart_drawer_item. Param `compact` para drawer mode. Usar `{% include "components/_stepper.html" %}` para qty. Remoção via `$store.confirm` (não hx-confirm). |
| 12 | **Cart Drawer** | `cart_drawer.html` | Sidebar: lista items (compact), min-order progress, coupon, subtotal, CTA. Usa novo cart_item com compact=True. |
| 13 | **Cart Content** | `cart_content.html` | Full page: lista items, warnings, coupon, totals, botão checkout. Usa novo cart_item sem compact. |
| 14 | **Order Status** | `order_status.html` | Timeline visual com steps (icons por status), tempo estimado, status badge |
| 15 | **Payment Status** | `payment_status.html` | PIX: QR code + copy button + countdown. Card: status display. |
| 16 | **Cart Warnings** | `cart_warnings.html` | Estoque: badges de warning, botão ajustar/remover |
| 17 | **Coupon Section** | `coupon_section.html` | Input + apply button ou badge de cupom aplicado |

**Deletar** após merge:
- `cart_drawer_item.html` (mergeado em cart_item com compact param)
- `storefront/partials/_bottom_sheet.html` (duplicata, usar components/)

### Fase 3: Estrutura

| # | Componente | Arquivo | Mudanças |
|---|-----------|---------|----------|
| 18 | **Header** | `components/_header.html` | Reescrever: `role="banner"`, nav com `aria-label="Navegação principal"`, search inline desktop, logo, cart badge via HTMX, mobile hamburger. Visual Oxbow (sticky, shadow-sm on scroll) |
| 19 | **Bottom Nav** | `components/_bottom_nav.html` | Reescrever: `role="navigation" aria-label="Menu principal"`, 3 tabs (Menu/Pedidos/Conta), badge de pedidos via HTMX polling, `aria-current="page"` |
| 20 | **Floating Cart Button** | `components/_floating_cart_button.html` | Polish: mobile FAB acima bottom nav, badge count, safe-area |

### Fase 4: Fix product_detail.html

- Corrigir `bg-error-light0` → `bg-error-light`
- Verificar que usa os novos components via include

## Princípios de Design (OBRIGATÓRIO)

1. **ARIA roles em tudo**: dialog, switch, radiogroup, radio, alert, navigation, banner
2. **Focus management**: trap em modais, restore on close, focus-visible:ring-2
3. **Keyboard nav**: ESC fecha modais, arrows em radio cards, Enter/Space em toggles
4. **Zero hardcoded colors**: tudo via design tokens (bg-primary, text-foreground, etc.)
5. **Oxbow visual**: rounded-xl cards, shadow-sm→shadow-md hover, transitions, group-hover:scale-105
6. **Consistent patterns**: remoção via `$store.confirm`, qty via `_stepper.html`, modais via `_bottom_sheet.html`
7. **HTMX ↔ servidor, Alpine ↔ DOM**: nunca onclick/onchange, sempre @click/x-show/$store

## Estado Atual dos Componentes (inventário)

### components/ (17 arquivos, 865L total)
- `_button.html` (19L) + `_button_inner.html` (51L) — funcional mas split desnecessário
- `_badge.html` (31L) — funcional, sem ARIA
- `_bottom_nav.html` (50L) — funcional, sem role/aria-label
- `_bottom_sheet.html` (73L) — Alpine store pattern, responsive, ARIA parcial, sem focus trap
- `_cart_added_confirmation.html` (64L) — toast de "adicionado", funcional
- `_floating_button.html` (34L) — CTA fixo, funcional
- `_floating_cart_button.html` (29L) — FAB mobile, funcional
- `_focus_overlay.html` (98L) — fullscreen search/overlay, funcional
- `_header.html` (80L) — sticky header, sem role=banner
- `_input.html` (55L) — text input com validation, bom ARIA base
- `_radio_cards.html` (60L) — radio cards, sem role=radiogroup
- `_skeleton.html` (40L) — loading placeholder, funcional
- `_stepper.html` (83L) — qty com long-press, funcional
- `_toggle.html` (43L) — dual-button toggle, sem role=switch
- `_toast.html` (22L) — não usado (Alpine store em base.html faz o trabalho)

### storefront/partials/ (33 arquivos, 2005L total)
- `cart_item.html` (66L) — full page cart item, remoção via hx-confirm
- `cart_drawer_item.html` (60L) — **DUPLICATA** de cart_item para drawer
- `cart_content.html` (55L) — full page cart wrapper
- `cart_drawer.html` (97L) — drawer sidebar
- `product_card.html` (109L) — grid card com featured variant, **bug: bg-error-light0**
- `_bottom_sheet.html` (52L) — **DUPLICATA** de components/_bottom_sheet
- (outros 27 arquivos funcionais)

## Verificação

1. `make test-framework` verde
2. `make seed && make run` → navegar: home → menu → product detail → add → cart drawer → remove → checkout
3. ARIA: Chrome DevTools → Accessibility panel, tab through interativos
4. Dark mode: `document.documentElement.classList.toggle('dark')` no console
5. Mobile: responsive ≤ 375px, verificar bottom sheet, FAB, bottom nav
