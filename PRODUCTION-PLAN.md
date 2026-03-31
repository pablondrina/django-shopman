# PRODUCTION-PLAN.md — Django Shopman

> Plano para tornar o Shopman um produto de excelência em fluxos, UX e operação.
> Benchmarks: iFood (storefront), Take.app (simplicidade + backoffice), Shopify (admin), Toast/Square (KDS).
> Princípio: confiar no Core, evoluir o App. Cada WP dimensionado para uma sessão do Claude Code.
> Infra, deploy, segurança, SEO, LGPD → plano separado posterior.

---

## Diagnóstico

O Core oferece muito mais do que o App consome. Há capacidades inteiras não utilizadas (ProductComponent,
StockAlerts automation, StockPlanning, Customer Merge/Consent, import/export). Há fluxos com falhas
silenciosas (payment timeout sem auto-cancel, race condition webhook+cancel, notification failure sem
escalação). E a UX do storefront, embora funcional, está distante de um app-like mobile-first (touch
targets subdimensionados, sem bottom nav, sem gestos, checkout longo demais).

**Pré-requisito**: Executar IMPROVEMENTS-PLAN (WP-1 a WP-3) antes deste plano.

---

## Status Geral

| WP | Área | Status | Deps |
|----|------|--------|------|
| F0 | Correções de Fluxo & Robustez | ✅ | IMPROVEMENTS-PLAN |
| F1 | Design System Mobile-First | ✅ | — |
| F2 | Storefront — Navegação App-Like | ✅ | F1 |
| F3 | Storefront — Catálogo & Discovery | ✅ | F1, F2 |
| F4 | Storefront — Carrinho & Checkout | ✅ | F1, F2 |
| F5 | Storefront — Pagamento & Confirmação | ✅ | F4 |
| F6 | Storefront — Tracking & Pós-Venda | ✅ | F5 |
| F7 | Storefront — Conta, Loyalty & Preferências | ✅ | F2 |
| F8 | Gestor de Pedidos — Painel do Operador | ✅ | F0 |
| F9 | KDS — Kitchen Display System | ✅ | F8 |
| F10 | Admin — POS & Operação Diária | ✅ | F0 |
| F11 | Admin — Backoffice & Configuração da Loja | ⬚ | — |
| F12 | Admin — Dashboard, Analytics & BI | ⬚ | F10 |
| F13 | Integração Plena: Vendas ↔ Produção ↔ Estoque ↔ CRM | ✅ | F0, F8, F9 |
| F14 | Notificações Multi-Canal | ⬚ | F6 |
| F15 | Canal WhatsApp | ⬚ | F14 |
| F16 | Canal Marketplace (iFood) | ⬚ | F13 |
| F17 | Testes E2E & Stress de Fluxos | ⬚ | Todos |
| F18 | Schema Governance — JSONField Docs & Validação | ⬚ | — |

### Dívidas Técnicas (cross-WP)

| Item | Origem | Status |
|------|--------|--------|
| Cores do storefront resetam no seed (secondary/accent/neutral vazios) | Seed não incluía cores secundárias | ✅ Corrigido — seed agora inclui todas as cores |
| `#cart-badge-desktop` → `#cart-badge-header` (hx-target stale) | Refactor do header para componente, templates não atualizados | ✅ Corrigido + teste de regressão em `test_storefront_flow.py` |
| `:hx-vals` Alpine binding incompatível com HTMX | Alpine `defer` resolve binding depois do HTMX processar | ✅ Corrigido → `hx-vals="js:..."` + teste de regressão |
| `_design_tokens.html` inclui Alpine — views standalone precisam de `_design_tokens_no_alpine.html` | KDS e POS precisam controlar ordem de carregamento do Alpine | ✅ Resolvido — partial separado criado |
| `is_primary` ausente nos CollectionItems do seed | KDS dispatch precisa de primary collection para rotear items | ✅ Corrigido no seed |

---

## WP-F0: Correções de Fluxo & Robustez

**Objetivo**: Eliminar falhas silenciosas e edge cases não tratados. O sistema nunca engole um erro.

### 0.1 Auto-cancel em timeout de pagamento

**Problema**: Pedido com PIX fica CONFIRMED indefinidamente se cliente não paga.
Stock holds expiram naturalmente, mas o pedido permanece ativo, poluindo o dashboard.

**Solução**:
- Em `hooks.py`, ao gerar PIX (`on_confirmed` pipeline), criar directive `PAYMENT_TIMEOUT`
  com `scheduled_at = now + settings.PIX_TIMEOUT` (15 min default).
- `PaymentTimeoutHandler`: se order ainda CONFIRMED e payment não captured →
  transicionar para CANCELLED, liberar holds, notificar cliente.
- Se payment foi captured entre criação e execução da directive → no-op (idempotente).
- Config: `PIX_TIMEOUT_MINUTES` no ChannelConfig (default 15, override por canal).

### 0.2 Race condition: webhook de pagamento + pedido já cancelado

**Problema**: Se operador cancela e webhook de pagamento chega quase simultaneamente,
`InvalidTransition` é levantado e o pagamento confirmado nunca é reembolsado.

**Solução**:
- Em `on_payment_confirmed()`: capturar `InvalidTransition`.
- Se order.status == CANCELLED → criar directive `PAYMENT_REFUND` automático.
- Log: `WARNING payment_confirmed_after_cancel order={ref} intent={id}`.
- Notificar operador via canal interno (admin notification).

### 0.3 Customer self-service cancellation

**Problema**: Só operador pode cancelar. Cliente não tem botão nem endpoint.

**Solução**:
- View `POST /pedido/{ref}/cancelar/` no storefront.
- Permitido apenas se status in (NEW, CONFIRMED) e payment não captured.
- Se payment captured → mostrar "Entre em contato para cancelar" + link WhatsApp.
- Confirmação modal: "Deseja mesmo cancelar?"
- Após cancelar: release holds, notificar operador, atualizar tracking page.

### 0.4 Notification failure → escalação

**Problema**: Se NotificationBackend falha 5x, falha silenciosamente. Cliente não recebe nada.

**Solução**:
- Após max retries, criar `OperatorAlert` (novo modelo leve em shop/):
  - `type`: notification_failed, payment_failed, stock_discrepancy.
  - `severity`: warning, error, critical.
  - `message`: texto descritivo.
  - `order_ref`: referência (opcional).
  - `acknowledged`: bool.
- Widget no admin dashboard: "Alertas" com badge de não lidos.
- Email para operador se severity == critical.

### 0.5 Session cleanup

**Problema**: Sessions sem pedido acumulam indefinidamente. Holds expiram, mas sessions ficam.

**Solução**:
- Management command `cleanup_stale_sessions`: delete sessions sem atividade há > 48h e sem order.
- Executar via cron diário (ou ao iniciar o app).

### 0.6 Stock hold expiry + order committed

**Problema**: Se holds expiram enquanto order está CONFIRMED (aguardando pagamento),
o pedido pode ficar oversold.

**Solução**:
- PaymentTimeoutHandler (0.1) já resolve para PIX: cancela o pedido antes do hold expirar.
- Para card (pagamento síncrono): hold commitado imediatamente após captura.
- Invariante: `HOLD_TTL >= PAYMENT_TIMEOUT + margem de 5 min`.
- Settings validation em startup: verificar que `HOLD_TTL > PIX_TIMEOUT_MINUTES`.

### 0.7 Custom error pages branded

- `templates/404.html`: branding da loja, "Página não encontrada", link para menu.
- `templates/500.html`: "Algo deu errado", link para contato.
- Inline CSS (sem dependência de static files).
- Mobile-responsive.

### 0.8 HTMX error handling global

- `base.html`: handler para `htmx:responseError`:
  - 4xx → toast com mensagem contextual.
  - 5xx → toast "Algo deu errado. Tente novamente." + botão retry.
  - Network error → toast "Sem conexão."
- `htmx:timeout` (15s) → retry 1x, depois toast de erro.
- Toasts com `aria-live="assertive"`.

### Arquivos

- `shopman/hooks.py` — auto-cancel timeout, race condition handling.
- `shopman/handlers/payment.py` — PaymentTimeoutHandler melhorado.
- `shop/models.py` — OperatorAlert model.
- `shop/dashboard.py` — widget de alertas.
- `channels/web/views/tracking.py` — self-service cancel endpoint.
- `channels/web/templates/404.html`, `500.html` — novos.
- `channels/web/templates/base.html` — HTMX error handler global.
- `shopman/management/commands/cleanup_stale_sessions.py` — novo.

### Testes

- `test_pix_timeout_cancels_order` — 15min sem pagar → cancelled.
- `test_payment_after_cancel_triggers_refund` — webhook após cancel → refund.
- `test_customer_cancel_releases_holds` — cancel do storefront libera holds.
- `test_customer_cancel_blocked_after_payment` — não cancela após captura.
- `test_notification_failure_creates_alert` — 5 falhas → OperatorAlert.
- `test_stale_sessions_cleaned` — sessions velhas removidas.
- `test_hold_ttl_gte_payment_timeout` — settings validation.
- `test_htmx_500_returns_toast_partial` — erro retorna toast.
- `test_404_page_branded` — 404 com branding.

---

## WP-F1: Design System Mobile-First

**Objetivo**: Fundação visual e técnica para todas as telas. Tudo que vier depois usa esses componentes.
Nada com tamanho impossível de ler ou difícil de clicar. Cada pixel conta em 375px.

### 1.1 Tailwind Local (saindo do CDN)

- `package.json`: `tailwindcss`, `@tailwindcss/forms`, `@tailwindcss/typography`.
- `tailwind.config.js`:
  - Content: templates, partials.
  - Extend colors: design tokens OKLCH da loja (primary, secondary, accent, neutral).
  - Extend fonts: display (serif), body (sans-serif).
  - Custom: `touch-target` utility (min-height/width 44px).
  - Screens: `xs: 375px` adicionado.
- Build: `npx tailwindcss -i ./static/src/input.css -o ./static/css/output.css --minify`.
- `Makefile`: `make css` (build CSS), integrado ao `make run`.
- **Resultado**: ~15KB otimizado vs ~400KB CDN. Zero dependência externa.

### 1.2 Tipografia Self-Hosted

- **Display** (títulos, nome da loja): serif — Playfair Display ou DM Serif Display.
- **Body** (texto, UI): sans-serif — Inter.
- `@font-face` em `input.css` com `font-display: swap`.
- Preload no `<head>` das variantes mais usadas (regular, medium, bold).
- Tamanhos mínimos enforced:
  - Body text: **16px** mínimo (nunca text-xs para conteúdo legível).
  - Labels: **14px** mínimo.
  - Captions/metadata: **12px** apenas para info terciária (timestamps, refs).
  - Headings: escalados por viewport (clamp).

### 1.3 Touch Targets — Regra de 44px

- **Toda área clicável**: min 44×44px. Sem exceção.
- Utility class: `.touch-target { min-height: 44px; min-width: 44px; }`.
- Botões: padding `py-3 px-4` mínimo.
- Links inline: padding `py-2` com `display: inline-block`.
- Icon buttons: `p-2.5` no ícone (24px) + padding = 44px.
- Radio/checkbox: custom visual com label como área clicável inteira (full-width, 48px height).
- Qty steppers: botões de 48×48px com ícones de 24px.

### 1.4 Componentes Base (Partials)

Biblioteca de partials HTMX-ready com acessibilidade built-in:

**Interativos:**
- `components/_button.html` — variantes: primary, secondary, outline, danger, ghost.
  - Loading: spinner + "Processando..." via `hx-indicator` + `hx-disabled-elt`.
  - Disabled: opacity + cursor-not-allowed.
  - Touch: min 44px em todas as variantes.
- `components/_input.html` — label acima, input 48px, erro inline vermelho, hint cinza.
  - Tel: input com máscara `(XX) XXXXX-XXXX` via Alpine.
  - CEP: input com máscara `XXXXX-XXX`, auto-fill ViaCEP on blur.
- `components/_stepper.html` — botões `−` / `+` (48×48px cada) com input numérico central.
  - Long-press: incrementa rápido após 500ms.
  - Min/max enforced visualmente (botão desabilitado no limite).
  - `aria-label="Quantidade"`, `role="spinbutton"`.
- `components/_toggle.html` — switch visual para opções binárias (ex: retirada/entrega).
  - Full-width, 48px height, cores distintas para cada estado.
- `components/_radio_cards.html` — radio buttons como cards selecionáveis.
  - Cada opção: full-width, 56px min-height, borda + background quando selecionado.
  - Ícone + título + subtítulo.

**Informacionais:**
- `components/_toast.html` — success/error/warning/info.
  - Posição: fixed bottom (acima do bottom nav em mobile), com margin.
  - Auto-dismiss: 5s (success/info), persistente (error/warning).
  - Dismissível: click/swipe.
  - `aria-live="assertive"` (errors), `"polite"` (info).
  - Animação: slide-up + fade-in, slide-down + fade-out.
