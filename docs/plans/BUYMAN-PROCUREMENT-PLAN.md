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

## Padrões herdados da suíte (verificado no código)

Estudo dos pacotes maduros para o Buyman nascer no mesmo nível:
- **Ledger-first** (Stockman `Move`/`Quant`; Payman `PaymentTransaction`): registro
  append-only é a verdade; saldo/estado deriva. Aplicar ao **recebimento**
  (append-only) e ao **histórico de custo** (futuro). Master data (Material/
  Supplier/custo atual) é mutável — **não** é ledger.
- **Immutability guards**: modelos append-only bloqueiam `.update()/.delete()`
  (Move/Transaction). Aplicar ao `PurchaseReceipt`.
- **Service `@classmethod`** (StockService/PaymentService): lógica centralizada,
  testável. Buyman terá `ReceiptService`/`PurchaseService` no mesmo estilo.
- **Desacoplamento por signal + contrib** (padrão Craftsman→Stockman): Buyman
  **nunca importa Stockman**; um `buyman/contrib/stockman` (opt-in em
  INSTALLED_APPS) escuta `receipt_created` e chama `stock.receive(...)` com import
  lazy + fallback gracioso.
- **Evitar over-engineering** (Orderman): sem Directives/fila async, sem snapshot
  selado, sem event-sourcing — `PurchaseOrder.status` simples basta.

> **Correção ao rascunho do outro agente**: não existe "StockEvent BUY" no
> Stockman. O ledger do Stockman é o **`Move`**, e o "tipo" é um **`reason`**
> string livre (+ metadata), não um enum. Recebimento de compra = `stock.receive`
> → `Move(reason="Compra <PO> de <fornecedor>", metadata={po_ref, supplier_ref})`,
> criando `Batch` com `expiry = recebimento + Material.shelf_life_days`. Mesmo
> espírito ledger-first, mas via o mecanismo que já existe (sem inventar evento novo).

## Fases

- **Fase 1 — Fundação (PRÉ go-live; desbloqueia shelf-life)** — master data
  (mutável): Item master + Fornecedor + custo + validador composto. WPs abaixo.
- **Fase 2 — Pedido de Compra**: `PurchaseOrder` (state-machine simples
  draft→confirmed→received) + `PurchaseOrderLine` (material, qty, `unit_cost_q`
  vindo de `SupplierMaterialCost`). Linhas seladas após confirmar.
- **Fase 3 — Recebimento (ledger-first)**: `PurchaseReceipt` **append-only**
  (correção = nova receipt, nunca edição) + `ReceiptService` que emite
  `receipt_created` → handler em `buyman/contrib/stockman` chama `stock.receive`
  (Move + Batch com expiry). Confere qty/custo.
- **Fase 4 — Reposição**: ponto de reposição/estoque mínimo → sugestão de compra
  (espelha o `suggest_production` do Craftsman).

## WP-B0 — `Move.kind` no Stockman (fundacional, aprovado) ✅ infra / 🟡 callers

Ledger categorizado por evento econômico: **MAKE/BUY/SELL/ADJUST/TRANSFER/RETURN/
WASTE** (decisão Pablo; WASTE adicionado após a provocação sobre planning). Mudança
aditiva no Core (Stockman) — justificada (kind é propriedade do Move; reason-string
não dá categoria queryable).
- ✅ **Infra + correções (commits `7d24784b`, `42750716`, `d647b7a8`)**: `Move.Kind`
  (7 kinds) + campo + índice; `receive`/`issue`/`realize`/`transfer`/`fulfill` aceitam
  `kind`; **UMA migração limpa (0003, 7 kinds) — backfill REMOVIDO** (dados fake/seed,
  pré-go-live, sem legado; backfill era bridge provisório); testes; stockman 219 verde.
- ✅ **Wiring inequívoco**: `planning.realize`→**MAKE** (era erro chamar de
  TRANSFER); `cleanup_d1`→**WASTE** (descarte de D-1 vencido). **TRANSFER fica
  reservado** (sem caller real hoje).
