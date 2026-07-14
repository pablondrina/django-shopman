# iFood — Sinais de Status de Saída (Outbound): Mapa e Verificação Pré-Go-Live

> **Escopo:** este documento cobre **apenas os sinais OUTBOUND** — os status que o
> Shopman envia **de volta ao iFood** conforme o pedido avança (confirmar, pronto,
> despachado, cancelar). O fluxo **inbound** (polling de novos pedidos, ingestão,
> aparecer no gestor) é tratado em outro lugar (`ifood_poll`, `ifood_events`,
> `ifood_ingest`) e **não** é o foco aqui.
>
> **Data:** 2026-07-14. **Fonte:** leitura direta do código (read-only). Nenhum
> código de produção foi alterado na elaboração deste documento.

---

## 1. Como funciona o outbound (visão de 30 segundos)

O outbound é **guiado por status do pedido interno**, não por chamadas espalhadas
pelo lifecycle. O caminho é sempre o mesmo, para qualquer transição:

```
Order.save() muda status
   └─ emite signal orderman.signals.order_changed (event_type="status_changed")
        └─ receiver: shopman/shop/handlers/ifood_status.py :: on_order_status_changed
             ├─ filtra: só channel_ref == "ifood"
             ├─ filtra: só status que mapeia para uma ação iFood (senão, ignora)
             ├─ enfileira Directive "ifood.status_callback" (deduped por order+status)
             └─ (async) IFoodStatusCallbackHandler.handle
                   └─ ifood_callbacks.send_for_status(order_id, status, ...)
                         └─ POST merchant-api.ifood.com.br/order/v1.0/orders/{id}/{action}
```

Pontos-chave de design:

- **A transição de status é agnóstica à origem.** Não importa *como* o pedido chegou
  a `ready`/`dispatched`/`cancelled` (operador no gestor, POS, KDS, lifecycle
  automático); qualquer `status_changed` de um pedido `channel_ref="ifood"` dispara
  o callback. Isso está em `on_order_status_changed`
  (`shopman/shop/handlers/ifood_status.py:54`).
- **Durável, não síncrono.** O callback vira uma **Directive** (ADR-003) com
  at-least-once + backoff, porque a chamada cruza a rede. Falha da API iFood vira
  `DirectiveTransientError` → retry (`ifood_status.py:44`).
- **Dedupe por (order.ref, order.status).** A mesma transição duas vezes gera **uma**
  directive viva só (`ifood_status.py:68`).
- **Gate de ativação.** O receiver e o handler só são registrados se
  `SHOPMAN_IFOOD["client_id"]` estiver setado
  (`shopman/shop/handlers/__init__.py:317`, `_register_ifood_status_callbacks`).
  Sem `client_id`, o iFood roda **em modo simulação** e **nenhum callback dispara**.

---

## 2. Tabela — cada sinal outbound

Enum de status interno (`packages/orderman/.../models/order.py:33`):
`new → confirmed → preparing → ready → dispatched → delivered → completed`, e `cancelled`.

Mapa canônico status→ação em
`shopman/shop/services/ifood_callbacks.py:41` (`STATUS_ACTION`):

| Sinal outbound (iFood) | Status interno (gatilho) | Chamada HTTP à iFood | Onde no código | Condição |
|---|---|---|---|---|
| **confirm** (aceitar pedido) | `confirmed` | `POST /order/v1.0/orders/{id}/confirm` | `ifood_callbacks.py:82` (`confirm`), map em `:42` | `channel_ref=="ifood"` **e** existe `ifood_order_id` |
| **readyToPickup** (pronto) | `ready` | `POST /order/v1.0/orders/{id}/readyToPickup` | `ifood_callbacks.py:86` (`ready_to_pickup`), map em `:43` | idem |
| **dispatch** (saiu p/ entrega) | `dispatched` | `POST /order/v1.0/orders/{id}/dispatch` | `ifood_callbacks.py:90` (`dispatch`), map em `:44` | idem |
| **requestCancellation** (cancelar) | `cancelled` | `POST /order/v1.0/orders/{id}/requestCancellation` (body `{reason, cancellationCode}`) | `ifood_callbacks.py:120` (`request_cancellation`), map em `:45` | idem **e** `cancellation_default_code` (ou código escolhido pelo operador) preenchido — senão **falha alto** |
| _(sem ação)_ | `preparing` | — | `action_for_status` retorna `None` (`:57`) | iFood não tem callback de "em preparo"; ignorado |
| _(sem ação)_ | `delivered` | — | não está em `STATUS_ACTION` | ver **Gap G1** abaixo |
| _(sem ação)_ | `completed` | — | não está em `STATUS_ACTION` | ver **Gap G1** abaixo |

