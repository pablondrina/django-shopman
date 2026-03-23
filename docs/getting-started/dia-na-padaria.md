# Um Dia na Padaria — Tutorial Narrativo

> **O que e isto?** Uma narrativa cronologica de um dia na **Nelson Boulangerie**, de 05:30 as 20:00.
> Cada momento aponta para o codigo real — metodo, parametros, retorno.
> Compreensivel por quem nunca viu o projeto, mas tecnicamente preciso.

## Os personagens

| Persona | Papel | Apps que usa |
|---------|-------|-------------|
| **Pierre** | Padeiro-chefe, responsavel pela producao | crafting, stocking |
| **Etienne** | Gerente de estoque e compras | stocking |
| **Nice** | Agente IA de atendimento (WhatsApp) | ordering, offering, attending |
| **Operador** | Caixa do balcao / atendente | ordering (admin), POS |
| **Anais** | Gestora financeira e estrategia | Todos (read) |

## Dados do seed

Este tutorial assume que `make seed` foi executado (comando `seed_nelson`). Os dados mencionados (SKUs, clientes, receitas) sao os que o seed cria.

---

## 05:30 — Pierre abre o admin

Pierre acessa http://localhost:8000/admin/. O dashboard mostra:

- **Producao hoje:** work orders abertas e fechadas
- **Alertas de estoque:** produtos abaixo do minimo
- **Pedidos novos:** sessoes aguardando acao

---

## 06:00 — Pierre consulta sugestoes de producao

Pierre quer saber o que produzir hoje. O sistema analisa vendas passadas e sugere quantidades.

**Codigo:** `shopman-core/crafting/shopman/crafting/services/queries.py`

```python
from shopman.crafting.services.queries import CraftQueries

suggestions = CraftQueries.suggest(date=date.today())
```

**O que acontece internamente:**

1. Busca todas as receitas ativas (`Recipe.objects.filter(is_active=True)`)
2. Para cada receita, consulta o `DEMAND_BACKEND` (protocolo `DemandProtocol`):
   - `backend.history(output_ref, days=28, same_weekday=True)` — historico de vendas
   - `backend.committed(output_ref, date)` — holds ativos no stocking
3. Calcula demanda media:
   - Se o produto esgotou cedo (tem `soldout_at`), extrapola a demanda real (caps em 2x)
4. Aplica safety stock: `quantity = (avg_demand + committed) x (1 + SAFETY_STOCK_PERCENT)`

**Retorno:** `list[Suggestion]` — cada item tem `recipe`, `quantity` (Decimal) e `basis` (dict com avg_demand, committed, safety_pct, sample_size).

**Config via settings:**

```python
# shopman-core/crafting/shopman/crafting/conf.py
CRAFTING = {
    "DEMAND_BACKEND": "shopman.crafting.contrib.demand.backend.OrderingDemandBackend",
    "SAFETY_STOCK_PERCENT": 0.10,  # 10% margem
    "HISTORICAL_DAYS": 28,
    "SAME_WEEKDAY_ONLY": True,
}
```

---

## 06:05 — Pierre planeja producao

Com as sugestoes em maos, Pierre cria ordens de producao.

**Codigo:** `shopman-core/crafting/shopman/crafting/services/scheduling.py`

```python
from shopman.crafting.services.scheduling import CraftPlanning
from shopman.crafting.models import Recipe

recipe = Recipe.objects.get(code="croissant-v1")
wo = CraftPlanning.plan(recipe, quantity=48, date=date.today())
# -> WorkOrder(status="open", scheduled_date=today)
```

**O que acontece internamente (dentro de `transaction.atomic()`):**

1. Valida `quantity > 0` (senao `CraftError("INVALID_QUANTITY")`)
2. Cria `WorkOrder` com status `OPEN`
3. **Congela o BOM** no `meta._recipe_snapshot` — se a receita for editada depois, a WO usa os insumos do momento do planejamento
4. Cria `WorkOrderEvent(kind="PLANNED", seq=0)`
5. Apos commit da transacao, emite signal `production_changed`

**Modo batch:**

```python
# Planejar varios de uma vez (atomico — tudo ou nada)
wos = CraftPlanning.plan([
    (Recipe.objects.get(code="pao-frances-v1"), 100),
    (Recipe.objects.get(code="croissant-v1"), 48),
    (Recipe.objects.get(code="baguete-v1"), 40),
], date=date.today())
# -> [WorkOrder, WorkOrder, WorkOrder]
```

**Signal:** `production_changed` (em `shopman.crafting.signals`) — o stocking pode ouvir este signal para reservar ingredientes automaticamente.

---

## 06:10 — Etienne verifica estoque

