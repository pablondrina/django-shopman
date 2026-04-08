# ADR-009: Semântica canônica do ciclo de vida de Order

**Status:** Aceito
**Data:** 2026-04-08
**Contexto:** Auditoria de 10 incongruências entre Kernel, Framework, Gestor,
Storefront e KDS no ciclo de vida do Order

---

## Contexto

A auditoria de 2026-04-08 identificou 10 pontos onde o significado dos status
do `Order` diverge entre camadas — docstrings ambíguas, regras de negócio
vivendo na UI em vez do Kernel, labels duplicadas no Storefront, e estados
operacionalmente órfãos. Este ADR valida cada item contra o código atual
e decide o tipo de correção a aplicar.

Arquivos de referência auditados:
- `packages/omniman/shopman/ordering/models/order.py` — enum `Status`, `DEFAULT_TRANSITIONS`, docstrings
- `framework/shopman/flows.py` — `BaseFlow.on_*`, `kds.dispatch`
- `framework/shopman/services/kds.py` — `dispatch()`, idempotência
- `framework/shopman/web/views/pedidos.py` — `_ACTIVE_STATUSES`, `_is_delivery()`, `_next_status_for()`
- `framework/shopman/web/views/tracking.py` — `STATUS_LABELS`, `FULFILLMENT_STATUS_LABELS`
- `framework/shopman/templates/storefront/tracking.html` — seção "Entrega" separada

---

## Itens auditados

---

### Item 1 — `new` docstring ambíguo

**Estado atual** (`order.py:14-15`):
```python
# new: Pedido recebido, aguardando processamento
```
Em modo `immediate`, `on_commit` já chama `stock.hold`, `loyalty.redeem` e
`order.transition_status(CONFIRMED, actor="auto_confirm")` — o order permanece
`new` por microssegundos antes de ser confirmado. A docstring "aguardando
processamento" descreve um estado que na prática não existe para canais immediate.

**Veredito:** `corrigir`

**Tipo de fix:** `refatorar Kernel`

**Nome final:** `new` (valor preservado)

**WP responsável:** ST1

**Justificativa:** A docstring cria expectativa falsa de que `new` é um estado
operacional de espera. O estado correto é "pedido criado pelo sistema, flow de
on_commit ainda não completou ou aguarda confirmação manual/otimista". O fix
é reescrever a docstring para descrever o estado real, distinguindo os três
modos (immediate/optimistic/pessimistic). Impacto: somente docstring — zero
impacto em código de negócio, testes ou queries.

---

### Item 2 — `processing` docstring diz "produção"

**Estado atual** (`order.py:18`):
```python
# processing: Em preparação/produção
```
O label TextChoices (`order.py:29`) já está correto: `_("em preparo")`.
`BaseFlow.on_processing()` (`flows.py:141-144`) chama `kds.dispatch(order)` e
notifica — isso é **montagem de pedido** no KDS, não produção em lote via
WorkOrder (regra `feedback_production_vs_sales`).

**Veredito:** `corrigir`

**Tipo de fix:** `refatorar Kernel`

**Nome final:** `processing` (ver também Item 9 — rename em ST1)

**WP responsável:** ST1

**Justificativa:** "/produção" contamina a docstring com semântica de WorkOrder.
WorkOrders são produção em lote antecipada (dias antes). KDS Prep é montagem
do pedido (minutos após `processing`). A confusão pode levar futuras mudanças
a disparar WorkOrders de pedidos — gambiarra categórica. Fix: reescrever
docstring descrevendo: "pedido em montagem na cozinha; KDS tickets ativos;
não confundir com produção em lote (WorkOrder)".

---

### Item 3 — `ready` ambíguo: balcão vs aguardando motoboy

**Estado atual:**
- `order.py:19`: docstring "Pronto para retirada/despacho" — reconhece a ambiguidade
- `tracking.py:23`: `STATUS_LABELS["ready"] = "Pronto"` — label único para os dois contextos
- `order_status.html`: badge mostra "Pronto" sem contexto de fulfillment
- `pedidos.py:74-78`: `_next_label_for()` JÁ diferencia: delivery mostra "Saiu para Entrega ▸"

**Veredito:** `corrigir`

**Tipo de fix:** `refatorar UI`

**Nome final:** `ready` (valor preservado; fix é na camada de apresentação)

**WP responsável:** ST5

**Justificativa:** O status `ready` é semanticamente correto e único — o pedido
foi produzido e aguarda a próxima etapa. O problema está no label
customer-facing idêntico para dois contextos operacionais distintos. O fix é
no Storefront: `_build_tracking_context` e `order_status.html` devem
mostrar "Pronto para retirada" (pickup) ou "Aguardando motoboy" (delivery)
usando `fulfillment_type` de `order.data`. O Kernel não muda.

