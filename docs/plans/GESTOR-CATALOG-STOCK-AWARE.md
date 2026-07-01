# Gestor de Cardápio ciente de estoque — Esgotado ≠ Pausado

> Aprovado por Pablo (2026-07-01). A matriz produto×canal do Gestor hoje só enxerga
> pausa/publicação (`is_sellable`/`is_published`). Ela deve também mostrar **Esgotado**
> (fato de estoque), distinto de **Pausado** (decisão do operador) — e o item **volta
> sozinho na próxima fornada** (loop produção→estoque→disponibilidade já existe).

## Motivação (medido)
- **51/51 produtos vendáveis da Nelson são stock-tracked** (0 untracked). O loop
  `production_changed → craftsman/contrib/stockman (MAKE) → quant → availability` está
  vivo pra todo o cardápio; só o Gestor é cego a isso.
- Reuso alto, reinvenção zero: `shop.projections.catalog_context.availability_for_skus(skus, channel_ref)`
  já entrega, **em 1 batch**, o dict canônico por SKU: `total_promisable`, `available`,
  `is_tracked`, `planned`, `breakdown.in_production`, `is_paused`. Degrada em silêncio sem Stockman.

## Modelo
- **Pausado** (`is_sellable=false`) e **Esgotado** (estoque) são **ortogonais**. Esgotar
  NÃO mexe no switch; a produção repõe sem despausar nada.
- Estoque é **produto-level** (físico) → o estado Esgotado vive na **linha**, não na célula
  (as células seguem sendo pausa+preço por canal). Espelha o esmaecer "fora em todos" já feito.
- Scope de estoque = de um canal representante (`surfaces[0].ref`); diferenças de scope entre
  canais (D-1/`excluded_positions`) são de borda pro olhar do operador.

## Work packages
- **WP-1 (backend, núcleo):** `build_catalog_matrix` faz 1 batch `availability_for_skus`.
  Novos campos em `CatalogRowProjection`: `stock_tracked: bool`, `stock_qty: int|None`
  (`total_promisable`), `sold_out: bool` (tracked & promisable≤0), `low_stock: bool`
  (0<promisable≤threshold), `replenish_qty: int` (planned + in_production). TS mirror.
- **WP-3 (frontend):** `rowStatus` ganha o estado **Esgotado** (precedência: Despublicado ›
  Pausado-global › **Esgotado** › Indisponível › Ativo), tom **neutro** (é ciclo normal, não
  erro). Selo "Esgotado" + (WP-2) "repõe {n} na fornada" quando `replenish_qty>0`. Reusa
  esmaecer/foto P&B. Aviso `low-stock` opcional ("resta {n}").
- **WP-2 (fast-follow, quase de graça):** o hint de reposição usa `replenish_qty` que já vem
  do dict — só a copy/UI.
- **WP-4:** testes (pure `rowStatus`/`availableAnywhere` + projeção) + verificação ao vivo
  (zerar estoque → Esgotado; finalizar WorkOrder → volta sozinho).

## Fronteira / regras
- `backstage.projections.catalog` → importa `shop.projections.catalog_context` (backstage→shop, ok);
  `catalog_context` fala com Stockman via adapter (shop→packages, ok). Sem quebra de camada.

## Fora de escopo
- Ação "marcar esgotado hoje" que zera estoque manualmente (correção de estoque) — decidir depois;
  pro caso untracked (inexistente na Nelson) sobraria o 86-por-tempo (Directive até próxima abertura).
