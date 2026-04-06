# STOREFRONT-PLAN.md — Storefront Excellence + Bugs + ProductionFlow

## Contexto

Reestruturação R0-R9 concluída. Core e App sólidos. Agora: polir a experiência do usuário final. O storefront funciona mas acumulou dívidas. O objetivo é reconstruí-lo com excelência — simples, robusto, elegante, configurável via Admin.

**Decisões-chave:**
- Design tokens antigos → **descartados**. Redefinir do zero.
- Estética do **Oxbow UI** (tokens, visual), estrutura/acessibilidade do **Penguin UI**
- Primitivos do Penguin (modals, forms, buttons) + e-commerce do Oxbow (product cards, cart, checkout)
- **Configuração via Admin** — operador muda cores/fontes → storefront reflete
- ProductionFlow como cidadão de primeira classe

---

## Análise de Bibliotecas

| Lib | Para quê | Pontos fortes |
|-----|----------|---------------|
| **Oxbow UI** (427 blocos, MIT, TW v4) | Design tokens + e-commerce blocks | Único com product lists, carts, checkout. Visual moderno. |
| **Penguin UI** (40 comp, MIT, TW v4) | Primitivos + acessibilidade | ARIA, focus traps, keyboard nav. Melhor estrutura de componentes. |

**Abordagem:** Penguin UI para primitivos acessíveis + Oxbow UI para visual/tokens/e-commerce. Copy-paste em Django templates. Alpine.js para interatividade. HTMX para servidor.

---

## WP-S0: Address Bugs — Google Places + Focus

**Objetivo:** Corrigir bugs urgentes do checkout.

### Entregáveis

1. **Google Places proximity bias** (`checkout_address.html` ~L205)
   - Adicionar `locationBias` com coordenadas do Shop (lat/lng)
   - Fallback: cidade/estado do Shop
   - Passar coords via context processor
   - Resultado: "Rua Henrique Dias" → Londrina, não Bahia

2. **Focus após transição** (`checkout_address.html` ~L211-280)
   - Root cause: `$nextTick()` não espera `x-transition` CSS (~300ms)
   - Fix: `setTimeout(() => smartFocus(), 350)` nos 3 pontos:
     - place_changed listener (~L217)
     - handleCepResult (~L266)
     - mode switches (~L21, L28, L44)

3. **Map init timing** — mover para mesmo setTimeout + `trigger('resize')`

4. **CEP debounce** — só disparar quando CEP completo (8+ dígitos)

### Arquivos
- `shopman-app/shopman/templates/storefront/partials/checkout_address.html`
- `shopman-app/shopman/templates/storefront/checkout.html`
- `shopman-app/shopman/context_processors.py`

---

## WP-S1: Design System — Tokens do Zero

**Objetivo:** Novo design token system inspirado no Oxbow UI, configurável via Admin.

### Entregáveis

1. **Novo `_design_tokens.html`** — inspirado no Oxbow UI
   - CSS variables com naming semântico (ex: `--color-primary`, `--color-surface`, `--color-muted`, `--radius-*`, `--shadow-*`)
   - Light + dark mode
   - Typography scale (heading, body, caption)
   - Spacing, radius, shadows
   - **Gerado dinamicamente** a partir do model Shop

2. **Novo `colors.py`** — gerador de tokens
   - Input: primary color, secondary color, color mode (light/dark/auto)
   - Output: paleta completa (background, surface, border, muted, accent, success/warning/error/info + foreground variants)
   - Baseado em OKLCH (manter — é superior)
   - Naming convention alinhada com Oxbow

3. **Admin configurável**
   - Color picker widget para primary/secondary color
   - Dropdown para color mode (light/dark/auto)
   - Font selector (heading + body)
   - Preview das cores geradas
   - **Reflexo imediato**: operador salva → reload do storefront → cores novas

4. **Tailwind config atualizado**
   - `tailwind.config.js` usa CSS variables (ex: `colors: { primary: 'var(--color-primary)' }`)
   - Permite que Tailwind classes (`bg-primary`, `text-surface`) resolvam para os tokens

### Critério de Sucesso
- Operador muda `primary_color` no admin → storefront usa cor nova
- Light/dark mode funciona
- Zero hardcoded colors nos templates (tudo via tokens)

### Arquivos
- `shopman-app/shopman/templates/storefront/partials/_design_tokens.html` (reescrever)
- `shopman-app/shopman/colors.py` (reescrever)
- `shopman-app/shopman/admin/shop.py` (color picker widget)
- `shopman-app/shopman/models/shop.py` (campos de design se necessário)
- `shopman-app/tailwind.config.js` (CSS variable mapping)

---

## WP-S2: Component System — Rebuild com Penguin + Oxbow

**Objetivo:** Reconstruir componentes com base no Penguin UI (estrutura) + Oxbow UI (visual).

### Entregáveis

1. **Primitivos (base Penguin UI, com acessibilidade)**
   - Modal/bottom sheet — focus trap, ARIA, ESC to close, backdrop click
   - Toast — auto-dismiss, acessibilidade, variantes (success/error/info)
   - Button — variantes (primary/secondary/ghost/destructive), loading state, disabled
   - Input — validation states, error messages inline, focus ring
   - Toggle/switch — ARIA role, keyboard accessible
   - Badge — variantes (solid/outline, cores semânticas)
   - Skeleton — loading placeholder
   - Stepper — steps com estado (active/completed/pending)
   - Radio cards — seleção visual estilo card