- ✅ **Wiring dos callers (quase 100%)**: craftsman produção (3 receives)→**MAKE**;
  venda (`fulfill_hold`)→**SELL**; devolução (`receive_return`)→**RETURN**;
  `realize`→MAKE; `cleanup_d1`→WASTE; `transfer`→TRANSFER. Buyman recebimento→BUY
  na Fase 3.
- ✅ **Consumo de insumo→MAKE — SESSÃO DEDICADA CONCLUÍDA (2026-06-27)**. A
  integração craftsman→stockman tinha 2 caminhos de escrita: signal
  `contrib/stockman` (VIVO, só saída) e InventoryProtocol `StockingBackend`
  (MORTO por typo de import — `from shopman.stockman.service import stock`
  lowercase inexistente; `_stockman_available` sempre False → consume/receive/
  release no-op). Riscos: insumo NUNCA era deduzido + dupla-contagem de saída se
  o backend fosse "consertado" (receive duplicaria o signal). **Resolvido: signal-
  path é o único caminho de escrita do ledger.**
  - `StockingBackend` (write) **deletado**; `execution._call_inventory_on_finish/
    _on_void` removidos; `CRAFTSMAN["INVENTORY_BACKEND"]` write desconfigurado.
  - **Consumo de insumo migrado para o signal** (`_handle_finished` →
    `_consume_materials`): lê os `WorkOrderItem` CONSUMPTION e emite
    `StockMovements.issue(kind=MAKE)` por insumo (greedy, present-stock-first;
    shortfall não-fatal — FEFO/near-expiry ficam p/ WP-B6). Saída continua via
    plan/start/realize (MAKE), recebida **exatamente uma vez** (sem dobra).
  - `InventoryProtocol` **emagrecido p/ contrato read-only de disponibilidade**
    (`available()` + `MaterialNeed`/`MaterialStatus`/`AvailabilityResult`); DTOs
    de escrita órfãos (`MaterialUsed`/`MaterialProduced`/`Consume/Receive/Reserve/
    ReleaseResult`/`MaterialHold`/`MaterialAdjustment`) removidos. O seam
    `INVENTORY_BACKEND` permanece **só p/ validação de disponibilidade** (V2
    shared-ingredients em `scheduling`; `backstage.check_finish_materials`),
    default None até um backend Buyman implementá-lo (WP-B3).
  - Teste de integração novo (`test_production_app_integration`): finish deduz
    insumo (1 Move MAKE -1) e recebe saída 1× (quant vendável = finished).
    `make test-framework`+`craftsman`+`stockman` verdes (2143/242/219).

## Fase 1 — WPs (a entrega que destrava o go-live)

- **WP-B1 ✅ (2026-06-27) · Pacote `buyman` + `Material`** — scaffold do pacote pip
  (10º persona); model `Material` (sku RefField, name, unit, shelf_life_days,
  metadata). Migração + testes. Registrado na suíte (INSTALLED_APPS, Makefile,
  test-buyman). *(Admin Unfold = WP-B1b, pendente.)*
- **WP-B2 ✅ (2026-06-27) · `Supplier` + custo-por-fornecedor** — `Supplier` +
  `SupplierMaterialCost` (custo por par fornecedor×insumo, `is_preferred` =
  canônico). 5 testes verdes (unicidade sku/par, 1 preferencial).
- **WP-B1b ✅ (2026-06-27) · Admin Unfold** — `buyman/contrib/admin_unfold/`
  (apps + admin) registra Material/Supplier/SupplierMaterialCost com `BaseModelAdmin`
  canônico: badges (validade perecível/não, custo preferencial canônico/alternativo),
  inlines de custo cruzados (custos por fornecedor / por insumo), autocomplete,
  `format_money` no custo. Sem admin core no buyman → sem dupla-registração. Em
  INSTALLED_APPS. `make admin` (gate canônico) verde (253 testes).
