# Padronização de UX — Gestor: Cardápio × Pedidos (item 1)

> Handoff para nova sessão. Objetivo do Pablo: os dois boards do Gestor Nuxt
> (**Pedidos** e **Cardápio**) precisam de **um padrão único** de UI/UX — design
> thinking, omotenashi, estado da arte, zero espaço à toa. Pegar o melhor de cada e
> unificar. O modelo (Coleção/Canal/Expositor) já foi refatorado e está estável —
> ESTE item é só a camada de apresentação dos dois boards. `make test`/vitest ao fim.

## Onde
Superfície `surfaces/orders-nuxt` (o Gestor; porta **3004**, Django **8000**,
sempre `127.0.0.1`). Nuxt + **reka-ui + tailwind-variants** (NÃO é Alpine — Alpine é
só o menuboard/Django). Componentes UI em `app/components/Ui/*`. Tokens em
`app/assets/css/tailwind.css` (neutro-first "à la Odoo": cor só com significado).
Login: sessão staff do Django (`shop.manage_orders`) — abrir `/admin/` antes; ⚠️ o
runserver às vezes precisa restart p/ carregar rotas novas.

## Os dois boards hoje (comparação já feita)
- **Pedidos** (`app/pages/index.vue`) — chrome de operador **maduro**: barra full-bleed
  compacta (ícone + "Gestor/Pedidos" + relógio + busca-com-ícone + AlertsBell + refresh
  ícone + toggle de tema), triage bar separada (chips `bg-primary` ativos + sort-menu +
  export/print + board/table), **atalhos de teclado** (`/ r v s Esc`), diálogos (reject/
  settle). Presentation em `app/presentation/board.ts`.
- **Cardápio** (`app/pages/catalog.vue`) — conteúdo **refinado** (feito nesta sessão):
  **heatmap** de disponibilidade (células tintadas verde/âmbar + dot→pausar no hover +
  preço inline), linha de produto (thumbnail c/ ring, SKU mono, tag de coleção),
  **seleção + barra de bulk flutuante**, chips do eixo coleção, **skeleton** de loading,
  tabela em card com header/coluna sticky. Presentation em `app/presentation/catalog.ts`.

## Divergências a eliminar
- Header: Pedidos = barra compacta full-bleed; Cardápio = header centralizado grande. → um só.
- Chip ativo: Pedidos `bg-primary text-primary-foreground`; Cardápio `bg-foreground`. → um só (`bg-primary`).
- Busca: larguras/comportamentos diferentes (Pedidos expande no focus + botão limpar). → unificar.
- Ferramentas: Pedidos tem tema/atalhos/refresh-ícone/relógio; Cardápio não. → padronizar.
- Layout: Pedidos full-bleed; Cardápio `max-w` centralizado. → um só.
- A nav do hub (`app.vue`, "Gestor · Pedidos · Catálogo") é a 3ª camada de chrome —
  racionalizar (ela dá o nav de topo; o header por-página não deve duplicar "Gestor").

## Padrão a adotar (o melhor de cada)
1. **Chrome de operador do Pedidos** como base compartilhada: barra compacta full-bleed,
   chips `bg-primary`, busca-com-ícone, refresh/tema como ícones, atalhos de teclado.
2. **Refinações de conteúdo do Cardápio** mantidas (heatmap, seleção+bulk flutuante,
   skeleton, sticky) e, onde fizer sentido, retro-portadas ao Pedidos (skeleton, empty).
3. **Extrair componentes de chrome compartilhados** — ex.: `Ui/Toolbar`, `Ui/FilterChip`,
   `Ui/SearchInput` (ou um composable de chrome) — usados pelos dois boards. É a
   "padronização" de verdade (uma linguagem só, não copy-paste).
4. Racionalizar a nav do hub vs header por-página (evitar 3 camadas).

## Passos sugeridos
1. Ler `index.vue`, `catalog.vue`, `app.vue`, `presentation/board.ts`, `catalog.ts`,
   `tailwind.css`, e `components/Ui/*` (inventário de primitivas).
2. Definir o design system compartilhado do Gestor (tokens já existem; falta o chrome).
3. Extrair os componentes de chrome; aplicar nos dois boards.
4. Verificar ao vivo (preview :3004, dados Nelson): os dois boards com a mesma linguagem.
5. `npm run test` (vitest) + `make test`. Commit na branch `feat/catalog-hub-registry-consolidation` (PR #27) ou nova, a critério do Pablo.

## Estado do hub (contexto)
PR #27 = Frentes 1–5 + UX da matriz + refactor Expositor. `make test` 2274, `make admin`
255, vitest 49. Modelo: Coleção (conteúdo) · Canal (venda) · Expositor/`Showcase`
(exibição: menuboard/feed, compõe N coleções). Ver `CROSS-CHANNEL-CATALOG-HUB-PLAN.md`
(§Refactor Expositor) e `CATALOG-FEEDS-GOOGLE-META.md`. Bloqueios do Pablo: credenciais
Google/Meta (push feeds), homologação iFood (código pronto).