- `components/_badge.html` — status badges com ícone + texto + cor.
  - Nunca só cor (acessibilidade para daltonismo).
  - Variantes: available, preparing, sold_out, d1, paused.
- `components/_empty_state.html` — ícone SVG + mensagem + CTA.
- `components/_skeleton.html` — loading skeleton para cards, listas, textos.
- `components/_bottom_sheet.html` — sheet de baixo (mobile) / modal lateral (desktop).
  - Handle de drag no topo (barra cinza, arrastável).
  - Close: swipe down, click fora, botão X, tecla Esc.
  - Focus trap via Alpine `x-trap`.
  - Backdrop semi-transparente.
  - `role="dialog"`, `aria-modal="true"`.
- `components/_floating_button.html` — botão fixo no bottom (ex: "Adicionar — R$ XX").
  - Fixed acima do bottom nav.
  - Animação de entrada: slide-up.
  - Sombra elevada.

### 1.5 Imagens — Pipeline

- Upload hook: resize max 800px, gerar variantes (thumb 200px, card 400px, detail 800px).
- Converter para WebP com fallback JPEG.
- Armazenar dimensões para evitar layout shift.
- Template tag `{% product_image product size="card" %}`:
  - `<img>` com srcset, width, height, loading="lazy", alt.
- Placeholder: SVG branded (ícone minimalista de pão/café), não emoji.

### 1.6 Motion & Transitions

- CSS transitions: 200ms ease-out para interações.
- HTMX swaps: `htmx-swapping { opacity: 0; transition: opacity 200ms; }`.
- Page transitions: Alpine `x-transition` para entradas de tela.
- `@media (prefers-reduced-motion: reduce)`: desabilita tudo.
- Animações utilitárias:
  - `slide-up`: translateY(100%) → 0 (entrada de bottom sheet/toast).
  - `fade-in`: opacity 0 → 1 (entrada de conteúdo).
  - `bounce`: scale(1.2) → 1 (badge de carrinho ao adicionar).
  - `pulse`: opacity alternada (status "aguardando").

### Arquivos

- `package.json`, `tailwind.config.js` — novos.
- `static/src/input.css` — Tailwind input com layers, utilities, animações.
- `static/fonts/` — Inter, DM Serif Display (ou similar).
- `static/img/placeholder.svg` — placeholder de produto.
- `channels/web/templates/components/` — ~15 componentes.
- `channels/web/templatetags/storefront.py` — product_image, format_money.
- `Makefile` — `make css`.

### Testes

- `test_tailwind_build_produces_output` — build não falha, output existe.
- `test_all_buttons_min_44px` — regex scan nos templates: todo `<button>` tem classe touch-target ou py-3+.
- `test_no_text_xs_in_body_content` — nenhum text-xs em conteúdo legível (apenas timestamps).
- `test_product_image_tag_generates_srcset` — template tag funciona.
- `test_toast_has_aria_live` — componente acessível.
- `test_bottom_sheet_has_focus_trap` — dialog acessível.

---

## WP-F2: Storefront — Navegação como Hospitalidade

**Objetivo**: A navegação reflete o pipeline real da Nelson Boulangerie, não um clone de marketplace.
Cada path de entrada do cliente é first-class. A tela é otimizada para o foco da tarefa em cada momento.
Um cliente distraído, idoso, com déficit de atenção, apressado ou ocupado deve usar sem equívoco.

**Princípios fundadores**:
- **Omotenashi digital**: o equivalente do atendente que diz "Primeira vez? Seja bem-vindo!"
- **Imersão contextual**: quando o cliente está numa tarefa, a tela elimina tudo que não pertence.
- **Pragmatismo japonês**: densidade informacional alta mas organizada. Economia de gesto.
  Cada toque leva o cliente exatamente onde precisa. Charme na tipografia e na copy, não no whitespace.
- **Sóbrio, nunca piegas**: acolhimento vem do gesto (informação certa na hora certa), não do adjetivo.
  "Acabou de sair do forno" é informação útil com personalidade. Nada de "feito com amor 💕".

### 2.1 Paths de Entrada (todos first-class)

Cada path tem: contexto de identidade, canal de notificação, e nível de onboarding.

| Path | Origem | Identidade | Notificação | Onboarding |
|------|--------|-----------|-------------|------------|
| WhatsApp/Manychat → `/menu/?t=<token>` | Mais comum | Já identificado (bridge token → `get_or_create` Customer) | WhatsApp | Nenhum (já conhece) |
| Instagram DM/Manychat → `/menu/?t=<token>` | Frequente | Já identificado (bridge token) | Instagram DM | Nenhum |
| QR code loja/embalagem → `/menu/` ou `/produto/<ref>/` | Presencial | Anônimo (pode logar depois) | Nenhum ou PWA push | Mínimo (já está na loja) |
| Google/SEO → `/` (home) → `/menu/` | Descoberta | Anônimo | Web (toast/polling) | Completo ("Como Funciona") |
| Link compartilhado → `/produto/<ref>/` | Social | Anônimo | Web | Mínimo (breadcrumb + nav) |
| Bookmark/PWA → `/menu/` | Recorrente | Logado (sessão persistente) | PWA push | Nenhum |

**Bridge token**: `?t=<token>` na URL. Sistema valida, identifica `ExternalIdentity`, match com `Customer`
existente ou cria novo. Zero tela de login. Session registra `origin_channel` para pipeline de notificação.

### 2.2 Canal de Notificação por Origem

O `Session` e `Order` registram `origin_channel`. O pipeline de notificação respeita:

```
origin_channel = whatsapp  → notifica via WhatsApp (Manychat API)
origin_channel = instagram → notifica via Instagram DM (Manychat API)
origin_channel = web_push  → push notification (PWA, se concedeu permissão)
origin_channel = web       → toast + polling na tela de tracking
origin_channel = pos       → sem notificação digital (presencial)
```

Regra: tenta o canal de origem primeiro. Fallback: web polling (sempre disponível).
Nunca notifica por canal que o cliente não usou. Nunca mistura canais sem consentimento.

### 2.3 Imersão Contextual — Inventário de Momentos

Princípio: quando o cliente está numa tarefa que exige atenção plena, a tela elimina tudo que
não pertence àquela tarefa. Fundo em cor da marca (inverted), texto claro, fonte grande, contraste AAA.

| Momento | Gatilho | Conteúdo do Foco | Ações disponíveis |
|---------|---------|-------------------|-------------------|
| **Busca + Exploração** | Toca "☰ Tudo" ou ícone de busca | Campo de busca + grid de categorias/coleções. Ao digitar: resultados substituem grid | Tocar categoria, selecionar resultado, fechar |
| **Adicionou ao carrinho** | POST `/cart/add/` retorna sucesso | Estado de confirmação dominante: "Adicionado!" + nome + qty. Inequívoco. Quantidade reseta a 1 na tela do produto | "Ver carrinho" / "Continuar escolhendo" |
| **Confirmação de endereço** | Checkout remoto, step de endereço | Mapa fullscreen, pin arrastável, campo de complemento. Nada mais | Confirmar, ajustar pin, voltar |
| **Pagamento PIX** | QR code gerado | QR grande e legível, timer de expiração, "Copiar código", status polling | Copiar, aguardar, cancelar |
| **Pós-checkout (omotenashi)** | Pedido enviado, aguardando confirmação | Status em tempo real, timer de confirmação otimista, copy acolhedora | Cancelar (se possível), voltar ao menu |
| **Tracking** | Pedido confirmado | Timeline visual (Recebido → Preparando → Pronto), detalhe do pedido, contato WhatsApp | Contato, voltar |
| **Onboarding "Como Funciona"** | Primeiro acesso via SEO/Google | 2-3 passos visuais: pedido online + visita à loja. Equivalente digital do "Primeira vez aqui?" | Avançar, pular, ir ao cardápio |
| **Login / Identificação** | Checkout sem sessão, acesso a histórico | Campo WhatsApp → "Enviar código" → campo OTP. Uma coisa de cada vez | Enviar, verificar, voltar |

Regra de adição ao carrinho: cada adição é **atômica**. Ao adicionar, a tela confirma de forma dominante.
A quantidade na tela do produto reseta a 1. O carrinho gerencia quantidades. Elimina a dúvida
"adicionei ou não?", "se apertar de novo, vai duplicar?".

### 2.4 Estrutura de Navegação

**Home (`/`)** — site institucional, vitrine da marca:
- Hero: "Pão bom como sempre" + CTA "Ver o cardápio de hoje"
- "Como Funciona" (duas dimensões):
  - Pedido online: 3 steps (Escolha → Pague → Retire/Receba)
  - Visita à loja: "Pães no autosserviço, cafés no balcão" (resolve dor de onboarding)
- "Direto do forno...": disponibilidade em tempo real (HTMX polling)
- Footer: horários, endereço (link Maps), WhatsApp, redes sociais

**Cardápio (`/menu/`)** — a experiência app-like:

**Header fixo (sticky):**
- Logo + nome (link → home)
- Ícone de busca (abre imersão de busca)
- Carrinho (badge com count, abre drawer)
- Usuário (se logado: nome; se não: "Entrar")

**Barra de pills (sticky, abaixo do header, só em `/menu/`):**
- Botão "☰ Tudo" à esquerda → abre imersão de busca/exploração
- Pills com scroll horizontal: categorias reais (Pães Rústicos, Viennoiserie, Cafés...)
  + coleções dinâmicas (Disponível Agora, Novidades, Favoritos se logado)
- Pill ativa: background primary, text white. Inativa: outline, text muted.
- Scroll da página atualiza pill ativa (IntersectionObserver)
- Pill toca → smooth scroll até seção correspondente

**Grid de produtos:**
- Pragmatismo japonês: cards compactos mas completos.
- 2-3 produtos visíveis por tela em mobile (não 1 gigante com foto enorme).
- Card mostra: foto (se houver), nome, descrição curta (1 linha), badge de disponibilidade, preço.
  Tudo visível sem expandir. Sem "clique para ver mais" no essencial.
- Hierarquia: nome em font-heading, preço em destaque, badge colorido.

**Bottom Navigation Bar (mobile, fixed bottom, 56px):**

```
┌──────────────────────────────────────┐
│  🏠 Cardápio │ 📦 Pedidos │ 👤 Conta │
└──────────────────────────────────────┘
```

- Tab ativo: ícone filled + primary + label. Inativo: outline + muted.
- Badge em "Pedidos": nº de pedidos ativos (HTMX polling).
- Cart é drawer (não tab) — abre via header ou floating button.
- Safe area: `padding-bottom: env(safe-area-inset-bottom)`.
- **Desktop**: bottom nav oculto, header completo com nav links.

**Floating Cart Button (mobile):**
- Fixed, acima do bottom nav (bottom: 72px + safe area).
- Circular (56×56px) com ícone + badge de quantidade.
- Aparece com animação ao adicionar primeiro item. Oculto se carrinho vazio.
- Tap: abre cart drawer (bottom sheet).

### 2.5 Status Bar do Device (extensão visual)

Colorir as áreas superior e inferior da tela do celular como extensão natural da loja:

- **Android Chrome**: `<meta name="theme-color" content="{{ storefront.theme_color }}">` (já existe)
  + `theme_color` no manifest.json (PWA).
- **iOS Safari**: `apple-mobile-web-app-status-bar-style: black-translucent`
  + cor de fundo do body preenche a status bar area.
- **Dark mode**: `<meta name="theme-color" media="(prefers-color-scheme: dark)" content="...">`.
- **PWA fullscreen**: controle total via `display: standalone` + `background_color` no manifest.
- Na imersão contextual: `theme-color` pode mudar dinamicamente para a cor do fundo invertido.

### 2.6 Transições de Tela

- HTMX `hx-push-url` + `hx-target="#main-content"` para navegação SPA-like.
- Menu → PDP: slide-left. PDP → voltar: slide-right.
- Tab switch (bottom nav): fade rápido (150ms).
- Bottom nav e floating cart permanecem fixos (nunca parte do swap).
- `hx-history-elt="#main-content"` para cache de telas anteriores.

### 2.7 Gestos

- **Swipe right** (edge, 80px threshold): navigate back.
- **Swipe down** em bottom sheets / imersão contextual: fecha.
- **Pull-to-refresh** em tracking, pedidos: atualiza via HTMX.

### 2.8 Acessibilidade & Pragmatismo

- **Fonte**: nunca abaixo de 16px em conteúdo de ação. Labels mínimo 14px.
- **Contraste**: WCAG AAA nos estados de imersão contextual (fundo invertido + texto claro).
- **Touch targets**: 44px mínimo (regra F1.3), 48px para ações primárias.
- **Copy**: verbo + objeto, direto. "Adicionado ao carrinho", não "Ótima escolha! Seu item foi adicionado
  com sucesso ao carrinho de compras!"
- **Tom de voz**: acolhedor, elegante, transparente, sóbrio. Nunca piegas.
  Referência: Copy Institucional e Manual de Hospitalidade (Notion).

### Arquivos

