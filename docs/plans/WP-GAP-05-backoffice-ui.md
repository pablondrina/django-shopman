# WP-GAP-05 — Backoffice UI Unification (executar WP-2 a WP-6 do BACKOFFICE-UI-PLAN)

> Coordenador para fechar a migração visual do backoffice para Penguin UI v4 Industrial. Prompt auto-contido: agente deve ler este arquivo + `BACKOFFICE-UI-PLAN.md` original.

**Status**: WP-1 pronto pra começar (shell + CSS foundation); WP-2 a WP-6 pendentes.
**Dependencies**: WP-1 do plano original (shell/foundation) deve rodar primeiro.
**Severidade original**: 🟠 Média. Cada surface operador tem visual próprio; duas árvores Tailwind (v3 + v4) coexistem.

---

## Contexto

### O plano original

[docs/plans/BACKOFFICE-UI-PLAN.md](BACKOFFICE-UI-PLAN.md) define 6 WPs (**referência obrigatória** para executar este WP-GAP-05):

- **WP-1** — Shell + CSS foundation (pronto para começar; execução direta).
- **WP-2** — Pedidos (`/pedidos/`) migrado.
- **WP-3** — KDS (`/kds/*`) migrado.
- **WP-4** — POS (`/gestao/pos/*`) migrado.
- **WP-5** — Produção (`/gestao/producao/*`) migrado.
- **WP-6** — Fechamento (`/admin/shop/closing/`) migrado.

Ler `BACKOFFICE-UI-PLAN.md` antes de começar — é o contrato de escopo por WP. **Este arquivo coordena**, não substitui.

### O intent

- Cada surface operador (Pedidos, KDS, POS, Produção, Fechamento) com visual coeso em Penguin UI v4 + Industrial theme (stone-based, orange-900 primary, warm amber accents), dark-first.
- Operador circula entre surfaces sem "descontinuidade visual" — Regra 95/5 do Omotenashi (staff merece omotenashi; operador com UI coerente entrega cliente com cuidado).
- Eliminar coexistência Tailwind v3 + v4 no repo.

### Estado atual (gap)

- WP-1 em "ready to start"; WP-2 a WP-6 pendentes.
- `package.json` tem `tailwindcss@^3.4.17` E `@tailwindcss/cli@^4.2.2`.
- Build scripts: `css:build` → `output.css` (v3 legacy); `v2:build` → `output-v2.css` (v4 storefront).
- Templates backoffice (Pedidos, KDS, POS) ainda consomem `output.css` v3.
- Storefront já migrou para v4 (PROTO-EXTRACTION-PLAN + PROJECTION-UI-PLAN Fase 1).

---

## Escopo

### In

- Executar **WP-1** (shell + CSS foundation) se não executado ainda — pré-requisito.
- Executar **WP-2 a WP-6 em série**, uma PR por WP, cada uma mergeável independentemente.
- **Ao final do WP-6**:
  - Remover `tailwindcss@^3.4.17` de `package.json` devDependencies.
  - Deletar `shopman/shop/web/static/storefront/css/output.css` (v3 build).
  - Remover script `css:build` v3 do `package.json`; renomear `v2:build` → `css:build` (tornar v4 o único).
  - Atualizar Makefile target `css` para usar apenas o build v4.
  - Grep final: zero referências a `output.css` (v3) remaining.
- Dark mode via `@media (prefers-color-scheme: dark)` funcional em cada surface.
- Screenshots de antes/depois por PR.

### Out

- Novas features em Pedidos/KDS/POS/Produção/Fechamento — **só visual e coerência**. Comportamento idêntico; só muda pintura.
- Storefront (já em v4) — não mexer neste WP.
- Django Admin Unfold — separado; Unfold tem seu próprio theme e não é Penguin.
- Acessibilidade regressions — não devem ocorrer; manter 48px / 16px+ / AAA mesmo em dark mode (validar em cada PR).

---

## Entregáveis

### Por sub-WP (uma PR independente cada)

**WP-2 — Pedidos**
- Templates em `shopman/shop/templates/pedidos/**` reescritos em tokens Penguin v4.
- `_card.html`, `_detail.html`, `index.html`: header, tabs de filtro por status, card grid, timer Alpine.
- Industrial theme: stone surfaces, orange-900 primary, warm amber accents.
- Dark mode via `prefers-color-scheme`.
- Preservar HTMX polling, Alpine countdown, ações confirm/reject/advance/mark-paid.
- Screenshots: light + dark, mobile + desktop.

**WP-3 — KDS**
- Templates em `shopman/shop/templates/kds/**`.
- Prep ticket card + Expedition ticket card com tokens v4.
- Timer cores: verde (< target), amarelo (< 2×target), vermelho (≥ 2×target) — mapear para tokens Penguin (não usar classes ad-hoc).
- Dark mode é o **default** no KDS (cozinha ilumina de trás, tela escura reduz fadiga).
- Preservar HTMX polling 5s + Alpine timer 1s + icon `priority_high` quando vermelho.
- Screenshots.