Detalhes finos:

- **`ifood_order_id`** vem de `order.external_ref` ou, como fallback,
  `order.data["external_order_code"]` (`ifood_status.py:63`). Sem ele, o receiver
  loga um warning e **não** enfileira nada (`:64-66`).
- **Auth/inércia.** Todas as chamadas passam por `ifood_auth.authorized_headers()`;
  sem `client_id`/`client_secret` retornam `None` e o callback levanta
  `IFoodCallbackError` (`ifood_callbacks.py:65`). O token OAuth é
  `client_credentials`, cacheado em processo (`ifood_auth.py`).
- **Cancelamento exige código válido da lista fixa do iFood.** O código default vem
  de `SHOPMAN_IFOOD["cancellation_default_code"]` (env `IFOOD_CANCELLATION_CODE`); o
  operador pode escolher um código por pedido no gestor (gravado em
  `order.data["ifood_cancellation_code"]`, propagado em `ifood_status.py:87`). Sem
  código nenhum → `IFoodCallbackError` **antes** de qualquer POST
  (`ifood_callbacks.py:128-133`). O `reason` nunca pode ser vazio (iFood 400) — há
  fallback para `"Cancelado pela loja"` (`:136-140`). Os códigos válidos por pedido
  vêm de `GET .../cancellationReasons` (`fetch_cancellation_reasons`, `:94`).
- **iFood responde 202 Accepted** para ações de status; o cliente aceita 200/202
  (`ifood_callbacks.py:75`).

---

## 3. Testabilidade de cada sinal, hoje

### 3.1 Testes unitários (existem e passam — `make test`)

Arquivo: `shopman/shop/tests/test_ifood_direct.py` (seção "WP-4: status callbacks",
linhas 411-618). Cobertura com `requests.post` mockado + `override_settings`:

| Sinal | Teste unitário | Linha |
|---|---|---|
| Mapa status→ação (todos + `preparing`→None) | `test_action_for_status_mapping` | 414 |
| `confirm` aceita 202 e monta URL certa | `test_send_action_accepts_202` | 425 |
| não-2xx levanta erro | `test_send_action_non_2xx_raises` | 435 |
| cancelamento usa código configurado + reason | `test_send_for_status_cancellation_uses_configured_code` | 445 |
| reason nunca vazio (fallback) | `test_cancellation_reason_never_empty` | 459 |
| reason usa default configurado | `test_cancellation_reason_uses_configured_default` | 475 |
| código escolhido pelo operador sobrepõe default | `test_send_for_status_uses_operator_chosen_code` | 485 |
| cancelar sem código → falha alto, sem POST | `test_request_cancellation_without_code_raises` | 542 |
| `fetch_cancellation_reasons` | `test_fetch_cancellation_reasons` | 553 |
| status não-mapeado → `False` (no-op) | `test_send_for_status_unmapped_returns_false` | 565 |
| handler levanta `DirectiveTransientError` p/ retry | `test_status_handler_raises_transient_on_callback_error` | 571 |
| signal enfileira directive p/ pedido iFood + idempotência | `test_signal_receiver_enqueues_directive_for_ifood_order` | 588 |
| signal ignora pedidos não-iFood | `test_signal_receiver_ignores_non_ifood_orders` | 609 |
| signal carrega código de cancelamento do operador | `test_signal_receiver_carries_operator_cancellation_code` | 500 |
| `cancellation_reasons` no facade backstage | `test_cancellation_reasons_service` | 518 |

**Conclusão:** a lógica de mapeamento, montagem de request, dedupe, retry e regras de
cancelamento estão **bem cobertas por unit test com mock**. O que os unit tests **não**
provam: que a API real do iFood aceita esses POSTs e devolve 202 no ambiente do
merchant real.