- `channels/web/templates/base.html` — rewrite (layout com bottom nav, floating cart, toast stack).
- `channels/web/templates/components/_bottom_nav.html` — novo.
- `channels/web/templates/components/_floating_cart_button.html` — novo.
- `channels/web/templates/components/_header.html` — novo (simplificado mobile).
- `channels/web/templates/components/_focus_overlay.html` — novo (imersão contextual genérica).
- `channels/web/templates/components/_cart_added_confirmation.html` — novo.
- `channels/web/templates/storefront/home.html` — novo (site institucional).
- `channels/web/templates/storefront/como_funciona.html` — rewrite (duas dimensões).
- `channels/web/static/js/gestures.js` — swipe back, pull-to-refresh.
- `channels/web/views/bridge.py` — novo: bridge token validation + session binding.
- `channels/hooks.py` — origin_channel no pipeline de notificação.
- Todos os templates: adaptar para `#main-content` swap.

### Testes

- `test_bridge_token_creates_session` — token válido cria sessão autenticada.
- `test_bridge_token_invalid_rejected` — token inválido não autentica.
- `test_origin_channel_persisted` — Session registra origin_channel.
- `test_notification_respects_origin` — notificação usa canal de origem.
- `test_bottom_nav_visible_on_mobile` — bottom nav presente em mobile.
- `test_bottom_nav_hidden_on_desktop` — oculto em desktop.
- `test_floating_cart_appears_with_items` — cart button visível com itens.
- `test_cart_add_resets_quantity` — tela do produto reseta qty após adicionar.
- `test_focus_overlay_fullscreen` — overlay ocupa viewport.
- `test_pills_intersection_observer` — pill ativa muda com scroll.
- `test_back_navigation_works` — history back funciona.
- `test_safe_area_padding` — padding para notch.
- `test_theme_color_meta_present` — meta theme-color renderizado.
- `test_minimum_font_size_16px` — nenhum texto de ação abaixo de 16px.

---

## WP-F3: Storefront — Catálogo & Discovery

**Objetivo**: Cliente encontra o que quer em 3 toques. Catálogo visual, busca eficaz, discovery
prazeroso. Cada produto faz o cliente querer comprar.

### 3.1 Menu — Redesign Mobile-First

**Layout mobile (375px)**:

```
┌─────────────────────────┐
│ [Header: Logo + Nome]   │  48px
├─────────────────────────┤
│ 🔍 Buscar...            │  48px search bar (full-width)
├─────────────────────────┤
│ [Pães] [Doces] [Café].. │  44px pills, horizontal scroll
├─────────────────────────┤
│ ┌───────┐ ┌───────┐     │
│ │ Foto  │ │ Foto  │     │  Product cards: 2 cols
│ │ Nome  │ │ Nome  │     │  aspect-ratio 3:4
│ │ R$X   │ │ R$X   │     │  ~170px width each
│ │ [+]   │ │ [+]   │     │  [+] = 44px touch target
│ └───────┘ └───────┘     │
│ ...                     │
├─────────────────────────┤
│ 🏠 Menu │ 📦 Pedidos │ 👤│  Bottom nav
└─────────────────────────┘
```

- **Search bar**: full-width, 48px, ícone de lupa à esquerda.
  - Placeholder contextual: "Buscar pães, doces, cafés...".
  - HTMX: `hx-trigger="input changed delay:300ms"`.
  - Resultados: substituem o grid de produtos no mesmo container.
- **Collection pills**: scroll horizontal (overflow-x-auto, -webkit-overflow-scrolling: touch).
  - Active: background primary, text white.
  - IntersectionObserver: highlight automático ao scrollar.
  - "Todos" como primeira pill.
- **Product cards** (2 cols mobile, 3 tablet, 4 desktop):
  - Foto: aspect-ratio 3:4 (imagem preenche, object-cover).
  - Nome: 1 linha, truncado.
  - Preço: `R$ X,XX` em body bold.
  - Badge (overlay top-right): disponibilidade.
  - Botão `[+]` (canto inferior direito, 44×44px):
    - Primeiro tap: adiciona 1 unidade, badge "1" aparece.
    - Taps subsequentes: incrementa. Stepper aparece ao redor do badge.
    - HTMX: `POST /cart/add/` com swap de toast + atualizar floating cart.
  - Tap no card (área toda exceto botão +): abre PDP.
- **D-1 section**: seção separada com header "Produtos do dia anterior — 50% off",
  visual distinto (background mais quente). Só aparece se canal permite D-1.
- **Empty state**: ícone + "Nenhum produto nesta categoria."
- **Pull-to-refresh**: atualiza cardápio + disponibilidade.

### 3.2 Busca — Fuzzy & Inteligente

- **PostgreSQL**: `TrigramSimilarity` para fuzzy matching.
  - Fallback `icontains` para SQLite em dev.
- **Campos buscados**: product.name, product.description, collection.name.
- **Ordenação**: por score de relevância (trigram).
- **0 resultados**: "Nenhum resultado para 'X'." + seção "Populares:" com top 4 produtos.
- **Resultado**: mesmos product cards do grid.
- **Acessibilidade**: `aria-live="polite"` no container de resultados.
  Anuncia "X resultados encontrados" para screen readers.

### 3.3 Product Detail Page (PDP) — Mobile-First

**Layout mobile**:

```
┌─────────────────────────┐
│ ← Voltar    [♡]         │  48px header com back + favorite
├─────────────────────────┤
│                         │
│      [Foto produto]     │  60% viewport height (max)
│    aspect-ratio 4:3     │  Swipe horizontal se múltiplas fotos
│                         │
├─────────────────────────┤
│ Pão Francês             │  h1, serif, 24px
│ Crocante por fora...    │  description, 14px, 2 linhas max
│                         │
│ R$ 1,50                 │  preço, 28px, bold
│ ● Disponível            │  badge
├─────────────────────────┤
│ 📋 Detalhes       ▼    │  Collapsible (Alpine)
│ 🥜 Alérgenos      ▼    │  Collapsible
│ 📐 Informações    ▼    │  Collapsible (peso, validade)
├─────────────────────────┤
│ Produtos similares      │  Scroll horizontal de cards
│ [card] [card] [card]    │
├─────────────────────────┤
│                         │
│ [Floating: Adicionar R$1,50]  Fixed bottom, acima do nav
│                         │
└─────────────────────────┘
```

- **Imagem**: max 60vh em mobile. Se múltiplas fotos: swipe horizontal com dots indicator.
- **Info**: nome (serif, 24px), descrição (2 linhas truncadas, expandível), preço grande.
- **Detalhes colapsáveis**: ingredientes, alérgenos, informações nutricionais, validade.
  Usa `<details>` nativo + estilizado para acessibilidade.
- **Stepper**: quando há item no carrinho, substituir "Adicionar" por stepper `[−] 2 [+]`.
- **Floating button**: fixed bottom (acima do bottom nav).
  - "Adicionar — R$ X,XX" (primary, full-width, 56px height).
  - Se já no carrinho: "[−] 2 [+] — R$ 3,00" (stepper inline no botão).
  - Animação de adição: bounce + toast "Adicionado!".
- **Observação**: campo de texto inline (colapsado): "Observação para este item (ex: fatiar, sem cobertura)".
- **Similares**: scroll horizontal de product cards compactos (mesma coleção).
- **JSON-LD**: `Product` schema (name, image, price, availability, brand).
- **Breadcrumb**: visível apenas em desktop.

### 3.4 Horário de Funcionamento no Menu

- **Banner no topo**: se loja aberta → "Aberto • Fecha às XXh".
  Se fechada → "Fechado • Abre amanhã às XXh". Cor de fundo distinta.
- Informação vem de `Shop.business_hours` (se existir) ou campo custom.
- Se fechado, pedidos ainda possíveis (preorder) → "Fechado agora — Agende para amanhã!".

### Arquivos

- `channels/web/templates/menu.html` — rewrite.
- `channels/web/templates/product_detail.html` — rewrite.
- `channels/web/templates/partials/search_results.html` — novo.
- `channels/web/templates/components/_product_card.html` — novo.
- `channels/web/templates/components/_quick_add.html` — novo (botão + do card).
- `channels/web/views/catalog.py` — SearchView com TrigramSimilarity.
- `channels/web/templatetags/seo.py` — json_ld_product.

### Testes

- `test_menu_2col_mobile_4col_desktop` — grid responsivo correto.
- `test_quick_add_from_card` — tap no + adiciona ao carrinho.
- `test_search_fuzzy_pao_finds_pao_frances` — fuzzy funciona.
- `test_search_0_results_shows_popular` — mostra populares.
- `test_pdp_floating_button_updates_with_qty` — stepper no floating button.
- `test_pdp_similares_from_same_collection` — similares corretos.
- `test_pdp_json_ld_product` — structured data presente.
- `test_pdp_image_max_60vh_mobile` — imagem não excede 60% viewport.
- `test_business_hours_banner` — banner correto aberto/fechado.

---

## WP-F4: Storefront — Carrinho & Checkout

**Objetivo**: Do carrinho ao "Confirmar pedido" em menos taps possível, sem sacrificar clareza.
Zero fricção para cliente recorrente. Checkout é single-page com seções inteligentes.

### 4.1 Cart Bottom Sheet (não página)

- **Abertura**: tap no floating cart button → bottom sheet (80vh mobile).
- **NÃO é uma página separada**. É overlay sobre o conteúdo atual.
- **Conteúdo**:

```
┌─────────────────────────┐
│ ─── (drag handle) ───   │
│ Seu Carrinho (3 items)  │  Header
├─────────────────────────┤
│ ┌───────────────────┐   │
│ │ [img] Pão Francês │   │  Item row (60px height)
│ │  R$1,50  [−]2[+]  │   │  Stepper à direita
│ └───────────────────┘   │
│ ┌───────────────────┐   │
│ │ [img] Croissant   │   │
│ │  R$8,00  [−]1[+]  │   │
│ └───────────────────┘   │
│ ...                     │
├─────────────────────────┤
│ [🏷️ Cupom: DESCONTO10 ×]│  Coupon applied (se houver)
│ [Adicionar cupom]       │  Link para expandir campo
├─────────────────────────┤
│ Subtotal      R$ 11,00  │
│ Desconto     -R$  1,10  │  (se cupom)
│ ─────────────────────── │
│ Total         R$  9,90  │  Bold, 20px
├─────────────────────────┤
│ [   Ir para Checkout   ]│  Primary button, 56px, full-width
└─────────────────────────┘
```

- **Item row**: imagem thumb (48×48), nome (1 linha), preço, stepper.
  - Swipe left no item: revela botão "Remover" (vermelho).
  - Ou: stepper vai até 0 → remove com confirmação "Remover?".
- **Cupom**: campo colapsado. Ao expandir: input + "Aplicar" (HTMX).
  - Sucesso: badge verde "DESCONTO10 — -10%" com botão × para remover.
  - Erro: mensagem vermelha inline.
- **HTMX**: toda interação (qty, remove, coupon) via swaps parciais. Zero reload.
- **Animação**: item removido com slide-left + collapse. Item adicionado com slide-down.
- **Empty**: emoji + "Carrinho vazio" + "Ver cardápio" (fecha sheet).

### 4.2 Checkout — Single Page com Seções Inteligentes

Checkout é uma página (não sheet) com seções que se adaptam ao contexto:

**Se cliente recorrente (já tem dados salvos)**:

```
┌─────────────────────────┐
│ ← Checkout              │
├─────────────────────────┤
│ 👤 Pablo — (11)99999    │  Card com dados. "Não é você?"
├─────────────────────────┤
│ 📍 Retirar na loja      │  Toggle selecionado (default)
│    Entrega              │
├─────────────────────────┤
│ 📅 Hoje                 │  Radio cards: Hoje | Amanhã
├─────────────────────────┤
│ 💳 PIX (5% desc.)       │  Radio card selecionado
│    Cartão               │  Radio card
├─────────────────────────┤
│ 📝 Observações (opc.)  ▼│  Colapsado
├─────────────────────────┤
│ ─── Resumo ───          │  Sempre visível
│ 2× Pão Francês   R$3,00│
│ 1× Croissant     R$8,00│
│ Subtotal         R$11,00│
│ PIX (-5%)       -R$ 0,55│
│ Total            R$10,45│
├─────────────────────────┤
│ [Confirmar Pedido R$10,45]│  56px, primary
└─────────────────────────┘
```

**Se cliente novo (primeiro pedido)**:

```
┌─────────────────────────┐
│ ← Checkout              │
├─────────────────────────┤
│ 📱 Seu WhatsApp         │  Input tel (48px)
│  [(11) 99999-0000  ]    │
│  [Continuar]            │  44px button
├─ (após verificar) ──────┤
│ 🔢 Código de verificação│
│  [0][0][0][0][0][0]     │  6 inputs, 48×48 cada
│  Reenviar em 0:52       │  Countdown
│  □ Lembrar dispositivo  │  Checkbox (explica o que é)
├─ (após verificar OTP) ──┤
│  ... (seções como acima) │
└─────────────────────────┘
```

