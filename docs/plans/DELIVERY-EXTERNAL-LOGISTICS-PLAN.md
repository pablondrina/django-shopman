# DELIVERY-EXTERNAL-LOGISTICS-PLAN — Despacho via serviço externo (TaOn / Taxi Machine)

> Entrega via logística externa de terceiros. Decisão Pablo (2026-06-29): **planejar agora,
> construir o adapter completo depois**; entregar **já** o stopgap "teleporte" (clipboard).
> Hoje a entrega é **própria** (`DeliveryDistanceBand` + `DeliveryZone`) + **retirada** — não
> há nenhuma chamada a logística externa no código.

---

## 1. Duas camadas, dois tempos

| Camada | O que é | Quando | Estado |
|---|---|---|---|
| **Teleporte (stopgap)** | Utilitário local que leva os dados de entrega do pedido para o form do serviço (sem API). | **Agora** | ✅ slice clipboard entregue (2026-06-29) |
| **Adapter de logística** | Integração first-class (despacho async + status do entregador) quando/se o serviço expuser API. | Pós-v1, sob decisão | 🔵 desenho abaixo |

O serviço usado hoje (TaOn / Taxi Machine) **não tem API pública conhecida**. Enquanto for assim,
a única integração possível é o teleporte. O adapter só faz sentido com API real — e, por
[ADR-001](../decisions/adr-001-protocol-adapter.md), só se cria seam plugável com **impl real**,
nunca "para o futuro".

---

## 2. Teleporte — entregue (slice clipboard)

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

### Próximo slice do teleporte (bloqueado no Pablo)
- **Auto-fill do form** (DOM via Playwright/autotype **ou** deep-link com query params). **Precisa
  de você**: URL do serviço + nomes/seletores dos campos. O `--json` já é o contrato de entrada
  do filler — quando os campos chegarem, o filler mapeia esse dict → form, sem mexer no resto.

---

## 3. Adapter de logística (desenho — não construído)

Quando/se TaOn (ou outro) expuser API, a integração segue os padrões do projeto:

- **Despacho = Directive async** ([ADR-003](../decisions/adr-003-directives-sem-celery.md)): no
  fulfillment de entrega, emitir `dispatch.request` com o payload estruturado (o mesmo de §2).
  Retry/idempotência nativos da Directive cobrem a chamada de rede ao courier.
- **Adapter swappable** ([ADR-001](../decisions/adr-001-protocol-adapter.md)): `delivery_courier`
  resolvido por settings (`SHOPMAN_COURIER_ADAPTER`), com Protocol `CourierBackend.dispatch(payload)
  -> CourierResult{tracking_ref, status}`. Criar o seam **só com impl real** (TaOn) — não antes.
- **Status do entregador = webhook**: se o courier faz callback, novo handler em
  `shopman/shop/webhooks/` (token-gated como os demais — ver `checks.py` `SHOPMAN_E004`),
  atualizando o tracking do pedido. Se não há callback, status fica manual (operador marca
  "saiu para entrega"/"entregue").
- **Credenciais**: entrar na [matriz por fase](GO-LIVE-CREDENTIALS-MATRIX.md) quando existirem
  (`COURIER_API_*` / `COURIER_WEBHOOK_TOKEN`).

**Não fazer antes da hora** (lição do `InventoryProtocol` morto, ver CLAUDE.md): nada de Protocol
de courier dormente sem TaOn real respondendo.

---

## 4. Decisão pendente do Pablo

1. **TaOn tem API?** Se sim, traz a doc → vira o adapter de §3. Se não, fica no teleporte.
2. **URL + campos do form do serviço** → destrava o auto-fill do teleporte (§2).
3. **v1 lança com teleporte (manual) ou exige adapter?** Default assumido: **v1 = teleporte**;
   adapter é pós-v1.

## Referências
- [STOREFRONT-GAPS-ACTION-PLAN](STOREFRONT-GAPS-ACTION-PLAN.md) — WP-11 (entrega), slice 3 (teleporte)
- [GO-LIVE-CREDENTIALS-MATRIX](GO-LIVE-CREDENTIALS-MATRIX.md) — §5 logística externa
- [data-schemas](../reference/data-schemas.md) — chaves de entrega em `Order.data`
- [ADR-001](../decisions/adr-001-protocol-adapter.md) · [ADR-003](../decisions/adr-003-directives-sem-celery.md)
