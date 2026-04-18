# Auditoria de Pipelines — 2026-04-17

Auditoria das dimensões **canal × pagamento × confirmação × notificação**
no `lifecycle.py` e correlacionados. Sem inventar — apenas o que existe
hoje no código.

## Matriz de cobertura

| Canal | Kind | Métodos | `payment.timing` | `confirmation.mode` | `stock.check_on_commit` | Notif backend | Guards | Testes |
|---|---|---|---|---|---|---|---|---|
| **balcao** (PDV) | pos | `cash` | `external` | `immediate` | ✅ true | manychat (default) | payment skippa (offline); availability obrigatória | ✅ E2E-1, `TestLocalChannelScenario` |
| **delivery** (próprio) | web | `pix`, `card` | `post_commit` | `auto_confirm` (5 min) | ❌ false | manychat (default) | ambos ativos | ✅ E2E-2/3/4, `TestRemoteChannelScenario` |
| **web** (e-commerce) | web | `pix`, `card` | `post_commit` | `auto_confirm` (5 min) | ❌ false | manychat (default) | ambos ativos | ✅ parcial |
| **whatsapp** | whatsapp | `pix`, `card` | `post_commit` (default) | `auto_confirm` (5 min) | ❌ false | **manychat (explícito)** | ambos ativos | ⚠️ sem E2E dedicado |
| **ifood** (marketplace) | ifood | `external` | `external` | `manual` | ✅ true | manychat (default) | payment skippa (external); availability obrigatória | ✅ E2E-5, `TestMarketplaceChannelScenario` |

## Lacunas identificadas

1. **`on_commit` sem notificação imediata** — cliente em fluxo `auto_confirm` remoto só recebe mensagem após 5 min (timeout) ou nunca (`manual`). Nenhum "Recebemos seu pedido" na entrada.
2. **`on_completed` sem notificação de fecho** — só faz `loyalty.earn` + `fiscal.emit`. Sem feedback de fim de ciclo.
3. **`on_delivery` / `pickup` inconsistentes** — `lifecycle._OFFLINE_PAYMENT_METHODS` inclui esses valores, mas `ChannelConfig.validate` (`config.py:229`) só aceita `{counter, pix, card, external}`. Schema e guard discordam.
4. **WhatsApp sem E2E dedicado** — roteamento `manychat → sms → email` não exercitado com `subscriber_id`.
5. **`on_paid` pós-cancelamento não libera estoque** — refunda + alerta, mas não chama `stock.release`.
6. **Guard de pagamento permite fallback desnecessário** — quando `method="cash"` mas existir `intent_ref` legado, roda `Payman.get` sem necessidade.
7. **`confirmation.mode="manual"` sem SLA** — iFood pode ficar em NEW indefinidamente sem `OperatorAlert("stale_new_order")` ou escalação.
8. **`on_preparing`/`on_ready` dependem de transição manual** — sem handler automatizado `CONFIRMED → PREPARING → READY`. Canais `immediate + external` (balcão) podem travar em CONFIRMED se ninguém no KDS.
9. **`system_notification` hardcoded a email+console** — `handlers/notification.py:126` ignora `ChannelConfig.notifications.fallback_chain`.
10. **`pre_commit` aceito pelo validator, ignorado pelo dispatcher** — `config.py:235` aceita em `valid_timings`, mas `lifecycle._on_commit` só trata `at_commit`/`post_commit`/`external`.

## Recomendações (top 3)

### R1 — Unificar enum de pagamento
Remover `"on_delivery"`/`"pickup"` de `_OFFLINE_PAYMENT_METHODS` **ou** adicioná-los a `valid_methods` em `ChannelConfig.validate`. Remover `"pre_commit"` de `valid_timings`. Schema e guards devem concordar.
- Arquivos: [lifecycle.py:95](shopman/shop/lifecycle.py:95), [config.py:229-237](shopman/shop/config.py:229)

### R2 — Notificação imediata em `_on_commit`
Canais remotos (`payment.timing != "external"`) devem enviar `order_received` ao cliente no momento do commit. Hoje o cliente fica 5 min sem feedback. Criar template + chamar `notification.send(order, "order_received")` em `_on_commit` após `loyalty.redeem`.

### R3 — SLA para `manual` + escalação `stale_new_order`
Criar directive `order.stale_new_alert` (análogo a `confirmation.timeout`) para canais `manual` (iFood) que alerta operador após X minutos sem decisão. Complementar com teste E2E dedicado de WhatsApp cobrindo fallback `manychat → sms → email`.

---

**Audit scope:** `shopman/shop/lifecycle.py`, `shopman/shop/services/*`, `shopman/shop/handlers/*`, `shopman/shop/config.py`, `shopman/shop/tests/e2e/`.
