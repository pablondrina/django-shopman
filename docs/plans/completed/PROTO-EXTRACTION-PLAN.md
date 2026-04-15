# Plano Temporário — Extração de Valor do `proto/` antes de Descartar

Data: 2026-04-15
Status: Pendente (executar **depois** dos commits C1-C9 e **antes** da Fase 1 do PROJECTION-UI-PLAN)
Escopo: Médio — porta padrões/tokens/animações/components de `proto/` para `v2/`, depois deleta `proto/`
Arquivar em: `docs/plans/completed/` ao concluir.

---

## Contexto

O diretório [`shopman/shop/web/templates/storefront/proto/`](../../shopman/shop/web/templates/storefront/proto/) contém 21 arquivos HTML estáticos (sandbox não roteado, nunca commitado até hoje). Uma análise superficial sugeriu "matar sem dó". Uma análise mais profunda (2026-04-15) encontrou valor real: **7 categorias de padrões/componentes** que `v1` e `v2` não têm e que valem extração.

Simultaneamente, `v1` e `v2` têm sistemas de tokens diferentes e nenhum dos dois é maduro:
- **v1** ([storefront/base.html:46-72](../../shopman/shop/templates/storefront/base.html)): CSS vars soltas, RGB bruto, dupla paleta mantida em JS inline
- **v2** ([storefront/v2/partials/_tokens.html](../../shopman/shop/templates/storefront/v2/partials/_tokens.html)): injeção dinâmica via Django `storefront.design_tokens`, melhor que v1 mas não centralizado
- **proto** ([proto/account-v2.html:9-68](../../shopman/shop/web/templates/storefront/proto/account-v2.html)): Tailwind v4 `@theme` + `@custom-variant dark` + `@layer components` com pares light/dark explícitos, semantic colors com contrast pairs (estilo Material Design 3), componentes reusáveis, touch-target built-in

O proto é o mais maduro em tokens — mas é HTML estático sem Django. **Portar o sistema do proto para v2 é o ganho.**

---

## O Que Extrair (7 itens)

### 1. Sistema de design tokens Tailwind v4 `@theme` + dark mode

**Origem:** [proto/account-v2.html:9-68](../../shopman/shop/web/templates/storefront/proto/account-v2.html)
**Destino:** `shopman/shop/templates/storefront/v2/partials/_tokens.html` + CSS build correspondente (`output-v2.css`)

Incluir:
- `@custom-variant dark (&:where(.dark, .dark *))` para dark mode consistente
- `@theme` com pares light/dark completos: `--color-surface` / `--color-surface-dark`, `--color-primary` / `--color-primary-dark`, `--color-outline` / `--color-outline-dark`, etc.
- Semantic colors com contrast pairs: `--color-info` + `--color-on-info`, `--color-success` + `--color-on-success`, `--color-warning` + `--color-on-warning`, `--color-danger` + `--color-on-danger` (padrão M3)
- Script inline que detecta `prefers-color-scheme` e aplica `.dark` no `<html>` antes do primeiro paint (previne FOUC)

### 2. Componentes em `@layer components`

**Origem:** [proto/account-v2.html:60-68](../../shopman/shop/web/templates/storefront/proto/account-v2.html)
**Destino:** novo `shopman/shop/templates/storefront/v2/components/` (partials Django) + utilities CSS

Incluir como utility classes Tailwind (via `@layer components`):
- `.card` — aplicado via `class="card"` em qualquer container
- `.btn-primary` / `.btn-secondary` — com `touch-target` built-in
- `.badge` — pra status, disponibilidade, promoções
- `.touch-target` — `min-height: 44px; min-width: 44px` (WCAG 2.5.5)

### 3. 6 keyframes de animação

