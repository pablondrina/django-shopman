# BACKOFFICE-UI-PLAN — Penguin UI Refactor (Omotenashi-First)

> O sistema serve o humano para que o humano sirva o cliente.
> — Omotenashi Protocol Framework

## Visão

Unificar todas as telas operador (Pedidos, KDS, POS, Produção, Fechamento)
sob o design system Penguin UI com tema Industrial. Cada tela aplica os
três portões do omotenashi: **Antecipar** (contexto proativo), **Estar
Presente** (foco + ma), **Ressoar** (fechamento com significado).

---

## Estado Atual

| Área | Base Template | Design System | Interatividade |
|------|--------------|---------------|----------------|
| Pedidos | `pedidos/base.html` (standalone) | OKLCH tokens custom (`--ped-*`) | Alpine + HTMX |
| KDS | `kds/base.html` (standalone) | OKLCH tokens custom (`--kds-*`) | Alpine + HTMX |
| POS | `pos/index.html` (standalone) | Tailwind + design tokens Django | Alpine + HTMX |
| Produção | `admin/base_site.html` (Unfold) | Tailwind raw | Nenhum |
| Fechamento | `admin/base_site.html` (Unfold) | Tailwind raw | Nenhum |
| Dashboard | `admin/base.html` (Unfold) | Unfold components | Nenhum |

**Problemas:**
- 3 sistemas visuais distintos, zero coesão
- Sem navegação entre áreas operador (cada tela é uma ilha)
- Produção/Fechamento sem HTMX — refresh manual
- KDS e Pedidos reinventam tokens que Penguin UI já resolve
- Dashboard preso ao Unfold — sem identidade da marca

---

## Arquitetura Proposta

### Shell: `gestao/base.html`

Template base compartilhado para TODAS as telas operador. Implementa o
padrão "Sidebar with top navbar" do Penguin UI.

```
┌──────────────────────────────────────────────────┐
│ [≡] Nelson Boulangerie    🕐 15:32   🔔 3   👤  │ ← Top navbar
├──────┬───────────────────────────────────────────┤
│      │                                           │
│ 📋   │  {% block content %}                      │
│ 🍳   │                                           │
│ 💰   │  Conteúdo da página                       │
│ 🏭   │                                           │
│ 📊   │  {% endblock %}                           │
│ 🔒   │                                           │
│      │                                           │
├──────┴───────────────────────────────────────────┤
│ Turno: 47 pedidos · R$ 3.240,00         v2.1.0  │ ← Footer (opcional)
└──────────────────────────────────────────────────┘
```

**Sidebar items:**
- Pedidos (`/pedidos/`) — com badge de contagem "new"
- KDS (`/kds/`) — lista estações
- POS (`/gestor/pos/`)
- Produção (`/admin/shop/shop/production/`)
- Dashboard (`/admin/`)
- Fechamento (`/admin/shop/shop/closing/`)

**Top navbar:**
- Nome da loja + logo
- Relógio (mono)
- Alertas (badge count)
- Perfil operador (nome + logout)

**Mobile:** sidebar colapsa em overlay (hamburger no top navbar).

**Dark mode:** toggle no sidebar. Persistido em `localStorage`.

### Design Tokens

Tema Industrial do Penguin UI aplicado ao backoffice:
- Surface: `stone-950` / `stone-900` (dark-first para operação)
- Primary: `amber-400` (dark mode — visibilidade máxima)
- Semantic: mesmo tema storefront (cyan-700, lime-800, yellow-600, orange-700)
- Font: Instrument Sans (consistência com storefront)
- Radius: `--radius-sm`

**Por que dark-first:** telas operador ficam ligadas o dia inteiro.
Dark mode reduz fadiga visual e brilho em ambiente de cozinha/balcão.
Opção light para ambientes com muita luz.

### CSS: Uma única stylesheet

Novo arquivo `static/src/style-gestao.css` com Tailwind v4:
- `@theme` com tokens Penguin UI (dark-first)
- `@source` apontando para os diretórios reais dos templates de backstage
- Componentes reutilizáveis via `@layer components`
- Elimina os 460+ linhas de CSS inline em `pedidos/base.html`
- Elimina os 200+ linhas de CSS inline em `kds/base.html`

---

## Work Packages

### WP-1: Shell + CSS Foundation (gestao/base.html)

**Cria:**
- Shell Penguin UI em `shopman/backstage/templates/` — sidebar compartilhada
- `static/src/style-gestao.css` — design tokens + components
- Build target `v3:build` no `package.json`

**Tokens do shell:**
- Sidebar: Penguin UI sidebar pattern (Alpine.js `x-data`)
- Top navbar: relógio, alertas, perfil
- Responsivo: sidebar persistent desktop, overlay mobile
- Dark/light toggle

**Omotenashi — Antecipar:**
- Badge no sidebar mostra contagem de pedidos "new" (sem precisar abrir)
- Relógio sempre visível (operador sabe a hora sem olhar o celular)
- Alertas operador visíveis no navbar (estoque baixo, pedidos atrasados)

### WP-2: Gestor de Pedidos — Penguin UI

**Migra:** `pedidos/` → `gestao/pedidos/` (estende `gestao/base.html`)

**Elimina:** ~460 linhas de CSS inline + tokens `--ped-*`

**Mantém:** Toda a lógica Alpine.js + HTMX (testada e funcional)