**Seção Identificação** (renderizada condicionalmente):
- Se logado: card com nome + phone + "Trocar conta".
- Se não logado: input phone → "Continuar" → OTP inline.
- OTP: 6 inputs de 1 dígito, 48×48px, auto-advance, auto-submit, paste-friendly.
- Timer de reenvio (60s countdown).
- "Não recebeu? Enviar por SMS" (se fallback disponível).
- Device trust: "Lembrar este dispositivo (não pediremos código novamente)" — checkbox.

**Seção Entrega/Retirada**:
- Toggle visual (não radio): "Retirar na loja" | "Entrega".
- Se **retirada**: card com endereço da loja + mini mapa (static image, não Google Maps JS).
- Se **entrega**:
  - Endereços salvos como cards selecionáveis (tap para selecionar).
  - "Novo endereço" → bottom sheet com form:
    - CEP (input com máscara, auto-fill ViaCEP).
    - Rua, número, complemento, bairro, cidade (preenchidos pelo CEP).
    - Referência (opcional).
    - "Salvar" → adiciona e seleciona.
  - Taxa de entrega: calculada e exibida ao selecionar endereço.

**Seção Data/Horário**:
- Radio cards: "Hoje" | "Amanhã" | "Agendar" (custom date).
- Time slots (se aplicável): radio cards com horários.
- Preorder banner: se fora do horário, destacar "Pedido agendado para [data]".

**Seção Pagamento**:
- Radio cards: PIX (com badge "X% de desconto") | Cartão.
- Se PIX: nada mais (QR gerado após confirmar).
- Se Cartão: Stripe Elements inline (aparece ao selecionar).
- Métodos salvos (se houver): card com últimos 4 dígitos.

**Resumo** (sticky em desktop, inline em mobile):
- Lista de items.
- Subtotal, descontos, frete (se delivery), total.
- **Botão**: "Confirmar Pedido — R$ XX,XX" (primary, 56px).
  - Loading state: spinner + "Processando...".
  - Disable form durante submit (prevent double-submit).

### 4.3 Validação em Tempo Real

- **Phone**: valida formato ao blur (Alpine). Feedback visual: ✓ verde ou ✗ vermelho.
- **CEP**: valida ao blur, busca ViaCEP. Se inválido: "CEP não encontrado".
- **Endereço**: campos obrigatórios marcados visualmente.
- **Coupon**: feedback inline imediato (HTMX).
- **Estoque**: pre-check antes de confirmar (directive existente). Se conflito:
  - Toast: "Pão Francês está esgotado." + botão "Remover do carrinho".
  - Ou: "Quantidade reduzida para X." + botão "Aceitar".

### Arquivos

- `channels/web/templates/cart_sheet.html` — novo (substitui cart.html).
- `channels/web/templates/checkout.html` — rewrite completo.
- `channels/web/templates/partials/checkout_identity.html` — novo.
- `channels/web/templates/partials/checkout_fulfillment.html` — novo.
- `channels/web/templates/partials/checkout_payment.html` — novo.
- `channels/web/templates/partials/checkout_summary.html` — novo.
- `channels/web/templates/partials/otp_input.html` — novo (6 dígitos).
- `channels/web/templates/partials/address_form_sheet.html` — novo.
- `channels/web/views/checkout.py` — refactor para single-page.
- `channels/web/views/cart.py` — adaptar para sheet.

### Testes

- `test_cart_sheet_opens_from_floating_button` — bottom sheet abre.
- `test_cart_swipe_to_remove` — swipe left remove item.
- `test_checkout_returning_customer_prefilled` — dados preenchidos.
- `test_checkout_new_customer_otp_flow` — OTP inline funciona.
- `test_checkout_cep_autofill` — CEP preenche campos.
- `test_checkout_stock_conflict_shows_toast` — conflito de estoque.
- `test_checkout_single_page_all_sections` — todas seções renderizam.
- `test_checkout_double_submit_prevented` — segundo click ignorado.
- `test_checkout_toggle_delivery_shows_addresses` — toggle muda seção.

---

## WP-F5: Storefront — Pagamento & Confirmação

**Objetivo**: Pagamento claro, seguro, com feedback constante. Confirmação celebratória.

### 5.1 Payment Page — PIX

- **Header**: "Pagamento PIX" + ref do pedido.
- **Valor**: grande, centralizado, 32px bold.
- **QR Code**: SVG (não imagem raster), 240×240px, centralizado.
- **Copia-e-cola**: input readonly + botão "Copiar" (44px, feedback "Copiado! ✓").
- **Timer**: countdown visual (MM:SS), muda de cor ao chegar em 2 min (amarelo → vermelho).
- **Status**: polling HTMX a cada 5s.
  - Aguardando: pulse animation no ícone.
  - Confirmado: check verde + "Pago!" + redirect automático em 3s.
  - Expirado: "PIX expirado" + "Gerar novo PIX" (cria nova intent).
  - Falhou: "Erro no pagamento" + "Tentar novamente".
- **Max polling**: 180 tentativas (15 min). Depois: "Verificar manualmente" (botão).

### 5.2 Payment Page — Cartão

- Stripe Elements inline (card number, expiry, CVC).
- Validação client-side pelo Stripe.js.
- Botão "Pagar R$ XX,XX" (primary, 56px).
- Loading: spinner no botão durante processamento.
- 3D Secure: popup handled by Stripe.
- Erros: mensagem específica ("Cartão recusado", "Saldo insuficiente").
- Retry: "Tentar com outro cartão" (re-renderiza form).
- **Timeout**: se order CONFIRMED por > 30min sem captura de card → auto-cancel
  (mesmo mecanismo do F0.1, com `CARD_TIMEOUT_MINUTES=30` no ChannelConfig).

### 5.3 Order Placed / Confirmation Page

Comportamento varia conforme o modo de confirmação do canal:

**Canais com confirmação imediata** (POS, marketplace):
- **Animação**: confetti sutil por 2s (CSS-only, sem lib).
- **Ícone**: check verde grande.
- **Mensagem**: "Pedido confirmado!" (serif, 28px).
- **Ref**: monospace, copiável.
- **Estimativa**: "Previsão: pronto às XXh" (se crafting integrado).
- **Resumo**: items colapsável.
- **Ações**:
  - "Acompanhar pedido" (primary).
  - "Compartilhar" (WhatsApp share link).
  - "Voltar ao cardápio" (secondary).

**Canais com confirmação otimista** (web, WhatsApp — 5 min timeout):
- Redirect direto para tracking page (`/pedido/{ref}/`) com estado "Aguardando confirmação".
- Tracking page mostra timer de 5 min + copy omotenashi (detalhes no F6.1).
- Ao confirmar: transição celebratória na própria tracking page.

### Arquivos

- `channels/web/templates/payment.html` — rewrite.
- `channels/web/templates/order_confirmation.html` — rewrite.
- `channels/web/views/payment.py` — melhorar polling, retry.

### Testes

- `test_pix_qr_renders_as_svg` — QR em SVG.
- `test_pix_copy_button_works` — clipboard API.
- `test_pix_timeout_shows_retry` — expirado → botão gerar novo.
- `test_pix_confirmed_redirects` — confirmado → redirect.
- `test_card_stripe_elements_render` — Stripe Elements carrega.
- `test_confirmation_shows_ref` — ref visível.
- `test_confirmation_share_link` — link de compartilhamento correto.

---

## WP-F6: Storefront — Tracking & Pós-Venda

**Objetivo**: Cliente acompanha pedido com confiança total. Operador atualiza, cliente vê
instantaneamente. Após entrega, facilitar recompra.

### 6.1 Tracking Page — Timeline Visual

- **Acessível por ref** (sem auth): `/pedido/{ref}/`.
- **Header**: nome da loja + ref + data.
- **Timeline vertical** (stepper):

```
  ✓ Recebido          14:32
  ────────────
  ✓ Confirmado         14:33
  ────────────
  ● Preparando         14:45    ← status atual (highlight)
  ────────────
  ○ Pronto             —
  ────────────
  ○ Entregue           —
```

  - Passados: check verde + hora.
  - Atual: dot primary + label bold + hora + animação pulse.
  - Futuros: dot cinza + label cinza.
  - Dots: 16px (não 12px — visibilidade).
  - Linha: 3px (não 2px).

- **Estado "Aguardando confirmação" (Omotenashi)**:
  - Quando pedido em status NEW (aguardando confirmação otimista, 5 min):
    - Step "Recebido" com check verde.
    - Step "Aguardando confirmação" como **status atual** com:
      - Copy: "Seu pedido foi recebido! A loja tem até 5 minutos para confirmar."
      - Timer visual: countdown (MM:SS) com animação pulse suave.
      - Cor: verde → amarelo (< 2min restantes) → auto-confirma.
    - Transparência total: cliente sabe exatamente o que está acontecendo.
  - Ao confirmar (ou auto-confirmar): transição celebratória → step "Confirmado" com check verde.

- **Estimativa**: se status `preparing` → "Previsão: pronto às XXh".
  - Se tem WorkOrder vinculado, calcular ETA do crafting.
  - Se não: estimativa genérica do ChannelConfig.
- **Card de resumo**: items + total (colapsável).
- **Contato**: "Falar com a loja" → link `wa.me/{phone}`.
- **Cancelamento**: botão vermelho ghost "Cancelar pedido" (se status permite).
  - Confirmação via bottom sheet: "Deseja cancelar? Essa ação não pode ser desfeita."
  - Após cancelar: timeline atualiza, toast de confirmação.

### 6.2 Real-time Updates

- HTMX polling a cada 10s no container da timeline.
- Se status mudou: slide-down no novo step + highlight.
- Se status terminal (completed, cancelled): parar polling.
- Transição suave via CSS.

### 6.3 Pós-Venda

- **Reorder**: botão "Pedir novamente" em pedidos com status completed.
  - Verifica disponibilidade de cada item.
  - Se tudo disponível: adiciona ao carrinho, redireciona para cart sheet.
  - Se algo indisponível: toast "X não está mais disponível" + adiciona o resto.
- **Avaliação**: após `delivered`, mostrar "Como foi seu pedido?"
  - 5 estrelas tap-friendly (48×48 cada).
  - Campo de comentário (opcional, 500 chars).
  - Salvar em `Order.data["rating"]`.
  - Só mostra 1x (flag em `Order.data["rating_requested"]`).

### 6.4 Lista de Pedidos (tab "Pedidos")

- Acessível via bottom nav tab "Pedidos".
- **Se logado**: lista de pedidos do customer.
  - Filtro pills: "Ativos" | "Anteriores" | "Todos".
  - Card por pedido: ref, data, status badge, nº items, total.
  - Tap → tracking page.
- **Se não logado**: input de phone para lookup → lista.
- **Empty state**: "Nenhum pedido ainda. Conheça nosso cardápio!" + CTA.

### Arquivos

- `channels/web/templates/tracking.html` — rewrite.
- `channels/web/templates/partials/order_timeline.html` — novo.
- `channels/web/templates/partials/order_actions.html` — novo.
- `channels/web/templates/orders_list.html` — novo (tab Pedidos).
- `channels/web/views/tracking.py` — cancel, reorder, rate, orders_list.

### Testes

- `test_tracking_timeline_renders` — timeline com status.
- `test_tracking_polling_updates` — polling atualiza.
- `test_tracking_cancel_button` — cancel funciona.
- `test_reorder_checks_availability` — verifica estoque.
- `test_rating_saved` — rating persiste.
- `test_orders_list_filters` — filtros funcionam.
- `test_tracking_stops_on_terminal` — completed não faz polling.

---

## WP-F7: Storefront — Conta, Loyalty & Preferências

**Objetivo**: Conta do cliente é hub de controle. Loyalty engaja. Preferências simplificam recompras.
Usa plenamente o Core: LoyaltyService, PreferenceService, AddressService, Timeline.

### 7.1 Account Page — Tabs Mobile

- **Acesso**: via bottom nav "Conta" (ou tab, se logado).
- **Se não logado**: tela de login (phone → OTP, mesmo fluxo do checkout).
- **Se logado**: tabs horizontais no topo:

  | Perfil | Pedidos | Fidelidade | Config |

- **Perfil**:
  - Nome (editável inline).
  - Phone (exibido, não editável — é o identificador).
  - Email (editável, com verificação).
  - Endereços como cards:
    - Label (Casa, Trabalho), endereço formatado, badge "Principal".
    - Ações: Editar (bottom sheet), Excluir (confirmação), Definir como principal.
    - "+ Novo endereço" → bottom sheet com form.
  - Dispositivos confiáveis: lista com nome parseado do User-Agent, botão "Remover".

- **Pedidos**: mesmo conteúdo de F6.4 (lista de pedidos com filtros).

- **Fidelidade** (usa `LoyaltyService` + `customers.contrib.loyalty`):
  - **Card visual** (tipo cartão fidelidade):
    - Tier: badge com cor (Bronze, Prata, Ouro, Platina).
    - Pontos: número grande.
    - Barra de progresso para próximo tier.
    - "Faltam X pontos para [próximo tier]".
  - **Stamps** (se habilitado): grid visual 2×5 (ex: 10 carimbos).
    - Preenchidos: cor + ícone.
    - Vazios: outline.
    - "Faltam X para ganhar [recompensa]".
  - **Histórico**: lista com data, operação (+/-), pontos, origem (ref do pedido).
  - **Resgate**: toggle "Usar pontos no próximo pedido" (salva via PreferenceService).