---

### Item 4 — `dispatched` enforced só na UI

**Estado atual:**
- `order.py:52`: `Status.READY: [Status.DISPATCHED, Status.COMPLETED]` — modelo
  permite `ready → dispatched` para QUALQUER pedido, pickup ou delivery
- Enforcement vive em `pedidos.py:58-71`: `_is_delivery()` checa
  `order.data.get("delivery_method")` (chave legada) e `_next_status_for()`
  roteia `ready → dispatched` apenas para delivery
- **Bug adicional:** `_is_delivery()` lê `"delivery_method"` mas a chave
  canônica é `"fulfillment_type"` (ver `data-schemas.md:19`). Pickup via
  storefront padrão tem `fulfillment_type = "pickup"`, nunca `delivery_method`

**Veredito:** `corrigir`

**Tipo de fix:** `enforcement`

**WP responsável:** ST2

**Justificativa:** A regra "dispatched só delivery" é invariante de domínio, não
detalhe de UI. Via admin ou API, um pedido pickup pode hoje transitionar para
`dispatched` silenciosamente. O fix é mover o guard para
`Order.transition_status()`: antes de permitir `ready → dispatched`, verificar
`order.data.get("fulfillment_type") == "delivery"` (com fallback a
`"delivery_method"`). Levantar `InvalidTransition` se violado. Após o fix em
ST2, remover a lógica de delivery check de `pedidos.py` (apenas puro lookup
de `NEXT_STATUS_MAP`).

---

### Item 5 — `delivered` fora de `_ACTIVE_STATUSES` com `next_action` definida

**Estado atual** (`pedidos.py:82`):
```python
_ACTIVE_STATUSES = ["new", "confirmed", "processing", "ready", "dispatched"]
```
`NEXT_ACTION_LABELS["delivered"] = "Concluir ✓"` (`pedidos.py:50`) e
`can_advance` inclui `"delivered"` (`pedidos.py:149`) — mas o gestor nunca
lista pedidos `delivered` porque estão fora de `_ACTIVE_STATUSES`.

O commit `0f2d745` adicionou `dispatched` à lista, mas `delivered` permanece
ausente. Pedidos delivery que chegam a `delivered` somem do gestor sem caminho
operacional para `completed`.

**Veredito:** `corrigir`

**Tipo de fix:** `refatorar UI`

**WP responsável:** ST4

**Justificativa:** O Kernel define `delivered → completed` como transição válida
(`order.py:54`) e `on_delivered` envia notificação ao cliente. Mas sem
`delivered` na fila do gestor, o operador não pode concluir o pedido —
loyalty points e fiscal não são disparados (`on_completed` nunca é chamado).
Fix: adicionar `"delivered"` a `_ACTIVE_STATUSES` em `pedidos.py`.

---

### Item 6 — `delivered` e `completed` indistinguíveis para o cliente

**Estado atual** (`tracking.py:25-27`, `STATUS_COLORS:37-38`):
```python
"delivered": "Entregue",   # bg-success-light
"completed": "Concluído",  # bg-success-light
```
Ambos verdes, semânticamente sobrepostos para o cliente. A diferença real
(loyalty earn + fiscal emit em `on_completed`) é invisível no Storefront.
Para um pedido delivery, o cliente vê "Entregue" → depois "Concluído" — dois
estados que do ponto de vista do cliente são o mesmo evento.

**Veredito:** `corrigir`

**Tipo de fix:** `refatorar UI`

**WP responsável:** ST5

**Justificativa:** O cliente não precisa saber sobre `completed` — é um status
interno de fechamento fiscal/loyalty. O Storefront deve mostrar "Entregue"
como estado final para o cliente (tanto `delivered` quanto `completed` rendem
o mesmo label "Entregue"). O status `completed` permanece no Kernel para fins
operacionais; apenas a apresentação no tracking muda. Não há
split/merge de status — apenas um ajuste de label no `_build_tracking_context`.

---

### Item 7 — `Order.status` × `Fulfillment.status` duplicados no Storefront

**Estado atual:**
- `tracking.html:29-59`: seção "Entrega" exibe `ful.status_label` (via
  `FULFILLMENT_STATUS_LABELS`, `tracking.py:43-49`)
- `order_status.html:2-6`: badge principal exibe `status_label` (via
  `STATUS_LABELS`, `tracking.py:19-29`)
- Para um pedido delivery em `dispatched`: badge mostra "Saiu para entrega"
  E a seção "Entrega" mostra "Saiu para entrega" (Fulfillment status)
