# STOCK-SUBSTITUTE-1CLICK-PLAN — Substituto acionável em 1 toque no carrinho

> **Status (2026-06-28):** 📋 Pronto para execução em sessão nova. Prompt auto-contido.
> Escopo pequeno e bem delimitado. **Frente:** storefront Nuxt. **Decisão de produto:** já
> aprovada pelo Pablo (fechar o 1-clique que a spec canônica sempre pediu).

## Por que este arco existe

A spec canônica [STOCK-UX-PLAN](STOCK-UX-PLAN.md) (princípio "NUNCA PERDER") diz: alerta de
estoque **nunca é informacional — é acionável, em 1 toque**. Quando um item falta, o cliente deve
poder **adicionar uma alternativa que já está em estoque com 1 clique**, sem fazer conta.

Hoje (verificado 2026-06-28) o storefront Nuxt **mostra** os substitutos no carrinho
([`app/pages/sacola.vue`](../../surfaces/storefront-nuxt/app/pages/sacola.vue) ~linha 147,
banner "Alternativas disponíveis") mas eles são **rótulos não-clicáveis**. O único 1-clique vivo é
"aceitar a quantidade disponível" (`acceptAvailableQty`). O princípio está **parcialmente
implementado**.

## O ponto-chave: o backend JÁ está pronto

Este é um arco de **completar o frontend**, não de construir do zero. O backend foi escrito
**antecipando** o 1-clique:

- [`shopman/shop/services/substitutes.py::find`](../../shopman/shop/services/substitutes.py) já
  retorna, por substituto: `{"sku", "name", "price_q", "price_display", "available_qty",
  "can_order", "target_qty"}`. O docstring é explícito:
  > `target_qty` is `min(requested_qty, sub.available_qty)` — the amount the client should add when
  > the shopper accepts this substitute in a **1-click swap**. Minimum of 1 so the button always
  > does something useful.
- [`shopman/shop/services/cart.py`](../../shopman/shop/services/cart.py) levanta
  `CartUnavailableError(substitutes=...)`; a API
  [`shopman/storefront/api/surface.py:117`](../../shopman/storefront/api/surface.py) serializa
  `"substitutes": exc.substitutes` no corpo do `409`.
- No Nuxt, [`app/composables/useCartState.ts`](../../surfaces/storefront-nuxt/app/composables/useCartState.ts)
  `issueFromPayload()` **já repassa os dicts crus** (`substitutes: Array.isArray(data?.substitutes) ? data.substitutes : []`).
  Ou seja: **`price_q`, `price_display` e `target_qty` já chegam no cliente em runtime** — só não
  estão tipados nem usados.

**Conclusão:** a lacuna é puramente de frontend (tipo + ação + UI + teste). Não há trabalho de
Core obrigatório (uma polonização opcional de `image_url` está no fim).

## Mecânica de carrinho relevante (já existe, reusar)

Em [`useCartState.ts`](../../surfaces/storefront-nuxt/app/composables/useCartState.ts):

- `setSkuQty(meta: ProductMutationMeta, qty)` — **é o único caminho de escrita** do carrinho
  (`PUT /api/v1/cart/skus/{sku}/` com `{ qty }`), com escrita otimista + fila serial + reconciliação
  do servidor + tratamento de `409/429`. No sucesso, `applyServerCart()` zera `cartIssue` (o banner
  some sozinho). **Adicionar um substituto = chamar `setSkuQty` com o sku/qty do substituto.**
- `ProductMutationMeta` ([`types/shopman.ts:503`](../../surfaces/storefront-nuxt/app/types/shopman.ts))
  = `{ sku, name, price_q, price_display, image_url: string | null }`. O substituto carrega tudo
  isso (menos `image_url`, que pode ser `null` — a linha otimista fica sem imagem por um instante e
  o servidor reconcilia com a imagem real no `applyServerCart`).
- `isPending(sku)` — estado de "em voo" por sku, para desabilitar o botão.
- A linha indisponível original **nunca entrou** no carrinho (o `409` reverteu o otimista via
  `refreshCart`). Então adicionar um substituto é um **add limpo** de outro sku — sem necessidade de
  "remover o original".

## Postura

- Frente storefront Nuxt. **Vue/Nuxt, nunca HTMX/Alpine** (HTMX morreu no headless). Componentes
  `Ui*` existentes; design tokens canônicos; sem lib de componentes externa.
- **Omotenashi:** copy acolhedora em "nós/conosco" (nunca "a gente"); o substituto é uma ajuda, não
  um erro. Acessível (botão real, foco, aria), mobile-first (storefront é mobile-first).
- Lógica pura testável em `app/presentation/cart.ts` (padrão da casa: `<script setup>` fino +
  vitest); zero gambiarra.
- Verificar AO VIVO no preview (`127.0.0.1:3000`, nunca localhost) antes de declarar pronto.

## Slices

### Slice 1 — Tipo `SubstituteProjection` (tipar o que já chega)
Em [`types/shopman.ts`](../../surfaces/storefront-nuxt/app/types/shopman.ts), criar:
```ts
export interface SubstituteProjection {
  sku: string
  name: string
  price_q: number
  price_display: string
  available_qty: number | null
  can_order: boolean
  target_qty: number | null
  reason?: string
}
```
Em [`useCartState.ts`](../../surfaces/storefront-nuxt/app/composables/useCartState.ts),
trocar o tipo inline de `CartIssue.substitutes` (linha ~14) por `SubstituteProjection[]`. Manter
`issueFromPayload` tolerante (campos podem faltar; normalizar `can_order`/`target_qty`).