- **Config**:
  - Preferências alimentares (uses `customers.contrib.preferences`):
    - Tags selecionáveis: "Sem glúten", "Vegano", "Sem lactose", etc.
    - Salvas como preferences no Core.
  - Preferências de checkout (usa PreferenceService):
    - Método de pagamento favorito (pre-select no checkout).
    - Endereço default (pre-select).
    - Tipo de entrega default (retirada/delivery).
  - Notificações: toggles por canal (Email, WhatsApp, Push) e tipo (Pedidos, Promoções).
  - "Excluir minha conta" → modal de confirmação.
    - Usa `customers.contrib.consent` para registrar consentimento.
    - Anonimiza dados (nome → "Anonimizado", phone → hash).
    - Mantém Orders com ref para auditoria.
  - "Exportar meus dados" → JSON/CSV com todos os dados do customer (LGPD).

### 7.3 Customer Merge (Admin)

O Core tem `customers.contrib.merge` para deduplicação de clientes. Hoje não é usado.

- No admin, quando operador identifica cliente duplicado:
  - Ação "Mesclar clientes" no Customer admin.
  - Seleciona customer principal e secundário.
  - `MergeService.merge()` consolida: pedidos, endereços, loyalty, timeline.
  - Customer secundário desativado.
- Detecção automática (sugestão): clientes com mesmo phone ou email → widget no dashboard.

### 7.2 Auth Flow — Polish

- **Login**: tela minimalista. Logo da loja + "Digite seu WhatsApp" + input phone + "Entrar".
  - Subtexto: "Enviaremos um código. Não precisa de senha."
- **OTP**: 6 dígitos, 48×48 cada, auto-advance, paste-friendly, auto-submit.
  - Timer: "Reenviar em 0:52".
  - Fallback: "Enviar por SMS" (se WhatsApp falhou).
- **Device trust**: após OTP, "Lembrar este dispositivo?" (checkbox).

### Arquivos

- `channels/web/templates/account.html` — rewrite com tabs.
- `channels/web/templates/partials/account_profile.html` — novo.
- `channels/web/templates/partials/account_loyalty.html` — novo.
- `channels/web/templates/partials/account_config.html` — novo.
- `channels/web/templates/login.html` — redesign.
- `channels/web/views/account.py` — expandir: loyalty, preferences, address CRUD.

### Testes

- `test_account_tabs_render` — todas tabs visíveis.
- `test_loyalty_card_shows_tier` — tier correto.
- `test_loyalty_stamps_progress` — stamps visuais corretos.
- `test_loyalty_history` — histórico de pontos.
- `test_preferences_saved` — preferências persistem.
- `test_address_crud` — criar, editar, excluir, set primary.
- `test_login_otp_flow` — login completo.

---

## WP-F8: Gestor de Pedidos — Painel do Operador

**Objetivo**: View standalone dedicada (`/pedidos/`) para o operador gerenciar o ciclo de vida
completo dos pedidos. Painel unificado multi-canal onde chegam todos os pedidos (web, WhatsApp,
iFood, POS) e o operador confirma, rejeita, avança status, e despacha para KDS.
Benchmark: iFood para Restaurantes (merchant app). NÃO é um KDS — é o nível macro de gestão.

### 8.1 Arquitetura

- **View standalone** fora do admin: `/pedidos/` (namespace separado).
- **Autenticação**: via admin session (operador precisa estar logado no admin).
- **Single-page feel**: HTMX polling a cada 5s + push updates via directives.
- **Responsivo**: otimizado para tablet landscape (primary) e desktop. Funcional em mobile portrait.
- **Som**: alerta sonoro configurável para novo pedido (Audio API). Padrão: ativo.
- **Persistência de estado**: pills/filtros mantidos via `sessionStorage` (Alpine.js).

### 8.2 Layout Principal

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 🏪 Nelson Boulangerie — Gestor de Pedidos        14:45  [🔊] [⚙️]      │
├──────────────────────────────────────────────────────────────────────────┤
│ [Aguardando (3)] [Confirmados (5)] [Preparando (2)] [Prontos (1)] [Todos]│
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│ ┌─────────────────────────────────┐  ┌─────────────────────────────────┐ │
│ │ 🌐 #ORD-047      há 2min  ⏱3:12│  │ 🍔 #ORD-046      há 4min  ⏱1:05│ │
│ │ Maria Silva — R$ 47,50          │  │ iFood — R$ 32,00               │ │
│ │ 3× Pão Francês, 1× Café...     │  │ 2× Croissant, 1× Suco...      │ │
│ │ 🚗 Delivery — Rua das Flores   │  │ 🚗 Delivery — via iFood        │ │
│ │                                 │  │                                 │ │
│ │ [✓ Confirmar]  [✗ Rejeitar]     │  │ [✓ Confirmar]  [✗ Rejeitar]    │ │
│ └─────────────────────────────────┘  └─────────────────────────────────┘ │
│                                                                          │
│ ┌─────────────────────────────────┐  ┌─────────────────────────────────┐ │
│ │ 📱 #ORD-045     há 3min  ⏱1:58 │  │ 🏪 #ORD-044     CONFIRMADO     │ │
│ │ João Pedro — R$ 22,00           │  │ Cliente Balcão — R$ 15,00      │ │
│ │ 1× Brioche, 2× Café Latte      │  │ 5× Pão 7 Grãos                 │ │
│ │ 🏪 Retirada — 15:00             │  │ 🏪 Retirada                    │ │
│ │ ⚠️ Café Latte: estoque previsto │  │                                 │ │
│ │ [✓ Confirmar]  [✗ Rejeitar]     │  │ [▸ Preparando]                  │ │
│ └─────────────────────────────────┘  └─────────────────────────────────┘ │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

- **Cards em grid**: 2 colunas em tablet/desktop, 1 coluna em mobile.
- **Cada card**: ref + canal badge + timer + cliente + items resumo + fulfillment type + ações.
- **Ordenação**: FIFO (mais antigo primeiro). Pedidos urgentes (timer amarelo/vermelho) sobem.
- **Cor do timer**: verde (< 3min), amarelo (3-4min), vermelho (> 4min dos 5min de timeout).

### 8.3 Timer de Confirmação (Omotenashi)

O timeout de confirmação otimista é **5 minutos**. Funciona assim:

- **Lado operador**: timer countdown no card do pedido. Visual urgente a partir de 1 min restante.
  Se não agir em 5 min → pedido auto-confirma (optimistic). Operador pode rejeitar antes.
- **Lado cliente** (storefront tracking page, F6):
  - Copy: "Seu pedido foi recebido! A loja tem até 5 minutos para confirmar."
  - Timer visual: countdown (MM:SS), animação pulse suave.
  - Se confirmado antes do timeout: transição celebratória (check verde + "Pedido confirmado!").
  - Se timeout esgota (auto-confirm): mesma transição celebratória.
  - Se rejeitado: mensagem empática + motivo + sugestão de alternativa.
- **Transparência total**: cliente nunca fica no escuro. Princípio omotenashi.

### 8.4 Card Detail — Expandido

Tap no card → expande inline (accordion) ou abre bottom sheet (mobile):

- **Items detalhados**: produto, qty, preço unitário, subtotal, notas especiais.
- **Disponibilidade em tempo real** por item:
  - Disponível (estoque físico): check verde.
  - Previsto (WorkOrder em andamento, ainda não finalizado): badge amarelo "Em produção".
  - Indisponível: badge vermelho + sugestão de alternativa (via `StockAlerts` + catálogo).
- **Ações contextuais** (variam por status):
  - **NEW**: "Confirmar ✓" / "Rejeitar ✗" (com campo motivo obrigatório).
  - **CONFIRMED**: "Iniciar Preparo ▸" (transiciona para PROCESSING, dispara KDS).
  - **PROCESSING**: "Marcar Pronto ▸" (transiciona para READY).
  - **READY**: "Entregar ✓" (retirada) ou "Despachar 🚗" (delivery).
- **Sugestão de alternativas**: se item indisponível, operador pode:
  - Substituir item (seleciona alternativa do catálogo, recalcula preço).
  - Remover item (recalcula total, notifica cliente).
  - Confirmar mesmo assim (se estoque previsto chega a tempo).
- **Notas internas**: textarea para anotações do operador (armazenadas em `Order.data["internal_notes"]`).
- **Timeline**: mini-timeline visual com histórico de status changes.

### 8.5 Integração com Disponibilidade

- Query `StockBackend.check_stock()` para cada item do pedido ao renderizar o card.
- Para items com estoque previsto (WorkOrder `PLANNED` ou `IN_PROGRESS` no Crafting):
  - Exibe badge "Previsto às ~HH:MM" (estimativa baseada no tempo médio de produção).
  - Operador decide se confirma (confiando na produção) ou aguarda.
- Se `StockAlert` ativo para um item:
  - Badge de alerta no card do pedido.
  - Sugestão automática: "Sugerir produção?" → cria WorkOrder com 1 click.
  - Se já há sugestão de produção pendente: link para o WorkOrder no admin.

### 8.6 Despacho para KDS

Quando operador confirma pedido E pagamento está resolvido (ou é POS/cash):
- Order transiciona para PROCESSING.
- Handler `KDSDispatchHandler` analisa items:
  - Item com estoque físico disponível → task para KDS Picking.
  - Item que precisa preparo (tem Recipe ou categoria "prep") → task para KDS Prep.
  - Item misto: split (parte picking, parte prep).
- Cada task é um `KDSTicket` (model leve) vinculado ao Order + item(s) + KDS instance.
- KDS views (F9) fazem polling e exibem os tickets.

### 8.7 Configurações

Acessível via ⚙️ no header:

- Som: on/off, volume, tipo de alerta (beep, chime, bell).
- Auto-refresh: intervalo (3s, 5s, 10s).
- Filtro padrão na abertura (Aguardando vs. Todos).
- Compacto: toggle para cards menores (mais pedidos visíveis).
- Fullscreen: toggle (esconde barra do browser).

### Arquivos

- `channels/web/views/pedidos.py` — novo: GestorPedidosView, PedidoCardPartial, PedidoDetailPartial.
- `channels/web/templates/pedidos/index.html` — novo: layout principal.
- `channels/web/templates/pedidos/partials/card.html` — novo: card de pedido.
- `channels/web/templates/pedidos/partials/detail.html` — novo: card expandido.
- `channels/web/templates/pedidos/partials/config.html` — novo: modal config.
- `channels/web/urls.py` — namespace `/pedidos/`.
- `channels/web/static/js/pedidos.js` — sons, fullscreen, sessionStorage.
- `shopman/handlers/kds.py` — novo: KDSDispatchHandler.
- `shopman/topics.py` — KDS_DISPATCH topic.

### Testes

- `test_gestor_shows_new_orders` — pedidos NEW aparecem.
- `test_gestor_confirm_order` — confirmar transiciona status + dispara KDS.
- `test_gestor_reject_order_requires_reason` — rejeitar exige motivo.
- `test_gestor_timer_countdown` — timer conta de 5:00 para 0:00.
- `test_gestor_auto_confirm_on_timeout` — auto-confirma após 5 min.
- `test_gestor_availability_badges` — items mostram estoque/previsto/indisponível.
- `test_gestor_suggest_alternative` — sugestão de alternativa funciona.
- `test_gestor_suggest_production` — cria WorkOrder com 1 click.
- `test_gestor_dispatches_to_kds` — confirm+paid → KDS tickets criados.
- `test_gestor_sound_on_new_order` — som toca.
- `test_gestor_multichannel_badges` — web, WhatsApp, iFood, POS badges corretos.
- `test_gestor_internal_notes` — notas persistem.

### Dívidas F8

| Item | Razão | Quando resolver |
|------|-------|-----------------|
| Disponibilidade em tempo real por item (8.4) | Check de StockBackend + WorkOrder badge no detail expandido. Implementado o detail mas sem badges de estoque por item | F13 (Integração Plena) |
| Sugestão de alternativas (8.4) | Substituir/remover item indisponível com recalculo. Requer ModifyService no pedido já commitado | F13 |
| Sugerir produção com 1 click (8.5) | Criar WorkOrder direto do gestor. Requer integração Crafting | ✅ F13 — link Produção no gestor + dashboard widget + bulk create |
| Modal de configurações (8.7) | Som, auto-refresh interval, filtro padrão, compacto, fullscreen. Som e fullscreen existem mas sem modal de config | UX polish |

---

## WP-F9: KDS — Kitchen Display System

**Objetivo**: Telas dedicadas de produção/montagem. Cada KDS instance é configurada por
categoria de produto, o que naturalmente define se é **Prep** (preparo: sanduíches, cafés) ou
**Picking** (separação: pães prontos, bebidas, mercearia). Múltiplas instâncias por tipo possíveis.
Opcional: tela de **Expedição** (pedidos totalmente resolvidos).
Benchmark: Toast POS + Square Kitchen + Fresh KDS.

