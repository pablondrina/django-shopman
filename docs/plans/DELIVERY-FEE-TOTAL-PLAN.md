# DELIVERY-FEE-TOTAL-PLAN — Taxa/mínimo de entrega ao vivo no checkout

> Aprovado por Pablo (2026-06-13). Raiz comum: o checkout Nuxt não grava nada
> na sessão até o POST final, então a taxa de entrega não entra no total e o
> mínimo não é reavaliado ao vivo. Resolver na fonte (Core resolve totais uma
> vez), não com band-aid no cliente.

## Problema (confirmado no código)

- `DeliveryFeeModifier` (modifiers.py) só calcula `delivery_fee_q` quando
  `session.data` tem `fulfillment_type=delivery` + `delivery_address_structured`.
  No checkout Nuxt isso só é gravado no POST final → durante o checkout
  `cart.delivery_fee_display` é vazio e **`grand_total` = subtotal** (total
  subestimado para entrega).
- A linha flutuante "Entrega disponível · taxa R$ X" vem de um quote puro
  (`api/delivery.py`) desconectado do total.
- Mínimo é channel-wide (`shop.defaults.rules.minimum_order_q` + validator
  `shop.minimum_order`) e já bloqueia a ENTRADA no checkout
  (`checkout_enabled = count and min_order is None`). Não existe mínimo de
  entrega. **Footgun**: `minimum_order_q = 0` cai num default escondido de
  R$10 (`_MINIMUM_ORDER_Q_DEFAULT`) — 0 deveria desligar.
- Admin: `minimum_order_q` NÃO tem campo no ShopAdmin (o form remove `defaults`
  cru) → hoje só editável via seed/shell. Taxa por zona (`DeliveryZone`) é
  inline e editável. Frete grátis não existe.
- **DUAS FONTES DESENCONTRADAS (bug)**: o commit usa a `RuleConfig`
  `minimum_order` (seed do Nelson: `params.minimum_q = 2500` = R$25), mas a
  barra de progresso (`build_minimum_order_progress`) lê
  `shop.defaults["rules"]["minimum_order_q"]` — que no Nelson não existe → cai
  no default mágico R$10. Resultado: barra mostra R$10, commit bloqueia em R$25.
  **Unificar numa fonte única** (a RuleConfig `params.minimum_q` é a
  autoritativa do commit; a projection deveria ler dela, não de outro JSON).

## A) Taxa no total ao vivo (rascunho progressivo) — APROVADO

Mecânica: gravar o rascunho na sessão conforme o cliente confirma, deixando o
Core recalcular. Padrão que o POS já usa (`pos_intent` com ops); storefront é
o único sem equivalente.

1. **Endpoint** `PATCH /api/v1/checkout/draft/` (storefront): aceita
   `fulfillment_type` e `delivery_address_structured` (chaves já documentadas),
   grava em `session.data`, roda o pipeline de modifiers e devolve o cart
   resolvido (mesmo shape do StorefrontCartView). Nada de chaves novas em JSON.
2. **checkout.vue**: ao confirmar recebimento/endereço (e ao limpar), chama o
   draft. `cart.delivery_fee_display` + `grand_total_display` passam a refletir
   a verdade. `CartSummaryBreakdown` já tem a linha "Entrega" — só popula.
3. **#1 (copy)**: some a frase flutuante "taxa R$ X". No passo de endereço fica
   só a confirmação acolhedora "✓ Entregamos no seu endereço". Dinheiro no
   resumo; tranquilidade no passo. Frete grátis em destaque ("Grátis").
4. O quote puro (`api/delivery.py`) pode ser aposentado (o draft cobre a
   cobertura via `delivery_zone_error`) OU ficar como pré-check rápido. Decidir
   na implementação.

## B) Políticas de entrega configuráveis — APROVADO (global primeiro)

Em `shop.defaults["rules"]`, semântica limpa **0/vazio = regra não existe**:

- `delivery_minimum_q` — não entrega abaixo disso. Avaliado quando
  `fulfillment_type=delivery`; informado ao vivo no passo de entrega ("Pedido
  mínimo para entrega R$30 · faltam R$X") e **bloqueia o commit** (na
  `DeliveryZoneRule`, que já roda lá). Retirada nunca tem mínimo.
- `free_delivery_above_q` — taxa zera no/above deste valor. Reusa a barra de
  progresso/upsell ("faltam R$8 para frete grátis"). Global (loja); por-zona
  fica para depois se necessário.
- `minimum_order_q` (geral) — mantido, mas **corrigir footgun**: 0/vazio =
  sem mínimo (remover `_MINIMUM_ORDER_Q_DEFAULT` mágico). Provavelmente fica
  zerado na config do Nelson (não faz sentido em food ticket-baixo).

### Admin (Unfold canônico)
Expor os três como campos tipados no ShopAdmin (em reais, help text), no mesmo
padrão dataclass-driven dos demais `defaults`. Taxa por zona segue no inline
`DeliveryZone`.

## Invariantes
- Core resolve totais uma vez (`build_cart`); nenhuma superfície re-deriva.
- Sem chaves novas em JSONField além das já documentadas em data-schemas.md
  (adicionar `delivery_minimum_q`/`free_delivery_above_q` em `shop.defaults.rules`
  é config da loja, não Session/Order.data — documentar mesmo assim).
- Gates: vitest + nuxt build + pytest storefront/calendar a cada passo.

## Ordem
1. B-footgun: `minimum_order_q = 0` desliga (+ teste). Pequeno, isolado.
2. A: endpoint draft + checkout.vue + copy #1 + total correto. (núcleo)
3. B: `delivery_minimum_q` + `free_delivery_above_q` no Core + UI proativa.
4. Admin: campos tipados no ShopAdmin para os três.
