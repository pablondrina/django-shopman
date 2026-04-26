# STOCK-UX-PLAN — Estoque insuficiente (acionável, 1-clique) — spec canônica

> **Este documento é a fonte única da verdade para a UX de estoque insuficiente no storefront.**
> O conceito vive no repo desde `docs/plans/completed/EVOLUTION-PLAN.md` (E1 — Disponibilidade + Alternativas)
> e em `cart_warnings.html` histórico. Já foi perdido várias vezes — antes de tocar qualquer
> código de alerta de estoque, **ler este arquivo**. Não reinventar.

## Princípio

Alerta de estoque **nunca é apenas informacional**. É **acionável, omotenashi, e em 1 clique**.

Quando o sistema detecta indisponibilidade, o cliente não lê um "disponível 3" e vai ter
que fazer conta do que fazer — ele vê **as opções já prontas para clicar**:

- **Ajustar para a quantidade disponível** (se algum estoque existe).
- **Adicionar uma alternativa** que já está em estoque, com nome, preço, 1 toque.
- **Fechar** discretamente quando mudou de ideia.

Ninguém deve ficar olhando pra mensagem tentando entender o que fazer.

## Dois momentos onde o alerta aparece

### A. No momento do "Adicionar" — modal acionável

Dispara quando o cliente clica em **Adicionar / Atualizar para N** no:
- **Card do menu** (stepper inline)
- **PDP** (botão Adicionar)
- **Home "Direto do forno"** (availability preview)
- **Upsell do drawer** ("Que tal adicionar?")

Servidor retorna `422` + `X-Shopman-Error-UI: 1` + `HX-Retarget: #stock-error-modal` +
`HX-Reswap: innerHTML`. O cliente injeta o HTML do modal no sentinel `<div id="stock-error-modal">`
em `base.html`.

**Estrutura do modal (Penguin UI tokens, bottom-sheet mobile, centered desktop):**

```
┌─────────────────────────── ✕ ┐
│  ⚠️  Restam apenas 3 deste pão │
│      Você pediu 10.             │
│                                  │
│  ┌─ Aceitar as 3 disponíveis ─┐ │  ← botão primário (sempre que available > 0)
│                                  │
│  Ou escolha uma destas:          │
│  ┌────────────────────────────┐  │
│  │ 🥖 Baguete Campagne  R$ 12 │  │  ← 1 clique adiciona a alternativa
│  └────────────────────────────┘  │
│  ┌────────────────────────────┐  │
│  │ 🥐 Croissant         R$ 8  │  │
│  └────────────────────────────┘  │
│                                  │
│                  [ fechar ]      │  ← subtle, não "Entendi"
└──────────────────────────────────┘
```

### B. No carrinho — warnings por linha (cart_warnings.html histórico)

Se o cliente chega ao carrinho com itens cuja disponibilidade mudou (holds expiraram,
estoque depletou entre tabs abertas, etc.), **cada linha afetada mostra ações inline**:

```
⚠️  Pão Francês: disponível 2 (pedido: 5)
                                            [Ajustar para 2]  [Remover]
```

Já existe referência histórica em `.claude/worktrees/*/shopman/shop/templates/storefront/partials/cart_warnings.html`.

## Contrato backend

**`CartUnavailableError`** (já existe em `shopman/shop/web/cart.py`):
- `sku: str`
- `requested_qty: int`
- `available_qty: int`
- `is_paused: bool`
- `alternatives: list[dict]` — cada dict: `{sku, name, price_q, price_display, available_qty, can_order}`
  (estrutura definida em `shopman/shop/services/alternatives.py::find`)
- `error_code: str` — `"below_stock"`, `"below_min_qty"`, `"paused"`, `"not_in_listing"`, etc.

**`_stock_error_response`** (em `shopman/shop/web/views/cart.py`):
- Renderiza `storefront/partials/stock_error_modal.html` com contexto:
  - `title`, `message` (mantém), **mais**:
  - `available_qty`, `requested_qty`, `error_code`, `alternatives`, `sku`, `product_name`.
- Headers: `422`, `X-Shopman-Error-UI: 1`, `HX-Retarget: #stock-error-modal`, `HX-Reswap: innerHTML`.

## Ações do modal (1 clique)

### "Aceitar N disponíveis" (primary)

- Só aparece se `available_qty > 0` e `error_code` ≠ `paused`/`not_in_listing`.
- Faz `POST /cart/set-qty/` com `sku` + `qty=available_qty` (qty absoluta, idempotente).
- Ao resolver: dispara `cartUpdated`, fecha modal, atualiza badge.
- Copy omotenashi: "Adicionar {N} disponíveis" (não "Ajustar", não "Usar o que tem").

### "Escolher alternativa" (cards 1-clique)

