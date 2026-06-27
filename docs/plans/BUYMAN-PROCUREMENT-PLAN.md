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
- **WP-B1b · Admin Unfold** — registrar Material/Supplier/Cost no admin (contrib).
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
- **WP-B5b · Ativar guardrails de disponibilidade de insumo (DORMENTE hoje)** —
  o seam read-only `INVENTORY_BACKEND` já tem 3 consumidores vivos e testados,
  porém **dormentes**: `scheduling._validate_shared_ingredients` (gateia
  `adjust`), `backstage.check_finish_materials` (gateia `apply_finish`),
  `formula._material_availability` (status na sugestão). Estão desligados porque
  insumo não tem quant no Stockman hoje — ligar agora **bloquearia adjust/finish**
  (provado empiricamente 2026-06-27, FARINHA 0.0). Quando WP-B4/B5 derem estoque
  real ao insumo: implementar um backend read-only `available()` (consulta
  `stock.available`, + noop p/ teste standalone = 2 impls → conforme ADR-001 §3),
  apontar `INVENTORY_BACKEND` a ele, e provar com teste que `adjust`/`finish`
  passam **com** insumo estocado e barram **sem**. Até lá, NÃO ligar o setting
  (comentário-guarda em `craftsman/conf.py` e nos 3 consumidores).
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
