# Remote Order E2E Matrix

Status: contrato executavel
Data-base: 2026-05-15

Esta matriz define os cenarios minimos para pedido remoto multi-superficie.
Ela nao cria lifecycle, status ou control plane novo. Cada linha deve ser
implementada contra o canon Shopman core/orquestrador: Orderman, Payman,
Stockman, Guestman, Doorman, ChannelConfig, Directives, services e projections.

Django/Penguin e referencia madura de implementacao da storefront, nao canon de
dominio. Nuxt, Ionic, ManyChat e Django/Penguin devem consumir Projection com
Actions resolvidas pelo backend.

## Fontes de verdade

| Dimensao | Fonte canonica | Superficies consomem |
| --- | --- | --- |
| Status operacional | `orderman.Order.status` | Tracking, backstage, account, ManyChat conversation projection |
| Pagamento | Payman `PaymentIntent.status` + `shopman.shop.services.payment_status` | Payment page, tracking payment gate, ManyChat payment CTA |
| Disponibilidade/holds | Stockman availability, promise, holds e `order.data["availability_decision"]` | Catalog, cart, checkout, tracking recovery |
| Canal | `ChannelConfig.for_channel(channel_ref)` | Projection com actions resolvidas por canal |
| Timers | Directives + datas de servidor | Countdown, stale state, active notifications |
| Identidade | Guestman + Doorman AccessLink/OTP/device trust | Web, Nuxt, Ionic, ManyChat |
| Conversa | Projection derivada do backend | ManyChat renderiza, nao decide regra |

## Canais e superficies

| Canal | Superficie primaria | Superficies consumidoras | Payment timing | Fulfillment timing | Observacao |
| --- | --- | --- | --- | --- | --- |
| `web` | Nuxt/Django storefront | Nuxt, Django/Penguin, Ionic WebView | `at_commit` ou `post_commit` conforme config | `post_commit` default | Canal proprio remoto com auth, cart, checkout, payment e tracking |
| `whatsapp` | ManyChat | ManyChat, AccessLink para web/Nuxt/Ionic | `post_commit` ou `at_commit` conforme config | `post_commit` default | Bot coleta intencao e chama Shopman; regra fica no backend |
| `mobile` | Ionic | Ionic, APIs `/api/v1` | herdado de `ChannelConfig` | herdado de `ChannelConfig` | Mesmo contrato JSON de Nuxt, sem backend separado |
| `pdv` | Backstage/POS | Operador | `external` ou pagamento de balcao | `at_commit` ou local | Canal presencial; cliente remoto nao decide status operacional |
| `ifood`/marketplace | Marketplace externo | Webhook/API externa + backstage | `external` | `external` ou sync externo | Preco/pagamento podem ser externos, mas Order.status continua canonico |

## Matriz de cenarios