Etienne verifica os alertas de estoque baixo.

**Codigo:** `shopman-core/stocking/shopman/stocking/services/alerts.py`

```python
from shopman.stocking.services.alerts import check_alerts

triggered = check_alerts()
# -> [(StockAlert<PAIN-CHOCOLAT>, Decimal("15")),
#    (StockAlert<BRIOCHE>, Decimal("10")),
#    (StockAlert<FOCACCIA>, Decimal("8")),
#    (StockAlert<CIABATTA>, Decimal("12"))]
```

**O que acontece para cada `StockAlert` ativo:**

1. Filtra `Quant` pelo SKU e posicao do alerta
2. Exclui estoque futuro (`target_date > today`)
3. Soma quantidade fisica: `Sum('_quantity')`
4. Deduz holds ativos para hoje
5. Se `available < alert.min_quantity` — alerta disparado, atualiza `last_triggered_at`

**Parametros:**
- `sku=None` — verifica todos os SKUs (default)
- `sku="CROISSANT"` — filtra por SKU especifico

**Retorno:** `list[tuple[StockAlert, Decimal]]` — tuples de (alerta, quantidade disponivel).

---

## 08:00 — Croissants saem do forno

Pierre fechou os croissants. 48 planejados, 46 sairam (2 de perda).

**Codigo:** `shopman-core/crafting/shopman/crafting/services/execution.py`

```python
from shopman.crafting.services.execution import CraftExecution
from shopman.crafting.models import WorkOrder

wo = WorkOrder.objects.get(recipe__code="croissant-v1", status="open")
wo = CraftExecution.close(wo, produced=46)
# -> WorkOrder(status="done", produced=46)
```

**Pipeline (dentro de `transaction.atomic()` com row lock):**

1. `select_for_update()` — trava a WO no banco
2. Verifica idempotencia (se `idempotency_key` fornecido)
3. Valida status = `OPEN` (senao `CraftError("TERMINAL_STATUS")`)
4. **Materializa requirements** usando BOM snapshot do planejamento:
   - Coeficiente frances: `quantity_real / batch_size` (ex: 46 / 48 = 0.958)
   - Cada insumo x coeficiente = consumo real
5. Cria `WorkOrderItem` para cada tipo:
   - `REQUIREMENT` — o que deveria consumir (do BOM)
   - `CONSUMPTION` — o que realmente consumiu
   - `OUTPUT` — producao (46 unidades)
   - `WASTE` — perda (2 unidades, calculado: `planned - produced`)
6. Atualiza WO: `status=DONE`, `produced=46`, `finished_at=now`
7. Cria `WorkOrderEvent(kind="CLOSED")`
8. Chama `InventoryProtocol` para sincronizar estoque (se configurado)
9. Emite `production_changed` signal

**Perda explicita (opcional):**

```python
CraftExecution.close(wo, produced=46, wasted=2)

# Ou com consumo explicito:
CraftExecution.close(wo, produced=46, consumed=[
    {"item_ref": "FARINHA-TRIGO", "quantity": "2.8"},
    {"item_ref": "MANTEIGA", "quantity": "1.45"},
])
```

---

## 08:05 — Estoque recebe os croissants

Apos a producao, o estoque da vitrine e atualizado.

**Codigo:** `shopman-core/stocking/shopman/stocking/services/movements.py`

```python
from shopman.stocking.services.movements import StockMovements
from shopman.stocking.models import Position

vitrine = Position.objects.get(ref="vitrine")

quant = StockMovements.receive(
    quantity=Decimal("46"),
    sku="CROISSANT",
    position=vitrine,
    reason="Producao: croissant-v1",
)
# -> Quant(sku="CROISSANT", position=vitrine, _quantity=76)
# (30 que ja tinha + 46 da producao)
```

**Pipeline (dentro de `transaction.atomic()`):**

1. Valida `quantity > 0`
2. `get_or_create` no `Quant` pela coordenada (sku, position, target_date, batch)
3. Cria `Move(delta=+46)` — movimento positivo
4. O Quant atualiza automaticamente seu `_quantity` via a criacao do Move

**Parametros opcionais:**
- `target_date` — data planejada de disponibilidade
- `batch` — identificador de lote
- `user` — usuario que executou
- `**metadata` — contexto extra no Move

**Retorno:** `Quant` atualizado.

---

## 08:15 — Cliente pede via WhatsApp (agente Nice)

Maria Santos envia mensagem no WhatsApp: "Quero 3 croissants e 2 cafes".

O agente Nice interage com a API do ordering. Primeiro, abre uma sessao:

**Codigo:** `shopman-core/ordering/shopman/ordering/services/modify.py`

