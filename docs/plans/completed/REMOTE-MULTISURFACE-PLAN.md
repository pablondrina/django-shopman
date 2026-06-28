# Remote Multi-Surface Order Plan

Status: ativo
Data-base: 2026-05-15

Este plano transforma o pedido remoto multi-superficie em uma sequencia de WPs
executaveis. Cada WP abaixo tem um prompt autocontido para iniciar uma nova
sessao sem depender de contexto conversacional externo.

## Canon e limites

O canon de pedido remoto e Shopman core/orquestrador:

- Orderman: Session, Order, Fulfillment, Directive, idempotency, modify/commit/resolve.
- Payman: PaymentIntent, PaymentTransaction, PaymentService e projections de pagamento.
- Stockman: availability, promise, holds, moves, positions, planned demand.
- Guestman: Customer, ContactPoint, Address, identifiers e ManyChat subscriber sync.
- Doorman: OTP, AccessLink, device trust e auth bridge chat-to-web.
- Shopman orchestrator: ChannelConfig, lifecycle, services, Directives, handlers, projections.
- Contratos documentados em `docs/reference/order-operational-contract.md`,
  `docs/reference/storefront-surface-parity-contract.md` e ADRs.

Django/Penguin e apenas a primeira referencia de implementacao completa e
madura da storefront. Ele ajuda a descobrir casos de UX, recovery e copy, mas
nao e canon de dominio. Nuxt, Ionic, ManyChat e Django/Penguin sao superficies
que consomem Projection com Actions resolvidas pelo backend.

Regras obrigatorias:

- Nao criar novo lifecycle nem novo status oficial sem prova de gap real.
- Estados intermediarios devem ser derivados de Orderman/Payman/Stockman/Directive.
- ChannelPolicyResolution e insumo interno; superficies consomem Projection com Actions.
- A camada entre canal/dominio e superficie deve ser projection ou extensao de
  projection existente, nao control plane novo.
- WhatsApp/ManyChat pode coletar intencao e mostrar resposta Shopman, mas nao
  pode ser fonte de verdade de pricing, stock, availability, payment gate ou
  lifecycle.
- Filosofia: core enxuto, flexivel, agnostico, KISS, DRY, YAGNI,
  Omotenashi-first, WhatsApp-first, Mobile-first.

## Ordem recomendada

1. WP-REMOTE-01 - Matriz E2E e contrato executavel.
2. WP-REMOTE-02 - Channel policy resolution para projection/actions.
3. WP-REMOTE-03 - Projection conversacional ManyChat.
4. WP-REMOTE-04 - Paridade Nuxt/Ionic sobre projections.
5. WP-REMOTE-05 - Mutations remotas idempotentes.
6. WP-REMOTE-06 - Observabilidade e runbooks de pedido remoto.

## Status de execucao

| WP | Status | Evidencia |
| --- | --- | --- |
| `WP-REMOTE-01` | Concluido | `docs/reference/remote-order-e2e-matrix.md` e `shopman/storefront/tests/test_remote_multisurface_contract.py` |
| `WP-REMOTE-02` | Concluido | projections/actions por canal e testes de checkout |
| `WP-REMOTE-03` | Concluido | `shopman/shop/services/conversation.py` e contrato ManyChat |
| `WP-REMOTE-04` | Concluido | Tipos Nuxt e contrato Nuxt/Ionic sobre projections |
| `WP-REMOTE-05` | Concluido | `remote_mutations` + cancel/reorder idempotentes |
| `WP-REMOTE-06` | Concluido | `diagnose_remote_order` e runbook de pedido remoto preso |

## WP-REMOTE-01 - Matriz E2E e contrato executavel

Objetivo: criar a matriz E2E canônica de pedido remoto multi-superficie e os
primeiros testes de contrato que impedem drift entre canal, projection e
superficie.

Prompt:

```text
Estamos em /Users/pablovalentini/Dev/Claude/django-shopman.

Execute o WP-REMOTE-01: matriz E2E e contrato executavel para pedido remoto
multi-superficie.

Contexto obrigatorio:
- O canon de pedido remoto e Shopman core/orquestrador: Orderman, Payman,
  Stockman, Guestman, Doorman, ChannelConfig, Directives, services, projections
  e contratos documentados.
- Django/Penguin nao e canon; e apenas a primeira referencia de implementacao
  completa/madura da storefront.
- Nao criar novo lifecycle nem novos status oficiais.
- Estados intermediarios devem ser derivados de Order.status, Payman status,
  Stockman/holds, Directives e projections.
- ChannelPolicyResolution e insumo interno; superficies consomem Projection com Actions
  resolvidas.
- ManyChat pode coletar intencao e mostrar resposta Shopman; nao pode conter
  regra autoritativa de pricing, stock, availability, payment gate ou lifecycle.

Leia antes de alterar:
- docs/reference/order-operational-contract.md
- docs/reference/storefront-surface-parity-contract.md
- docs/decisions/adr-007-lifecycle-dispatch-functional.md
- docs/decisions/adr-009-whatsapp-via-manychat.md
- shopman/shop/config.py
- shopman/shop/lifecycle.py
- shopman/shop/services/checkout.py
- shopman/shop/services/order_tracking.py
- shopman/shop/services/payment_status.py
- shopman/storefront/api/urls.py
- surfaces/storefront-nuxt/app/types/shopman.ts

Entregaveis:
1. Criar `docs/reference/remote-order-e2e-matrix.md` com matriz por canal e
   superficie. Incluir pelo menos: web/Nuxt, Ionic, WhatsApp/ManyChat, POS,
   marketplace/external.
2. A matriz deve cobrir: pickup, delivery, pagamento cash/external/pix/card,
   payment.timing at_commit/post_commit/external, confirmation immediate/manual/
   auto_confirm/auto_cancel, stock disponivel/baixo/indisponivel/planned, hold
   expirado, payment timeout, cancelamento permitido/bloqueado, tracking,
   rating, reorder, AccessLink chat-to-web e erro/recovery.
3. Adicionar testes de contrato pequenos e focados que provem:
   - nenhuma superficie precisa inventar status fora do canon;
   - tracking/payment projections expõem estados derivados suficientes;
   - Django/Penguin e tratado como referencia de paridade, nao fonte canonica;
   - ManyChat nao deve carregar regra propria de pricing/stock.
4. Atualizar `docs/plans/REMOTE-MULTISURFACE-PLAN.md` com status do WP.

Restricoes:
- Nao implementar channel policy ainda; este WP define matriz e testes
  de contrato.
- Nao adicionar endpoints novos.
- Nao editar fluxos de runtime salvo se um teste revelar bug documental trivial.
- Preserve mudancas existentes do usuario; nao reverta arquivos nao relacionados.

Verificacao esperada:
- Rodar testes adicionados ou a menor suite relevante.
- Se nao for possivel rodar, explicar o motivo e deixar comando exato.
```

## WP-REMOTE-02 - Channel policy resolution para projection/actions

Objetivo: resolver policy por canal como insumo interno para Projection com
Actions, sem expor policy crua para surfaces.

Prompt:

```text
Estamos em /Users/pablovalentini/Dev/Claude/django-shopman.

Execute o WP-REMOTE-02: Channel policy resolution para pedido remoto.

Contexto obrigatorio:
- Channel policy e por canal; superficies consomem Projection com Actions.
- Nao criar control plane novo.
- Nao criar novo status/lifecycle.
- A projection deve derivar de ChannelConfig, Shop defaults, services e regras
  existentes.
- Deve servir Nuxt, Ionic, Django/Penguin e ManyChat sem regra propria por
  superficie.

Leia antes de alterar:
- docs/plans/REMOTE-MULTISURFACE-PLAN.md
- docs/reference/remote-order-e2e-matrix.md
- shopman/shop/config.py
- shopman/shop/models/channel.py
- shopman/storefront/projections/checkout.py
- shopman/storefront/api/surface.py
- shopman/storefront/api/serializers.py
- surfaces/storefront-nuxt/app/types/shopman.ts

Implementacao desejada:
1. Criar/estender uma resolucao interna, preferencialmente em
   `shopman/shop/services`, para alimentar projection builders.
2. Campos internos iniciais esperados, se sustentados pelo canon existente:
   - `channel_ref`
   - `payment_methods`
   - `payment_timing`
   - `fulfillment_timing`
   - `fulfillment_types` ou equivalente derivado
   - `stock_scope` resumido sem vazar detalhe interno excessivo
   - `notifications`
   - `can_checkout`
   - `channel_action_refs` derivados, por exemplo `cancel_order` e `rate_order`
   - `requires_payment_gate`
   - `supports_access_link`
   - `action_refs`
3. Substituir hardcodes evidentes de checkout, especialmente `has_pickup=True`
   e `has_delivery=True`, por valor derivado da policy resolution e exposto como
   campos/actions da projection.
4. Nao expor policy crua em payload API-first.
5. Atualizar tipos Nuxt se o payload exposto mudar.
6. Cobrir com testes de projection/API.

Restricoes:
- Se uma decisao nao tiver fonte canonica clara, documente como gap em vez
  de inventar regra.
- Nao mover regra de dominio para storefront/Nuxt.
- Nao criar app novo.

Verificacao esperada:
- Rodar testes de projection/API relevantes.
- Rodar static/type checks Nuxt apenas se tipos forem alterados e o ambiente
  local permitir.
```

