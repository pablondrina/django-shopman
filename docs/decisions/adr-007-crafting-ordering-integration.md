# ADR-007: Integracao Crafting ↔ Ordering

**Status:** Accepted (implementado em WP-S9)
**Data:** 2026-03-24
**Contexto:** Conectar o ciclo de producao (Crafting) ao ciclo de pedidos (Ordering)

---

## Contexto

O Crafting core esta completo (plan/adjust/close/void + suggest/needs/expected) e ja integra
com Stocking via signal `production_changed`. O Stocking ja tem o conceito de hold de demanda
(hold sem quant vinculado) e `realize()` que materializa producao planejada.

**O que ja existe e funciona:**
- `StockHoldHandler` cria holds de demanda quando `session.data["delivery_date"]` e futuro
- `on_holds_materialized` auto-comita sessions quando holds planejados materializam
- `confirmation_hooks.on_order_created` dispara pagamento apos commit
- `craft.suggest()` usa `committed()` do DemandBackend para incluir encomendas no calculo
- `CraftingProductionBackend` no Stocking permite solicitar producao automaticamente

**O que nao existe:**
- Conexao entre producao planejada e "fermata" de pedidos antecipados
- Verificacao de disponibilidade em producao planejada (descontando margem de seguranca)
- Trigger de pagamento apos materializacao de estoque

---

## Modelo de Negocio Real

A padaria opera com **producao na vespera**, validade 0, variedade regular diaria.

### Conceito-chave: Encomenda = pedido antecipado/agendado

Nao sao bolos sob medida. Sao os **mesmos produtos regulares** (paes, croissants),
mas o cliente pede com antecedencia. Uma encomenda de "50 croissants para sexta"
e identica a comprar 50 croissants no balcao — so muda o TIMING.

### Timeline de um dia

```
Vespera (17h):
  Operador abre tela de sugestoes
  craft.suggest(amanha) calcula:
    demanda_historica + encomendas_comprometidas + margem_seguranca
  Operador aprova → craft.plan() para cada variedade
  → production_changed(planned) → Stocking cria Quants planejados

Madrugada (04h):
  Producao inicia

Manha (06h):
  craft.close(wo, produced=N)
  → production_changed(closed) → Stocking realize()
  → holds_materialized signal dispara
  → Sessions com holds planejados auto-comitam (on_holds_materialized)
  → Orders criados → pagamento dispara (PIX QR / card intent)

Dia (07h-19h):
  Vendas normais sobre estoque fisico materializado
  Novos pedidos antecipados para D+1, D+2, etc.
```

### Tres fases temporais de um pedido

| Fase | Quando | Estoque | Pedido e... |
|------|--------|---------|-------------|
| **Pre-planejamento** | Antes do operador planejar | Nenhum | Intencao → alimenta `suggest()` via `committed()` |
| **Pos-planejamento, pre-materializacao** | Produzindo | Planejado (Quant com target_date) | Hold de demanda → "fermata" (session open, aguardando) |
| **Pos-materializacao** | Estoque fisico na vitrine | Fisico (Quant sem target_date) | Hold materializa → auto-commit → pagamento → entrega |

---

## A Fermata

A "fermata" e o periodo em que a Session **fica parada** esperando a producao materializar:

```
Cliente pede 10 croissants para amanha (session com delivery_date)
  → StockHoldHandler cria hold de demanda (is_planned=True)
  → Session fica OPEN com has_planned_holds=True
  → [FERMATA — session aguarda]

Producao fecha na manha seguinte:
  → craft.close() → realize() → holds_materialized
  → on_holds_materialized verifica:
      todos os holds planejados dessa session viraram fisicos?
      SIM → auto-commit session → Order criado
  → confirmation_hooks.on_order_created:
      PIX: gera QR code agora, aguarda pagamento com timeout
      Cartao: captura Intent pre-autorizado
  → Pagamento confirmado → stock.commit → pronto para retirada/entrega
```

**Isso ja esta implementado em:**
- `channels/handlers/stock.py:StockHoldHandler` (cria hold com target_date)
- `channels/handlers/_stock_receivers.py:on_holds_materialized` (auto-commit)
- `channels/confirmation_hooks.py` (dispara pagamento)

---

## Decisao

### Principio: O Crafting NAO depende do Ordering

Toda integracao fica no App layer. O Crafting core nao importa nada do Ordering.

### O que falta implementar

#### 1. Disponibilidade em producao planejada (CRITICO) — Implementado em WP-S9

`StockingBackend.check_availability()` agora aceita `safety_margin` e o subtrai do
available quando `target_date` e futuro. `StockHoldHandler` passa a margem do canal
via `get_safety_margin()` de `channels/confirmation.py`.

#### 2. Encomendas como input do suggest() (JA FUNCIONA)

`OmnimanDemandBackend.committed()` ja consulta holds ativos no Stocking.
Quando o operador roda `craft.suggest(sexta)`, as encomendas ja estao contabilizadas
no calculo de demanda.

**Nenhuma mudanca necessaria.**

#### 3. Cancelamento de pedido com holds de demanda — Implementado em WP-S9

`_on_cancelled()` em `confirmation_hooks.py` agora chama
`backend.release_holds_for_reference(session_key)` antes da notificacao.

#### 4. Preparos (sanduiches, cafes) — DECISAO PENDENTE

Produtos montados na hora com ingredientes do estoque. Duas opcoes:

| Opcao | Mecanismo | Pros | Contras |
|-------|-----------|------|---------|
| **BOM consumption** | Recipe lookup → `stock.issue()` por ingrediente | Simples, sem WO | Sem historico formal |
| **WO instantaneo** | `craft.plan() + craft.close()` atomico | Rastreabilidade completa | Overhead por item |

**Recomendacao:** Comecar com BOM consumption direto.
O Crafting ja tem `craft.needs()` para explosao de BOM. Basta consumir os
ingredientes via `stock.issue()` sem criar WO.

**Implementacao futura:** Novo handler `ingredient.consume` no App layer.

---

## Onde vive cada coisa

| Componente | Camada | Status |
|------------|--------|--------|
| `craft.suggest/plan/close/void` | Core (Crafting) | Existe |
| `production_changed` signal | Core (Crafting) | Existe |
| Stocking handlers (plan→quant, realize) | Core (Crafting contrib) | Existe |
| `holds_materialized` signal | Core (Stocking) | Existe |
| `StockHoldHandler` (hold de demanda) | App (channels/handlers/) | Existe |
| `on_holds_materialized` (auto-commit) | App (channels/handlers/) | Existe |
| `confirmation_hooks` (pagamento) | App (channels/) | Existe |
| Verificacao de disponibilidade planejada | App (channels/backends/) | Implementado (WP-S9) |
| Release de holds no cancelamento | App (channels/) | Implementado (WP-S9) |
| Receiver `production_changed` (voided) | App (channels/handlers/) | Implementado (WP-S9) |
| `ingredient.consume` handler | App (channels/handlers/) | **Futuro** |

---

## Fluxo Nelson (Padaria Demo)

### Cenario 1: Venda normal (estoque fisico)

```
Maria entra no site as 10h, pede 3 croissants
  → stock.hold(3, "croissant", None) — hold em estoque fisico
  → Session comita imediatamente (sem fermata)
  → Order criado → auto-confirm → PIX QR code
  → Maria paga → stock.commit → "Retire na loja"
```

### Cenario 2: Encomenda antecipada (pre-planejamento)

```
Joao liga na quarta pedindo 50 croissants para sexta
  → Session com delivery_date=sexta
  → stock.hold(50, "croissant", sexta) — hold de demanda (sem quant)
  → Session fica OPEN [FERMATA]

Quinta 17h: operador planeja
  → craft.suggest(sexta) inclui 50 do Joao via committed()
  → Operador aprova 120 croissants (50 Joao + 50 historico + 20 margem)
  → craft.plan(receita_croissant, 120, sexta)
  → Stocking cria Quant planejado (120, target_date=sexta)
  → Hold do Joao vincula ao Quant planejado

Sexta 06h: producao fecha
  → craft.close(wo, produced=118)
  → realize(croissant, sexta, 118, vitrine)
  → holds_materialized → Session do Joao auto-comita
  → Order criado → PIX QR gerado → notificacao pro Joao
  → Joao paga → "Retire na loja a partir das 07h"
```

### Cenario 3: Encomenda tardia (pos-planejamento)

```
Ana pede 10 croissants para sexta, quinta as 20h (apos planejamento)
  → stock.hold(10, "croissant", sexta) — verifica Quant planejado
  → Planejado: 120, ja reservado: 50, margem: 16
  → Disponivel: 120 - 50 - 16 = 54 — OK, cria hold
  → Session fica OPEN [FERMATA]
  → Sexta 06h: materializacao → mesmo fluxo do cenario 2
```

### Cenario 4: Encomenda tardia SEM disponibilidade

```
Carlos pede 60 croissants para sexta, quinta as 22h
  → Disponivel: 54 — INSUFICIENTE
  → Issue: stock.insufficient (60 pedidos, 54 disponiveis)
  → Opcoes: ajustar para 54, ou remover item
```

---

## Decisoes Pendentes

1. **Preparos:** BOM consumption direto vs WO instantaneo
   - Recomendacao: comecar sem (fase futura), quando necessario usar BOM consumption

2. **Recipe resolver:** Como mapear SKU vendavel → Recipe?
   - `Recipe.output_ref` ja usa SKU como referencia — resolver trivial
   - Nao precisa de tabela separada

3. **UI de programacao diaria:** Admin view customizada
   - Fora do escopo deste ADR

4. **Producao parcial:** Se produced < quantity?
   - realize() ja transfere holds FIFO ate esgotar
   - Holds nao atendidos permanecem como demanda
   - Operador pode replanejar (`craft.adjust` ou novo `craft.plan`)

5. **Timeout da fermata:** Implementado em WP-S9
   - Holds planejados recebem TTL de `planned_hold_ttl_hours` (default: 48h)
   - Receiver `on_production_voided` libera holds e notifica sessions quando producao e cancelada

---

## Consequencias

### Positivas
- **90% do fluxo ja esta implementado** — fermata, auto-commit, pagamento pos-materializacao
- Crafting core permanece 100% agnostico (zero imports de Ordering)
- `suggest()` ja incorpora encomendas via `committed()` do DemandBackend
- Hold de demanda + realize() + holds_materialized ja existem
- Apenas gaps pontuais a corrigir (disponibilidade planejada, release no cancel)

### Negativas
- Verificacao de disponibilidade em estoque planejado precisa de logica de margem
- "Preparos" ainda indefinidos
- Fermata pode confundir clientes se nao houver UX clara ("seu pedido aguarda producao")

### Riscos
- Session pendurada: hold planejado sem materializacao → TTL + alerta
- Producao insuficiente: realize() com menos que planned → holds parciais → operador decide
- Concorrencia: multiplas encomendas disputando estoque planejado → holds sao atomicos (OK)