### Slice 2 — Helper puro `substituteSwapPlan` (testável)
Em [`presentation/cart.ts`](../../surfaces/storefront-nuxt/app/presentation/cart.ts):
```ts
export function substituteSwapPlan(
  sub: SubstituteProjection,
  requestedQty: number | null
): { meta: ProductMutationMeta, qty: number } | null
```
- Se `!sub.can_order` ou sem `sku` → `null` (botão não deve agir).
- `qty` = `sub.target_qty` se >0; senão `min(requestedQty ?? 1, sub.available_qty ?? Infinity)`;
  piso de `1` (sempre faz algo útil — espelha o docstring do backend).
- `meta` = `{ sku, name, price_q, price_display, image_url: null }`.

### Slice 3 — Ação `addSubstitute` no composable
Em [`useCartState.ts`](../../surfaces/storefront-nuxt/app/composables/useCartState.ts),
adicionar e exportar:
```ts
async function addSubstitute(sub: SubstituteProjection) {
  const plan = substituteSwapPlan(sub, cartIssue.value?.requested_qty ?? null)
  if (!plan) return null
  const res = await setSkuQty(plan.meta, plan.qty)   // sucesso zera cartIssue via applyServerCart
  if (import.meta.client) useSonner.success(`Adicionamos ${sub.name} à sua sacola.`)
  return res
}
```
Reusa toda a robustez de `setSkuQty` (otimista, fila, 409/429). Não duplicar lógica de escrita.

### Slice 4 — UI acionável em `sacola.vue`
No bloco de substitutos (~linha 147) de
[`sacola.vue`](../../surfaces/storefront-nuxt/app/pages/sacola.vue):
- Importar `addSubstitute` e `isPending` de `useCartState()`.
- Para cada `substitute` (manter `.slice(0, 3)`): adicionar um `UiButton` de ação ("Adicionar" +
  `price_display`), wired `@click="addSubstitute(substitute)"`.
- Desabilitar quando `!substitute.can_order` ou `isPending(substitute.sku)`; mostrar estado de
  carregamento. Mostrar `price_display`.
- Manter `UiItemTitle`/`reason`/`available_qty`. Copy do header pode evoluir para algo mais
  acionável ("Troque por uma destas, em 1 toque" — decidir no preview com bom gosto omotenashi).
- Respeitar acessibilidade (botão real, label claro) e mobile-first (botão alcançável com polegar).

### Slice 5 — Testes (vitest)
Em [`tests/cartPresentation.test.ts`](../../surfaces/storefront-nuxt/tests/cartPresentation.test.ts)
(já existe), cobrir `substituteSwapPlan`:
- `target_qty` presente → usa `target_qty`.
- sem `target_qty` → `min(requested, available)`, piso 1.
- sem `available_qty` e sem `target_qty` → 1.
- `can_order: false` → `null`.
- `meta` montado corretamente (sku/name/price_q/price_display/image_url=null).

Rodar `cd surfaces/storefront-nuxt && npm run test`. Verde.

### Slice 6 (OPCIONAL, polish) — `image_url` no substituto
Só se valer a pena: em [`shopman/shop/services/substitutes.py::find`](../../shopman/shop/services/substitutes.py)
incluir `image_url` no dict (e na `SubstituteProjection`), para a linha otimista já nascer com
imagem em vez de aparecer após a reconciliação. Não bloqueia o arco; `image_url: null` é aceitável.
Se mexer no Core, seguir as regras de integridade do [CLAUDE.md](../../CLAUDE.md) (é só leitura
adicional, sem migração).

## Critério de pronto

1. No carrinho, com um item indisponível que tenha substitutos, **clicar num substituto o adiciona
   em 1 toque**; o banner de indisponibilidade some; o substituto aparece como linha do carrinho.
2. Botão respeita `can_order` (desabilitado quando não-ordenável) e estado pendente (sem duplo-add).
3. Feedback de sucesso omotenashi; copy em "nós/conosco".
4. Acessível + mobile-first; sem HTMX/Alpine; só `Ui*` + tokens.
5. `npm run test` (vitest) verde, incluindo os casos de `substituteSwapPlan`.
6. Verificado AO VIVO no preview (`127.0.0.1:3000`): print do antes/depois do swap.

## Como reproduzir o estado de indisponibilidade (para QA)

O `409` dispara quando `setSkuQty` pede mais que o disponível para um SKU com substitutos elegíveis
(mesmas keywords/coleção, publicados, vendáveis, com estoque). Opções:
- Via seed/admin: zerar/limitar estoque de um produto que tenha "irmãos" por keyword/coleção e tentar
  adicionar qty acima do disponível.
- Inspecionar `shop/services/substitutes.py::find` + `availability.reserve` para montar o cenário.
Confirmar no preview que o array `substitutes` chega populado no `cartIssue`.

## Arquivos-âncora (resumo)

| Camada | Arquivo |
|---|---|
| Tipo | `surfaces/storefront-nuxt/app/types/shopman.ts` |
| Helper puro | `surfaces/storefront-nuxt/app/presentation/cart.ts` |
| Ação/estado | `surfaces/storefront-nuxt/app/composables/useCartState.ts` |
| UI | `surfaces/storefront-nuxt/app/pages/sacola.vue` |
| Teste | `surfaces/storefront-nuxt/tests/cartPresentation.test.ts` |
| Backend (já pronto; opcional polish) | `shopman/shop/services/substitutes.py`, `shopman/storefront/api/surface.py` |

Ao concluir, atualizar [STOCK-UX-PLAN](STOCK-UX-PLAN.md) (remover a nota de "lacuna real") e a
memória `project_stock_ux_spec`, e mover ESTE plano para `docs/plans/completed/`.
