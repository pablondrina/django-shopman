# WP-S2 Continuação: Componentes Reais Penguin + Oxbow

## O que já foi feito

### WP-S1 (Design Tokens) — CONCLUÍDO
- `colors.py` reescrito: `generate_neutral_scale` com target L values calibrados ao Oxbow
- Paleta Oxbow aplicada: primary preto (#1a1a1a), secondary cinza (#f5f5f5), accent coral (#d4643b), background branco (#ffffff)
- Shadows multi-layer Oxbow (blue-tinted rgba) em `_design_tokens.html`
- Radius: 6/12/16/20px. Font: Inter.
- Tokens Oxbow completos salvos em memória (`reference_oxbow_tokens.md`)

### WP-S2 Fases 1-4 — CONCLUÍDO (estrutura)
- 8 primitivos reescritos (button, input, badge, toast, bottom_sheet, toggle, stepper, radio_cards)
- 9 e-commerce partials reescritos (product_card, cart_item merged, cart_drawer, cart_content, order_status, payment_status, cart_warnings, coupon_section, product_card_skeleton)
- 3 estrutura (header, bottom_nav, floating_cart_button)
- product_detail.html atualizado
- Deletados: _button_inner.html, _toast.html, cart_drawer_item.html, partials/_bottom_sheet.html

### Visual cleanup — CONCLUÍDO
- Header: branco/blur Oxbow (`bg-background/80 backdrop-blur border-b border-border`)
- Footer: preto (`bg-foreground text-background`)
- Promo cards: `bg-muted border-border`, badges `bg-foreground`
- Collection pills: preto ativo, cinza inativo
- Product card badges: `bg-foreground text-background`

## O que falta

### 1. Buscar código REAL dos componentes Penguin UI
O Penguin UI é open source: `github.com/nicepenguin/penguinui`. Buscar no GitHub:
- **Buttons** — classes Tailwind reais (não os vazios do WebFetch)
- **Modal/Dialog** — focus trap Alpine, ESC, backdrop
- **Toggle/Switch** — role=switch, aria-checked, keyboard
- **Toast/Notification** — auto-dismiss, aria-live
- **Navbar** — mobile menu Alpine, aria-expanded, aria-controls
- **Text Input** — error state, validation, aria-describedby
- **Radio Group** — aria, keyboard arrows
- **Badge** — variantes com classes

### 2. Buscar código REAL dos componentes Oxbow e-commerce
Navegar no browser (com permissões) ao Oxbow playground:
- `oxbowui.com/playground/ecommerce/product-list/01/` até `/10/`
- `oxbowui.com/playground/ecommerce/product-details/01/` até `/08/`
- `oxbowui.com/playground/ecommerce/category-previews/01/` até `/04/`
- Cada um: clicar `<>` code view → `get_page_text()` para extrair HTML
- OU: acessar iframe direto (`/iframe/ecommerce/...`) e extrair via JS

### 3. Adaptar templates com código real
Com os componentes reais em mãos, reescrever os templates Django:
- **Primitivos**: substituir nossos componentes pela estrutura Penguin (ARIA, focus, keyboard) + visual Oxbow (classes, tokens)
- **E-commerce**: substituir product_card, cart, checkout pela estrutura Oxbow
- **Páginas restantes**: login, account, checkout, tracking, payment — aplicar os novos componentes

### 4. Páginas que ainda usam estilo antigo
Verificar e atualizar estas páginas para usar os novos componentes e o visual Oxbow:
- `storefront/login.html` — form, buttons
- `storefront/account.html` — tabs, forms, toggles
- `storefront/checkout.html` — steps, form, address, summary
- `storefront/payment.html` — PIX QR, status
- `storefront/tracking.html` — order status, timeline
- `storefront/order_confirmation.html` — summary, CTA
- `storefront/history.html` — order list, cards
- `storefront/como_funciona.html` — info page
- `storefront/home.html` — landing page

## Tokens Oxbow (referência rápida)

```
Light: primary=oklch(0.205 0 0), bg=oklch(1 0 0), fg=oklch(0.145 0 0)
       muted=oklch(0.97 0 0), border=oklch(0.922 0 0), ring=oklch(0.708 0 0)
       accent=oklch(0.659 0.23 35.2), brand=accent
Dark:  primary=oklch(0.985 0 0), bg=oklch(0.145 0 0), fg=oklch(0.985 0 0)
       muted=oklch(0.269 0 0), border=oklch(0.269 0 0), ring=oklch(0.439 0 0)
       accent=oklch(0.769 0.188 70.08)
Radius: base=0.625rem, sm=calc(base-4px), md=calc(base-2px), lg=base, xl=calc(base+4px)
Font: Inter (sans), LTRemark (serif), Geist Mono (mono)
```

## Princípios (manter)
1. Penguin = estrutura (ARIA, focus trap, keyboard nav, Alpine patterns)
2. Oxbow = visual (tokens, classes, e-commerce blocks)
3. HTMX ↔ servidor, Alpine ↔ DOM
4. Zero hardcoded colors — tudo via tokens
5. Remoção via `$store.confirm`, qty via stepper, modais via bottom_sheet

## Verificação
1. `make test-framework` verde
2. `make run` → navegar todas as páginas
3. ARIA: Chrome Accessibility panel
4. Dark mode: `document.documentElement.classList.toggle('dark')`
