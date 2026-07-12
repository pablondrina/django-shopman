# POS — Fase C (revisão reversa do PDV)

> Revisão reversa (a partir do código) da superfície de PDV `surfaces/pos-nuxt`
> + backend headless. Frente **v1** (Onda 1). Cada achado abaixo tem **status de
> verificação** — claims não confirmados no código não viram "gap".

**Status**: 🟡 Auditoria em curso (2026-06-26). 1 fix aplicado; resto = achados + recomendações.

---

## Método (e uma lição)

A primeira passada (agente de exploração) listou vários "gaps" que **não
resistiram à verificação no código** — coerente com a regra do projeto:
*confirmar no código antes de reportar gap*. Por isso este doc separa
**confirmado** de **a verificar**.

Exemplos de claims **derrubados na verificação**:
- *"Atalhos de teclado não implementados (WP-1)"* → **falso**: há handlers de
  teclado em `app/app.vue`, `app/components/PosTabHeader.vue`,
  `app/components/PosCartPanel.vue`, `app/composables/useOperatorLock.ts`.
- *"Seletor de fulfillment ausente no checkout"* → **não confirmado**:
  `fulfillment` aparece em `app/components/PosPaymentWorkspace.vue`,
  `app/composables/usePosSale.ts`, `app/presentation/payment.ts`. Precisa de
  verificação funcional antes de declarar gap.

Conclusão honesta: **o POS está mais completo do que uma leitura de superfície
sugere.** Uma Fase C real é uma auditoria item-a-item verificada, não uma lista
de suspeitas.

---

## Arquitetura (confirmada)

- **Superfície ativa**: `surfaces/pos-nuxt` (Nuxt, desktop-first).
  `app.vue` orquestra `usePosTerminal` (read) + `usePosSale` (write) +
  `useOperatorLock`. Presentation pura em `app/presentation/` (payment, tabBoard,
  moveLines, cash, kitchen, …).
- **Backend headless**: `shopman/backstage/api/operations.py` (POSView + ações),
  `shopman/backstage/projections/pos.py`, `shopman/shop/services/pos.py`
  (open/review/close/move/fire/cancel), `shopman/backstage/services/pos.py`
  (caixa).
- **Sem POS-HTMX legado ativo** (confirmado: superfície é só Nuxt).

## O que funciona (confirmado por testes existentes)

Comanda (abrir/tocar/renomear), itens, **move_lines** (split/transfer/merge,
preço congelado, kernel atômico), **fire-to-kitchen** progressivo, pagamento
(dinheiro/PIX/cartão/misto, troco derivado), **caixa cego**, **manager-PIN**,
cancelamento. Backend com cobertura robusta (`test_pos_*` extenso); vitest no
surface cobre intent/payment math/operator lock.

---

## Achados

### ✅ Corrigido nesta sessão

- **move_lines: rollback de cleanup mascarava o erro original**
  ([`shopman/shop/services/pos.py`](../../shopman/shop/services/pos.py)) — quando
  o split criava a comanda destino e o move falhava, o `abandon_session` de
  rollback era desprotegido; se ele lançasse, o erro original do move sumia.
  Agora o cleanup é best-effort (try/except + log), e o erro `move_failed`
  original sempre chega ao operador. Teste:
  `test_split_rollback_failure_does_not_mask_move_error`.

### 🟡 Confirmado, menor (recomendação — não executado sem você)

- **Cédulas de dinheiro hardcoded** em
  [`app/presentation/payment.ts:103`](../../surfaces/pos-nuxt/app/presentation/payment.ts)
  (`BRL_CASH_NOTES_Q`). Funciona, mas para tornar config-driven seria expor
  `cash_notes_q` em `POSCheckoutContractProjection` com fallback. Baixo valor;
  decidir se entra.

### 🔵 A verificar antes de virar tarefa (não asserir como gap)

- **Completude do seletor de fulfillment** (pickup/delivery/balcão) no checkout —
  o código referencia `fulfillment`, mas falta confirmar o fluxo de UI ponta a
  ponta (especialmente delivery com taxa/endereço no PDV).
- **Campos fiscais de produto para NFC-e** (NCM/CFOP/CSOSN/CEST/origem) — o
  report sugeriu incompletos; precisa confirmar se vivem em `Product.metadata`
  ou se faltam de fato. **Cruza com o bloqueio de credenciais Focus NFe** (gate
  de go-live), então é melhor verificar junto com o smoke fiscal real.
- **Cobertura de atalhos de teclado** — existem handlers; falta mapear o conjunto
  real vs. o spec (WP-1) e cobrir por teste.
- **Reconciliação fire→KDS→commit** (Path B) — sem teste de ciclo fechado
  (operador cancela `fired`, KDS já recebeu). Verificar risco de comanda "solta".

### ⚪ Decisões de produto (suas — não autônomas)

- **Aviso "dinheiro abaixo do total" é warning, não erro** (review_sale) — pode
  ser intencional (pagamento parcial/fiado). Mudar para erro é decisão de regra.
- **Labels de operação hardcoded** ("Dinheiro"/"PIX"/"Balcão") — config via
  Omotenashi é a frente de *surface convergence/config*, não um fix pontual.
- **Health de terminal nunca bloqueia** (impressora obrigatória vs. recibo) —
  decisão operacional.

---

## Recomendação

A Fase C **não** deve virar um refactor amplo do POS unsupervised — o POS está
maduro. O caminho honesto:

1. ✅ Fix de robustez do move_lines (feito).
2. Verificar item-a-item os 🔵 acima (cada um vira tarefa só se confirmado).
3. Cruzar fiscal de produto com o gate de credenciais Focus NFe (go-live).
4. Decisões ⚪ ficam com o Pablo.

Cobertura de testes do surface (vitest) é a área de maior retorno seguro: cart
mutations, payment numpad, move dialog. Candidata a próxima leva autônoma.

---

## Referências

- [PRODUCT-V1-SCOPE-BACKLOG](PRODUCT-V1-SCOPE-BACKLOG.md) · [POS-FIRST-CLASS-PLAN](POS-FIRST-CLASS-PLAN.md) · [POS-UITHING-REDESIGN-PLAN](POS-UITHING-REDESIGN-PLAN.md)
- `surfaces/pos-nuxt/` · `shopman/shop/services/pos.py` · `shopman/backstage/projections/pos.py`