Só recebe pedidos "quentes": confirmados + pagos (status PROCESSING).

### 9.1 Arquitetura

- **Views standalone** fora do admin: `/kds/` (namespace separado).
- **Autenticação**: via admin session (operador precisa estar logado no admin).
- **Instâncias múltiplas**: cada KDS é uma instância com categorias atribuídas.
  - Ex: `/kds/padaria/` = Prep (pães, croissants), `/kds/cafe/` = Prep (drinks),
    `/kds/montagem/` = Picking (separação e embalagem).
  - Configurável via admin: `KDSInstance(ref, name, type=prep|picking, categories=[...])`.
  - `ref` é o slug único da instância (auto-gerado do name, editável).
- **Fullscreen**: sem header/footer. Otimizado para tablet 10" e monitor touch.
- **Dark mode**: fundo escuro padrão (reduz cansaço visual, brilho em cozinha).
- **Auto-refresh**: HTMX polling a cada 5s.
- **Som**: alerta sonoro para novo ticket (Audio API, configurável).

### 9.2 KDS Prep (Preparo)

Recebe tasks de items que precisam ser preparados sob demanda (sanduíches, cafés, receitas).

**Layout**:

```
┌──────────────────────────────────────────────────────────────┐
│ ☕ Café (Prep)          Hoje 14:45          [🔊] [⚙️] [↻]   │
├──────────┬──────────┬──────────┬──────────┬──────────────────┤
│ #ORD-047 │ #ORD-045 │ #ORD-043 │          │                 │
│ 14:32    │ 14:35    │ 14:28    │          │                 │
│ 12min ⏱  │ 9min ⏱   │ 16min ⏱  │          │                 │
│ ──────── │ ──────── │ ──────── │          │                 │
│ □ 2× Lat │ □ 1× Cap │ ✓ 1× Lat │          │                 │
│   te     │   puccino│ □ 1× Moc │          │                 │
│ □ 1× Cap │          │   ha     │          │                 │
│   puccino│          │          │          │                 │
│ ──────── │ ──────── │ ──────── │          │                 │
│ [PRONTO] │ [PRONTO] │ [PRONTO] │          │                 │
│ 🟢 Normal│ 🟢 Normal│ 🔴 Atraso│          │                 │
└──────────┴──────────┴──────────┴──────────┴──────────────────┘
```

- **Tickets**: cards verticais (colunas) organizados por FIFO.
- **Cada ticket**:
  - Header: ref do pedido + hora de entrada no KDS.
  - Timer: tempo desde entrada. Muda de cor conforme target time configurado:
    - Verde (< target time). Amarelo (> target time). Vermelho (> 2× target time).
  - Items: checkbox por item. Tap → toggle ✓/□.
  - Instruções especiais: highlight amarelo se houver notas no item.
  - Botão "PRONTO": full-width. Tap → ticket sai com animação slide-out.
    - Ação: marca items como ready (`FULFILLMENT_ITEM_READY` directive).
    - Se TODOS os items do pedido estão ready → order avança para READY.
- **Filtro por sub-categoria** (opcional): pills "Todos | Bebidas | Sanduíches".
- **Tamanho de texto**: ajustável (P/M/G) via ⚙️.
- **Som**: beep curto (novo), beep duplo (urgente/vermelho).

### 9.3 KDS Picking (Separação/Montagem)

Recebe tasks de items que já existem em estoque e precisam ser separados, embalados e agrupados
por pedido. Ex: pães já assados, bebidas prontas, geléias, queijos.

**Layout**: similar ao Prep, com diferenças de lógica:

- **Tickets**: agrupados por pedido. Contêm apenas items de picking daquela instância.
- **Cada ticket**:
  - Header: ref + nome do cliente + tipo fulfillment (🏪 Retirada | 🚗 Entrega).
  - Items: lista com checkbox "separado/embalado".
  - Prioridade visual: delivery primeiro (precisa sair), retirada depois.
  - Botão "SEPARADO": marca picking completo para aquele grupo de items.
    - Se TODOS os items do pedido (prep + picking) estão ready → order avança para READY.
- **Integração com estoque**: se item deveria estar em estoque mas Quant physical = 0,
  alerta visual no ticket ("⚠ Estoque zerado — verificar").

### 9.4 Expedição (Opcional)

Tela de saída final. Só exibe pedidos **totalmente resolvidos**: confirmados + pagos + TODOS
os items prontos (status READY). Útil para operações com balcão de retirada separado da produção.

**Layout**:

```
┌──────────────────────────────────────────────────────────────┐
│ 📦 Expedição            Hoje 14:45          [🔊] [⚙️]       │
├──────────┬──────────┬──────────┬─────────────────────────────┤
│ #ORD-043 │ #ORD-041 │ #ORD-039 │                             │
│ Maria S. │ João P.  │ iFood    │                             │
│ 🏪 Retir.│ 🚗 Deliv.│ 🚗 Deliv.│                             │
│ ──────── │ ──────── │ ──────── │                             │
│ 3 items  │ 5 items  │ 2 items  │                             │
│ R$ 47,50 │ R$ 62,00 │ R$ 32,00 │                             │
│ ──────── │ ──────── │ ──────── │                             │
│[ENTREGAR]│[DESPACHAR│[DESPACHAR│                             │
│          │    ]     │    ]     │                             │
└──────────┴──────────┴──────────┴─────────────────────────────┘
```

- **Ações**:
  - Retirada → "ENTREGAR" → status DELIVERED, notifica cliente.
  - Delivery → "DESPACHAR" → status DISPATCHED, notifica cliente.
- **Sem checklist de items**: aqui é só confirmar saída. Items já foram validados no Prep/Picking.
- **Badge de canal**: destaque visual para iFood (pode ter SLA de entrega).

### 9.5 Roteamento Pedido → KDS

Quando order muda para PROCESSING (disparado pelo Gestor de Pedidos, F8):

- Handler `KDSDispatchHandler` analisa cada item do pedido:
  - Consulta categoria do produto → determina quais KDS instances recebem.
  - Se produto tem Recipe (Crafting) → KDS Prep instance correspondente.
  - Se produto só precisa separação (estoque físico) → KDS Picking instance correspondente.
  - Item pode ir para múltiplos KDS se necessário (ex: combo com café + pão).
- Cria `KDSTicket` (model leve):
  - `order` (FK), `kds_instance` (FK), `items` (JSON), `status` (pending/in_progress/done),
    `created_at`, `completed_at`.
- KDS views fazem query: `KDSTicket.objects.filter(kds_instance__ref=ref, status__in=[pending, in_progress])`.

### 9.6 Configuração de Instâncias KDS

Acessível via admin: `/gestao/kds/config/`.

- **Criar instância**: nome, tipo (Prep | Picking | Expedição), categorias de produto atribuídas.
  - Ex: "Padaria" tipo Prep, categorias: Pães, Doces.
  - Ex: "Montagem" tipo Picking, categorias: Todas (ou selecionar específicas).
  - Ex: "Expedição" tipo Expedição, categorias: N/A (recebe todos os pedidos READY).
- **Settings por instância**:
  - Target time (minutos) — define quando timer fica amarelo.
  - Som: on/off + tipo de alerta.
  - Tamanho de texto: default P/M/G.
  - Auto-refresh interval (default 5s).
  - Dark mode: on/off (default: on).

### Arquivos

- `shopman/models/kds.py` — novo: KDSInstance, KDSTicket.
- `channels/web/views/kds.py` — novo: KDSView (genérica, renderiza conforme tipo), KDSConfigView.
- `channels/web/templates/kds/base.html` — novo: layout fullscreen dark.
- `channels/web/templates/kds/prep.html` — novo.
- `channels/web/templates/kds/picking.html` — novo.
- `channels/web/templates/kds/expedition.html` — novo.
- `channels/web/templates/kds/partials/ticket.html` — novo: ticket card reutilizável.
- `channels/web/templates/kds/config.html` — novo.
- `channels/web/urls.py` — namespace `/kds/`, routes `/kds/<ref>/`.
- `channels/web/static/js/kds.js` — sons, fullscreen, text size.

### Testes

- `test_kds_instance_creation` — criar instância via admin.
- `test_kds_prep_shows_only_prep_tickets` — filtra por tipo.
- `test_kds_picking_shows_only_picking_tickets` — filtra por tipo.
- `test_kds_expedition_shows_only_ready_orders` — só READY.
- `test_kds_ticket_created_on_processing` — tickets criados ao transicionar.
- `test_kds_routing_by_category` — categoria determina instância.
- `test_kds_multiple_instances_same_type` — 2 KDS Prep com categorias diferentes.
- `test_kds_prep_pronto_marks_items_ready` — botão Pronto funciona.
- `test_kds_all_items_ready_advances_order` — todos prontos → READY.
- `test_kds_timer_color_coding` — timer muda de cor.
- `test_kds_sound_on_new_ticket` — som toca.
- `test_kds_dark_mode` — dark mode aplicado.
- `test_kds_expedition_despachar` — despachar muda status para DISPATCHED.

### Dívidas F9

| Item | Razão | Quando resolver |
|------|-------|-----------------|
| Tamanho de texto ajustável P/M/G (9.6) | Settings por instância via config modal. Admin permite editar mas KDS view não expõe toggle | UX polish |
| Filtro por sub-categoria no KDS Prep (9.2) | Pills "Todos / Bebidas / Sanduíches" dentro de uma estação. Não implementado — items vêm todos juntos | UX polish |
| Picking prioridade visual delivery vs retirada (9.3) | Delivery deveria aparecer primeiro. Hoje ordena por created_at | UX polish |
| Alerta "Estoque zerado" no Picking (9.3) | Se Quant physical=0, mostrar aviso no ticket. Requer query de estoque por item | ✅ F13 — _add_stock_warnings() no KDS Picking + badge no template |
| Beep duplo para tickets urgentes (9.2) | Som diferenciado para timer vermelho. Hoje toca o mesmo beep | UX polish |
| Config page `/gestao/kds/config/` (9.6) | UI dedicada para configurar instâncias. Hoje usa admin padrão (KDSInstanceAdmin) | UX polish |

---

## WP-F10: Admin — POS & Operação Diária

**Objetivo**: POS para balcão e rotinas diárias de operação (fechamento, bundles).
Tudo acessível via admin (Unfold).

### 10.1 Order Admin — Enhanced

No admin padrão do Unfold (complementa o Gestor de Pedidos para operações não-urgentes):

- **Filtros pill** (topo): Novos | Confirmados | Preparando | Prontos | Todos.
  - Badge com contagem em cada pill. HTMX: trocar filtro sem reload.
- **Busca**: por ref, nome do cliente, phone.
- **Cada row**: status badge + canal badge + ref + cliente + hora + nº items + total.
- **Quick actions inline**: confirmar/cancelar/avançar diretamente na row.
- **Auto-refresh**: polling HTMX a cada 15s.

### 10.2 Order Detail — Enhanced

- **Header**: ref + status badge + canal + data + customer link.
- **Timeline**: mesma do storefront (steps visuais).
- **Items**: tabela com produto, qty, preço, subtotal.
- **Pagamento**: status, método, valor, intent_id.
- **Ações contextuais** (botões à direita):
  - Confirmar / Cancelar / Preparar / Pronto / Despachar / Entregar.
  - "Adicionar nota interna" → textarea (visível só para operador).
- **Notas internas**: lista de notas com timestamp + autor.
  - Armazenadas em `Order.data["internal_notes"]`.

### 10.3 POS Mode (Balcão)

**URL**: `/gestao/pos/` (custom view dentro do admin).

**Layout (tablet landscape)**:

```
┌────────────────────────────────────┬──────────────────────┐
│ 🔍 Buscar produto...               │ Venda #42            │
│                                    │                      │
│ [Pães] [Doces] [Café] [Salgados]  │ 3× Pão Francês  4,50│
│                                    │ 1× Croissant    8,00│
│ ┌──────┐ ┌──────┐ ┌──────┐        │ 1× Café         5,00│
│ │ Pão  │ │ Croi │ │ Brio │        │                      │
│ │ Franc│ │ ssant│ │ che  │        │ ──────────────────── │
│ │R$1,50│ │R$8,00│ │R$6,00│        │ Subtotal      17,50 │
│ └──────┘ └──────┘ └──────┘        │ Desconto       0,00 │
│ ┌──────┐ ┌──────┐ ┌──────┐        │ Total         17,50 │
│ │ Éclr │ │ Café │ │ Bolo │        │                      │
│ │R$7,00│ │R$5,00│ │R$12  │        │ 👤 Cliente avulso  ▼│
│ └──────┘ └──────┘ └──────┘        │                      │
│                                    │ [💵 Dinheiro]        │
│                                    │ [📱 PIX]             │
│                                    │ [💳 Cartão]          │
│                                    │                      │
│                                    │ [  FECHAR VENDA  ]   │
└────────────────────────────────────┴──────────────────────┘
```