- Para cada item em `alternatives`:
  - Botão full-width com nome + preço.
  - Faz `POST /cart/set-qty/` com `sku=alt.sku`, `qty=min(requested_qty, alt.available_qty)`.
  - Ao resolver: dispara `cartUpdated`, fecha modal, opcional toast "X adicionado".

### "Fechar" (subtle, terciária)

- Só um ✕ no canto superior direito + backdrop clique + ESC + botão secundário discreto.
- Nunca botão grande "Entendi" — o cliente não precisa confirmar que leu.

### "Corrigir quantidade" (opcional, futuro)

- Se e quando houver valor: stepper inline que permite escolher qty entre 1..available_qty.
- Por enquanto, "Aceitar N disponíveis" já cobre o caso comum. **Não implementar a menos que o fluxo primário não baste.**

## Poka-yoke

- Se `alternatives` vem vazia E `available_qty === 0` E sem `is_paused`: mostra só o
  botão "Fechar" com copy "Acabou no momento. Volta amanhã a partir das 7h."
- Se `is_paused`: copy "Pausado pela loja no momento" + alternativas (se houver).
- Se `error_code === "below_min_qty"`: copy "Quantidade mínima: N unidades" + botão
  "Adicionar N unidades" (ajusta para o mínimo).

## Regras invariantes

- **Ação primária é sempre 1 clique.** O cliente nunca digita nada no modal.
- **Copy é curta e humana.** Sem "Ocorreu um erro", sem "Estoque insuficiente" frio no
  corpo — título pode ser seco, corpo tem que ser conciso e útil.
- **Penguin UI tokens.** `bg-surface-alt`, `on-surface-strong`, `border-outline`,
  `text-primary`, etc.
- **Mobile-first.** Modal é bottom-sheet no mobile (swipe-to-dismiss opcional), centered
  no desktop.
- **Modal auto-dismissível.** Clique no backdrop, ESC, ✕, botão secundário — tudo fecha.
- **Dispatcher HTMX.** `X-Shopman-Error-UI: 1` é obrigatório para o handler de erro
  global em `base.html` pular o toast genérico. Qualquer nova view que dispara esse
  contrato DEVE setar esse header.

## Testes de regressão (obrigatórios)

Já existem em `shopman/shop/tests/test_stock_error_ux.py`:
1. 422 + headers corretos.
2. Modal HTML usa tokens Penguin, não v1.

**Adicionar ao implementar ações:**
3. Modal tem botão "Aceitar N disponíveis" quando `available_qty > 0`.
4. Modal renderiza alternativas como botões clicáveis com sku + price_display.
5. Clique no botão de ação faz POST correto para `/cart/set-qty/` com qty apropriada.

## Status atual (atualizado)

- ✅ Contrato 422 + X-Shopman-Error-UI + HX-Retarget consolidado.
- ✅ JS pattern em menu-card, PDP, availability-preview despacha para modal sentinel.
- ✅ CartUnavailableError carrega alternatives.
- ✅ Modal acionável (WP-STOCK-UX-1) — botão primário "Adicionar N disponíveis" + alternativas 1-clique via `cart_set_qty` idempotente + close discreto.
- ✅ `availability.reserve` e `reconcile` dividem a reserva entre múltiplos quants quando o stock está fragmentado (evita o paradoxo "Restam 52" + "clique em 52 falha").
- ✅ PDP: stepper abre o modal automaticamente quando `qty > available`, sem esperar o clique em "Adicionar".
- ✅ Injeção do modal chama `Alpine.initTree` após `innerHTML` — sem isso as diretivas `@click` dentro do modal não eram bindadas.
- ❌ `cart_warnings.html` (warnings por linha no carrinho) — **ainda não migrado para v2**. WP-STOCK-UX-2.
- ⚠️ Menu card ainda não tem `available_qty` no projection — o modal só abre **após** o POST falhar (UX equivalente, mas um round-trip a mais). Seria melhor ter a info no projection para abrir client-side imediatamente, como PDP faz.

## Sistema de busca de alternativas

Implementado hoje em `packages/offerman/shopman/offerman/contrib/suggestions/suggestions.py::find_alternatives`:

- ✅ **Keywords compartilhadas** — filtro + score por overlap.
- ✅ **Coleção primária** — filtro + boost.
- ✅ **Categoria via coleção** — indireto, OK.
- ❌ **Similaridade de nome** (Levenshtein / trigram) — ausente.
- ❌ **Fuzzy** — ausente.

**Par mais próximo quando só um:** hoje retorna lista ordenada por score (máx `limit`). Quando `limit=1`, já devolve o "par mais próximo" pelo score de keywords + coleção. Se adicionarmos name-similarity, fica mais robusto para edge cases (ex: produto sem keywords ou sem coleção).

