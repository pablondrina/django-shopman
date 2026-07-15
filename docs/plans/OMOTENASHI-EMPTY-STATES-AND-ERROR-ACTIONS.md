# WP — Omotenashi: empty states + error actions (storefront)

Fecha os achados da auditoria omotenashi do storefront (ver
`shopman/storefront/tests/e2e/test_omotenashi_audit.py`). Tema único: **toda
superfície vazia ou de erro deve oferecer um caminho adiante, com copy vinda do
registro `OmotenashiCopy` (configurável no Admin), consistente entre telas.**

## Princípio

- Empty state = `{title, message, cta?}` resolvido de `OmotenashiCopy`, nunca
  hardcoded no Vue nem `[]` cru sem orientação.
- Erro = ação, não só texto (avise-me, retirada, reabertura/encomenda).
- Mudança BE+FE atômica; chaves novas no payload são aditivas (o proxy Nuxt
  repassa verbatim, consumidores leem chaves nomeadas).

## Achados e correções

| # | Achado | Correção | Camada |
|---|--------|----------|--------|
| 4 | Favoritos vazio sem copy do registro (hardcoded no Vue) | `FAVORITES_EMPTY` + envelope `{items, copy.empty}`; Vue consome com fallback | BE+FE |
| 5 | Catálogo/busca vazios sem bloco configurável | `CATALOG_EMPTY`/`SEARCH_EMPTY` em `CatalogProjection.empty_state`; `menu.vue`/`busca.vue` consomem | BE+FE |
| 6b | Esgotado no carrinho não oferece "Me avise" | `is_notifiable` + ação `notify_when_available` no payload 409; `SubstituteSheet.vue` mostra `StockNotifyButton` | BE+FE |
| 7b | Checkout fechado não diz reabertura/encomenda | `next_open_at` + `earliest_available_date` no 400; `finalizar.vue` mostra | BE+FE |
| 12b | `ProfileView.patch` vaza `str(exc)` | mensagem pt-BR fixa + log | BE |
| 14b | Reasons de bloqueio do carrinho hardcoded | rotear por `CART_CHECKOUT_BLOCK_*` | BE |
| 3b | Endereços default `[]` sem copy | **não é defeito**: `?include=copy` é design deliberado; a tela de Endereços já opta e renderiza. Mudar o default quebra o checkout. Assertar o real. | — |
| 10b | Zona sem fallback de retirada | **já resolvido no FE** (`shouldOfferPickupSwap`); tornar a copy configurável e assertar o swap ponta-a-ponta | (copy) |

## Pré-existente

- `Customer.insight` é OneToOne reverso criado sob demanda (sem signal). Único
  acesso em produção (`storefront/cart.py:231`) já está guardado com try/except.
  As falhas transitórias de `test_persona_2_loyal` não reproduzem; baseline verde
  (854 passed). Sem correção de código necessária; suíte confirmada.

## Verificação

- `test_omotenashi_audit.py`: os 8 `xfail` viram asserts do comportamento novo.
- `make test-framework` (storefront) verde.
- Nuxt: vitest de presentation + build limpo.
