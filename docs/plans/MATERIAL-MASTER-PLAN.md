# MATERIAL-MASTER-PLAN — Insumos com lar próprio (Opção A)

> Tirar insumos do Offerman e dar a eles um **material master** próprio, honrando
> a convenção do projeto (*"Offerman = só vendáveis; insumos nunca no Offerman"*).
> Desbloqueia o shelf-life de verdade (ver [VALIDITY-SHELFLIFE-REVIEW](VALIDITY-SHELFLIFE-REVIEW.md)).
> Decisão do Pablo (2026-06-27): **Opção A, investigando bem**.

**Status**: 🟡 Design proposto — aguarda escolha do "lar" + go do Pablo. Não iniciado.

## O problema (o muddle)

Hoje há uma incoerência interna: a convenção proíbe insumo no Offerman; o **dado
real honra** (insumos = SKUs `INS-*` em `RecipeItem.input_sku`, sem Product); mas
o **help text de `is_sellable`** ("Não = insumo ou pausado") e **vários fixtures
de teste** modelam insumo como `Product is_sellable=False`. Esse muddle é a raiz
do bloqueio do shelf-life (o validator não consegue servir um catálogo que mistura
vendáveis e insumos).

## O que de fato falta um lar (vs o que já tem)

| Metadado de insumo | Onde está hoje | Precisa de master? |
|---|---|---|
| Unidade | `RecipeItem.unit` (campo próprio) | ✅ já tem |
| Nutrição / alérgenos / dieta | `RecipeItem.meta` | ✅ já tem (continua source) |
| Fornecedor (por lote) | `Batch.supplier` | parcial (lote, não SKU) |
| **Nome/display** | só no seed `INGREDIENT_PROFILES` | ❌ **sem casa** |
| **Custo unitário** | nenhum nativo (só via Product+CostBackend) | ❌ **sem casa** |
| **Validade-padrão do insumo** | nenhuma (só `Batch.expiry` por lote) | ❌ **sem casa** |

Ou seja: o master só precisa centralizar **nome, custo, validade-padrão e
fornecedor-por-SKU**. Nutrição/dieta/unidade **não mudam de lugar**.

## Acoplamento atual (quase tudo SOFT)

- **SOFT** (degrada com fallback): nutrição/dieta materializadas
  (`nutrition_from_recipe`, `dietary_from_recipe`) — leem `RecipeItem.meta`, pulam
  se não há Product; `_catalog_unit_for_sku` (fallback `""`); admin `mark_as_ingredient`.
- **DURO** (quebra sem Product): concentrado em **testes/fixtures** que criam
  `Product(is_sellable=False)` p/ insumo (`test_production_catalog`,
  `test_production_stock`, conftests) + a leitura de `is_sellable` no SkuValidator.

> Conclusão: a migração é majoritariamente **reescrever fixtures de teste**, não
> reescrever fluxos reais. Quando liguei o validator do Offerman, quebraram só 3
> testes (de 2151) — todos de insumo-como-Product.

## Decisão-chave: onde mora o master (honrando "Core é último recurso")

**Recomendado: um model `Material` no ORQUESTRADOR (`shopman/shop/`), NÃO em
`packages/`.** O orquestrador já é a camada de wiring de adapters; ele pode:
- ter `shopman/shop/models/material.py` (`Material`: sku, name, unit, cost_q,
  supplier, shelf_life_days, metadata) — migração no app `shop`, **zero mudança
  nos pacotes do Core**;
- expor esses dados a Stockman/Craftsman **implementando os protocolos que já
  existem**: `SkuValidator` (stockman) e `CatalogBackend` (craftsman), via
  adapters compostos em `shopman/shop/adapters/`.

Assim, **nenhum pacote do Core muda** — respeita a regra "Core sagrado / último
recurso". (Alternativa purista: um 10º pacote `materials`; mais limpo
conceitualmente, mas é adição no Core e mais complexidade. Evitar Offerman.)

## Design (composição via protocolos)

- `shopman/shop/adapters/sku_validator_composite.py` → implementa `SkuValidator`:
  resolve **Offerman** p/ SKUs vendáveis (shelf_life real), **Material** p/ insumos
  (defaults neutros, **sem marcar is_sellable=False → sem pausar holds**), e
  default neutro p/ desconhecidos. Configurado via `STOCKMAN_SKU_VALIDATOR`.
- `shopman/shop/adapters/catalog_composite.py` → implementa o `CatalogBackend` do
  Craftsman do mesmo jeito (nome/unidade do insumo via Material).
- `RecipeItem`/nutrição/dieta: **sem mudança** (já leem `RecipeItem.unit`/`.meta`).

### Por que isso desbloqueia o shelf-life
Com o validator composto, ligar `STOCKMAN_SKU_VALIDATOR` para ele faz: produtos
ganham shelf-life (não vender vencido), insumos **não são pausados** (resolvidos
pelo Material, não como Product is_sellable=False). O bloqueio que eu havia
diagnosticado some — porque ele vinha do muddle, não do modelo.

## Arcos propostos

- **Arc 1 · Material model + admin** (orquestrador): model + migração (app shop) +
  admin Unfold CRUD. Seed popula `Material` a partir de `INGREDIENT_PROFILES`.
- **Arc 2 · Adapters compostos** (SkuValidator + CatalogBackend) + wiring por
  config. Testes dos adapters.
- **Arc 3 · Migrar fixtures de teste** insumo-como-Product → `Material` (o grosso
  do esforço). Rodar suíte inteira verde.
- **Arc 4 · Ligar o validator composto** (config) + provar que disponibilidade de
  venda filtra vencidos e holds de produção seguem ok (`test_production_stock`).
- **(depois) Validity hardening** (FEFO, Batch-no-finish, near-expiry) sobre essa
  base — ver VALIDITY-SHELFLIFE-REVIEW.

## Custo honesto
~5–6 dias de engenharia (model+migração, 2 adapters, ~50 linhas de fixtures
reescritas, seed, testes). Risco baixo (RecipeItem.meta desacoplado; protocolos
já existem). **Não é zero-friction**, mas é aditivo e não toca `packages/`.
Candidato a rodar perto do go-live (junto com media persistente / validity).

## Sub-decisões para o Pablo
1. **Lar do master**: orquestrador (`shop`, recomendado, sem tocar Core) vs 10º
   pacote `materials` (purista, adição no Core).
2. **Custo/fornecedor por SKU agora ou depois?** (afeta o escopo do model).
3. **Quando**: agora ou perto do go-live (com validity/media)?

## Referências
- [VALIDITY-SHELFLIFE-REVIEW](VALIDITY-SHELFLIFE-REVIEW.md) · CLAUDE.md (Offerman=vendáveis)
- recipe.py (RecipeItem.unit/meta, _catalog_unit_for_sku) · protocols/sku.py · craftsman/adapters/catalog.py
- nutrition_from_recipe.py · dietary_from_recipe.py · seed.py (INGREDIENT_PROFILES)