## WP-REMOTE-03 - Projection conversacional ManyChat

Objetivo: criar contrato conversacional derivado das projections canônicas para
WhatsApp/ManyChat, sem regra propria de pedido no bot.

Prompt:

```text
Estamos em /Users/pablovalentini/Dev/Claude/django-shopman.

Execute o WP-REMOTE-03: projection conversacional ManyChat derivada do canon.

Contexto obrigatorio:
- WhatsApp e via ManyChat, conforme ADR-009.
- ManyChat pode coletar intencao, chamar Shopman e exibir resposta.
- ManyChat nao pode ser fonte de verdade de pricing, stock, availability,
  payment gate ou lifecycle.
- O contrato conversacional deve derivar de ChannelConfig/channel policy e das
  projections canônicas de checkout, payment e tracking.

Leia antes de alterar:
- docs/decisions/adr-009-whatsapp-via-manychat.md
- docs/reference/remote-order-e2e-matrix.md
- packages/guestman/shopman/guestman/contrib/manychat/service.py
- packages/guestman/shopman/guestman/contrib/manychat/resolver.py
- packages/guestman/shopman/guestman/contrib/manychat/views.py
- shopman/shop/adapters/notification_manychat.py
- shopman/shop/services/order_tracking.py
- shopman/shop/services/payment_status.py
- shopman/shop/services/order_confirmation.py
- packages/doorman/shopman/doorman/models/access_link.py

Implementacao desejada:
1. Criar projection conversacional compacta, em local canonico do orquestrador,
   para responder "o que o cliente deve ver/fazer agora?".
2. A projection deve incluir somente campos derivados, como:
   - `state`
   - `title`
   - `message`
   - `tone`
   - `actions`
   - `deadline_at`
   - `next_event`
   - `recovery`
   - `items_summary`
   - `total_display`
   - `order_ref`
   - `tracking_url`
   - `payment_url`
3. Reusar `OrderTrackingProjection`, `PaymentProjection` e channel policy.
4. Adicionar testes que provem que estados conversacionais derivam do canon e
   nao introduzem status oficial novo.
5. Documentar como ManyChat deve consumir esta projection.

Restricoes:
- Nao escrever regras de pricing/stock em ManyChat.
- Nao acoplar a projection a templates hardcoded do adapter.
- Nao exigir Meta Cloud API direta.

Verificacao esperada:
- Rodar testes da projection conversacional e testes ManyChat existentes
  relacionados, se houver.
```

## WP-REMOTE-04 - Paridade Nuxt/Ionic sobre projections

Objetivo: garantir que Nuxt e futuras superficies Ionic usem payloads canônicos
sem recriar regra operacional no frontend.

Prompt:

```text
Estamos em /Users/pablovalentini/Dev/Claude/django-shopman.

Execute o WP-REMOTE-04: paridade Nuxt/Ionic sobre projections canônicas.

Contexto obrigatorio:
- Nuxt/Ionic sao superficies; nao podem inventar status, payment state,
  availability ou policy.
- Django/Penguin e referencia de implementacao madura, nao canon.
- Os payloads devem vir das APIs/projections do backend.

Leia antes de alterar:
- docs/reference/storefront-surface-parity-contract.md
- docs/reference/remote-order-e2e-matrix.md
- shopman/storefront/api/urls.py
- shopman/storefront/api/surface.py
- shopman/storefront/api/tracking.py
- shopman/storefront/api/payment.py
- surfaces/storefront-nuxt/app/types/shopman.ts
- surfaces/storefront-nuxt/app/pages/checkout.vue
- surfaces/storefront-nuxt/app/pages/tracking/[ref].vue
- surfaces/storefront-nuxt/app/pages/order/[ref]/payment.vue
- surfaces/storefront-nuxt/server/utils/djangoProxy.ts

Implementacao desejada:
1. Alinhar tipos Nuxt aos payloads canônicos de checkout/actions,
   tracking e payment.
2. Remover ou cercar qualquer status/estado frontend que nao exista no canon ou
   nao venha de projection.
3. Garantir que tracking/payment exibem `promise`, `deadline`, `next_event`,
   `recovery`, stale/freshness e action URLs vindos do backend.
4. Registrar no contrato como Ionic deve consumir os mesmos endpoints, sem
   criar backend separado.
5. Cobrir com testes estaticos e, se viavel, Browser smoke mobile.

Restricoes:
- Nao mover regra de checkout/pagamento para Nuxt.
- Nao alterar lifecycle ou status backend.
- Nao duplicar DTO backend em nova camada se os tipos existentes bastarem.

Verificacao esperada:
- Rodar testes Nuxt relevantes e/ou `npm run build` quando viavel.
- Rodar testes Django de API/projection afetados.
```