- **Grid de produtos**: tap para adicionar (incrementa qty se já no carrinho).
- **Carrinho lateral**: items com stepper, subtotal, total.
- **Cliente**: "Cliente avulso" (default) ou busca por phone.
  - Input phone → lookup → preenche nome.
  - Aplica descontos (employee, loyalty) se encontrado.
- **Pagamento**: seleção rápida. Dinheiro = fecha imediatamente. PIX = gera QR. Cartão = integra.
- **Fechar venda**: cria Session → commit → Order (preset `pos()`).
  - Confirmação imediata (sem timeout).
  - Se fiscal configurado: emite NFC-e.
- **Atalhos**: Enter (fechar), Esc (cancelar item), F1-F4 (categorias).

### 10.4 Day Closing

- Wizard no admin: `/gestao/fechamento/`.
- **Step 1**: Resumo de vendas (por canal, método de pagamento, total).
- **Step 2**: Conferência de estoque (quants esperados vs. informados).
  - Input por produto: "Quantidade física no balcão".
  - Diferença calculada automaticamente.
- **Step 3**: Registrar sobras/perdas (StockMovements.adjust).
- **Step 4**: Confirmar → gera `DayClosing` record.
- **PDF/relatório**: gerar para impressão (campo para futuro).

### 10.5 Bundles / Combos (ProductComponent)

O Core tem `ProductComponent` (offering) para composição de produtos (ex: "Combo Café da Manhã"
= 1 pão + 1 café + 1 suco). Hoje não é usado pelo App.

- **No POS**: ao criar combo, items individuais são registrados separadamente para estoque/produção,
  mas o preço cobrado é o do bundle.
- **No storefront**: produto bundle aparece como card normal. PDP mostra "Inclui: X, Y, Z".
  Quick-add adiciona o bundle inteiro.
- **No admin**: criar bundle via form de produto com sub-items (ProductComponent).
- **No KDS**: items do bundle aparecem como items individuais (para preparo correto).
- **Impacto em estoque**: hold criado por sub-item (não pelo bundle SKU).

### Arquivos

- `shopman/admin/order_admin.py` — enhanced com quick actions.
- `channels/web/views/pos.py` — novo.
- `channels/web/views/closing.py` — refactor wizard.
- `channels/web/templates/admin/pos.html` — novo.
- `channels/web/templates/admin/orders/` — partials enhanced.

### Testes

- `test_order_list_quick_confirm` — confirmar da lista.
- `test_order_list_auto_refresh` — polling atualiza.
- `test_pos_add_product_tap` — tap adiciona.
- `test_pos_customer_lookup` — busca por phone.
- `test_pos_close_sale_creates_order` — venda vira order.
- `test_day_closing_creates_record` — fechamento gera DayClosing.
- `test_bundle_adds_subitems_to_cart` — bundle decompõe em sub-items para estoque.
- `test_bundle_kds_shows_individual_items` — KDS mostra items individuais.

### Dívidas F10

| Item | Razão | Quando resolver |
|------|-------|-----------------|
| Descontos employee/loyalty ao identificar cliente no POS | Requer rodar ModifyService modifiers no fluxo POS (hoje cria Session sem rodar modifiers de desconto por cliente) | ✅ F13 — _resolve_customer() seta customer.group antes do ModifyService |
| PIX no POS gera QR | Hoje o POS fecha direto independente do método selecionado. Precisa de redirect para tela PIX após commit se method=pix | Quando payment gateway PIX estiver integrado |
| NFC-e após fechar venda | Depende do backend fiscal (FISCAL_EMIT_NFCE). Não existe implementação fiscal ainda | F-Fiscal (plano separado) |
| Bundles no POS (10.5) | ProductComponent existe no Core mas POS não decompõe bundles em sub-items para estoque/KDS | Sprint dedicado — requer integração com StockHoldHandler bundle expansion |

---

## WP-F11: Admin — Backoffice & Configuração da Loja

**Objetivo**: Operador configura tudo da loja sem assistência técnica.
Benchmark: Take.app (wizard simples, preview da loja). Aproveitar Unfold admin com custom views.

### 11.1 Wizard de Onboarding

- Na primeira vez que acessa o admin (Shop não configurado):
  - Redirect para `/gestao/setup/`.
  - **Step 1**: Nome da loja, logo, descrição curta.
  - **Step 2**: Endereço, telefone (WhatsApp), email.
  - **Step 3**: Horário de funcionamento (grid de dias × horário abre/fecha).
  - **Step 4**: Cores e visual (seletor de palette, preview em tempo real).
  - **Step 5**: Método de pagamento (PIX config, Cartão toggle).
  - **Step 6**: Primeiro produto (criar produto rápido com foto, nome, preço).
  - Ao finalizar: Shop criado, redirect para dashboard com "Sua loja está no ar! 🎉".

### 11.2 Shop Settings Page

- Custom view: `/gestao/configuracoes/`.
- Seções (tabs ou accordion):
  - **Identidade**: nome, logo, cores, tipografia.
  - **Contato**: endereço, phone, email, redes sociais.
  - **Horários**: grid editável. Toggle "Aceitar pedidos fora do horário" (preorder).
  - **Delivery**: toggle "Habilitar delivery", zonas (CEPs), taxa fixa ou por distância.
  - **Pagamentos**: PIX (chave, banco), Cartão (Stripe key), toggles on/off.
  - **Canais**: web (on/off), WhatsApp (config), iFood (config).
  - **Promoções**: lista de promoções ativas, criar nova.
  - **Cupons**: lista de cupons, criar novo.
  - **KDS**: config de estações, tempos alvo, sons.
  - **Operação** (configs sensíveis, editáveis em produção):
    - Timeout de confirmação otimista (minutos).
    - Timeout de pagamento PIX (minutos).
    - Timeout de pagamento Cartão (minutos).
    - Hold TTL de estoque (minutos).
    - Safety margin de estoque.
    - Planned hold TTL (horas).
    - Posições de estoque permitidas por canal.
    - Auto-sync fulfillment (on/off).
    - Cada campo salva no `Shop.defaults` → sobrescreve preset via cascata ChannelConfig.
    - Protegido por permissão admin (grupo "Gerência").
- **Preview**: botão "Ver minha loja" → abre storefront em nova tab.

### 11.3 Catálogo — Enhanced

- **Produto form**: melhorado com:
  - Drag-and-drop para reordenar fotos.
  - Preview da imagem com crop (aspect-ratio 4:3).
  - Campos: nome, descrição, preço, SKU, coleções (tags), disponibilidade.
  - Toggle "Disponível" (on/off rápido).
  - Alérgenos (tags selecionáveis).
  - Ingredientes (textarea).
- **Bulk actions**: ativar/desativar múltiplos produtos.
- **Import/export** (usa `offering.contrib.import_export`):
  - CSV upload para atualizar preços em massa.
  - CSV download para backup.

### 11.4 Coleções — Enhanced

- Drag-and-drop para reordenar coleções e produtos dentro de coleções.
- Preview visual do menu (como fica no storefront).

### Arquivos

- `channels/web/views/setup.py` — novo: wizard de onboarding.
- `channels/web/views/settings.py` — novo: shop settings.
- `channels/web/templates/admin/setup/` — novo: steps do wizard.
- `channels/web/templates/admin/settings.html` — novo.
- `shop/admin.py` — enhanced produto form.

### Testes

- `test_onboarding_wizard_creates_shop` — wizard completo cria Shop.
- `test_settings_update_shop` — settings atualizam.
- `test_product_bulk_toggle` — ativar/desativar em massa.
- `test_import_csv_updates_prices` — CSV atualiza preços.
- `test_collection_reorder` — reordenação persiste.

---

## WP-F12: Admin — Dashboard, Analytics & BI

**Objetivo**: Dashboard operacional rico + dados prontos para BI externo.
Usa plenamente: DayClosing, StockAlerts, Order data, Customer insights, LoyaltyService.

### 12.1 Dashboard Operacional — Upgrade

Sobre o existente (493 linhas), adicionar:

- **KPIs com comparação**: valor + variação vs. ontem/semana passada. Seta verde/vermelha.
  - Pedidos hoje, ticket médio, receita, tempo médio de preparo.
- **Pedidos pendentes de ação**: card alerta "X pedidos aguardando confirmação" → link direto.
- **Alertas do sistema**: widget com OperatorAlerts (F0.4) não lidos.
- **Gráfico de vendas por hora**: barras por hora do dia (útil para padaria ver pico).
- **Auto-refresh**: HTMX polling a cada 60s nos widgets dinâmicos.

### 12.2 Analytics Views

- **Vendas por período**: filtro data range + gráfico de linha + tabela.
  - Métricas: pedidos, receita, ticket médio, cancelamentos.
  - Breakdown por canal (web, WhatsApp, POS, iFood).
- **Top produtos**: ranking por quantidade vendida e por receita. Período selecionável.
- **Clientes**: RFM segmentation (usa `customers.contrib.insights`).
  - Tabela: top clientes por valor, frequência, recência.
  - Insights automáticos: "15 clientes não compram há 30 dias".
- **Estoque**: alertas de mínimo (usa `StockAlerts`), produtos mais movimentados.
- **Produção**: eficiência (WorkOrders completados vs. planejados), desperdício (sobras do DayClosing).
- **Loyalty**: pontos emitidos, resgatados, tier distribution.

### 12.3 Export para BI

- **Endpoints API** para cada analytics view (JSON):
  - `GET /api/analytics/sales/?from=&to=` → vendas por período.
  - `GET /api/analytics/products/?from=&to=` → top produtos.
  - `GET /api/analytics/customers/rfm/` → segmentação RFM.
  - `GET /api/analytics/stock/alerts/` → alertas de estoque.
- **CSV export**: botão em cada view de analytics.
- **Dados estruturados**: Orders com `snapshot` (items, pricing, customer), DayClosing,
  Moves, WorkOrders — tudo queryable para Metabase/Power BI via PostgreSQL direto.

### Arquivos

- `shop/dashboard.py` — expandir widgets.
- `channels/web/views/analytics.py` — novo.
- `channels/api/analytics.py` — novo: endpoints JSON.
- `channels/web/templates/admin/analytics/` — novo.

### Testes

- `test_dashboard_kpis_with_comparison` — variação calculada.
- `test_analytics_sales_by_period` — vendas por data range.
- `test_analytics_top_products` — ranking correto.
- `test_analytics_rfm_segments` — segmentos calculados.
- `test_analytics_api_json` — endpoint retorna JSON válido.
- `test_analytics_csv_export` — CSV com headers corretos.

---

## WP-F13: Integração Plena: Vendas ↔ Produção ↔ Estoque ↔ CRM

**Objetivo**: O ciclo completo funciona de ponta a ponta sem intervenção manual.
Pedido → estoque reservado → produção disparada → estoque atualizado → KDS notificado →
cliente notificado → CRM atualizado → analytics computados.

### 13.1 Pedido → Produção Automática

Quando order em PROCESSING e items precisam produção:
- `KDSDispatchHandler` (F8/F9) identifica items sem estoque físico.
- Cria ou vincula WorkOrder no Crafting:
  - Se WorkOrder do dia já existe para esse SKU: incrementar quantidade.
  - Se não: criar WorkOrder com items do pedido.
- WorkOrder aparece no KDS Prep.

### 13.2 Produção → Estoque

Quando WorkOrder completa no KDS Prep (botão "Pronto"):
- `CraftingBackend.complete_work_order()` → `StockMovements.receive()`.
- Quants atualizados: posição de produção → posição de venda.
- Signal `holds_materialized` dispara → holds pendentes são confirmados.
- KDS Picking atualiza (items agora disponíveis para montagem).

### 13.3 Estoque → Alertas Automatizados (Pipeline Completo)

Usar `StockAlerts` do Core (underutilizado hoje) como trigger de uma pipeline:

- **Trigger**: Quando Move.post_save atualiza Quant e cai abaixo do mínimo do StockAlert:
  1. Criar `OperatorAlert` (F0.4) com severity=warning.
  2. Widget no dashboard: "Estoque baixo: Pão Francês (5 unidades restantes)".
  3. Email para operador (se configurado).
  4. **Cascata automática** (configurable):
     - Se produto tem Recipe → sugerir WorkOrder (F13.5).
     - Se canal iFood ativo → pausar item no iFood (F16.3).
     - Se canal web ativo → badge "Últimas unidades" no storefront.
- Automatizar via signal em Move.post_save → `StockAlertService.check(sku)`.
- Config por produto: `StockAlert.auto_reorder = True/False`,
  `StockAlert.auto_pause_marketplace = True/False`.

### 13.4 CRM → Timeline & Insights

- Cada pedido completado:
  - `TimelineEvent` criado para o Customer (via handler existente).
  - `InsightService.recalculate()` atualizado (RFM scores).
  - `LoyaltyService.earn_points()` executado (handler existente).