**Origem:** vários arquivos proto — [cart.html:33-40](../../shopman/shop/web/templates/storefront/proto/cart.html), [checkout.html:17-18](../../shopman/shop/web/templates/storefront/proto/checkout.html), [tracking.html:17-18](../../shopman/shop/web/templates/storefront/proto/tracking.html), [pdp.html:27-31](../../shopman/shop/web/templates/storefront/proto/pdp.html), [home.html:32-39](../../shopman/shop/web/templates/storefront/proto/home.html), [tracking-v2.html:60-63](../../shopman/shop/web/templates/storefront/proto/tracking-v2.html)
**Destino:** novo `shopman/shop/static/storefront/v2/css/animations.css` (ou inline em `_tokens.html`)

Incluir:
- `@keyframes fadeIn` (opacity)
- `@keyframes slideUp` (translateY + cubic-bezier `(0.16, 1, 0.3, 1)`)
- `@keyframes pop` (scale micro-feedback — útil no stepper do cardápio)
- `@keyframes flash-green` (feedback "adicionado ao carrinho")
- `@keyframes bounce-down` (chevron "scroll pra baixo")
- `@keyframes pulse-gentle` (cubic-bezier `(0.4, 0, 0.6, 1)` — mais suave que o `animate-pulse` nativo Tailwind)

Respeitar `prefers-reduced-motion` em um wrapper media query.

### 4. `AVAILABILITY_CONFIG` como componente de badge

**Origem:** [proto/menu.html:147-149](../../shopman/shop/web/templates/storefront/proto/menu.html)
**Destino:** quando a Fase 1 do PROJECTION-UI-PLAN implementar `CatalogItemProjection.availability` como enum, o template consumirá isso via um partial Django `components/availability_badge.html`. Por enquanto, portar como objeto JS Alpine reusável.

```js
const AVAILABILITY_CONFIG = {
  available:   { text: 'Disponível',              bg: 'bg-success/10 border-success/30',    color: 'text-on-success' },
  low_stock:   { text: 'Últimas unid.',           bg: 'bg-warning/10 border-warning/30',    color: 'text-on-warning' },
  planned_ok:  { text: 'Encomenda',               bg: 'bg-info/10 border-info/30',          color: 'text-on-info' },
  unavailable: { text: 'Indisponível · Volta amanhã', bg: 'bg-surface-alt border-outline', color: 'text-on-surface-alt' },
}
```

### 5. Timeline component (tracking)

**Origem:** [proto/tracking.html:67-102](../../shopman/shop/web/templates/storefront/proto/tracking.html)
**Destino:** `shopman/shop/templates/storefront/v2/components/timeline.html`

Estrutura: dots + linhas conectando + labels + timestamps. Estados:
- `completed` — bg sólido (primary)
- `current` — `animate-pulse` (ou `pulse-gentle` do item 3)
- `pending` — outline neutro

Ele vai casar naturalmente com `OrderTrackingProjection.timeline: list[TimelineStepProjection]` quando a Fase 2 do PROJECTION-UI-PLAN chegar.

### 6. Haptic feedback utility

**Origem:** [proto/tracking.html:522-525](../../shopman/shop/web/templates/storefront/proto/tracking.html) + 15 outros arquivos proto
**Destino:** `shopman/shop/static/storefront/v2/js/haptic.js` (módulo Alpine reutilizável)

```js
// Alpine.data('haptic', () => ({...})) or utility helper
window.triggerHaptic = (pattern = 10) => {
  if (navigator.vibrate) navigator.vibrate(pattern);
};
```

Aplicar em:
- Add to cart → `triggerHaptic(10)` (leve)
- Remove from cart → `triggerHaptic([30, 20, 30])` (dupla)
- Cancelar pedido → `triggerHaptic([50, 30, 50])` (confirmação)
- Error toast → `triggerHaptic([100])` (firme)

Respeita automaticamente quem não suporta (Safari desktop, etc.) — vibrate é opt-in no browser.

### 7. `proto-scenarios.js` — sistema de simulação de personas

