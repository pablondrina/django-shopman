# AVAILABILITY-PLAN — Disponibilidade, Sugestão & Alternativas

> Plano de reconstrução do fluxo de disponibilidade E2E.
> Objetivo: torná-lo absolutamente seguro, à prova de falhas, simples, robusto e elegante.

**Status**: Em análise
**Criado**: 2026-04-07

---

## Sumário Executivo

O sistema de disponibilidade é funcional no backend (Stockman é sólido), mas a
camada de apresentação (storefront) e orquestração (framework) tem problemas
sérios de semântica, restrições artificiais e vazamento de conceitos internos.

Este plano reconstrói a experiência E2E preservando o Core (packages/) e
refatorando o Framework (shopman/) e Storefront (web/templates/).

---

## Diagnóstico

### Problemas Críticos

| # | Problema | Severidade |
|---|----------|-----------|
| D1 | **D-1 visível para o cliente** — badge "Últimas unidades", preço com desconto, texto "Produzido ontem". Viola regra definida. | Crítica |
| D2 | **Badges com semântica quebrada** — `preparing`, `planned`, `d1_only` são conceitos internos expostos ao cliente. | Alta |
| D3 | **`availability_for_sku` vaza breakdown interno** — frontend consome `{ready, in_production, d1}` e toma decisões com isso. | Alta |
| D4 | **Restrições artificiais no storefront** — cutoff 18h, janela 7 dias, min qty pré-pedido. Desconexo da realidade. | Alta |
| D5 | **Alternativas descentralizadas** — cada view importa de forma diferente, sem serviço unificado. | Média |
| D6 | **`craft.suggest()` é cidadão de segunda classe** — sem sazonalidade, sem waste, soldout_at nunca populado. | Alta |
| D7 | **Banner de horário existe mas não funciona** — `_shop_status()` definido, banner no template, mas nunca wired. | Média |
| D8 | **Sem validação server-side de slots** — delivery_time_slot aceita qualquer valor. | Alta |
| D9 | **`adjust()` sem validação de insumos compartilhados** — operador pode remanejar WOs sem o sistema verificar limites de insumo. | Média |
| D10 | **Seed sem dados de demanda realistas** — soldout_at nunca populado, sem sazonalidade, sem waste. | Média |

### O Que Está Correto (Preservar)

- **Stockman Core**: Quant (coordenadas espaço-tempo), Hold lifecycle, Move (ledger imutável), shelflife. Sólido.
- **Craftsman Core**: Recipe, WorkOrder (OPEN/DONE/VOID), BOM multinível com `needs(expand=True)`, suggest() básico funcional. Sólido.
- **Offerman Core**: Product, Listing, ListingItem, CatalogService. Sólido.
- **Omniman Core**: Session→Order via CommitService, directives at-least-once, idempotency. Sólido.
- **Hold lifecycle**: PENDING→CONFIRMED→FULFILLED | RELEASED. Correto.
- **Pickup slots**: Baseados em produção histórica, bottleneck logic. Correto.
- **`find_alternatives()`**: Algoritmo de keywords + collection + score. Funcional (centralizar consumo).

---

## Decisões de Design

### DD-1: Estados de disponibilidade para o cliente

O cliente vê **no máximo 2 badges**:

| Estado | Quando | Badge | Pode comprar? |
|--------|--------|-------|---------------|
| Disponível | `available_qty > 0` para o canal/data | Nenhum (implícito) | Sim |
| Indisponível | `available_qty == 0` OR `is_paused` | Cinza "Indisponível" | Não |

**Distinção "esgotado" — se custo técnico aceitável:**

| Estado | Quando | Badge |
|--------|--------|-------|
| Esgotado | O produto **tinha** estoque para a data/canal mas foi a zero (houve estoque planejado/recebido que se esgotou) | Cinza "Esgotado" |

"Indisponível" = genérico (pode nem ter saído, pode estar pausado, pode não haver produção).
"Esgotado" = tinha mas acabou (informação relevante para o cliente).

**Regra**: D-1 NUNCA aparece para o cliente. Nem badge, nem preço, nem texto.

### DD-2: API de disponibilidade para o frontend

O storefront consome uma **visão simplificada**, não o breakdown interno:

```python
# O que o frontend recebe (via helper ou API)
{
    "available_qty": Decimal,   # qty disponível para o canal+data (já com scope)
    "can_order": bool,          # available_qty > 0 AND product.is_orderable
    "is_paused": bool,          # product.is_available = False
    "had_stock": bool,          # para distinguir "esgotado" de "indisponível"
}
```

O breakdown `{ready, in_production, d1}` continua existindo em `availability_for_sku()`
para **consumo interno** (operadores, API, dashboard). O frontend nunca o consome diretamente.

**Implementação**: Novo helper `storefront_availability(sku, channel)` que chama
`availability_for_sku()` com scope do canal e retorna a visão simplificada.

### DD-3: Encomendas sem restrições artificiais

- **Sem cutoff hour** bloqueante. O cliente encomenda a qualquer hora.
- **Janela máxima**: Configurável via `Shop.defaults["max_preorder_days"]` (default: 30).
  Editável pelo admin.
- **Sem min quantity** para pré-pedidos (remover restrição).
- **Business hours**: Informativo (banner), nunca bloqueante.
- **Calendário do shop**: `Shop.defaults["closed_dates"]` — lista de datas fechadas
  (feriados, férias coletivas). Editável pelo admin.
  Datas fechadas não aparecem como opção de entrega/retirada.

**Formato do calendário**:
```python
Shop.defaults["closed_dates"] = [
    {"date": "2026-12-25", "label": "Natal"},
    {"date": "2026-12-31", "label": "Réveillon"},
    {"from": "2026-01-15", "to": "2026-01-31", "label": "Férias coletivas"},
]
```

### DD-4: Quantidades muito grandes

Anotar para tratamento futuro. Precisa de definição de parâmetros.
Ideia inicial: `Shop.defaults["max_order_qty_per_sku"]` — se qty > limite, exigir
confirmação ou bloquear com mensagem "Para quantidades maiores, entre em contato".

> **TODO**: Definir parâmetros (média + X%? Fixo por SKU? Por canal?).

### DD-5: Alternativas — serviço centralizado

Um único ponto de consumo para todos os contextos:

```python
# framework/shopman/services/alternatives.py
def find_alternatives(sku: str, *, qty: Decimal = 1, channel: str = None, limit: int = 4) -> list[dict]:
    """
    Busca alternativas disponíveis para o canal.

    1. Offerman: find_alternatives(sku) → candidatos por keywords+collection+score
    2. Stockman: filtra por disponibilidade no canal (scope)
    3. Framework: anotação (preço, badge simplificado)

    Retorna lista rankeada de dicts prontos para template/API.
    """
```

Consumidores: PDP, carrinho, checkout, handler de stock, API — todos chamam este serviço.

### DD-6: Sazonalidade no `craft.suggest()`

**Modelo de estações** (configurável via `Shop.defaults["seasons"]`, editável pelo admin):

```python
Shop.defaults["seasons"] = {
    "hot":  [10, 11, 12, 1, 2, 3],   # Outubro a Março
    "mild": [4, 5, 9],                # Abril, Maio, Setembro
    "cold": [6, 7, 8],                # Junho a Agosto
}
```

**Fatores adicionais**:
- Véspera de feriado / fim de semana (sexta e sábado): multiplicador configurável
  via `Shop.defaults["high_demand_multiplier"]` (default: 1.2). Editável pelo admin.
- `DailyDemand.wasted`: incluir na análise (waste alto → reduzir sugestão)
- `soldout_at`: popular corretamente no backend de demanda
- Safety stock: `CRAFTING["SAFETY_STOCK_PERCENT"]` (default 0.20), expor também
  em `Shop.defaults["safety_stock_percent"]` para edição via admin.

**Confiança**: Indicação pragmática para o operador, baseada em sample_size:

| sample_size | Nível | Significado |
|-------------|-------|-------------|
| ≥ 8 | `high` | Padrão consolidado, operador pode confiar |
| 3–7 | `medium` | Razoável, mas operador deve usar julgamento |
| < 3 | `low` | Poucos dados, sugestão fraca |
| 0 | — | Sem dados, não sugere |

Não é machine learning nem estatística complexa — é "quantos dados sustentam
esta sugestão?". Aparece no dashboard e no output de `suggest_production`.

Refinamento futuro: coeficiente de variação (CV = desvio padrão / média) para
detectar instabilidade mesmo com sample_size alto. Mas sample_size já resolve
90% do problema.