**Componentes Penguin UI:**
- Cards: `bg-surface-dark-alt` + `border-outline-dark` + left accent
- Badges: semantic colors (warning, info, success)
- Pills: filter tabs com contagem
- Buttons: `btn-primary`, `btn-secondary`, semantic variants
- Timer: `font-mono` + semantic color classes
- Detail accordion: disclosure pattern

**Omotenashi — Estar Presente:**
- **Ma:** grid com gap adequado. Cards respiram. Sem informação amontoada.
- **Foco:** um pedido aberto por vez no detalhe. Ação principal é grande e clara.
- **Contexto:** canal (ícone), tipo de entrega (ícone), tempo na fila (cor timer).
- **Poka-yoke:** confirmação antes de rejeitar. Motivo obrigatório para rejeição.

**Omotenashi — Ressoar:**
- Timer verde quando ok, amarelo > 5min, vermelho > 10min
- Som no pedido novo (já existe)
- Contagem de pedidos resolvidos no turno (footer)

### WP-3: KDS — Penguin UI

**Migra:** `kds/` → `gestao/kds/` (estende `gestao/base.html`)

**Elimina:** ~200 linhas de CSS inline + tokens `--kds-*`

**Mantém:** Lógica Alpine.js + HTMX polling + som + fullscreen

**Componentes Penguin UI:**
- Ticket cards: surface-dark-alt + accent left border por status
- Item checklist: checkbox visual com strikethrough
- Timer: mono + semantic colors
- Station header: name + queue count + clock
- Expedition cards (variant com tracking info)

**Nota especial:** KDS tem requisito de fullscreen. O shell sidebar deve
poder ser ocultado em modo fullscreen (`document.fullscreenElement`).
Quando fullscreen, sidebar hidden + top navbar minimal (clock + exit).

**Omotenashi — Antecipar:**
- Pedidos ordenados por urgência (tempo na fila)
- Alergias/notas do cliente em destaque (badge danger)
- Stock warnings inline (item com estoque baixo)

**Omotenashi — Estar Presente:**
- Tela limpa: só tickets relevantes para esta estação
- Touch-first: botões 48px+, áreas de toque generosas
- Feedback tátil: vibração em item checked (já implementado)
- Ma: espaço entre tickets, sem grid apertado

### WP-4: POS — Penguin UI

**Migra:** `pos/` → `gestao/pos/` (estende `gestao/base.html`)

**Mantém:** Layout 2-column (product grid + cart sidebar) — já funciona bem.

**Ajustes:**
- Remover design tokens inline da `_design_tokens_no_alpine.html`
- Usar tokens do `style-gestao.css`
- Product tiles: Penguin card pattern
- Cart: Penguin surface-alt
- Modais: Penguin modal pattern

**Omotenashi — Ressoar:**
- Após venda: resultado com nome do cliente + total + feedback visual
- Shift summary no footer: "47 clientes servidos hoje · R$ 3.240,00"

### WP-5: Produção + Fechamento — Penguin UI

**Migra:** `admin/shop/production.html` e `admin/shop/closing.html`
→ `gestao/producao/` e `gestao/fechamento/` (estendem `gestao/base.html`)

**Desacopla do Unfold:** Não dependem mais de `admin/base_site.html`

**Produção — melhorias:**
- Adicionar HTMX polling para work orders (atualiza sem F5)
- KPI cards: Penguin card pattern com cores semânticas
- Quick entry form: inline em card, sem página separada
- Table: Penguin table pattern com badges de status

**Fechamento — melhorias:**
- Formulário com validação client-side (Alpine)
- Preview do impacto antes de confirmar
- Resultado: snapshot legível pós-fechamento

### WP-6: Dashboard — Penguin UI (opcional)

**Avaliação:** O dashboard Unfold funciona. Migrar para Penguin UI é
desejável por coesão visual, mas é o maior esforço (templates de chart,
table builders do Unfold). Pode ser fase posterior.

**Se fizer:**
- `gestao/dashboard/` estendendo `gestao/base.html`
- Chart.js direto (sem Unfold wrappers)
- KPI cards: Penguin pattern
- Tables: Penguin table pattern

---

## Ordem de Execução

```
WP-1 (Shell)
  ↓
WP-2 (Pedidos) ←── prioridade: tela mais usada
  ↓
WP-3 (KDS) ←── segunda prioridade: operação em tempo real
  ↓
WP-4 (POS)
  ↓
WP-5 (Produção + Fechamento)
  ↓
WP-6 (Dashboard) ←── opcional, fase posterior
```

**Estimativa de complexidade:**
- WP-1: Médio (shell + CSS setup)
- WP-2: Alto (templates + preserve Alpine/HTMX)
- WP-3: Alto (fullscreen mode + touch targets)
- WP-4: Médio (layout já bom, ajustes de tokens)
- WP-5: Baixo (templates simples)
- WP-6: Alto (charts + tables + desacoplamento Unfold)

---

## Princípios de Design (Omotenashi para Operador)

1. **Dark-first, light available.** Operador trabalha o dia inteiro olhando a tela.
2. **Touch-first, keyboard-friendly.** Tablet no balcão, desktop no escritório.
3. **Informação contextual proativa.** Não esperar o operador perguntar.
4. **Uma ação clara por estado.** O botão principal é óbvio e grande.
5. **Ma generoso.** Cards respiram. Nunca amontoar.
6. **Feedback imediato.** HTMX swap + indicadores de loading em tudo.
7. **Navegação sempre disponível.** Sidebar permite trocar entre áreas sem perder contexto.
8. **Turno como unidade.** Contadores, resumos e KPIs sempre referentes ao turno atual.
