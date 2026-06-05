# ManyChat Conversation Projection

Data-base: 2026-05-15

Este contrato define como WhatsApp/ManyChat deve consumir o estado de um
pedido remoto sem conter regra propria de pedido.

## Fonte canonica

ManyChat nao calcula preco, estoque, disponibilidade, pagamento, cancelamento
ou lifecycle. O bot coleta intencao, chama Shopman e renderiza a resposta.

A projection conversacional e `RemoteConversationProjection`, construida por
`shopman.shop.services.conversation.build_order_conversation(order, channel_ref=...)`.
Ela deriva de:

- `OrderTrackingProjection`, para status oficial, promise, recovery, timeline
  resumida, total e cancelamento.
- `PaymentProjection`, quando existe pagamento digital com action canonica
  pendente.
- Channel policy resolution, para regras resolvidas por canal, como AccessLink,
  gate de pagamento e cancelamento.

`state` na projection conversacional nao e status oficial de Orderman. Ele e o
estado de promise ja resolvido por tracking/payment. O status oficial permanece
em `order_status`.

## Campos

- `order_ref`: referencia do pedido.
- `order_status`: status oficial de Orderman.
- `channel_ref`: canal resolvido.
- `source_projection`: `tracking` ou `payment`.
- `state`, `title`, `message`, `tone`: texto e tom derivados da promise
  canonica.
- `actions`: lista ordenada de `Action` que a superficie pode
  renderizar/executar. Lista vazia significa que nao ha acao acionavel agora.
- `deadline_at`: prazo canonico quando existe timer de pagamento ou
  disponibilidade.
- `next_event`: o que Shopman espera que aconteca em seguida.
- `recovery`: orientacao de recuperacao ja resolvida pelo backend.
- `items_summary`: resumo compacto dos itens.
- `total_display`: total formatado pelo backend.
- `tracking_url`: URL relativa de acompanhamento.
- `payment_url`: URL relativa de pagamento quando aplicavel.
- `supports_access_link`: canal pode usar AccessLink para levar conversa ao web.
- `requires_payment_gate`: canal exige gate de pagamento digital do Shopman.

## Consumo ManyChat

1. Identificar ou sincronizar o cliente via Guestman.
2. Chamar um adapter fino de Shopman para obter ou criar o pedido usando
   mutations canonicas.
3. Chamar `build_order_conversation` para o pedido/canal.
4. Renderizar `title`, `message`, `actions`, `deadline_at`, `next_event` e
   `recovery`.
5. Se `supports_access_link=true` e a conversa precisa migrar para web, gerar
   AccessLink pelo Doorman e usar a URL retornada. ManyChat nao monta token.
6. Para atualizar o cliente, chamar Shopman novamente. ManyChat nao infere
   transicao de status, pagamento ou disponibilidade.

## Anti-regras

- Nao duplicar pricing ou availability no fluxo ManyChat.
- Nao criar status remoto ou `RemoteOrder`.
- Nao decidir cancelamento ou avaliacao apenas no bot; usar `cancel_order` ou
  `rate_order` somente quando a projection oferecer a action.
- Nao transformar `state` conversacional em lifecycle oficial.
- Nao considerar Django/Penguin canon; ele e referencia madura de superficie.