## WP-REMOTE-05 - Mutations remotas idempotentes

Objetivo: padronizar mutations de superficies remotas para chamar os services
canônicos com idempotencia, sem regra propria por superficie.

Prompt:

```text
Estamos em /Users/pablovalentini/Dev/Claude/django-shopman.

Execute o WP-REMOTE-05: mutations remotas idempotentes para ManyChat/Ionic/Nuxt.

Contexto obrigatorio:
- Mutations remotas devem chamar services/APIs existentes: cart/session modify,
  checkout.process, payment projection/status, cancel, reorder, AccessLink.
- Nao criar lifecycle remoto.
- Nao criar tabela RemoteOrder.
- Idempotencia e obrigatoria em checkout e acoes sensiveis.

Leia antes de alterar:
- docs/reference/remote-order-e2e-matrix.md
- shopman/shop/services/checkout.py
- packages/orderman/shopman/orderman/services/modify.py
- packages/orderman/shopman/orderman/services/commit.py
- shopman/storefront/api/views.py
- shopman/storefront/api/surface.py
- shopman/storefront/api/tracking.py
- shopman/storefront/api/payment.py
- packages/doorman/shopman/doorman/api/views.py
- packages/guestman/shopman/guestman/contrib/manychat/views.py

Implementacao desejada:
1. Definir contrato de mutation remota para:
   - criar/atualizar carrinho;
   - iniciar checkout;
   - obter payment/tracking/conversation projection;
   - cancelar pedido quando permitido;
   - gerar AccessLink quando a conversa precisa ir para web;
   - reorder quando aplicavel.
2. Implementar apenas adapters finos que traduzem payload externo para mutations
   canônicos.
3. Garantir idempotency keys em checkout e mutations destrutivas/sensiveis.
4. Retornar projections/actions em vez de estados ad hoc.
5. Cobrir com testes HTTP/service.

Restricoes:
- Nao colocar pricing/stock em payload ManyChat como decisao autoritativa.
- Nao duplicar serializer se projection_data existente bastar.
- Nao quebrar endpoints atuais.

Verificacao esperada:
- Rodar testes dos endpoints/mutations criados ou alterados.
```

## WP-REMOTE-06 - Observabilidade e runbooks

Objetivo: tornar pedido remoto operavel: falhas de directive, pagamento,
AccessLink, ManyChat e stock devem ter visibilidade e caminho de recuperacao.

Prompt:

```text
Estamos em /Users/pablovalentini/Dev/Claude/django-shopman.

Execute o WP-REMOTE-06: observabilidade e runbooks de pedido remoto.

Contexto obrigatorio:
- O fluxo remoto depende de Directives, payment webhooks/reconcile, Stockman,
  AccessLink e ManyChat.
- Observabilidade nao deve criar fonte paralela de estado; deve ler fontes
  canônicas e apontar recuperacao.

Leia antes de alterar:
- docs/reference/order-operational-contract.md
- docs/runbooks/README.md
- docs/runbooks/directive-worker-parado.md
- docs/runbooks/webhook-falhando.md
- docs/runbooks/pagamento-divergente.md
- docs/runbooks/estoque-divergente.md
- shopman/shop/management/commands/reconcile_payments.py
- packages/orderman/shopman/orderman/management/commands/process_directives.py
- packages/stockman/shopman/stockman/management/commands/release_expired_holds.py
- packages/doorman/shopman/doorman/management/commands/auth_cleanup.py

Implementacao desejada:
1. Documentar runbook especifico de pedido remoto preso em:
   - aguardando pagamento;
   - aguardando confirmacao;
   - directive failed;
   - AccessLink expirado/usado;
   - ManyChat indisponivel;
   - stock hold expirado/divergente.
2. Se necessario, adicionar checks ou comandos de diagnostico pequenos que leem
   fontes canônicas e imprimem acao recomendada.
3. Atualizar `docs/reference/commands.md` se management command novo/flag nova for criada.
4. Cobrir management commands/checks com testes quando houver codigo.

Restricoes:
- Nao criar tabela de monitoramento paralela.
- Nao resolver incidente mudando status direto.
- Nao substituir `process_directives`/`reconcile_payments`; complementar.

Verificacao esperada:
- Rodar testes de comandos ou checks.
- Validar links de docs/runbooks.
```