**Implementação**: `suggest()` filtra histórico por estação atual (além de weekday).
Se estação atual é "hot", só considera dias históricos de meses "hot".

### DD-7: Remanejo de produção via `adjust()` — sem novo status

**Decisão**: Manter 3 estados (OPEN, DONE, VOID). Sem estado PROCESSING.

O cenário real de remanejo é: **redistribuir quantidades entre WOs OPEN que
compartilham o mesmo insumo**. Isso é `adjust()` em múltiplas WOs, não um novo
estado. KISS prevalece.

**Exemplo**:

Massa de tradição planejada: 52kg (disponível via Quant ou WO de pré-preparo).
4 WOs OPEN para a mesma data:

| WO | SKU | Planejado | Massa necessária |
|----|-----|-----------|-----------------|
| WO-1 | BAGUETTE | 20 | 10kg |
| WO-2 | BÂTARD | 20 | 12kg |
| WO-3 | FENDU | 30 | 15kg |
| WO-4 | TABATIÈRE | 30 | 15kg |
| **Total** | | **100** | **52kg** |

Chegam encomendas. Operador remaneja:

| WO | SKU | Novo | Massa | Constraint |
|----|-----|------|-------|------------|
| WO-1 | BAGUETTE | 40 | 20kg | ✅ |
| WO-2 | BÂTARD | 0 → void | 0kg | ✅ só se holds ≤ 0 para BÂTARD na data |
| WO-3 | FENDU | 50 | 25kg | ✅ |
| WO-4 | TABATIÈRE | 10 | 5kg | ✅ só se holds ≤ 10 |
| **Total** | | **100** | **50kg ≤ 52kg** | ✅ |

**3 validações no `adjust()`**:

**V1 — Holds do SKU de saída (compromissos com clientes)**:
```
Se qty_nova < holds_ativos para SKU+data → REJEITA
"Não pode reduzir TABATIÈRE para 10: há 15 unidades comprometidas"
```

**V2 — Insumos compartilhados (total não excede disponível)**:
```
Para cada insumo do BOM desta WO:
  total_necessário = soma de consumo de TODAS as WOs OPEN da data que usam este insumo
  disponível = estoque (planejado+recebido) do insumo para a data
  Se total_necessário > disponível → REJEITA
  "Não pode: excede massa de tradição disponível (52kg)"
```

**V3 — Quantidade zero = void()**:
```
Se qty_nova == 0 → void() a WO (libera tudo)
```

**O que acontece automaticamente ao adjust()**:
1. Signal `production_changed(action="adjusted")` → Quant planejado atualizado no Stockman
2. Disponibilidade refletida imediatamente para clientes (BÂTARD → indisponível, BAGUETTE → +20)
3. `close()` recebe quantidades já coerentes com o remanejo

**Sobre alterar quantidade de insumo planejado (WO da massa de tradição)**:

Proteção: **warn + confirm, não block**.
- Se operador reduz massa de 52kg para 40kg e WOs dependentes precisam de 50kg:
  - Warning: "Insumo insuficiente para produção planejada. Déficit 10kg. Continuar?"
  - Se confirma: ajusta. Dashboard mostra inconsistência. Operador sabe que precisa
    remanejar WOs de SKU.
- Não bloqueia: operador pode estar planejando receber mais massa, ou vai ajustar WOs depois.
- Não cancela+recria: perde histórico de eventos e holds vinculados.

### DD-8: Validação server-side de slots

Adicionar validação no `CheckoutView.post()`:
- Slot deve existir na lista configurada de `Shop.defaults["pickup_slots"]`
- Se hoje: slot.starts_at > now (não pode selecionar slot passado)
- Se futuro: qualquer slot válido

### DD-9: Toda configuração prática-comercial no admin

Toda configuração que afeta o comportamento comercial deve ser editável via
`Shop.defaults` no admin Unfold, sem deploy:

| Config | Chave | Default |
|--------|-------|---------|
| Janela máxima de encomenda | `max_preorder_days` | 30 |
| Datas fechadas | `closed_dates` | `[]` |
| Estações do ano | `seasons` | hot/mild/cold (DD-6) |
| Multiplicador alta demanda | `high_demand_multiplier` | 1.2 |
| Margem de segurança produção | `safety_stock_percent` | 0.20 |
| Slots de retirada | `pickup_slots` | 3 slots (09h, 12h, 15h) |
| Config de slots | `pickup_slot_config` | history_days, rounding, fallback |
| Horário de funcionamento | `opening_hours` | Por dia da semana |
| Qty máxima por SKU (futuro) | `max_order_qty_per_sku` | — |

---

## Work Packages

### WP-A1: Limpar D-1 do storefront (Crítico) ✅ 2026-04-07

**Objetivo**: D-1 nunca visível para o cliente.

**Ações**:
1. `_availability_badge()`: Remover estado `badge-d1` / "Últimas unidades".
   Quando só há D-1: retornar `badge-unavailable` ("Indisponível").
2. `product_card.html`: Remover badge de desconto D-1, preço D-1, texto D-1.
3. `product_detail.html`: Idem.
4. `_annotate_products()`: Remover lógica `is_d1` e `d1_pct`.
5. `_line_item_is_d1()`: Remover do storefront. Manter apenas para POS (internal-only).
6. Verificar: `allowed_positions` do canal web já exclui "ontem" — confirmar que
   `availability_for_sku()` com scope do canal retorna `d1=0` corretamente.

**Arquivos**: `_helpers.py`, `product_card.html`, `product_detail.html`, `catalog.py`

### WP-A2: Simplificar badges para o cliente ✅ 2026-04-07

**Objetivo**: Apenas "indisponível" e opcionalmente "esgotado".

**Ações**:
1. Criar `storefront_availability(sku, channel)` em `_helpers.py` (ou novo módulo):
   - Chama `availability_for_sku(sku, **scope)` com scope do canal
   - Retorna `{available_qty, can_order, is_paused, had_stock}`
   - `had_stock`: True se houve Quant planejado ou recebido para o SKU+data
     (distingue "esgotado" de "nunca teve")
2. Refatorar `_availability_badge()`:
   - Remover: `badge-preparing`, `badge-planned`, `badge-d1`
   - Manter: `badge-available` (sem label), `badge-unavailable` ("Indisponível"),
     `badge-sold-out` ("Esgotado" — se `had_stock` e `available_qty == 0`)
   - Se `had_stock` for custoso demais: apenas "Indisponível" para tudo
3. Atualizar templates que consomem badges (product_card, product_detail)
4. Atualizar CSS (remover classes obsoletas)

**Arquivos**: `_helpers.py`, `product_card.html`, `product_detail.html`, `output.css`

### WP-A3: Remover restrições artificiais de encomenda ✅ 2026-04-07

**Objetivo**: Cliente encomenda a qualquer hora, para qualquer data com disponibilidade.

**Ações**:
1. `checkout.py`: Remover cutoff hour logic (bloco `_validate_preorder` que bloqueia
   por horário). Manter apenas validação de data dentro da janela configurável.
2. `checkout.py`: Trocar `max_date = today + timedelta(days=7)` por
   `Shop.defaults["max_preorder_days"]` (default 30).
3. `checkout.py`: Remover `preorder_min_quantity` check.
4. Implementar `Shop.defaults["closed_dates"]` — lista de datas/ranges fechados.
5. Checkout: filtrar datas fechadas das opções de entrega/retirada.
6. Template de checkout: atualizar date picker para respeitar janela e closed_dates.

**Arquivos**: `checkout.py`, `checkout.html`, `seed.py` (popular defaults)

### WP-A4: Wiring do banner de horário de funcionamento ✅ 2026-04-07

**Objetivo**: Banner informativo de "Aberto/Fechado" funcional em todas as páginas.

**Ações**:
1. `context_processors.py`: Adicionar `shop_status` ao contexto global via
   `_shop_status()` (já existe, só precisa chamar).
2. Verificar `_shop_status()`: mensagens de "fecha em X min", "abre em X min".
3. `base.html`: Banner já existe no template — confirmar que renderiza corretamente
   com o context processor wired.
4. `_format_opening_hours()`: Wiring no footer e home (já têm placeholders).
5. Seed: popular `Shop.opening_hours` com dados realistas.

**Arquivos**: `context_processors.py`, `_helpers.py`, `base.html`, `seed.py`

### WP-A5: Centralizar serviço de alternativas ✅ 2026-04-07