- Dois blocos exibindo semanticamente a mesma informação sem enforcement
  de sincronismo entre `Order.status` e `Fulfillment.status`

**Veredito:** `corrigir`

**Tipo de fix:** `dedupe`

**WP responsável:** ST5

**Justificativa:** A duplicação existe porque `Order.status` e
`Fulfillment.status` são modelos separados com lifecycles independentes. A
fonte da verdade para o cliente é `Order.status`. A seção "Entrega" deve
mostrar apenas detalhes logísticos (transportadora, código de rastreio,
timestamps) — não o status repetido. Fix: remover o badge de status da seção
"Entrega"; manter apenas tracking_code, carrier e timestamps quando presentes.
A timeline única em `order_status.html` é suficiente para mostrar o progresso.

---

### Item 8 — `returned` terminal no negócio, não no Kernel

**Estado atual:**
- `order.py:55`: `Status.RETURNED: [Status.COMPLETED]` — Kernel permite
  `returned → completed`
- `order.py:60`: `TERMINAL_STATUSES = [Status.COMPLETED, Status.CANCELLED]` —
  `returned` NÃO é terminal
- Gestor não inclui `returned` em `_ACTIVE_STATUSES`; devolução só via admin
- `BaseFlow.on_returned()` (`flows.py:170-175`) já executa o ciclo completo:
  `stock.revert` + `payment.refund` + `fiscal.cancel` + `notification.send`

Semanticamente, um pedido devolvido é um pedido finalizado negativamente.
`completed` implica sucesso; `returned → completed` causaria disparo de
`loyalty.earn` e `fiscal.emit` sobre um pedido já revertido.

**Veredito:** `corrigir`

**Tipo de fix:** `refatorar Kernel`

**WP responsável:** ST1

**Justificativa:** `returned` deve ser terminal. A transição `returned →
completed` é semanticamente incorreta: `on_completed` emite NFCe e acumula
loyalty — operações que não fazem sentido após devolução. O fix é: (1) remover
`returned → completed` de `DEFAULT_TRANSITIONS`; (2) adicionar `returned` a
`TERMINAL_STATUSES`. O gestor não precisa de UI para `returned` — a operação
de devolução permanece no admin (ReturnService já existe).

---

### Item 9 — `processing` carrega jargão técnico

**Estado atual** (`order.py:29`):
```python
PROCESSING = "processing", _("em preparo")
```
O valor string `"processing"` é o único gerúndio no enum; todos os outros são
adjetivos ou particípios passados (`new`, `confirmed`, `ready`, `dispatched`,
`delivered`, `completed`, `cancelled`, `returned`). "processing" carrega
semântica de processamento de dados/sistema, não de preparo culinário.
O label `_("em preparo")` está correto; o valor do enum está desalinhado.

**Veredito:** `corrigir`

**Tipo de fix:** `renomear`

**Nome final:** `preparing`

**WP responsável:** ST1

