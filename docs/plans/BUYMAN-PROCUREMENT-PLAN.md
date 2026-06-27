# BUYMAN-PROCUREMENT-PLAN — Domínio de Compras (lado montante)

> A suíte tem o lado **jusante** (vender: Orderman→Stockman) mas **não tem o lado
> montante** (comprar: fornecedores→compra→recebimento→estoque). Este plano cria
> esse domínio como um **novo pacote persona**, dono do **item/material master**,
> fornecedores e custo — e, em fases, pedido de compra, recebimento e reposição.
> Decisão do Pablo (2026-06-27): novo pacote persona; Fase 1 = fundação
> (Material + Supplier + custo); merece plano + WPs dedicados.

**Status**: 🟡 Plano proposto. **Nome recomendado: `Buyman`** (simetria com
Orderman: venda↔compra) — confirmar. Não iniciado.

## Por que um novo pacote (e por que isso respeita "Core sagrado")

Hoje não existe domínio de compras: `Batch.supplier` é uma string; custo é só um
seam (`CostBackend`, offerman/conf.py) sem fonte real; sem `Supplier`, sem
`PurchaseOrder`, sem recebimento, sem reorder. Criar um **novo app pip
independente** (como os 9 atuais) **não modifica** o Core existente — é o mesmo
padrão da suíte, não uma violação. Diferente de mexer em offerman/stockman.

## Fronteiras do domínio

**Buyman é dono de**: Material/Item master (insumos e seus metadados canônicos),
Fornecedores, Custo de compra; (fases) Pedido de Compra, Recebimento, Reposição.

**Integra com** (via protocolos/seams existentes, sem acoplar — wiring no
orquestrador):
- **Stockman**: recebimento vira `Batch`/`Quant` (com `expiry` derivada da
  validade-padrão do material); Buyman implementa o `SkuValidator` p/ insumos.
- **Craftsman**: custo de insumo alimenta o custeio de receita/`BOM`; Buyman
  implementa o `CatalogBackend` (nome/unidade de insumo).
- **Offerman**: alimenta o `CostBackend` (margem/custo de produto).
- **Payman** (fase futura): pagamento a fornecedor.

**Regra de dependência**: Buyman é independente (não importa offerman/stockman/
craftsman). Os **adapters compostos vivem no ORQUESTRADOR** (`shopman/shop/`), que
lê Buyman (Material) + Offerman (Product) e implementa `SkuValidator`/
`CatalogBackend`/`CostBackend` — exatamente o papel de wiring do shop.

## Fases

- **Fase 1 — Fundação (PRÉ go-live; desbloqueia shelf-life)**
  Item master + Fornecedor + custo + validador composto. Detalhe nos WPs abaixo.
- **Fase 2 — Pedido de Compra**: `PurchaseOrder` + linhas (material, qty, custo,
  fornecedor), estados, catálogo de fornecedor.
- **Fase 3 — Recebimento**: receber contra PO → cria `Batch`/`Quant` no Stockman
  (expiry = recebimento/produção + validade-padrão); conferência (qty/custo).
- **Fase 4 — Reposição**: ponto de reposição/estoque mínimo → sugestão de compra
  (espelha o `suggest_production` do Craftsman).

## Fase 1 — WPs (a entrega que destrava o go-live)

- **WP-B1 · Pacote `buyman` + `Material`** — scaffold do pacote pip; model
  `Material` (sku `INS-*`, name, unit, shelf_life_days, metadata JSON). Admin
  Unfold. Testes do pacote.
- **WP-B2 · `Supplier` + custo** — model `Supplier`; custo unitário do material
  (`cost_q`, opcional por fornecedor). Contrato p/ alimentar `CostBackend`.
- **WP-B3 · Adapters compostos no orquestrador** — `shopman/shop/adapters/`
  implementando `SkuValidator` (Offerman p/ vendáveis + Buyman p/ insumos +
  default neutro) e `CatalogBackend`/`CostBackend` análogos. Wiring por config
  (`STOCKMAN_SKU_VALIDATOR` etc.).
- **WP-B4 · Migração de dados + fixtures** — seed popula `Material` a partir de
  `INGREDIENT_PROFILES`; reescrever os fixtures de teste que criam
  `Product(is_sellable=False)` de insumo → `Material`. Suíte verde.
- **WP-B5 · Ligar shelf-life** — apontar o validator composto; provar que
  disponibilidade de venda filtra vencidos (produtos) e que holds de produção
  (insumos) seguem ok (`test_production_stock`). `is_sellable=False` volta a
  significar só "produto pausado".
- **WP-B6 (encadeia VALIDITY)** — sobre essa base: FEFO de insumos, Batch+expiry
  no finish de produção, near-expiry gate (config). Ver
  [VALIDITY-SHELFLIFE-REVIEW](VALIDITY-SHELFLIFE-REVIEW.md).

## Custo / risco
Fase 1 ~5–7 dias (pacote+model+admin, supplier+custo, 2-3 adapters, seed,
reescrever ~50 linhas de fixtures, ligar validator). Aditivo; risco baixo
(RecipeItem.meta desacoplado; protocolos já existem). Fases 2–4 são incrementos
maiores, pós-go-live.

## Decisões abertas (Pablo)
1. **Nome do pacote** — `Buyman` (recomendado) / outro persona.
2. **Quando a Fase 1** — agora (foco atual) ou agendada perto do go-live (com
   validity/media).
3. **Custo por fornecedor** já na Fase 1, ou custo único por material primeiro?

## Referências
- [MATERIAL-MASTER-PLAN](MATERIAL-MASTER-PLAN.md) (origem) · [VALIDITY-SHELFLIFE-REVIEW](VALIDITY-SHELFLIFE-REVIEW.md)
- CLAUDE.md (Offerman=vendáveis; regra de dependência) · offerman/conf.py (CostBackend)
- protocols/sku.py (SkuValidator) · craftsman/adapters/catalog.py (CatalogBackend) · Batch.supplier
