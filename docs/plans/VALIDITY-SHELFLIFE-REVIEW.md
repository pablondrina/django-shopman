# VALIDITY-SHELFLIFE-REVIEW — Como o Core trata validade hoje (e o caminho)

> Revisão profunda (verificada no código, arquivo:linha) de como o Core/Backend
> trata **validade de produtos** nas 3 dimensões de uso da Nelson, para decidir o
> caminho **priorizando configuração e o orquestrador; mudança no Core como último
> recurso**. (2026-06-27)

## Veredito de uma linha

**Nenhuma mudança no Core (`packages/`) é necessária.** A estrutura de validade já
existe nos modelos (`Product.shelf_life_days`, `Batch.expiry_date/production_date`,
`is_sellable`, scoping por posição). O que falta é (1) **ativar** via um validator
que sirva produtos **e** insumos, (2) **config**, e (3) alguns **handlers no
orquestrador** (`shopman/shop/`). Tudo fora dos pacotes do Core.

## As 3 dimensões (uso Nelson)

- **(a) Validade de INSUMOS p/ produção** — crítico; estoque, FEFO.
- **(b) Validade de produtos de REVENDA** — crítico; não vender vencido **nem
  muito próximo** do vencimento.
- **(c) Validade de produtos PRODUZIDOS aqui** — crítico, mas validade ~0–1 dia,
  com preço diferenciado (D-1).

## O que o Core JÁ tem (estrutura)

- `Product.shelf_life_days` (janela relativa) + `Product.is_sellable`/`availability_policy`
  ([offerman/models/product.py](../../packages/offerman/shopman/offerman/models/product.py)).
- `Batch.expiry_date`/`production_date` + `Batch.clean()` de consistência
  ([stockman/models/batch.py](../../packages/stockman/shopman/stockman/models/batch.py)).
- `quants_eligible_for` aplica shelf_life **AND** batch-expiry
  ([stockman/services/scope.py](../../packages/stockman/shopman/stockman/services/scope.py)).
- Config de estoque: `Shop.defaults`/`ChannelConfig.stock` (`safety_margin`,
  `allowed_positions`, `excluded_positions`, `hold_ttl_minutes`, `check_on_commit`,
  `low_stock_threshold`).
- D-1: posição `"ontem"` (excluída de canais remotos) + `D1Rule` (desconto
  config-driven via `RuleConfig`).

## A descoberta crítica

**Validade está DESLIGADA em todo ambiente real:** o `SKU_VALIDATOR` default é
**Noop** (retorna `shelflife_days=None` p/ tudo), então `quants_eligible_for` só
filtra por `Batch.expiry_date` — e **produto sem Batch nunca "vence"**. Motivo de
estar Noop: **insumos são `Product` com `is_sellable=False`**; wirar o validator do
Offerman globalmente os marca "pausados" e **quebra os holds de produção**
(`test_production_stock`). É preciso um validator que diferencie *disponibilidade
de venda* de *disponibilidade para produção*.

## Matriz de gaps (cada um classificado)

| # | Caso | Gap | Hoje | Classe | Onde |
|---|---|---|---|---|---|
| A2 | Insumos | **FEFO** (consumir o que vence antes) | FIFO por `created_at` ([holds.py:72](../../packages/stockman/shopman/stockman/services/holds.py)) | **Orquestrador/Core-svc** (ordenar por `Batch.expiry`) | pequeno |
| A3 | Insumos | Excluir lote vencido | ✅ já exclui (scope.py) | JÁ ATENDE | — |
| B1 | Revenda | Bloquear vencido | ✅ estrutura, ❌ **off (Noop)** | **CONFIG** (ativar validator) | — |
| B2 | Revenda | **Near-expiry** (não vender perto do vencimento) | ❌ não existe | **CONFIG** (margem em `Shop.defaults`/RuleConfig) + check no orquestrador | médio |
| C1 | Produzido | **Batch+expiry automático** ao finalizar WO | ❌ cria quant com `batch=''` | **Orquestrador** (handler no finish: expiry = produção + shelf_life) | médio |
| C3 | Produzido | D-1 / preço diferenciado | ✅ funciona (manual) | JÁ ATENDE; falta auto-transfer p/ "ontem" (P2) | — |
| T | Transversal | Validator produtos **e** insumos | ❌ Noop | **Orquestrador** (composite validator) + CONFIG | médio |

> Correção ao primeiro rascunho: o **composite validator deve viver no
> ORQUESTRADOR** (`shopman/shop/adapters/`), não em `packages/stockman` — assim
> ele pode compor Offerman (produtos) + defaults p/ insumos **sem tocar o Core**.
> E a **margem near-expiry deve ser CONFIG** (`Shop.defaults`/RuleConfig), não um
> campo novo em `Product` (evita migração no Core).

## Caminho proposto (config-first; sem Core)

- **P0 — Ligar validade com segurança**: `CompositeSkuValidator` no orquestrador
  (Offerman p/ vendáveis; defaults neutros p/ insumos, sem pausá-los) + apontar
  `STOCKMAN_SKU_VALIDATOR` pra ele. Destrava (b) e a base do shelf-life. Rodar
  `test_production_stock` (não pode quebrar holds de insumo).
- **P1 — FEFO de insumos**: ordenar `_find_quant_for_hold` por `Batch.expiry`
  (vencendo antes primeiro), fallback `created_at`.
- **P1 — Batch+expiry no finish de produção**: handler craftsman→stockman cria/
  vincula `Batch(expiry = production_date + shelf_life_days)` ao concluir a WO.
- **P1 — Near-expiry gate**: margem (dias) em `Shop.defaults["stock"]`; o adapter
  de disponibilidade do orquestrador reduz/zera disponibilidade dentro da margem.
- **P2 — Auto-transfer D-1**: task diária movendo sobras `vitrine → "ontem"`.

Nenhum item exige mudar `packages/`. É uma **iniciativa própria** ("validity
hardening"), candidata a rodar perto do go-live (junto com media persistente),
por ser operacionalmente crítica e tocar disponibilidade real.

## Referências
- [ROADMAP](../ROADMAP.md) (linha shelf-life) · [GO-LIVE-READINESS-PLAN](GO-LIVE-READINESS-PLAN.md)
- scope.py · shelflife.py · holds.py · craftsman/contrib/stockman/handlers.py · shop/adapters/stock.py