### 3.2 Homologação / sandbox / live

- **Não há mock/dry-run de outbound em runtime.** `ifood_simulation.py` é só um gerador
  de payload **inbound** (injeta pedido simulado no `ingest`); ele **não** exercita
  nenhum callback de saída. Ou seja: pedido simulado avança de status mas, se o pedido
  não tem `external_ref` real e/ou `client_id` não está setado, nenhum POST sai.
- **O "sandbox" prático é o app do Portal do Desenvolvedor iFood** com `client_id`/
  `client_secret` reais apontando para `merchant-api.ifood.com.br` (mesma base de prod;
  não há URL de sandbox separada configurada — `api_base` default é a de produção). Os
  contratos das rotas foram verificados ao vivo (id falso → `404 OrderNotFound`) — ver
  docstrings em `ifood_callbacks.py:3-9` e `ifood_orders.py:6-14`.
- **Bloqueio conhecido:** a loja de teste do portal estava `DISABLED` e **sem pedidos**,
  então o schema de pedido real e o ciclo completo de callbacks **não puderam ser
  exercitados end-to-end** ainda (`ifood_orders.py:11-14`). Confirmar/pronto/despachar/
  cancelar contra um pedido real é exatamente o que falta validar na homologação.

---

## 4. Checklist de verificação pré-go-live (outbound)

Pré-requisitos de configuração (env do deployment):

- [ ] `IFOOD_CLIENT_ID` e `IFOOD_CLIENT_SECRET` setados (senão os callbacks **nem se
      registram** — `handlers/__init__.py:324`).
- [ ] `IFOOD_MERCHANT_ID` setado (usado no polling inbound e no map).
- [ ] `IFOOD_CANCELLATION_CODE` setado com um código **válido da lista do iFood**
      (descobrir via `fetch_cancellation_reasons` num pedido real). Sem ele, todo
      cancelamento de pedido iFood falha alto.
- [ ] **Worker de directives rodando no deployment** — ver **Gap G2**. Sem
      `process_directives` ativo, as directives `ifood.status_callback` ficam
      enfileiradas e **nenhum status chega ao iFood**, mesmo com tudo configurado.

Verificação end-to-end (idealmente na homologação, com 1 pedido de teste real que
entrou pelo polling e tem `external_ref` preenchido):

- [ ] **confirm** — Aceitar o pedido no gestor (`confirm_order`). Confirmar
      `202` no log `ifood_callbacks: confirm ok for order {id}` e que o pedido aparece
      como confirmado no app/painel do iFood.
- [ ] **readyToPickup** — Avançar o pedido para `ready`. Confirmar callback
      `readyToPickup` e reflexo no iFood.
- [ ] **dispatch** — Avançar para `dispatched`. Confirmar callback `dispatch` e que o
      iFood mostra "saiu para entrega".
- [ ] **requestCancellation** — Cancelar/recusar um pedido de teste escolhendo um
      motivo/código no seletor do gestor. Confirmar body `{reason, cancellationCode}`
      correto, resposta OK do iFood e o pedido cancelado no painel iFood. Testar também
      o caminho **sem código configurado** para garantir que falha visível (não POST
      com código chutado).
- [ ] **Retry/durabilidade** — Simular indisponibilidade do iFood (ou derrubar rede) e
      confirmar que a directive re-tenta com backoff e não fica presa (checar
      `check_directive_health` / `OperatorAlert`).
- [ ] **Idempotência** — Forçar duas transições para o mesmo status e confirmar que só
      **um** callback sai (dedupe).
- [ ] **Não-vazamento entre canais** — Confirmar que um pedido não-iFood mudando de
      status **não** gera directive `ifood.status_callback`.
- [ ] **Revalidar o schema do pedido real** contra `map_order` (inbound) durante a
      mesma sessão de homologação (`ifood_orders.py:11-14`), já que confirmar depende de
      o `external_ref` estar corretamente gravado na ingestão.

---

## 5. Gaps explícitos (sinais sem caminho de teste / de risco)