**WP-STOCK-UX-3 (futuro):** adicionar name-similarity na função `_score_candidates` usando `difflib.SequenceMatcher` (sem dependência nova) ou `pg_trgm` em PostgreSQL (produção). Opt-in via config para não reordenar o comportamento atual sem supervisão.

## Fluxo de retorno após ação — **DECISÃO PENDENTE**

Quando o cliente clica numa ação do modal (seja primary ou alternativa), o
modal fecha e o carrinho reflete a mudança. Mas **onde o cliente deve estar
visualmente?** Três cenários com trade-offs diferentes:

### Cenário A — Primary action ("Adicionar N disponíveis")

Cliente pediu X do MESMO produto que está olhando na PDP. Adicionou N disponíveis.
- **Permanecer na PDP ✓** — não há ambiguidade. O produto é o mesmo. Stepper
  atualiza para N (o valor efetivamente adicionado). Toast opcional.
- **Redirecionar ao carrinho ✗** — rouba foco desnecessariamente.
- **Decisão recomendada:** permanecer na PDP, atualizar stepper para N, toast
  discreto "Adicionamos N ao carrinho".

### Cenário B — Alternativa escolhida a partir da PDP

Cliente estava olhando Pão Francês; aceitou Ciabatta como alternativa. Agora:
- **Permanecer na PDP do Pão Francês ✗** — PDP mostra Francês mas Ciabatta
  foi adicionado. Confusão total. Stepper do Francês fica em qual valor?
- **Redirecionar para PDP da Ciabatta** — faz sentido se cliente quer ver
  mais sobre o novo produto. Mas perde o "lugar" dele.
- **Redirecionar para o carrinho** — confirma a ação e reorienta.
- **Decisão recomendada:** redirecionar para o carrinho (`/cart/`) com o
  item já lá. Cliente vê o que tem, decide se compra mais ou vai ao checkout.
  Toast inicial "Adicionamos Ciabatta ao carrinho".

### Cenário C — Alternativa escolhida a partir do menu/home

Cliente estava no cardápio; + no Pão Francês falhou; escolheu Ciabatta.
- **Permanecer no cardápio ✓** — contexto é de exploração, não foco num produto.
- **Redirecionar ao carrinho ✗** — tira o cliente do browsing.
- **Decisão recomendada:** permanecer. Toast "Ciabatta adicionado". O próprio
  card do Ciabatta (no grid) já atualiza o stepper via `cartUpdated`.

### Resumo do comportamento por origem

| Origem do modal | Ação primary (mesmo SKU) | Ação alternativa (SKU novo) |
|---|---|---|
| PDP | Stay + stepper=N + toast | **Redirect para /cart/** + toast |
| Menu / Home / Availability | Stay + card stepper=N + toast | Stay + card do alt stepper=1 + toast |
| Drawer / Cart page | Stay + linha atualiza + toast | Stay + nova linha + toast |

### Pendência técnica

- `pickAction` hoje não sabe a "origem" nem o `sku original`. Precisa receber
  via contexto do template (ex: `data-picker-origin="pdp"` no sentinel ou
  param do `pickAction`).
- Redirect do "Cenário B" precisa ser explícito (`window.location.href =
  '/cart/'`) pós-sucesso. Hoje apenas fecha o modal.

### WP-STOCK-UX-1b (adenda imediata ao WP-1)

1. Passar a "origem" ao modal via parâmetro do template (`picker_origin`).
2. `pickAction(sku, qty, shouldClose, isAlternative)` — 4º param decide
   redirect vs stay.
3. Toast de sucesso com nome do produto adicionado.
4. Testes cobrindo os 3 cenários.

## Execução

### WP-STOCK-UX-1 — Modal acionável (ESTE PR)

1. Reescrever `stock_error_modal.html` com ações (Aceitar / Alternativas / Fechar).
2. Estender `_stock_error_response` para passar `available_qty`, `requested_qty`,
   `error_code`, `product_name` ao contexto.
3. Adicionar 3 testes de regressão conforme seção anterior.

### WP-STOCK-UX-2 — Warnings no carrinho (futuro)

1. Recriar `cart_warnings.html` no padrão v2 (Penguin, acionável).
2. Exibir no drawer + cart page quando `cart.has_unavailable_items`.
3. Ações por linha: "Ajustar para N", "Substituir por alternativa", "Remover".

## Referências

- `docs/plans/completed/EVOLUTION-PLAN.md` — E1 (Disponibilidade + Alternativas).
- `.claude/worktrees/*/shopman/shop/templates/storefront/partials/cart_warnings.html` — histórico da UX acionável por linha.
- `shopman/shop/services/alternatives.py` — `find(sku, qty, channel) → list[dict]`.
- `shopman/shop/services/availability.py` — `reserve()` retorna `alternatives` em falha.
- `shopman/shop/tests/test_stock_error_ux.py` — regressão do contrato.