2. **E-commerce (base Oxbow UI, adaptado)**
   - Product card — imagem, preço, botão add, skeleton loading, badge D-1
   - Cart item — qty stepper, remove, preço, compacto
   - Cart drawer — sidebar com items + summary + CTA
   - Checkout layout — steps + form + summary
   - Order status — timeline visual do pedido
   - Payment status — PIX QR, card status, countdown

3. **Eliminar duplicados**
   - cart_item + cart_drawer_item → componente único com `compact` param
   - 2x bottom_sheet → uma implementação
   - Padronizar eventos Alpine: `open-{id}` / `close-{id}`

4. **Header + Bottom Nav**
   - Header responsivo (logo, search, cart badge)
   - Bottom nav mobile (home, menu, cart, account)
   - Floating cart button (mobile)

### Critério de Sucesso
- Zero duplicados
- ARIA roles em todos os interativos
- Keyboard nav funciona
- Visual coerente Oxbow-like

### Arquivos
- `shopman-app/shopman/templates/components/` (rebuild)
- `shopman-app/shopman/templates/storefront/partials/` (rebuild)
- `shopman-app/shopman/templates/storefront/base.html` (Alpine stores)

### Pendência registrada (pós-S2)
- **Focus trap completo no drawer do carrinho** — hoje há foco inicial no botão fechar e restauração ao fechar; falta ciclo Tab em todo o painel com conteúdo HTMX dinâmico.

---

## WP-S3: Checkout Flow — Robustez

**Objetivo:** Checkout robusto e à prova de edge cases.

### Entregáveis

1. **Validação visual** — erros → borda vermelha + mensagem + focus
2. **Cart state sync** — check estoque antes do submit
3. **Min order warning** — replicar aviso "Faltam R$X" no checkout
4. **Coupon unificado** — tanto no cart drawer quanto no checkout

### Pendência crítica registrada

- **Bloqueio duro de estoque ainda incompleto**
  - Sintoma observado: o storefront avisa quando a quantidade disponível é menor que a solicitada, mas ainda pode permitir prosseguir em alguns cenários, tanto ao adicionar item no carrinho quanto ao fechar o pedido.
  - Correção futura necessária:
    1. impedir ajuste/adição no carrinho quando `qty > available_qty`
    2. bloquear submissão final do checkout de forma determinística no backend
    3. cobrir com teste e2e de concorrência/estoque insuficiente

### Arquivos
- `shopman-app/shopman/templates/storefront/checkout.html`
- `shopman-app/shopman/web/views/checkout.py`

---

## WP-S4: Configurabilidade — Admin Live

**Objetivo:** Operador muda configuração → storefront reflete na hora.

### Entregáveis

1. **Color picker** no Admin Unfold para primary/secondary
2. **Font selector** com preview visual
3. **Preview panel** (stretch) — iframe com storefront no admin

### Arquivos
- `shopman-app/shopman/admin/shop.py`
- `shopman-app/shopman/models/shop.py`

---

## WP-S5: ProductionFlow — Produção First-Class

**Objetivo:** Lifecycle flow para produção, paralelo ao OrderFlow.

### Entregáveis

1. **`shopman/production_flows.py`**
   ```
   BaseProductionFlow          # plan → start → close/void
   ├── StandardFlow            # plan → produzir → fechar
   ├── ForecastFlow            # plan → produzir → auto-fechar
   └── SubcontractFlow         # plan → enviar → receber → fechar
   ```
   Fases: `on_planned`, `on_started`, `on_closed`, `on_voided`

2. **Wire signal** em `apps.py`: `production_changed` → `dispatch_production()`

3. **`shopman/services/production.py`** — reserve materials, emit goods, notify

4. **Recipe.production_flow** — config por receita (default: "standard")

### Impacto no Core: **ZERO**. Usa signals existentes.

### Arquivos
- `shopman-app/shopman/production_flows.py` (novo)
- `shopman-app/shopman/services/production.py` (novo)
- `shopman-app/shopman/apps.py` (wire signal)

---

## WP-S6: Flow Review — Incongruências

**Objetivo:** Audit final de todos os fluxos.

### Entregáveis
1. Audit end-to-end: Cart → Checkout → Payment → Tracking
2. BusinessHours: definir comportamento correto
3. Pipeline audit: guards, transições, edge cases
4. Cancelamento: 4 paths → 1 service

---

## Ordem de Execução

```
WP-S0  Address Bugs            (urgente)
  ↓
WP-S1  Design Tokens do Zero   (fundação visual)
  ↓
WP-S2  Component Rebuild       (depende de S1)
  ↓
WP-S3  Checkout Robustez       (depende de S2)
  ↓
WP-S4  Admin Live Config       (depende de S1)
  ↓
WP-S5  ProductionFlow          (independente, paralelo com S2-S4)
  ↓
WP-S6  Flow Review             (audit final)
```

## Verificação

- `make test` verde após cada WP
- `make seed && make run` funcional
- Manual: endereço → proximity, foco → digitar, checkout e2e, admin → cores, production flow

## Fora de Escopo (registrado em memória)

- PDV standalone, KDS standalone, Gestor de Pedidos redesign