```python
from shopman.ordering.services.modify import ModifyService

# Nice cria uma sessao e adiciona itens
session = ModifyService.modify_session(
    session_key="WA-a1b2c3d4",
    channel_ref="remote",
    ops=[
        {"op": "add_line", "sku": "CROISSANT", "qty": 3},
        {"op": "add_line", "sku": "CAFE-ESPRESSO", "qty": 2},
    ],
    ctx={"actor": "nice_agent"},
)
```

**Pipeline (dentro de `transaction.atomic()`):**

1. Trava sessao com `select_for_update()`
2. Valida estado (`draft`, nao `committed`/`abandoned`)
3. Valida `edit_policy` (nao pode ser `locked`)
4. Aplica operacoes sequencialmente:
   - `add_line` — cria `SessionItem` com `line_id` gerado, `sku`, `qty`, `unit_price_q`
   - Outras ops: `remove_line`, `set_qty`, `replace_sku`, `set_data`, `merge_lines`
5. Roda **modifiers** via registry (pricing, taxes, etc.)
6. Roda **validators** de stage `draft` via registry
7. Incrementa `rev` (controle de concorrencia otimista)
8. Limpa `session.data["checks"]` e `session.data["issues"]` (mudanca invalida checks anteriores)

**Retorno:** `Session` atualizada.

**Preco:** Como o canal remote tem `pricing_policy="internal"`, o preco vem do `Listing` correspondente. Croissant = R$ 6,90, Cafe = R$ 5,90.

---

## 08:16 — Operador confirma o pedido

O operador ve a sessao no admin e confirma (via `SessionAdmin` action).

**Codigo:** `shopman-core/ordering/shopman/ordering/services/commit.py`

```python
from shopman.ordering.services.commit import CommitService

result = CommitService.commit(
    session_key="WA-a1b2c3d4",
    channel_ref="remote",
    idempotency_key="commit-WA-a1b2c3d4-rev5",
    ctx={"actor": "operador"},
)
# -> {
#     "order_ref": "ORD-20260322-A1B2C3D4",
#     "order_id": 42,
#     "status": "committed",
#     "total_q": 3250,    # R$ 32,50 (3x690 + 2x590)
#     "items_count": 2,
# }
```

**Pipeline:**

1. **Idempotencia** (fora da transacao):
   - Se a chave ja foi processada (`done`), retorna resposta cacheada
   - Se esta em andamento, espera ou retorna erro
   - Se nova, marca como `in_progress`

2. **Commit atomico** (`_do_commit()` dentro de `transaction.atomic()`):
   - Trava sessao (`select_for_update`)
   - Valida: estado = draft, checks frescos, sem issues bloqueantes
   - Roda validators de stage `commit` via registry
   - Valida que sessao tem itens
   - Cria `Order` com snapshot completo (itens, data, pricing, rev)
   - Cria `OrderItem` para cada item da sessao
   - Emite signal `order_changed`
   - Marca sessao como `committed`
   - Enfileira **post-commit directives** (ex: `stock.hold`, `notification.send`)

3. **Pos-transacao:** marca idempotencia como `done`, cacheia resposta

**O que o commit dispara (via Directives):**
- `stock.hold` — reserva estoque no stocking
- `notification.send` — notifica cliente via WhatsApp (se configurado no canal)

---

## 08:17 — Estoque reservado

A directive `stock.hold` e processada. O handler `StockHoldHandler` (registrado em `shopman.inventory.apps.InventoryConfig.ready()`) cria um `Hold` para cada item do pedido via `StockBackend.create_hold()`, reservando 3 croissants e 2 cafes. Isso evita que outro pedido venda os mesmos itens.

---

## 09:00 — Pedido do balcao (POS)

Um cliente no balcao pede 2 paes franceses e 1 baguete. O operador usa o terminal PDV (POS).

O fluxo e similar: cria sessao -> adiciona itens -> commit. Mas o canal `pos` tem:
- `pricing_policy="internal"` — preco cheio do catalogo
- `edit_policy="open"` — operador pode editar livremente
- `post_commit_directives=["stock.hold", "notification.send"]` — reserva estoque e notifica

---

## 12:00 — Baguetes ficam prontas

Pierre fecha a WO de baguetes (a ultima aberta para hoje):

```python
wo_baguete = WorkOrder.objects.get(recipe__code="baguete-v1", status="open")
CraftExecution.close(wo_baguete, produced=38)
# 40 planejadas, 38 produzidas -> 2 de perda (5%)
```

O estoque da vitrine recebe +38 baguetes via `StockMovements.receive()`.

---

## 14:00 — Cafe Parisiense encomenda (at_risk!)