- Customer.data enriquecido: total_spent, order_count, last_order_date, favorite_products.
- Isso alimenta:
  - Analytics de clientes (F12).
  - Sugestões de recompra (future).
  - Segmentação para notificações (F14).

### 13.5 Sugestão de Produção Automática

- Management command `suggest_production` (já existe!) usa `craft.suggest()`:
  - Baseado em histórico de demanda (DemandProtocol).
  - Sugere WorkOrders para o dia seguinte.
- **Upgrade**: dashboard widget "Sugestão de produção para amanhã":
  - Lista de produtos + quantidade sugerida.
  - Botão "Criar ordens de produção" (bulk create WorkOrders).
  - Operador ajusta quantidades e confirma.

### 13.6 Dados para BI

Garantir que todas as entidades relevantes têm campos para análise:
- `Order.snapshot`: items completos com preços, descontos, canal.
- `DayClosing`: vendas, estoque, sobras.
- `Move`: rastreabilidade completa (quem, quando, por quê, quanto).
- `WorkOrder`: produção planejada vs. real.
- `Customer` + insights: RFM, lifetime value.
- `LoyaltyTransaction`: pontos emitidos/resgatados.
- Todos com timestamps e refs para joins.

### Arquivos

- `shopman/handlers/kds.py` — routing items → WorkOrder.
- `shopman/handlers/stock.py` — integrar com StockAlerts.
- `shop/dashboard.py` — widget de sugestão de produção.
- `channels/web/views/production.py` — bulk create WorkOrders.

### Testes

- `test_order_creates_work_order` — pedido sem estoque gera WorkOrder.
- `test_work_order_complete_updates_stock` — produção atualiza Quant.
- `test_holds_materialized_confirms_holds` — signal funciona.
- `test_stock_alert_creates_operator_alert` — estoque baixo gera alerta.
- `test_order_complete_updates_crm` — timeline + insights + loyalty.
- `test_suggest_production_shows_in_dashboard` — sugestão visível.
- `test_bulk_create_work_orders` — criar múltiplas WOs.
- `test_e2e_order_to_production_to_stock` — ciclo completo.

---

## WP-F14: Notificações Multi-Canal

**Objetivo**: Cliente nunca no escuro. Cada evento relevante gera notificação no canal certo.

### 14.1 Email Templates Completos

Todos os eventos com template HTML branded:

| Evento | Template | Status |
|--------|----------|--------|
| order_placed | Pedido recebido + link tracking | ✅ Existe |
| order_confirmed | Confirmado + estimativa tempo | ✅ Existe |
| order_processing | Em preparo | ✅ Existe |
| order_ready | Pronto! | ✅ Existe |
| order_dispatched | Saiu para entrega | ⬚ Criar |
| order_delivered | Entregue + pedir avaliação | ⬚ Criar |
| order_cancelled | Cancelado + info reembolso | ⬚ Criar |
| payment_confirmed | Pagamento recebido | ⬚ Criar |
| payment_refunded | Reembolso processado | ⬚ Criar |
| loyalty_earned | Pontos ganhos + saldo | ⬚ Criar |

Design: logo, cores da loja, CTA button, footer, plain text fallback, responsivo (< 600px).

### 14.2 WhatsApp Notifications

- Via ManychatBackend (existente) ou WhatsApp Business API.
- Mensagens para: order_placed, order_ready, payment_confirmed.
- Link de tracking no corpo.

### 14.3 Notification Preferences

- Em Conta > Config: toggles por canal × tipo.
- Respeitar sempre: não enviar se desativado.
- Default: tudo ativo (opt-out).

### Arquivos

- `channels/templates/notifications/` — 6 novos templates.
- `shopman/backends/notification_email.py` — registrar novos eventos.
- `channels/web/views/account.py` — notification preferences.

### Testes

- `test_email_order_cancelled_sent` — email enviado.
- `test_whatsapp_order_ready_sent` — WhatsApp enviado.
- `test_notification_preference_respected` — desativado não envia.

---

## WP-F15: Canal WhatsApp

**Objetivo**: Pedido via WhatsApp fluido. Link para cardápio web → checkout → notificações
no chat. Preset `whatsapp()` configurado.

### 15.1 Preset

- `whatsapp()` em `presets.py`:
  - Confirmation: optimistic.
  - Payment: PIX (link).
  - Notifications: WhatsApp.
  - Pipeline: stock → payment → notification.

### 15.2 Flow

1. Cliente envia msg / clica link → redirect para storefront mobile com `?channel=whatsapp`.
2. Checkout marca `channel=whatsapp`.
3. Confirmações e updates via WhatsApp.
4. PIX: link de pagamento enviado no chat.

### 15.3 Bot Simples

- Webhook para mensagens incoming.
- Respostas automáticas: "Oi! Acesse nosso cardápio: [link]", "Status do seu pedido: [link]".
- FAQ: horário, endereço, cardápio.

### Arquivos

- `shopman/presets.py` — `whatsapp()`.
- `shopman/webhooks.py` — WhatsApp webhook.
- `shopman/backends/notification_whatsapp.py` — expandir.

### Testes

- `test_whatsapp_preset_configured`.
- `test_whatsapp_order_receives_notification`.
- `test_whatsapp_webhook_parses_message`.

---

## WP-F16: Canal Marketplace (iFood)

**Objetivo**: Pedidos iFood integrados ao Shopman. Estoque, produção, KDS — tudo conectado.

### 16.1 Integration

- Webhook receiver para events iFood.
- Mapeamento iFood product ID → Shopman SKU.
- Order creation: iFood event → Session → Order (preset `marketplace()`).

### 16.2 Operator Visibility

- Badge "iFood" nos pedidos no admin e KDS.
- Aceitar/recusar → callback para iFood API.

### 16.3 Stock Sync

- Ao esgotar no Shopman: pausar item no iFood.
- Ao repor: reativar.

### Arquivos

- `shopman/backends/marketplace_ifood.py` — novo.
- `shopman/webhooks.py` — iFood webhook.

### Testes

- `test_ifood_webhook_creates_order`.
- `test_ifood_sku_mapping`.
- `test_ifood_stock_sync`.

---

## WP-F17: Testes E2E & Stress de Fluxos

**Objetivo**: Todo fluxo crítico testado de ponta a ponta. Nenhum caminho sem cobertura.

### 17.1 E2E (Playwright)

Happy paths:
1. Menu → add → cart → checkout → PIX → tracking (cliente novo).
2. Menu → add → cart → checkout prefilled → PIX → tracking (cliente recorrente).
3. Gestor de Pedidos → ver pedido → confirmar → preparar → pronto → entregue.
4. KDS Prep → check items → Pronto → KDS Picking → Despachar.
5. POS → add items → selecionar cliente → fechar venda.

Edge cases:
6. Produto esgota durante checkout → toast de conflito.
7. PIX expira → auto-cancel → cliente vê "Pedido cancelado".
8. Double-click submit → idempotency protege.
9. OTP incorreto 5x → rate limit.
10. Reorder com item indisponível → toast parcial.

### 17.2 Load Testing (Locust)

- 100 concurrent browsing menu.
- 50 concurrent checkouts.
- 20 concurrent PIX payments.
- Dashboard admin com 10 operators.
- KDS com 30 tickets simultâneos.
- Target: P95 < 500ms.

### 17.3 Flow Integrity

- `test_e2e_order_to_kds_to_delivery` — ciclo completo.
- `test_e2e_cancel_refund_stock_release` — cancelamento libera tudo.
- `test_e2e_loyalty_earn_redeem` — pontos ganhos e resgatados.
- `test_e2e_production_suggestion_to_work_order` — sugestão → produção.

### Arquivos

- `tests/e2e/` — novo diretório com Playwright.
- `tests/load/locustfile.py` — cenários de carga.

---

## Ordem de Execução

```
Fase 1 — Fundação
  F0: Correções de Fluxo & Robustez
  F1: Design System Mobile-First

Fase 2 — Storefront App-Like
  F2: Navegação (bottom nav, gestos, transições)
  F3: Catálogo & Discovery
  F4: Carrinho & Checkout
  F5: Pagamento & Confirmação
  F6: Tracking & Pós-Venda
  F7: Conta, Loyalty & Preferências

Fase 3 — Operação
  F8: Gestor de Pedidos (painel standalone)
  F9: KDS — Prep, Picking & Expedição
  F10: POS & Operação Diária
  F11: Backoffice & Config da Loja
  F12: Dashboard, Analytics & BI
  F13: Integração Vendas↔Produção↔Estoque↔CRM

Fase 4 — Canais & Validação
  F14: Notificações Multi-Canal
  F15: Canal WhatsApp
  F16: Canal Marketplace (iFood)
  F17: Testes E2E & Stress
```

**Dependências**:
- F1 antes de F2-F7 (componentes base).
- F0 antes de F8, F10 e F13 (fluxos corrigidos).
- F2 antes de F3-F7 (navegação base).
- F8 antes de F9 (KDS recebe pedidos do Gestor).
- F8-F10 podem rodar em paralelo com F2-F7.
- F13 requer F0 + F8 + F9 (gestão + KDS + fluxos corrigidos).
- F17 por último (valida tudo).

---

## Princípios Transversais

1. **Core é sagrado — compreenda antes de alterar**:
   - O Core (`shopman-core/`) é robusto e flexível por design. Não adicionar campos, migrações
     ou classes sem comprovar que o mecanismo existente não atende.
   - `Session.data`, `Order.data`, `Directive.payload`, `Channel.config` são JSONFields
     desenhados para extensibilidade sem migrações. Dados contextuais vivem no JSON.
   - Antes de propor alteração no Core: ler os services (`commit.py`, `modify.py`, `write.py`),
     os handlers, e os testes existentes. Se parece que o Core não suporta, é mais provável
     que não se encontrou onde ele já resolve.
   - Referência obrigatória: [`docs/reference/data-schemas.md`](docs/reference/data-schemas.md)
     — inventário de chaves usadas em cada JSONField. Toda nova chave deve ser documentada lá
     antes de ser usada.
2. **44px mínimo**: toda área clicável, sem exceção.
3. **Mobile-first real**: design em 375px primeiro, desktop depois.
4. **HTMX ↔ servidor, Alpine ↔ DOM**: sem exceção.
5. **Testes acompanham**: nenhum WP sem testes.
6. **Acessibilidade**: ARIA, contraste, teclado, screen reader — em cada componente.
7. **Zero emoji como fallback**: placeholder SVG branded.
8. **Centavos com _q**: sem exceção.
9. **Português na UI, inglês no código**.
10. **Cada WP é deployable**: nenhum WP quebra o que já funciona.

---

## WP-F18: Schema Governance — Documentação e Validação de JSONFields

**Objetivo**: Tornar os schemas dos JSONFields (`Session.data`, `Order.data`, `Directive.payload`,
`Channel.config`) explícitos, documentados, e protegidos contra uso incorreto.

**Problema resolvido**: O Core é flexível por design — JSONFields permitem extensão sem migrações.
Mas essa flexibilidade cria risco: qualquer agente ou desenvolvedor pode inventar chaves, duplicar
informação, ou quebrar contratos implícitos. Sem documentação explícita dos schemas, cada pessoa
que toca no código reinventa ou colide.

### 18.1 Referência de Schemas (docs/reference/data-schemas.md)

Documento vivo com o inventário completo de chaves usadas em cada JSONField:

- `Session.data`: customer, fulfillment_type, delivery_address, delivery_date, delivery_time_slot,
  order_notes, origin_channel, coupon_code, checks, issues
- `Order.data`: (tudo acima via CommitService) + payment, customer_ref, fulfillment_created,
  returns, nfce_*, cancellation_reason, is_preorder
- `Directive.payload`: order_ref, channel_ref, session_key, origin_channel, template, holds, items, rev
- `Channel.config`: ChannelConfig schema (7 aspectos)

Cada chave documentada com: tipo, quem escreve, quem lê, quando, exemplo.

### 18.2 Regras de Governança

- **Toda nova chave** em qualquer JSONField deve ser adicionada ao data-schemas.md antes do merge.
- **CommitService._do_commit()** tem a lista explícita de chaves propagadas Session→Order. Para
  propagar uma nova chave, adicione-a nessa lista. Não invente fluxos paralelos.
- **Nenhum handler escreve em chave que outro handler lê** sem contrato documentado.

### 18.3 Validação Futura (pós-MVP)

Quando o projeto amadurecer, considerar:
- Pydantic/dataclass validators nos services de write/commit.
- JSON Schema formal no `Channel.config` (já tem ChannelConfig dataclass com `validate()`).
- Testes que verificam que nenhuma chave não-documentada aparece nos JSONFields.

### Arquivos

- `docs/reference/data-schemas.md` — novo, referência de schemas.
- `CLAUDE.md` — atualizado com regras de integridade do Core.
- `PRODUCTION-PLAN.md` — princípio 1 expandido.

### Testes

- `test_commit_propagates_documented_keys` — verifica que CommitService copia exatamente as chaves documentadas.
- `test_no_undocumented_keys_in_order_data` — fixture que cria order via commit e verifica que todas as chaves em order.data estão na lista documentada.