**Origem:** `shopman/shop/web/templates/storefront/proto/proto-scenarios.js` (563 linhas)
**Destino:** **não** migrar pra produção. Extrair como ferramenta de dev/QA em `tools/demo-scenarios/` ou documentar em `docs/guides/demo-personas.md` como referência.

Por quê:
- Contém 10 personas predefinidas (Maria-morning, João-new, Pedro-denied, etc.)
- Painel floating com tabs Personas/Controles
- `pushToPage()` que modifica `$data` Alpine dinamicamente
- sessionStorage persistence cross-page

Valor: **ouro para demos a stakeholders + QA manual**. Uma pena deletar. Mas é um sistema de dev tooling que não pertence ao bundle de produção. Ideal: virar um bookmarklet ou uma ferramenta ativada só em `DEBUG=True`.

---

## O Que NÃO Extrair

- Estrutura monolítica de 600-900 linhas por arquivo HTML estático — substituída por herança Django.
- Tailwind via browser CDN (`@tailwindcss/browser@4`) — JIT em browser é lento, build estático é o caminho.
- Duplicatas v1/v2 dentro do proto — o sistema real vive em `shopman/shop/templates/storefront/`.
- Geolocalização client-side via sessionStorage — ideia interessante (calcular ETA de delivery no cliente sem round trip) mas **não pronta**. Documentar em `docs/ideas/client-side-delivery-eta.md` e arquivar.
- `proto/v1-backup/` (8 arquivos) — snapshot antigo. Ignorar.

---

## Execução

Ordem sugerida:

1. **Setup**: criar `shopman/shop/templates/storefront/v2/components/` e `shopman/shop/static/storefront/v2/{css,js}/`
2. **Tokens primeiro** (item 1) — porta `@theme` + dark mode pro `_tokens.html`. Build `output-v2.css`. Verifica que v2 ainda renderiza (home).
3. **Componentes** (item 2) — `.card`, `.btn-*`, `.badge`, `.touch-target`. Usar no `home.html` v2 existente como teste.
4. **Animações** (item 3) — 6 keyframes + `prefers-reduced-motion` wrapper.
5. **Badge de disponibilidade** (item 4) — como partial Django + Alpine.
6. **Timeline** (item 5) — como partial Django.
7. **Haptic utility** (item 6) — módulo JS.
8. **Cenarios** (item 7) — arquivar em `tools/` ou docs, NÃO produção.
9. **Documentar no roadmap**: criar `docs/ideas/client-side-delivery-eta.md` se valer.
10. **Deletar** `shopman/shop/web/templates/storefront/proto/` inteiro.
11. **Grep sanity check** por referências a `proto/` em qualquer lugar do repo antes de fechar.

### Testes

- Verificar que `v2/home.html` (a única página v2 hoje) continua renderizando corretamente com os tokens novos.
- Verificar que o dark mode script não causa FOUC.
- Verificar que `touch-target` aparece nos botões v2.

### Critério de "pronto"

- `shopman/shop/web/templates/storefront/proto/` não existe mais.
- v2 usa `@theme` + dark mode + 6 keyframes + 4 componentes utility + haptic helper.
- `docs/guides/demo-personas.md` documenta o sistema de personas.
- Este plano movido para `docs/plans/completed/`.

---

## Dependências e Ordem Externa

- **Depende de**: C1-C9 mergeados (não misturar extração com polish de v1 em trânsito).
- **Deve acontecer antes de**: Fase 1 do [PROJECTION-UI-PLAN.md](PROJECTION-UI-PLAN.md). Porque quando a Fase 1 começar a migrar telas uma a uma (menu, cart, PDP, etc.) para Penguin + projections, ela já vai encontrar os tokens, componentes, animações e o sistema de badge disponíveis — reutiliza em vez de recriar.
- **Não depende de**: [NAMING-CONSOLIDATION-PLAN.md](NAMING-CONSOLIDATION-PLAN.md). Os dois são independentes e podem rodar em qualquer ordem.
