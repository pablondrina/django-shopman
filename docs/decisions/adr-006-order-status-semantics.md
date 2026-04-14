# ADR-006: Semântica canônica do ciclo de vida de Order

**Status:** Aceito
**Data:** 2026-04-14 (consolidação)
**Supera:** auditoria de 2026-04-08

---

## Contexto

O `Order` é a entidade mais trafegada da suite — passa por orderman (criação
e transições), framework (lifecycle, KDS, fiscal, loyalty, notificações),
storefront (tracking público), admin (gestão) e API. Cada camada tende a
atribuir significado próprio aos status, gerando divergência (labels
duplicados, regras de negócio na UI em vez do core, estados órfãos).

Esta ADR fixa o vocabulário canônico: **o que cada status significa, quem
decide a transição, e quais regras são invariantes independentes da camada**.

## Decisão

### 1. Estados canônicos

Os nove estados são definidos em `packages/orderman/shopman/orderman/models/order.py`
em `Order.Status`. Essa é a fonte da verdade; as definições abaixo resumem.

| Status | Significado | Terminal |
|---|---|---|
| `new` | Pedido criado. Em canais `immediate`, estado de microssegundos antes de auto-confirmar. Em `optimistic`/`pessimistic`, aguarda operador ou timeout. | — |
| `confirmed` | Confirmado (operador ou auto-confirm). Pagamento iniciado se digital. | — |
| `preparing` | Em montagem na cozinha. KDS tickets ativos. **Não é** produção em lote (WorkOrder) — é montagem do pedido específico. | — |
| `ready` | Produzido/montado. Pickup: aguarda retirada. Delivery: aguarda motoboy. O status é único; o label customer-facing varia pelo `fulfillment_type`. | — |
| `dispatched` | Em trânsito. **Exclusivo para delivery** — pedidos pickup nunca passam por aqui. | — |
| `delivered` | Entregue ao destinatário (delivery). Aguarda fechamento fiscal/loyalty. | — |
| `completed` | Finalizado. Fiscal emitido, loyalty acumulado. Estado interno — cliente não distingue de `delivered`. | ✔ |
| `cancelled` | Cancelado antes do fechamento. Stock released, pagamento estornado se houve captura. | ✔ |
| `returned` | Devolvido após entrega. Stock revertido, reembolso efetuado. | ✔ |

### 2. Transições permitidas

`Order.DEFAULT_TRANSITIONS` é a fonte única:

```
new        → confirmed, cancelled
confirmed  → preparing, ready, cancelled
preparing  → ready, cancelled
ready      → dispatched, completed
dispatched → delivered, returned
delivered  → completed, returned
completed  → returned
cancelled  → ∅  (terminal)
returned   → ∅  (terminal)
```

Canais podem **restringir** (nunca expandir) o mapa via `ChannelConfig`.

### 3. Invariantes

- **`dispatched` é exclusivo de delivery.** Regra vive no core (via
  `ChannelConfig` + guarda em `transition_status`), não na UI. O storefront
  apenas reflete a regra.
- **`ready` tem um único valor, dois labels.** O valor de status é `ready`
  sempre. O label customer-facing (`"Pronto para retirada"` vs
  `"Aguardando motoboy"`) é derivado de `order.data["fulfillment_type"]`
  na camada de apresentação.
- **`completed` é interno.** Tracking público mostra "Entregue" tanto para
  `delivered` quanto `completed`. O cliente não precisa saber que o fiscal
  foi emitido.
- **Terminais são absolutos.** Uma vez em `cancelled` ou `returned`, nenhuma
  transição é permitida (exceto `completed → returned`, que é o caminho
  legítimo de devolução pós-fechamento).
- **A transição é atômica e auditada.** `Order.transition_status(new, actor=…)`
  valida contra `DEFAULT_TRANSITIONS`, grava o evento e é o único caminho
  para mudar status — nenhuma camada escreve `order.status = …` direto.

### 4. Responsabilidade por camada

- **Core (`orderman`)**: define enum, transições, guardas de integridade,
  método `transition_status`. Não conhece canais nem fulfillment.
- **Framework (`framework/shopman/`)**: decide *quando* transitar via
  lifecycle dispatch + `ChannelConfig`. Aplica regra "dispatched só em
  delivery". Dispara handlers de KDS, fiscal, loyalty, notificação.
- **Storefront**: deriva labels do status + `fulfillment_type`. Nunca inventa
  estados nem aplica regras de negócio próprias.
- **Admin**: mostra estado interno real (inclui `completed`, `preparing`).
- **API**: expõe o valor do status; consumidores mapeiam para labels.

## Consequências

### Positivas

- **Vocabulário único.** Qualquer camada que precise saber "em que estado
  está o pedido?" olha `Order.Status`. Labels variam; o valor não.
- **Regras centralizadas.** `dispatched`-só-delivery, auto-confirm,
  terminalidade — tudo no core + framework, testável isoladamente.
- **Storefront burro por design.** Apresentação não toma decisões de negócio.

### Negativas

- **Duplicação de labels.** Cada camada tem sua tabela de labels (admin,
  storefront, tracking público). É custo aceito — cada contexto tem
  vocabulário próprio.
- **`preparing` vs `WorkOrder` exige disciplina.** "Preparing" é montagem do
  pedido, não produção em lote. Ver `feedback_production_vs_sales`.

### Mitigações

- Testes de invariante garantem que `DEFAULT_TRANSITIONS` é respeitado em
  todos os caminhos de mutação de status.
- O guard "dispatched só em delivery" tem teste dedicado no framework.
- Labels estão em um único módulo por camada — `web/views/tracking.py`
  para storefront, `admin/orders.py` para gestão.

## Referências

- `packages/orderman/shopman/orderman/models/order.py` — enum e transições
- `docs/constitution.md` §4.4 — estados canônicos da suite
- ADR-005 — por que o framework decide *quando* transitar
- `feedback_production_vs_sales` — WorkOrder vs KDS Prep