**Justificativa:** "preparing" descreve o estado operacional com precisão ("o
pedido está sendo preparado"), não carrega conotação técnica de sistema, e
alinha com o label "em preparo". É o rename de maior impacto cross-layer do
plano — toca DB values, todos os templates, testes, handlers, JSON em
session/order.data, `NEXT_STATUS_MAP`, `_ACTIVE_STATUSES`, `STATUS_LABELS`.
ST1 deve fazer grep amplo e substituir TUDO. Zero residuals: nenhum alias
`processing = "preparing"`, nenhum comentário `# formerly processing`.

**Schemas impactados:** `Channel.config.pipeline.on_processing` (chave de
configuração) deve ser renomeada para `on_preparing` em ST1 — documentar
em `data-schemas.md` e atualizar `ChannelConfig` dataclass.

---

### Item 10 — KDS não reage a rollback/cancelamento de `Order.status`

**Estado atual:**
- `services/kds.py:37`: idempotência implementada — `if KDSTicket.objects.filter(order=order).exists(): return []`
- Commit `0f2d745` removeu a chamada duplicada de `dispatch_to_kds` do gestor;
  `BaseFlow.on_processing()` é agora a única origem de dispatch
- `BaseFlow.on_cancelled()` (`flows.py:164-168`): chama `stock.release`,
  `payment.refund`, `notification.send` — mas NÃO cancela KDSTickets
- `DEFAULT_TRANSITIONS` (`order.py:51`): `PROCESSING → [READY, CANCELLED]` —
  não há rollback para `confirmed` mas há cancelamento enquanto tickets ativos

Resultado: um pedido cancelado no estado `processing` deixa KDSTickets abertos
na tela da cozinha. Operador pode marcar ticket como "done" mesmo após
cancelamento.

**Veredito:** `corrigir`

**Tipo de fix:** `refatorar Kernel` (no Framework — `flows.py` e/ou
`services/kds.py`)

**WP responsável:** ST3

**Justificativa:** Tickets KDS órfãos após cancelamento são ruído operacional
real: a cozinha produz itens de um pedido já cancelado. O fix em ST3 é
adicionar em `BaseFlow.on_cancelled()` uma chamada a `kds.cancel_tickets(order)`
que muda todos os `KDSTicket` do pedido de status `open` para `cancelled`.
A idempotência já garante que re-dispatch não cria duplicatas. A decisão de
bridge é: KDS é **reativo a Order.status** — cria tickets quando `processing`,
cancela quando `cancelled`. Documentar no docstring de `services/kds.py`.

---

## Decisão — tabela resumida

| # | Veredito | Tipo de fix | Nome final | WP |
|---|----------|-------------|------------|----|
| 1 | corrigir | refatorar Kernel | `new` (docstring) | ST1 |
| 2 | corrigir | refatorar Kernel | `preparing` (docstring; ver #9) | ST1 |
| 3 | corrigir | refatorar UI | `ready` (label contextual no Storefront) | ST5 |
| 4 | corrigir | enforcement | `dispatched` (guard no Kernel + chave canônica `fulfillment_type`) | ST2 |
| 5 | corrigir | refatorar UI | `delivered` em `_ACTIVE_STATUSES` | ST4 |
| 6 | corrigir | refatorar UI | `completed` invisível ao cliente | ST5 |
| 7 | corrigir | dedupe | Fulfillment section sem badge de status | ST5 |
| 8 | corrigir | refatorar Kernel | `returned` terminal, remover `returned→completed` | ST1 |
| 9 | corrigir | renomear | `processing` → `preparing` | ST1 |
| 10 | corrigir | refatorar Kernel | `kds.cancel_tickets()` em `on_cancelled` | ST3 |

---

## Consequencias

### Positivas

- **Semântica canônica única:** cada status tem um significado inequívoco
  documentado no modelo; futuras extensões partem de base sólida
- **Invariantes no Kernel:** a regra "dispatched só delivery" migra para o
  único lugar que todas as camadas respeitam — o modelo
- **KDS confiável:** tickets nunca ficam órfãos; operador vê apenas pedidos ativos
- **Storefront sem duplicação:** cliente recebe informação clara, não redundante

### Negativas

- **Item 9 é o rename de maior impacto do projeto:** `processing → preparing`
  toca cada arquivo que referencia o status. Requer execução cuidadosa em ST1
  com grep amplo e revisão de todos os testes
- **Item 4 (enforcement) pode revelar dados históricos incorretos:** orders
  antigas com `fulfillment_type` vazio ou `delivery_method` como chave
  alternativa precisam de tratamento gracioso no guard (não levantar exceção
  para orders antigas, apenas para novas transições)

### Mitigacoes

- ST1 executa renomes em sessão dedicada com `make test` ao final —
  qualquer quebra é identificada e corrigida antes de merge
- O guard do Item 4 usa `order.data.get("fulfillment_type") == "delivery" or
  order.data.get("delivery_method") == "delivery"` para compatibilidade
  com dados históricos (pedidos que usam a chave legada)
- Nenhum item requer migração de banco — status são `CharField` com
  `choices`; o rename é no código Python + enum value string

---

## Notas de implementacao para WP-ST1

O WP-ST1 deve executar os itens 1, 2, 8 e 9 nesta ordem:

1. **Item 8 primeiro** (mais seguro): tornar `returned` terminal — menos código
   tocado, bom aquecimento
2. **Itens 1 e 2**: reescrever docstrings — zero risco de quebra
3. **Item 9** (maior esforço): renomear `processing → preparing`:
   - Trocar valor do enum: `PREPARING = "preparing", _("em preparo")`
   - Grep por: `"processing"`, `'processing'`, `status="processing"`,
     `Status.PROCESSING`, `STATUS_PROCESSING`, `on_processing`, `order_processing`
   - Renomear `Channel.config.pipeline.on_processing → on_preparing`
   - Atualizar `data-schemas.md` (chave `on_processing` em `Channel.config`)
   - Atualizar `ChannelConfig` dataclass (`config.py`)
   - Atualizar `STATUS_LABELS`, `STATUS_COLORS`, `NEXT_STATUS_MAP`,
     `_ACTIVE_STATUSES`, `NEXT_ACTION_LABELS`, `EVENT_LABELS`
   - Atualizar todos os templates que referenciam `order.status == "processing"`
   - Atualizar todos os testes
