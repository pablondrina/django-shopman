# Remote Mutation Contract

Data-base: 2026-05-15

Este contrato padroniza mutations de superficies remotas sem criar lifecycle,
status ou tabela paralela de pedido.

Nao existe compatibilidade aberta. Este documento descreve endpoints existentes;
ele nao autoriza nova regra, novo lifecycle, novo status ou novo consumidor de
UX fora de Projection com Actions.

## Principios

- Mutations remotas sao adapters finos sobre services canonicos.
- Respostas retornam projections/actions ou resultado canonico, nao estado
  ad hoc de superficie nem policy crua como volante de UX.
- Checkout, cancelamento, reorder e qualquer mutation destrutiva/sensivel devem
  receber `Idempotency-Key` ou `idempotency_key`.
- Quando uma integracao externa nao consegue enviar header de idempotencia, o
  adapter pode aceitar `idempotency_key` no body ou usar fallback deterministico
  por pedido/sessao para evitar retry duplicado.
- ManyChat nao envia preco/estoque como decisao autoritativa; envia intencao.

## Mutations

| Mutation | Endpoint/service | Fonte canonica | Idempotencia |
| --- | --- | --- | --- |
| Ler cart/projection | `GET /api/v1/storefront/cart/` | `CartProjection` | N/A |
| Criar/atualizar carrinho | `/api/v1/cart/*`, `CartSkuQtyView` | `CartService`, `ModifyService`, Stockman | Recomendado por chamada de cliente |
| Iniciar checkout | `POST /api/v1/checkout/`, `checkout.process` | `Session`, `CommitService`, ChannelConfig | Obrigatoria (`idempotency_key`) |
| Tracking | `GET /api/v1/tracking/{ref}/` | `OrderTrackingProjection` | N/A |
| Payment | `GET /api/v1/payment/{ref}/`, `/status/` | `PaymentProjection`, Payman | N/A |
| Conversation | `build_order_conversation(order, channel_ref=...)` | Tracking + payment + channel policy | N/A |
| Cancelar pedido | `POST /api/v1/orders/{ref}/cancel/` | `customer_orders.cancel`/cancellation service | Obrigatoria; adapter aceita header/body/fallback |
| Reorder | `POST /api/v1/orders/{ref}/reorder/` | `customer_orders.add_reorder_items` | Obrigatoria; adapter aceita header/body/fallback |
| AccessLink | Doorman `AccessLink.create_with_token`/API de auth bridge | Doorman | Obrigatoria por chamada externa |

## Executor comum

`shopman.shop.services.remote_mutations.run_idempotent_mutation` usa
`orderman.IdempotencyKey` existente. Ele:

1. cria ou bloqueia a chave `scope/key`;
2. retorna replay quando a resposta anterior ja esta `done`;
3. rejeita concorrencia com `mutation_in_progress`;
4. salva `response_body`/`response_code` para mutations sem erro 5xx.

Nao ha tabela `RemoteOrder`, fila nova, status remoto ou control plane
separado.

## ManyChat/Ionic/Nuxt

- Nuxt e Ionic chamam os endpoints acima diretamente via proxy/autenticacao
  existente.
- ManyChat deve ter adapter fino: sincroniza cliente, chama mutation Shopman,
  renderiza `RemoteConversationProjection`, e usa Doorman para AccessLink
  quando precisar migrar a conversa para web.
- Nenhuma superficie calcula payment gate, availability, holds, cancelamento,
  avaliacao ou next_event por conta propria; essas decisoes chegam como
  Projection/Actions.