- **WP-B3 ✅ (2026-06-27) · Adapters compostos** — Buyman ganhou adapters próprios
  (`buyman/adapters/`): `MaterialSkuValidator` + `BuymanCatalogBackend` (resolvem
  insumo=Material via os contratos de Stockman/Craftsman, import lazy, ADR-001). O
  orquestrador compõe Offerman→Buyman: `shop/adapters/catalog_backend.ComposedCatalogBackend`
  (proxy: `get_product` Offerman→Buyman, resto delega) e `shop/adapters/sku_validator.ComposedSkuValidator`
  (Offerman→Buyman→neutro). **`CRAFTSMAN["CATALOG_BACKEND"]`→composto JÁ (resolução de
  unidade do insumo; seguro, não toca disponibilidade).** **`STOCKMAN["SKU_VALIDATOR"]`
  segue Noop** — flipar p/ o composto é o WP-B5 (muda semântica de disponibilidade de
  TODO sku). 14 testes (buyman 9, shop composed 5). framework 2148 / craftsman 242 verdes.
  *CostBackend composto: adiado p/ quando houver consumidor real de custo (Fase 3 PO).*
- **WP-B4 ✅ (2026-06-27) · Seed Material + rename `INS-`** — o seed popula os 23
  `Material` a partir de `INGREDIENT_PROFILES` (unit + shelf-life da tabela aprovada
  pelo Pablo; "todos frescos" → fermento-bio/alecrim = 14d). **SKU de insumo perdeu o
  prefixo `INS-`** (rename consistente: `INGREDIENT_PROFILES` + `input_sku` das receitas
  + help_text + testes de insumo; **guestman `CUST-INS-` = "insights", intocado**).
  Smoke test do seed assere 23 Materials + invariante "todo input de receita resolve
  como insumo/intermediário(MASSA-*)/produto". framework 2148 / craftsman 242 / buyman 9.
- **WP-B4b (repensado, opcional) · Converter fixtures `Product(insumo)→Material`** — a
  conversão ampla NÃO se sustenta: (a) testes de CORE (offerman) não podem importar
  buyman (independência); (b) nem todo `is_sellable=False` é insumo (produto pausado é
  legítimo); (c) `ingredient` fixture vive em `CollectionItem` (exige Product). Só vale
  onde a semântica insumo=Material é o ponto do teste — reavaliar junto com B5. Sem
  conversão cega.
- **WP-B5 ✅ (2026-06-27) · Shelf-life LIGADO** — `STOCKMAN["SKU_VALIDATOR"]`
  flipado p/ `ComposedSkuValidator`. Raio de explosão medido: só 3 testes (holds de
  insumo), tudo de venda passou. Design "venda vs produção" resolvido em
  `StockHolds.hold`: **hold de produção (`purpose="workorder"`) reserva estoque físico
  e ignora o gate de venda** (pause/sellability/demanda) — insumo é não-vendável por
  natureza, mas reservável p/ WO. **+ bugfix latente**: `StockQueries.available()`
  montava `SimpleNamespace(shelflife=...)` mas `filter_valid_quants` lê `shelf_life_days`
  → validade NUNCA filtrava no caminho por **sku-string** (escondido pelo Noop).
  Corrigido → venda por sku filtra vencidos (teste novo `test_perishable_filtered_by_sku_string`,
  provado: falha com Noop, passa com composto). framework 2149/craftsman 242/stockman 219.
  ⚠️ Seed cria o **master** de insumo (Material) mas NÃO recebe **estoque** (quants) de
  insumo → consume de produção loga "insuficiente" (graceful) e B5b segue travado.
- **WP-B5b ✅ (2026-06-27) · Guardrails de disponibilidade de insumo LIGADOS** —
  seed passou a receber **estoque de abertura de insumo** (500 de cada, no depósito,
  ADJUST); novo backend read-only `shop/adapters/inventory.InventoryAvailabilityBackend`
  (`available()` consulta `stock.available` por MaterialNeed); `CRAFTSMAN["INVENTORY_BACKEND"]`
  apontado p/ ele. Os 3 consumidores (scheduling adjust / backstage finish / formula
  sugestão) saíram do dormente. Raio medido: só **1 teste** quebrou
  (`test_adjust_updates_planned_quant` ajustava sem insumo) — o guardrail funcionando
  como projetado; teste recebeu setup realista (insumo em mãos). Comentários-guarda
  atualizados (de "NÃO ligar" → "ativo quando configurado"). framework 2149/craftsman 242.
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