**Objetivo**: Um único serviço para todos os contextos.

**Ações**:
1. Criar `framework/shopman/services/alternatives.py`:
   - `find(sku, *, qty=1, channel=None, limit=4) -> list[dict]`
   - Usa `offering.contrib.suggestions.find_alternatives()` (Offerman)
   - Filtra por disponibilidade no canal (Stockman via `storefront_availability`)
   - Anota com preço e badge simplificado
2. Refatorar consumidores:
   - `catalog.py` → `_load_alternatives()` → delegar para serviço
   - `cart.py` → `CartAlternativesView` → delegar para serviço
   - `handlers/stock.py` → `_build_issue()` → delegar para serviço
   - `api/catalog.py` → endpoint de alternativas → delegar para serviço
3. Remover `get_alternatives()` do adapter `stock_internal.py` (alternativas não
   são responsabilidade do adapter de estoque).

**Arquivos**: Novo `services/alternatives.py`, `catalog.py`, `cart.py`,
`handlers/stock.py`, `api/catalog.py`, `stock_internal.py`

### WP-A6: Validação server-side de slots ✅ 2026-04-07

**Objetivo**: Slot inválido rejeitado no servidor.

**Ações**:
1. `checkout.py`: Validar `delivery_time_slot` contra `Shop.defaults["pickup_slots"]`.
2. Se hoje: validar que `slot.starts_at > now`.
3. Se slot inválido: erro no form, não permite commit.
4. Adicionar teste para slot passado, slot inexistente, slot futuro.

**Arquivos**: `checkout.py`, testes

### WP-A7: Elevar `craft.suggest()` a first-class ✅ 2026-04-07

**Objetivo**: Sugestão de produção inteligente com sazonalidade, waste, confiança.

**Ações**:
1. **Sazonalidade**: `suggest()` filtra histórico por estação atual.
   - Config: `Shop.defaults["seasons"]` (hot/mild/cold → meses). Editável no admin.
   - `SAME_WEEKDAY_ONLY` continua ativo dentro da estação.
   - Véspera de feriado/fim de semana: `Shop.defaults["high_demand_multiplier"]`.
     Editável no admin.
2. **Waste**: Incluir `DailyDemand.wasted` na análise.
   - Se waste_rate > threshold → reduzir sugestão proporcionalmente.
3. **soldout_at**: Popular no `OrderingDemandBackend.history()`.
   - Requer tracking de quando um SKU esgotou (novo campo ou cálculo).
4. **Confiança**: Retornar `confidence` na Suggestion.
   - `sample_size < 3` → "low", `3-7` → "medium", `≥8` → "high".
5. **Safety stock**: `CRAFTING["SAFETY_STOCK_PERCENT"]` (default 0.20).
   Expor também em `Shop.defaults["safety_stock_percent"]` para edição no admin.
6. **Basis expandido**: Incluir estação, waste_rate, confidence no basis dict.

**Não inclui**: Sugestão de sub-receitas. `suggest()` sugere SKUs. A explosão de BOM
via `needs(expand=True)` já resolve os componentes e pré-preparos nativamente.

**Arquivos**: `craftsman/services/queries.py`, `craftsman/contrib/demand/backend.py`,
`craftsman/conf.py`, seed

### WP-A8: Validação de insumos e holds no `adjust()` (remanejo de produção) ✅ 2026-04-07

**Objetivo**: Remanejo seguro de quantidades entre WOs que compartilham insumos,
respeitando compromissos com clientes. Sem novo status — mantém OPEN/DONE/VOID.

**Ações**:
1. **V1 — Validar holds do SKU de saída**:
   - `adjust()`: Se `qty_nova < holds_ativos` para o `output_ref + scheduled_date` → rejeita.
   - `CraftError("COMMITTED_HOLDS", committed=N, requested=qty_nova)`.
   - Consulta `StockHolds` (ou `DemandProtocol.committed()`) para o SKU na data.

2. **V2 — Validar insumos compartilhados**:
   - `adjust()`: Para cada insumo do BOM, calcula o total necessário de TODAS as
     WOs OPEN na mesma data que usam o mesmo insumo.
   - Se `total_necessário > disponível` → rejeita.
   - `CraftError("INSUFFICIENT_MATERIALS", shortages=[{sku, needed, available}])`.
   - Usa `InventoryProtocol.available()` (ou `StockQueries.available()`) para insumos.
   - Usa `craft.needs(date)` para calcular total de consumo das demais WOs.

