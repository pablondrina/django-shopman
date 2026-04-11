# ADR-007: Integração Craftsman ↔ Orderman

**Status:** Implemented
**Data:** 2026-03-24
**Atualizado:** 2026-04-07
**Contexto:** Conectar o ciclo de produção (Craftsman) ao ciclo de pedidos (Orderman)

---

## Contexto

O Craftsman core está completo (plan/adjust/close/void + suggest/needs/expected) e já integra
com Stockman via signal `production_changed`. O Stockman já tem o conceito de hold de demanda
(hold sem quant vinculado) e `realize()` que materializa produção planejada.

**Implementado e funcionando:**
- `StockHoldHandler` cria holds de demanda quando `session.data["delivery_date"]` é futuro
- `on_holds_materialized` auto-comita sessions quando holds planejados materializam
- Auto-commit → Order criado → flow normal → `on_confirmed` → `payment.initiate()`
- `craft.suggest()` usa `committed()` do DemandBackend para incluir encomendas no cálculo
- Verificação de disponibilidade em produção planejada (com margem de segurança)
- Release de holds no cancelamento
- TTL de holds planejados + receiver de produção voided

**Decisão pendente:**
- Preparos (sanduíches, cafés): BOM consumption direto vs WO instantâneo

---

## Modelo de Negócio Real

A padaria opera com **produção na véspera**, validade 0, variedade regular diária.

### Conceito-chave: Encomenda = pedido antecipado/agendado

Não são bolos sob medida. São os **mesmos produtos regulares** (pães, croissants),
mas o cliente pede com antecedência. Uma encomenda de "50 croissants para sexta"
é idêntica a comprar 50 croissants no balcão — só muda o TIMING.

### Timeline de um dia

```
Véspera (17h):
  Operador abre tela de sugestões
  craft.suggest(amanhã) calcula:
    demanda_histórica + encomendas_comprometidas + margem_segurança
  Operador aprova → craft.plan() para cada variedade
  → production_changed(planned) → Stockman cria Quants planejados

Madrugada (04h):
  Produção inicia

Manhã (06h):
  craft.close(wo, produced=N)
  → production_changed(closed) → Stockman realize()
  → holds_materialized signal dispara
  → Sessions com holds planejados auto-comitam (on_holds_materialized)
  → Orders criados → flow normal → on_confirmed → payment.initiate()
  → PIX QR gerado / card intent capturado → notificação pro cliente

Dia (07h-19h):
  Vendas normais sobre estoque físico materializado
  Novos pedidos antecipados para D+1, D+2, etc.
```

### Três fases temporais de um pedido

| Fase | Quando | Estoque | Pedido é... |
|------|--------|---------|-------------|
| **Pré-planejamento** | Antes do operador planejar | Nenhum | Intenção → alimenta `suggest()` via `committed()` |
| **Pós-planejamento, pré-materialização** | Produzindo | Planejado (Quant com target_date) | Hold de demanda → "fermata" (session open, aguardando) |
| **Pós-materialização** | Estoque físico na vitrine | Físico (Quant sem target_date) | Hold materializa → auto-commit → payment → entrega |

---

## A Fermata

A "fermata" é o período em que a Session **fica parada** esperando a produção materializar:

```
Cliente pede 10 croissants para amanhã (session com delivery_date)
  → StockHoldHandler cria hold de demanda (is_planned=True)
  → Session fica OPEN com has_planned_holds=True
  → [FERMATA — session aguarda]

Produção fecha na manhã seguinte:
  → craft.close() → realize() → holds_materialized
  → on_holds_materialized verifica:
      todos os holds planejados dessa session viraram físicos?
      SIM → auto-commit session → Order criado
  → Flow normal: on_commit → on_confirmed → payment.initiate()
      PIX: gera QR code agora, aguarda pagamento com timeout
      Cartão: captura Intent pré-autorizado
  → Pagamento confirmado → stock.commit → pronto para retirada/entrega
```

**Implementado em:**
- `shopman/handlers/stock.py:StockHoldHandler` (cria hold com target_date)
- `shopman/handlers/_stock_receivers.py:on_holds_materialized` (auto-commit)
- `shopman/flows.py:on_confirmed` (dispara pagamento via flow normal)

---

## Decisão

### Princípio: O Craftsman NÃO depende do Orderman

Toda integração fica no framework (App layer). O Craftsman core não importa nada do Orderman.

### Implementação (completa)

#### 1. Disponibilidade em produção planejada (IMPLEMENTADO)

`StockingBackend.check_availability()` aceita `safety_margin` e o subtrai do
available quando `target_date` é futuro. `StockHoldHandler` passa a margem do canal
via `get_safety_margin()`.

#### 2. Encomendas como input do suggest() (IMPLEMENTADO)

`OrdermanDemandBackend.committed()` consulta holds ativos no Stockman.
Quando o operador roda `craft.suggest(sexta)`, as encomendas estão contabilizadas
no cálculo de demanda.

#### 3. Cancelamento de pedido com holds de demanda (IMPLEMENTADO)

`on_cancelled()` no flow chama `stock.release(order)` e
`backend.release_holds_for_reference(session_key)`.

#### 4. Payment timing na fermata (IMPLEMENTADO)

O auto-commit via `on_holds_materialized` cria o Order que passa pelo flow normal:
`on_commit` → confirmação imediata → CONFIRMED → `on_confirmed` → `payment.initiate()`.
O pagamento só dispara DEPOIS da materialização. Não há timing mismatch.

#### 5. Produção voided → release + notificação (IMPLEMENTADO)

Receiver `on_production_voided` libera holds planejados e notifica sessions
quando produção é cancelada. Holds planejados recebem TTL de `planned_hold_ttl_hours`.