O Cafe Parisiense faz um pedido de encomenda: 24 croissants + 18 pain au chocolat para amanha.

O sistema de insights (attending) sabe que este cliente e **at_risk** (churn alto, muitos dias sem pedir). Um atendente atento pode notar isso no `CustomerAdmin` e oferecer atencao especial.

---

## 17:00 — Pedidos do dia concluidos

O operador avanca os ultimos pedidos para `completed` via admin (OrderAdmin -> "Avancar"). A state machine valida as transicoes:

Cada transicao cria um `OrderEvent` com `type="status_changed"` e atualiza timestamps (`confirmed_at`, `ready_at`, `completed_at`, etc.).

---

## 20:00 — Anais consulta o dia e atualiza insights

Anais revisa o dia no dashboard e dispara atualizacao dos insights RFM dos clientes.

**Codigo:** `shopman-core/attending/shopman/attending/contrib/insights/service.py`

```python
from shopman.attending.contrib.insights.service import InsightService

# Recalcular para um cliente especifico
insight = InsightService.recalculate(customer_ref="CLI-001")
# -> CustomerInsight(
#     total_orders=29, rfm_recency=5, rfm_frequency=5,
#     rfm_monetary=4, rfm_segment="champion", churn_risk=0.05
# )

# Ou recalcular todos de uma vez
count = InsightService.recalculate_all()
# -> 5 (numero de clientes atualizados)
```

**Pipeline do `recalculate()`:**

1. `get_or_create` o `CustomerInsight` para o cliente
2. Busca `OrderHistoryBackend` configurado em settings
3. Se nao ha backend — reseta metricas a zero
4. Se ha backend:
   - Calcula metricas: total_orders, total_spent_q, avg_ticket
   - Dia/horario/canal preferido
   - **RFM (1-5, onde 5 = melhor):**
     - **Recency:** 5 se <=7 dias, 4 se <=30d, 3 se <=90d, 2 se <=180d, 1 se >180d
     - **Frequency:** 5 se >=20 orders, 4 se >=10, 3 se >=5, 2 se >=2, 1 se 1
     - **Monetary:** 5 se >=R$10k, 4 se >=R$5k, 3 se >=R$2k, 2 se >=R$500, 1 se <R$500
   - **Segmentacao** (baseada em score R+F+M):
     - `champion` — score >= 13
     - `loyal_customer` — R>=4 e F>=3
     - `recent_customer` — R>=4 e F<=2
     - `at_risk` — R<=2 e F>=3
     - `lost` — R<=2 e F<=2
     - `regular` — default
   - **Churn risk:** `days_since_last_order / average_days_between`

---

## Resumo do fluxo de dados

```
                    ┌──────────────────────────┐
                    │       OFFERING            │
                    │  Products, Listings       │
                    │  Precos por canal          │
                    └──────────┬───────────────┘
                               │ sku, price_q
                               ▼
┌──────────┐    suggest    ┌──────────┐    plan     ┌──────────┐
│ DEMAND   │◄─────────────│ CRAFTING │────────────►│ WorkOrder│
│ BACKEND  │  history()    │ Queries  │             │ OPEN     │
└──────────┘               └──────────┘             └────┬─────┘
                                                         │ close(produced=46)
                                                         ▼
                                                    ┌──────────┐
                                                    │ WorkOrder│
                                                    │ DONE     │
                                                    │ +Output  │
                                                    │ +Waste   │
                                                    └────┬─────┘
                                                         │ receive()
                                                         ▼
┌──────────┐                                        ┌──────────┐
│StockAlert│◄─── check_alerts() ───────────────────│ STOCKING │
│ triggered│                                        │ Quant +46│
└──────────┘                                        │ Move +46 │
                                                    └────┬─────┘
                                                         │ hold
                                                         ▼
┌──────────┐   modify_session    ┌──────────┐  commit  ┌──────────┐
│ Nice     │───────────────────►│ Session  │────────►│ Order    │
│ Agent    │   add_line, qty     │ draft    │         │ committed│
└──────────┘                     └──────────┘         └────┬─────┘
                                                          │ Directives
                                                          ▼
                                                     stock.hold
                                                     notification.send
                                                     payment.capture

┌──────────┐   recalculate()
│ATTENDING │◄─────────────── fim do dia
│ Insights │   RFM, churn,
│ RFM/LTV  │   segmento, LTV
└──────────┘
```

---

## Proximos passos

- [quickstart.md](quickstart.md) — como rodar tudo isso localmente
- [Arquitetura](../architecture.md) — diagrama de camadas e Protocol/Adapter
- [ADRs](../decisions/) — decisoes arquiteturais