| ID | Canal | Superficie | Fulfillment | Pagamento | Confirmacao | Estoque | Resultado canonico esperado | Projection/contrato |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `REMOTE-PICKUP-CASH-IMMEDIATE` | `web` | Nuxt/Django/Ionic | pickup | cash, `external` timing local | immediate | available | `new -> confirmed -> preparing -> ready -> completed`; sem Payman digital obrigatorio | checkout projection mostra cash; tracking usa pickup promise |
| `REMOTE-PICKUP-PIX-AT-COMMIT` | `web` | Nuxt/Django/Ionic | pickup | pix, `at_commit` | manual ou auto | available | Order fica `new` ate pagamento/confirmacao; Payman `pending -> captured`; payment timeout cancela se expirar | payment projection expoe QR, deadline, recovery; tracking redireciona payment gate |
| `REMOTE-PICKUP-PIX-POST-COMMIT` | `web` | Nuxt/Django/Ionic | pickup | pix, `post_commit` | manual/auto | available | Loja confirma disponibilidade antes de pedir pagamento; depois Payman captura e pedido prepara | tracking promise `payment_requested`; ManyChat pode enviar CTA de pagamento |
| `REMOTE-DELIVERY-CARD-AUTH` | `web` | Nuxt/Django/Ionic | delivery | card hosted checkout | manual | available | Payman `authorized/captured` conforme adapter; `ready` nao significa entregue; `dispatched` e a saida | payment projection expoe hosted checkout; tracking separa `ready_delivery` de `dispatched` |
| `REMOTE-DELIVERY-EXTERNAL-MARKETPLACE` | `ifood` | marketplace/backstage | delivery | external | manual ou auto | check por canal | Payman pode ausentar; `Order.status` permanece decisao operacional | ChannelConfig `payment.timing=external`; tracking/backstage nao le `order.data.payment.status` |
| `REMOTE-WA-PREORDER-PLANNED` | `whatsapp` | ManyChat | pickup/delivery | pix ou cash | manual/auto | planned/demand | ManyChat coleta intencao; Shopman cria sessao/hold/demanda; projection informa espera e proxima acao | conversation projection deriva de cart/checkout/tracking/payment |
| `REMOTE-WA-ACCESS-LINK-CHECKOUT` | `whatsapp` | ManyChat + web | pickup/delivery | qualquer habilitado | conforme canal | available/low | ManyChat solicita AccessLink; Doorman autentica e redireciona para checkout/tracking seguro | AccessLink source manychat; no ref guessing |
| `REMOTE-OOS-RECOVERY` | `web`/`whatsapp` | Nuxt/Ionic/ManyChat | qualquer | qualquer | qualquer | unavailable | Commit/modify bloqueia issue ou cancela por availability conforme config; nao cria status novo | cart/checkout/conversation mostram itens afetados e recovery |
| `REMOTE-LOW-STOCK-HOLD` | `web`/`mobile` | Nuxt/Ionic | pickup/delivery | qualquer | qualquer | low_stock | Stockman aplica safety/hold; concorrencia nao permite oversell | catalog/cart mostram `available_qty`/warning; checkout respeita issue |
| `REMOTE-HOLD-EXPIRED` | `web`/`whatsapp` | Nuxt/Ionic/ManyChat | qualquer | qualquer | qualquer | hold expired | Hold liberado por Stockman; cliente ve recovery, nao estado paralelo | cart/tracking/conversation usam projection de recovery |
| `REMOTE-PAYMENT-TIMEOUT` | `web`/`whatsapp` | Nuxt/Ionic/ManyChat | qualquer | pix | qualquer | reserved | `payment.timeout` cancela intent/order se ainda sem captura | payment/tracking promise `expired/payment_expired` e active notification |
| `REMOTE-CANCEL-ALLOWED` | `web`/`mobile` | Nuxt/Ionic | qualquer | qualquer | antes do corte operacional | any | Cancelamento passa por service canonico, release/refund quando necessario | tracking expoe action `cancel_order` com confirmacao destrutiva |
| `REMOTE-CANCEL-BLOCKED` | `web`/`mobile` | Nuxt/Ionic | delivery | paid/dispatched | depois do corte | any | Cancelamento bloqueado ou vira return/refund flow; status terminal respeitado | tracking nao expoe action `cancel_order` |
| `REMOTE-RATING` | `web`/`mobile` | Nuxt/Ionic | delivery/pickup | qualquer | completed/delivered | any | Rating permitido quando projection expuser action `rate_order`; rating nao depende de status paralelo | tracking/account renderizam actions da projection |
| `REMOTE-REORDER` | `web`/`mobile` | Nuxt/Ionic | qualquer | qualquer | novo pedido | current availability | Reorder usa mutation explicita `append/replace`; indisponiveis viram skipped/recovery | cart/reorder projections e modais destrutivos |
| `REMOTE-POS-COUNTER` | `pdv` | Backstage/POS | pickup/local | external/cash | immediate/manual operador | stock local | POS pode usar payment externo/local; nao muda regra de pedido remoto | Backstage projections operacionais, sem surface status novo |

Notas de confirmacao:

- `auto_confirm` e `auto_cancel` sao modos de `ChannelConfig.confirmation` e
  devem obedecer as mesmas precondicoes de pagamento/disponibilidade da
  confirmacao manual.
- `manual` sem timer pode usar `order.stale_new_alert` para escalar ao operador,
  mas nao cria status intermediario.

## Cobertura obrigatoria por WP

| WP | Cobertura minima |
| --- | --- |
| `WP-REMOTE-01` | Esta matriz, testes de contrato e prova documental de canon |
| `WP-REMOTE-02` | Projection/action builders resolvem payment, fulfillment, stock, notification e actions por canal |
| `WP-REMOTE-03` | ManyChat conversation projection deriva de tracking/payment/checkout/channel policy |
| `WP-REMOTE-04` | Nuxt/Ionic consomem payloads canonicos sem status local novo |
| `WP-REMOTE-05` | Mutations remotas chamam services/APIs canonicos com idempotencia |
| `WP-REMOTE-06` | Runbooks e diagnostico leem fontes canonicas e nao escrevem status direto |

## Anti-requisitos

- Nao criar `RemoteOrder`.
- Nao criar lifecycle remoto.
- Nao criar status oficiais como `awaiting_payment`, `awaiting_store_confirmation`
  ou `out_for_delivery`; estes sao estados derivados de Orderman, Payman,
  Stockman, Directives e projections.
- Nao colocar regra autoritativa de pricing/stock/availability/payment gate no
  ManyChat.
- Nao tratar Django/Penguin como canon de dominio.
- Nao criar backend separado para Ionic.