3. **V3 — Quantidade zero**:
   - Se `qty_nova == 0`: chama `void()` (libera tudo).

4. **Warning ao ajustar insumo (WO de pré-preparo)**:
   - Se operador reduz Quant de insumo e WOs dependentes excedem disponível:
   - Warning com contexto (déficit, WOs afetadas) — warn + confirm, não block.
   - Implementar como flag `force=True` no adjust() ou via confirmação no admin/API.

5. **Reflexo automático**:
   - Signal `production_changed(action="adjusted")` já atualiza Quant planejado
     no Stockman, que reflete na disponibilidade imediatamente.

**Arquivos**: `craftsman/services/scheduling.py` (adjust), `craftsman/protocols/inventory.py`,
`craftsman/contrib/stocking/handlers.py`, testes

### WP-A9: Seed com dados realistas de demanda

**Objetivo**: Seed popula dados que exercitam todo o fluxo de disponibilidade.

**Ações**:
1. **Mais dias de histórico**: 28+ dias (não 7) para suggest() funcionar.
2. **Sazonalidade**: Dados variam por estação (hot/mild/cold).
3. **Waste**: Alguns dias com waste > 0.
4. **soldout_at**: Alguns dias com esgotamento antes do fim do expediente.
5. **Work Orders**: Criar WOs com `finished_at` para popular pickup slots.
6. **Stock Alerts**: Manter (já funciona).
7. **Closed dates**: Popular `Shop.defaults["closed_dates"]` com feriados exemplo.
8. **Opening hours**: Popular `Shop.opening_hours` (já parcialmente feito).
9. **Seasons**: Popular `Shop.defaults["seasons"]`.
10. **Safety stock**: Popular `Shop.defaults["safety_stock_percent"]`.
11. **High demand multiplier**: Popular `Shop.defaults["high_demand_multiplier"]`.
12. **Max preorder days**: Popular `Shop.defaults["max_preorder_days"]`.

**Arquivos**: `seed.py`

---

## Ordem de Execução

```
WP-A1  Limpar D-1 do storefront          ← PRIMEIRO (violação ativa)
WP-A2  Simplificar badges                ← depende de A1
WP-A4  Wiring banner de horário          ← independente
WP-A6  Validação server-side de slots    ← independente
  ↓
WP-A3  Remover restrições artificiais    ← depende de A4 (banner informativo)
WP-A5  Centralizar alternativas          ← depende de A2 (badge simplificado)
  ↓
WP-A7  Elevar craft.suggest()            ← independente do frontend
WP-A8  Validação de remanejo no adjust() ← independente
WP-A9  Seed realista                     ← depende de A7, A8 (usa features novas)
```

**Paralelizáveis**:
- (A1 + A4 + A6) em paralelo
- (A7 + A8) em paralelo
- A9 por último (integra tudo)

---

## Fora de Escopo (Anotar para Futuro)

- **Quantidades muito grandes**: Definir parâmetros e implementar tratamento.
  Config: `Shop.defaults["max_order_qty_per_sku"]` ou fórmula (média + X%).
- **Calendário avançado estilo Google Empresas**: Além de closed_dates, horários
  especiais por data (véspera de feriado com horário reduzido, etc.).
- **Real-time push**: WebSocket/SSE para atualizar badges de disponibilidade em
  tempo real no catálogo (hoje é request-based).
- **Weather API**: Integração com previsão do tempo para ajustar sugestões.
- **Coeficiente de variação**: Complemento à confiança — CV = desvio padrão / média
  para detectar instabilidade mesmo com sample_size alto.

---

## Referências

- [docs/reference/data-schemas.md](../reference/data-schemas.md) — Schemas de Session/Order data
- [docs/guides/flows.md](../guides/flows.md) — Arquitetura de Flows
- [CLAUDE.md](../../CLAUDE.md) — Convenções do projeto
- Stockman: `packages/stockman/shopman/stocking/services/availability.py`
- Craftsman: `packages/craftsman/shopman/crafting/services/queries.py`
- Storefront: `framework/shopman/web/views/_helpers.py`, `catalog.py`, `checkout.py`