#### 6. Preparos (sanduíches, cafés) — DECISÃO PENDENTE

Produtos montados na hora com ingredientes do estoque. Duas opções:

| Opção | Mecanismo | Prós | Contras |
|-------|-----------|------|---------|
| **BOM consumption** | Recipe lookup → `stock.issue()` por ingrediente | Simples, sem WO | Sem histórico formal |
| **WO instantâneo** | `craft.plan() + craft.close()` atômico | Rastreabilidade completa | Overhead por item |

**Recomendação:** Começar com BOM consumption direto.
O Craftsman já tem `craft.needs()` para explosão de BOM. Basta consumir os
ingredientes via `stock.issue()` sem criar WO.

**Implementação futura:** Novo handler `ingredient.consume` no framework.

---

## Onde vive cada coisa

| Componente | Camada | Status |
|------------|--------|--------|
| `craft.suggest/plan/close/void` | Core (Craftsman) | ✅ Implementado |
| `production_changed` signal | Core (Craftsman) | ✅ Implementado |
| Stockman handlers (plan→quant, realize) | Core (Craftsman contrib) | ✅ Implementado |
| `holds_materialized` signal | Core (Stockman) | ✅ Implementado |
| `StockHoldHandler` (hold de demanda) | Framework (shopman/handlers/) | ✅ Implementado |
| `on_holds_materialized` (auto-commit) | Framework (shopman/handlers/) | ✅ Implementado |
| Flow `on_confirmed` (pagamento) | Framework (shopman/flows.py) | ✅ Implementado |
| Verificação de disponibilidade planejada | Framework (shopman/backends/) | ✅ Implementado |
| Release de holds no cancelamento | Framework (shopman/flows.py) | ✅ Implementado |
| Receiver `production_changed` (voided) | Framework (shopman/handlers/) | ✅ Implementado |
| `ingredient.consume` handler | Framework (shopman/handlers/) | ⏳ Futuro |

---

## Fluxo Nelson (Padaria Demo)

### Cenário 1: Venda normal (estoque físico)

```
Maria entra no site às 10h, pede 3 croissants
  → stock.hold(3, "croissant", None) — hold em estoque físico
  → Session comita imediatamente (sem fermata)
  → Order criado → auto-confirm → PIX QR code
  → Maria paga → stock.commit → "Retire na loja"
```

### Cenário 2: Encomenda antecipada (pré-planejamento)

```
João liga na quarta pedindo 50 croissants para sexta
  → Session com delivery_date=sexta
  → stock.hold(50, "croissant", sexta) — hold de demanda (sem quant)
  → Session fica OPEN [FERMATA]

Quinta 17h: operador planeja
  → craft.suggest(sexta) inclui 50 do João via committed()
  → Operador aprova 120 croissants (50 João + 50 histórico + 20 margem)
  → craft.plan(receita_croissant, 120, sexta)
  → Stockman cria Quant planejado (120, target_date=sexta)
  → Hold do João vincula ao Quant planejado

Sexta 06h: produção fecha
  → craft.close(wo, produced=118)
  → realize(croissant, sexta, 118, vitrine)
  → holds_materialized → Session do João auto-comita
  → Order criado → flow normal → payment.initiate() → PIX QR → notificação
  → João paga → "Retire na loja a partir das 07h"
```

### Cenário 3: Encomenda tardia (pós-planejamento)

```
Ana pede 10 croissants para sexta, quinta às 20h (após planejamento)
  → stock.hold(10, "croissant", sexta) — verifica Quant planejado
  → Planejado: 120, já reservado: 50, margem: 16
  → Disponível: 120 - 50 - 16 = 54 — OK, cria hold
  → Session fica OPEN [FERMATA]
  → Sexta 06h: materialização → mesmo fluxo do cenário 2
```

### Cenário 4: Encomenda tardia SEM disponibilidade

```
Carlos pede 60 croissants para sexta, quinta às 22h
  → Disponível: 54 — INSUFICIENTE
  → Issue: stock.insufficient (60 pedidos, 54 disponíveis)
  → Alternativas sugeridas via get_alternatives()
  → Opções: ajustar para 54, ou remover item
```

---

## Decisões Resolvidas

1. **Payment timing:** Pagamento dispara via flow normal (`on_confirmed`) DEPOIS do auto-commit.
   Não há timing mismatch — o flow garante a sequência correta.

2. **Recipe resolver:** `Recipe.output_ref` já usa SKU como referência — resolver trivial.

3. **Produção parcial:** `realize()` transfere holds FIFO até esgotar.
   Holds não atendidos permanecem como demanda. Operador pode replanejar.

4. **Timeout da fermata:** Holds planejados recebem TTL de `planned_hold_ttl_hours` (default: 48h).
   Receiver `on_production_voided` libera holds e notifica sessions.

## Decisão Pendente

1. **Preparos:** BOM consumption direto vs WO instantâneo.
   Recomendação: começar sem (fase futura), quando necessário usar BOM consumption.

---

## Consequências

### Positivas
- **100% do fluxo fermata implementado** — auto-commit, pagamento pós-materialização, TTL
- Craftsman core permanece 100% agnóstico (zero imports de Orderman)
- `suggest()` incorpora encomendas via `committed()` do DemandBackend
- Hold de demanda + realize() + holds_materialized funcionam E2E
- Disponibilidade com margem de segurança para estoque planejado

### Negativas
- "Preparos" ainda indefinidos (futuro)
- Fermata pode confundir clientes se não houver UX clara ("seu pedido aguarda produção")

### Riscos
- Session pendurada: hold planejado sem materialização → TTL + alerta
- Produção insuficiente: realize() com menos que planned → holds parciais → operador decide
- Concorrência: múltiplas encomendas disputando estoque planejado → holds são atômicos (OK)