**WP-4 — POS**
- Templates em `shopman/shop/templates/pos/**`.
- Grid produtos + carrinho + payment selector.
- Customer lookup, sangria, abrir/fechar caixa em v4.
- Tipografia otimizada para leitura rápida (body maior, headings destacados).
- Screenshots.

**WP-5 — Produção**
- Templates em `shopman/shop/templates/producao/**` (ou path equivalente — verificar).
- Form de criação WO + lista do dia em v4.
- Preservar integração com `CraftService`.
- Screenshots.

**WP-6 — Fechamento**
- Templates em `shopman/shop/templates/closing/**` ou `admin/closing.html` (verificar — pode ser custom admin view).
- Form por SKU qty_unsold + projection board em v4.
- Screenshots.

**WP-Final (pós WP-6) — Consolidação**
- [package.json](../../package.json): remover `tailwindcss@^3.4.17`, remover script `css:build` v3, renomear `v2:build` → `css:build`.
- Deletar `shopman/shop/web/static/storefront/css/output.css`.
- [Makefile](../../Makefile): `css` target usa apenas build v4.
- Grep validation: `output.css` sem matches remaining.
- PR de limpeza final.

---

## Invariantes a respeitar

- **Comportamento idêntico**: zero mudança funcional; só visual. Tests passam sem alteração.
- **Convenções HTMX + Alpine** preserved: sem `onclick`, `document.getElementById`, `classList.toggle` em código novo.
- **Tailwind classes existentes only** — memória [feedback_tailwind_only_existing_classes.md](.claude/memory). Se precisar classe nova, adicionar ao design token / tema Industrial primeiro.
- **Material Symbols**: tabela canônica de tamanhos — memória [feedback_icon_size_convention.md](.claude/memory). `size-11 button → text-2xl (24px)`.
- **`{% comment %}` multi-linha** — nunca `{#` multi-linha.
- **Omotenashi para operador (Regra 95/5)**: UI clara, ação óbvia, sem sobrecarga cognitiva. Ícones com labels ou tooltips (Alpine). Estado loading visível (`hx-indicator`).
- **Acessibilidade**: 48px touch (KDS + POS podem ter toque em tablet); 16px+ body; contraste AAA em dark mode também (validar com ferramenta — axe, Contrast Checker).
- **Core é sagrado**: nenhuma alteração em pacotes `packages/*` — só templates + CSS.
- **Zero residuals**: após WP-Final, `grep output.css` e `grep tailwindcss@3` retornam zero.

---

## Critérios de aceite

### Por sub-WP

1. Surface visualmente coerente com storefront (mesmos tokens).
2. Dark mode funcional.
3. Screenshots anexados à PR (light + dark × mobile + desktop).
4. Regression suite passa sem alteração.
5. Axe/Contrast Checker sem regressão de contraste.

### Pós WP-Final

1. `grep -r "output.css" shopman/` → zero matches (só `output-v2.css` ou o renomeado novo canonical).
2. `grep -r "tailwindcss\"" package.json` → só `@tailwindcss/cli` (v4).
3. `make css` builda apenas um CSS.
4. Tamanho do CSS final menor que a soma anterior (dedup).
5. Operador em demo percorre Pedidos → KDS → POS → Produção → Fechamento sem sentir "mudança de app".

---

## Estratégia de execução

- **Paralelização cuidadosa**: WP-2 a WP-6 podem rodar em paralelo por agentes diferentes (cada um em seu branch), **desde que WP-1 já esteja merged**. PRs não conflitam entre si (templates separados).
- **WP-Final só depois de todos os 5 merged** — consolidação de package.json é dependente.
- Cada PR deve ter screenshots. Revisor valida visualmente.
- Se qualquer surface tiver feature nova não planejada sendo misturada: **rejeitar** e refazer isolando.

---

## Referências

- [docs/plans/BACKOFFICE-UI-PLAN.md](BACKOFFICE-UI-PLAN.md) — **especificação detalhada por WP**; ler antes de executar.
- [docs/plans/PROJECTION-UI-PLAN.md](PROJECTION-UI-PLAN.md) — Phase 1 (storefront v4) como referência visual.
- [shopman/shop/templates/storefront/partials/_tokens.html](../../shopman/shop/templates/storefront/partials/_tokens.html) — tokens Penguin v4 fonte da verdade.
- [package.json](../../package.json).
- [docs/reference/system-spec.md](../reference/system-spec.md) §2.11 Web UI (design tokens).
- Memórias `.claude/memory/`:
  - [feedback_tailwind_only_existing_classes.md](.claude/memory).
  - [feedback_icon_size_convention.md](.claude/memory).
  - [feedback_accessibility_omotenashi_first_class.md](.claude/memory).
  - [feedback_no_external_component_lib.md](.claude/memory) — sem libs de componentes; Alpine+HTMX+Tailwind only.