**G1 — Não há sinal de "concluído/entregue" para o iFood.**
`STATUS_ACTION` mapeia apenas `confirmed/ready/dispatched/cancelled`. Os status
internos `delivered` e `completed` **não** disparam nenhum callback. Para pedidos de
**entrega própria** isso é esperado (o iFood conclui automaticamente após `dispatch`).
**Risco a validar na homologação:** confirmar que, para o modelo logístico da loja
(entrega própria vs. entrega iFood/`deliveredBy`), o iFood realmente não espera um
sinal explícito de conclusão. Se esperar, falta implementar (não existe hoje). Também
**não há sinal outbound para `preparing`** — intencional (iFood não tem essa ação).

**G2 — O worker que drena directives é separado do `maintenance_worker` (risco de deploy).**
`maintenance_worker` roda só limpezas + `check_directive_health`
(`shopman/shop/management/commands/maintenance_worker.py:33`); ele **não** processa
directives. Quem executa os handlers (incl. `ifood.status_callback`) é
`process_directives` (`packages/orderman/.../management/commands/process_directives.py`).
Se o deployment não tiver um processo `process_directives` ativo, **todos os callbacks
outbound ficam enfileirados e nunca saem** — sem erro visível na tela, só backlog de
directives. Este é o maior risco silencioso de go-live. (Consistente com a nota de
memória: "worker process_directives ≠ maintenance_worker".)

**G3 — Nenhum teste end-to-end real de outbound foi executado ainda.**
Toda a cobertura é unit com `requests` mockado. O ciclo confirm→ready→dispatch→cancel
contra um pedido real do iFood **nunca rodou** (loja de teste `DISABLED`/sem pedidos —
`ifood_orders.py:11-14`). Até a homologação, a compatibilidade real de payload/resposta
das 4 ações é **presumida a partir de docstrings de verificação de rota**, não provada
com um pedido de verdade.

**G4 — Sem URL de sandbox dedicada.**
`api_base` default é a de produção (`merchant-api.ifood.com.br`). A "homologação" usa a
mesma base com credenciais de teste. Não há flag de ambiente que torne os callbacks
outbound inertes fora de DEBUG **além** do gate de `client_id`. Cuidado ao setar
`IFOOD_CLIENT_ID` em qualquer ambiente que compartilhe base com pedidos reais.

**G5 — Cancelamento pós-confirmação pode exigir aprovação do iFood.**
`requestCancellation` depois de confirmado pode não ser aceito automaticamente pelo
iFood (`ifood_callbacks.py:18-21`). O sistema envia a solicitação; a decisão final é do
iFood. Validar o comportamento real (e a UX do operador quando o iFood recusa o
cancelamento) na homologação.

---

## 6. Referências de código (arquivo:linha)

- Mapa status→ação + cliente HTTP outbound: `shopman/shop/services/ifood_callbacks.py`
  (`STATUS_ACTION` :41, `send_action` :62, `request_cancellation` :120,
  `send_for_status` :148, `fetch_cancellation_reasons` :94)
- Receiver de signal + handler de directive: `shopman/shop/handlers/ifood_status.py`
  (`on_order_status_changed` :54, `IFoodStatusCallbackHandler` :26)
- Registro condicionado a `client_id`: `shopman/shop/handlers/__init__.py:317`
- Constante de tópico: `shopman/shop/directives.py:66` (`IFOOD_STATUS_CALLBACK`)
- OAuth (inércia sem creds): `shopman/shop/services/ifood_auth.py`
- Enum de status: `packages/orderman/shopman/orderman/models/order.py:33`
- Emissão do signal `order_changed` no `save()`:
  `packages/orderman/shopman/orderman/models/order.py:283`
- Facade de mutação do operador (confirm/reject/cancel + `cancellation_reasons`):
  `shopman/backstage/services/orders.py`
- Config: `config/settings.py:495` (`SHOPMAN_IFOOD`)
- Worker de manutenção (NÃO drena directives): `shopman/shop/management/commands/maintenance_worker.py`
- Worker de directives (drena): `packages/orderman/shopman/orderman/management/commands/process_directives.py`
- Testes outbound: `shopman/shop/tests/test_ifood_direct.py:411-618`
