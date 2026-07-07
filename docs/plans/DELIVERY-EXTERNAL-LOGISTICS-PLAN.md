# DELIVERY-EXTERNAL-LOGISTICS-PLAN — Despacho via serviço externo (TaOn / Taxi Machine)

> Entrega via logística externa de terceiros. **2026-07-07: a API existe e a integração
> first-class foi CONSTRUÍDA** — a TaOn roda sobre a **Machine** (Gaudium,
> api.taximachine.com.br) e a doc Postman chegou. O preço ao cliente segue nas faixas/zonas
> (`DeliveryDistanceBand` + `DeliveryZone`); a cotação da Machine é **custo interno** exibido
> no gestor (decisão Pablo, 2026-07-07).

---

## 1. Duas camadas

| Camada | O que é | Estado |
|---|---|---|
| **Integração Machine** | Despacho automático + status em tempo real + ações do operador no gestor. | ✅ construída (2026-07-07), aguarda credenciais + homologação |
| **Teleporte (fallback)** | Utilitário local que leva os dados de entrega para o form do serviço (clipboard). | ✅ entregue (2026-06-29) — fallback manual (API fora / entrega própria) |

---

## 2. Integração Machine — construída (2026-07-07)

Arquitetura (funil único; letras de status da Machine: D/G/P aguardando, A aceita, S na loja,
E em andamento, F finalizada, N não atendida, C cancelada):

```
READY (lifecycle._on_ready) + ChannelConfig.fulfillment.courier == "auto" + delivery
  → Directive courier.dispatch → adapter courier → POST /abrirSolicitacao → id_mch
       → Order.data["courier"] (schema em data-schemas.md) + SSE + agenda courier.sync

Status (2 vias → services/courier.apply_status, idempotente):
  webhooks/machine.py (push, ?token=)  ─┐
  CourierSyncHandler (poll reagendável) ┴→ E→DISPATCHED (notif. "saiu p/ entrega")
                                           F→DELIVERED (notif. "entregue")
                                           N/C→OperatorAlert + re-despacho no gestor
```

- **Adapter**: `shopman/shop/adapters/courier_machine.py` (borda HTTP única; dinheiro → `_q`;
  inerte em DEBUG via `SHOPMAN_MACHINE_ALLOW_IN_DEBUG`) + `courier_mock.py` (dev/testes).
  Registro: `get_adapter("courier")` ← `Shop.integrations["courier"]` > `SHOPMAN_COURIER_ADAPTER`.
- **Config por canal**: `ChannelConfig.Fulfillment.courier` = `"none" | "auto"` (iFood tem
  logística própria = none; canal delivery próprio = auto). Config diz SE; adapter diz QUEM.
- **Gestor** (orders-nuxt, página do pedido): painel da corrida (timeline, entregador, rastreio,
  custo) + ações **Cotar entrega** (avulsa, sem abrir corrida), **Chamar/Re-despachar** e
  **Cancelar corrida** (só antes da coleta). Tempo real via SSE + poll.
- **Notificações**: reusa `order_dispatched`/`order_delivered`; link de rastreio do entregador
  entra como `{courier_tracking_suffix}` (auto-suprimível).
- **Redes de segurança preservadas**: `DELIVERY_AUTO_COMPLETE` (ETA+folga) e "Recebi" do cliente
  continuam; viram no-op quando o `F` da Machine chega antes.
- **Checks**: `SHOPMAN_E011` (credenciais em prod) e `SHOPMAN_W010` (sem webhook_token → polling).

### Go-live (pendências externas)
1. Credenciais da central: `MACHINE_API_USER/PASSWORD/API_KEY` + permissão "API - Entrega"
   (ver [GO-LIVE-CREDENTIALS-MATRIX](GO-LIVE-CREDENTIALS-MATRIX.md)).
2. Ligar: `SHOPMAN_COURIER_ADAPTER=shopman.shop.adapters.courier_machine` +
   `fulfillment.courier="auto"` no canal delivery. Polling ativo desde o dia 1.
3. Homologar webhook: `MACHINE_WEBHOOK_TOKEN` + `manage.py machine_register_webhook
   https://api.<dominio>`; observar o primeiro evento real (payload não documentado — o endpoint
   loga o corpo cru) e então reduzir/zerar `Shop.defaults.delivery.courier_poll_seconds`.
4. Confirmar com a central: `MACHINE_FORMA_PAGAMENTO` (default `F` faturado) e `motivo_id`
   válido de cancelamento (`MACHINE_CANCEL_REASON_ID`).

---

## 3. Teleporte — fallback manual (slice clipboard)

WP-11 slice 3 do [STOREFRONT-GAPS-ACTION-PLAN](STOREFRONT-GAPS-ACTION-PLAN.md). Decisão travada
(Pablo, 2026-06-17): **utilitário LOCAL Python**, roda na máquina do operador (desacoplado do
deploy), **clipboard como fallback**, DOM-fill quando houver URL/campos.

**Entregue 2026-06-29:**
- [`shopman/shop/services/dispatch_handoff.py`](../../shopman/shop/services/dispatch_handoff.py) —
  `build_dispatch_payload(order)` (payload estruturado a partir de `Order.data`; rejeita retirada),
  `format_dispatch_text(payload)` (bloco pt-BR paste-ready), `copy_to_clipboard(text)`
  (best-effort pbcopy/wl-copy/xclip/xsel/clip).
- [`manage.py teleporte ORDER-REF`](../../shopman/shop/management/commands/teleporte.py) —
  imprime + copia. `--json` emite o payload estruturado; `--no-copy` só imprime.
- 7 testes ([`test_dispatch_handoff.py`](../../shopman/shop/tests/test_dispatch_handoff.py)).

Lê de `Order.data`: `customer{name,phone}`, `delivery_address_structured{route, street_number,
complement, neighborhood, city, state_code, postal_code, formatted_address,
delivery_instructions, lat/lng}`, `delivery_distance_km`, `delivery_fee_q` (ver
[data-schemas](../reference/data-schemas.md)).

O auto-fill do form (DOM/deep-link) que estava bloqueado em URL/campos ficou **obsoleto** com a
integração Machine — o despacho agora é API. O teleporte permanece como fallback de contingência
(API fora do ar, corrida não atendida com entrega própria).

---

## 4. Decisões (histórico)

1. ~~TaOn tem API?~~ **Sim** — TaOn roda sobre a Machine (Gaudium); doc Postman chegou 2026-07-07
   → virou a integração de §2.
2. Preço ao cliente = faixas/zonas; cotação Machine = custo interno no gestor (Pablo, 2026-07-07).
3. Auto-avanço: coleta→"saiu p/ entrega" e finalização→"entregue" automáticos, sem gate de
   confirmação do cliente (benchmark iFood); "como foi a entrega?" = avaliação pós-entrega,
   feature separada (`customer_rating`).
4. Falha de despacho: alerta + re-despacho manual (sem retry automático de corrida).

## Referências
- [STOREFRONT-GAPS-ACTION-PLAN](STOREFRONT-GAPS-ACTION-PLAN.md) — WP-11 (entrega), slice 3 (teleporte)
- [GO-LIVE-CREDENTIALS-MATRIX](GO-LIVE-CREDENTIALS-MATRIX.md) — §5 logística externa
- [data-schemas](../reference/data-schemas.md) — chaves de entrega em `Order.data`
- [ADR-001](../decisions/adr-001-protocol-adapter.md) · [ADR-003](../decisions/adr-003-directives-sem-celery.md)
