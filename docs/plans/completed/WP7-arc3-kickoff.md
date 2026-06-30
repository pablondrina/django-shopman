# WP7 · Arc 3 — Checkout/pagamento (Odoo) + manager-PIN por-permissão + caixa cego · kickoff autossuficiente

> Prompt de abertura para sessão limpa. Branch `redesign/surface-excellence`.
> **Arc 1 (seam dado/contrato) e Arc 2 (Presentation TS + 3 telas-núcleo) estão FECHADOS.** O monolito
> `app.vue` morreu: virou shell de ~515 ln; toda a orquestração de venda vive em
> `usePosSale`/`usePosTerminal`; as telas (Tab Board, Sale Workspace) são componentes que consomem a
> `Projection` pela camada `app/presentation/`. Agora é a **tela de Pagamento** (o coração financeiro do
> PDV) recomposta com o mesmo rigor.

## Postura & autonomia
**AUTONOMIA TOTAL** (Pablo, 2026-06-06): decidir por mérito e prosseguir sem perguntar.
**NUNCA menor-diff/menor-esforço** — só a solução mais Simples/Robusta/Elegante pelo mérito
(`feedback_never_recommend_smallest_diff`). Zero gambiarra, zero residual em renames/deleções, **não
inventar features** (notify-me/ACP/WhatsApp-in-chat = WP9). Verde a cada passo; commit coerente por
incremento. Acessibilidade + omotenashi são first-class (`feedback_accessibility_omotenashi_first_class`):
alvos grandes, contraste, idoso em mente — o caixa é ambiente de pressão.

**Core SAGRADO** (`packages/`, intocável sem autorização explícita). `shop/` é orquestrador editável mas
**cada mudança sinalizada**. Antes de "o Core/orquestrador não cobre", assumir que cobre e procurar onde
(`feedback_respect_core_no_reinvent` — o write-side de pagamento já existe em `shop/services/pos.py`:
`close_sale`/`review_sale`/reconciliação + payman + adapters). **Zero política no cliente:**
total/troco/métodos/gates/threshold de manager vêm da `Projection`+`Action[]`; a tela **renderiza**.

## ⚠️ Nomenclatura (travada)
Comanda = `Tab`/`POSTab` (NUNCA "Command"). Ver `feedback_comanda_is_tab_not_command`. Pagamento é
**injeção de tenders estilo Odoo**: o operador injeta valores em formas (dinheiro/PIX/cartão); o método é
**derivado** (sem seletor "misto"), finalizar é travado até cobrir o total. Ver `resolvePayment`.

## Ler primeiro (obrigatório, antes de editar)
- `docs/redesign/05-spec-pos.md` **§2.4 (Pagamento), §1.4 + §3 (manager-approval por permissão), §2.6
  (caixa cego), §1.5 (caixa cego + confirmação otimista)** — a spec.
- `docs/decisions/adr-014-surface-data-presentation-cut.md` — o contrato Projection(dado)/`Action`/
  Presentation(aparência). A Presentation do PDV é TS no Nuxt.
- `project_pos_uithing_redesign_goal` (benchmarks; **Pablo exige fidelidade Odoo no pagamento** — ver
  `project_pos_visual_fidelity_deep_dive`, feedback da tela de pagamento Odoo) + `project_wp7_pos_status`
  (estado consolidado + os 2 gotchas Nuxt abaixo) + `project_card_payment_delegated_stripe`
  (**PCI SAQ A: zero captura de cartão no cliente**; Stripe Checkout/Elements; webhook é o retorno
  confiável) + `project_excellence_refactor_initiative`.

## Estado atual (auditado 2026-06-06 — não re-descobrir)
- **Arquitetura do Nuxt (entregue no Arc 2):**
  - `app/presentation/` — Presentation TS pura: `actions.ts` (Action→affordance), `catalog.ts`,
    `tabBoard.ts`, `numpad.ts`. **Toda nova apresentação de pagamento nasce aqui** (ex.: shape de
    tender/troco/método, mapeamento `Action`→affordance dos botões de pagamento). Testes em
    `tests/presentation.test.ts`.
  - `app/composables/usePosTerminal.ts` — read-side (fetch da Projection via **useFetch** — ver gotcha #1).
  - `app/composables/usePosSale.ts` — write-side: cart + comandos. **A lógica de pagamento JÁ ESTÁ AQUI**
    (`addTender`/`addCashTender`/`removeTender`/`selectTender`/`tenderDigit`/`tenderBackspace`/`tenderClear`/
    `tenderAdd`/`reviewSale`/`prepareCheckout`/`reviewCheckout`/`submitSale`/`currentIntentState`; computeds
    `paymentTotalQ`/`paymentRemainingQ`/`paymentChangeQ`/`paymentCovered`/`selectedTenderIndex`). **Reusar,
    não reinventar.** Manager-approval já trafega: `cart.managerUsername`/`cart.managerPin` →
    `currentIntentState().managerApproval` → intent; o review devolve `requires_manager_approval` +
    `manager_approval_threshold_q`.
  - `app/components/PosCheckoutWorkspace.vue` + `PosCashPanel.vue` — **preservados como estavam (ouro a
    pescar), AINDA NÃO recompostos pela Presentation.** Este arco os recompõe. `PosNumpad` reusável.
- **REST/contrato (byte-estável, Arc 1):** `backstage/api/operations.py` + `backstage/projections/pos.py`
  publicam `checkout` (POSCheckoutContractProjection: sections/fields/tender_methods/discount_*/
  capabilities) e os `Action`s `review_sale`/`close_sale`/`cancel_recent_sale`/`open_cash_shift`/
  `close_cash_shift`/`cash_movement`. `review_sale` devolve POSSaleReviewProjection (totais, troco,
  tender_total, `requires_manager_approval`, threshold, warnings). Schema do intent gerado em
  `app/generated/posContract.ts` (drift-test `shop/tests/test_pos_schema_export.py`).

## O trabalho do Arc 3
1. **Recompor a tela de Pagamento §2.4** (`PosCheckoutWorkspace` → componente(s) limpos sobre a
   Presentation): tela dedicada (não gaveta), métodos com alvos grandes, **numpad p/ dinheiro/troco**
   (reusar `PosNumpad` + `presentation/numpad`), split tender por injeção, prova de pagamento, fluxo
   contínuo (Shopify "single continuous flow"). **Fidelidade Odoo** (ver visual_fidelity_deep_dive). A
   apresentação de tender/método/troco que hoje está inline migra para `app/presentation/` (funções puras
   testadas, ex.: `payment.ts` — shape de linha de tender, "falta/troco", método derivado, `Action`→
   affordance dos botões). **Zero aritmética de política**: total/troco/cobertura vêm do `review` da
   Projection (o cliente só exibe; `paymentCovered` local é gate de UX, o backend é autoritativo).
2. **Manager-approval por-permissão §1.4/§3:** a tela pede PIN de gerente **só quando a Projection diz**
   (`review.requires_manager_approval` / flag de permissão `requires_manager_approval`), não por 4 gates
   fixos. PIN via doorman (`verify_manager_pin`). **Não inventar gate no cliente** — renderizar o que o
   review exige. (O transporte managerApproval já existe em usePosSale.)
3. **Caixa cego §2.6:** recompor `PosCashPanel` (abertura/fechamento/sangria/suprimento) **sem mostrar o
   esperado** (contagem cega). Relatório de turno fica no backoffice (Unfold), não no PDV. A lógica
   (`openCashShift`/`closeCashShift`/`registerCashMovement`) já está em usePosSale.
4. **Cartão = PCI SAQ A:** o PDV **não captura cartão**. Pagamento cartão delega (Stripe Checkout/Elements
   ou terminal físico via adapter); o retorno confiável é o webhook. Renderizar prova/estado de pagamento
   (`POSPaymentResultProjection`: status/qr_code/copy_paste/checkout_url) — **não** processar cartão no Nuxt.
5. **Ordem sugerida (incremento verde por tela):** Pagamento → manager-PIN (entrelaçado) → caixa cego.
   Commit coerente por tela.

## Decisões abertas (decidir por mérito)
- **Onde a apresentação de pagamento mora:** novo `app/presentation/payment.ts` (provável) consumido por
  um `PosPaymentWorkspace.vue` recomposto. Avaliar quebrar `PosCheckoutWorkspace` (hoje monolítico de
  checkout) em sub-componentes (métodos / numpad-dinheiro / split / cliente-inline / fulfillment).
- **D2 (layout cart-dir Shopify × ticket-esq Odoo) e D3 (impressão de comprovante)** = shell visual,
  **Arc 5** — não travar aqui (mas o fluxo de pagamento contínuo é deste arco).
- Cliente inline (criar/buscar Guestman) na tela de pagamento: já há `lookupCustomer`; avaliar UX.

## Gates (verde ao fim de cada tela)
- `cd surfaces/pos-uithing-nuxt && export PATH="/opt/homebrew/bin:$PATH"` → `npx nuxi typecheck`
  (ignorar erros **pré-existentes** conhecidos em `djangoProxy.ts`/`nuxt.config.ts` — `noUnusedLocals`
  está OFF) + `npx vitest run` (35 baseline; somar testes de `presentation/payment`).
- Se tocar backend (projection/serializer/endpoint): `pytest shopman/shop/tests shopman/backstage/tests -q`
  (e `storefront/tests` se cruzar a fronteira). **NÃO** `make test-framework` (`project_backstage_pos_test_pollution`).
  `make admin` só se tocar Admin/Unfold. Se mexer no intent/schema: regenerar `posContract.ts` via
  `manage.py export_pos_schema` e checar o drift-test.

## Preview ao vivo (prova obrigatória, `preview_*`) — receita validada
- Servers em `.claude/launch.json`: **django** (porta 8000) + **pos** (3002). `preview_start` em cada.
- Browser via **`http://127.0.0.1:3002/`** (gotcha IPv6 426 em `localhost`).
- **Autenticar sem digitar senha/PIN** (proibido digitar credencial em form): semear sessão server-side e
  injetar o cookie:
  ```bash
  .venv/bin/python manage.py shell  # SessionStore + _auth_user_id/_auth_user_backend/_auth_user_hash
                                    # + pos_active_operator = operator_card(u); s.create(); print(s.session_key)
  ```
  então `document.cookie="sessionid=<key>; path=/"` + `window.location.href="http://127.0.0.1:3002/"`.
- **Auto-lock atrapalha:** zerar p/ testar via `POSTerminal.default().metadata['auto_lock_seconds']=0`
  (restaurar removendo a chave ao fim — não deixar resíduo no db dev).
- Screenshot de cada tela tocada; `preview_console_logs level=error` limpo; `preview_network` p/ os POSTs.

### ⚠️ 2 gotchas Nuxt (custaram tempo no Arc 2 — não repetir)
1. **`usePosTerminal` usa `useFetch`, não `useAsyncData`+`$fetch`.** Só `useFetch` transfere o payload SSR
   de forma confiável; com useAsyncData o SSR renderiza destravado mas o cliente re-semeia o lock com
   `operator=null` → trava por hidratação.
2. **Composable `.ts` chamado depois do `await` do shell NÃO pode chamar composable Nuxt**
   (useCookie/useRuntimeConfig/usePosApiPath/usePosAction) — o contexto de instância não sobrevive ao
   await fora do `<script setup>`. Padrão: o shell cria as primitivas Nuxt e passa como **deps**; o
   composable usa só primitivas vue (ref/reactive/computed/watch/nextTick) + utils puros. Lifecycle hooks
   (onMounted) ficam no shell.

## Ao terminar
Commit coerente por tela; atualizar `project_wp7_pos_status` (Arc 3 progresso/done). Seguir para **Arc 4**
(`move_lines` / fire-to-kitchen progressivo) e depois **Arc 5** (shell visual: D2 layout + D3 impressão +
fidelidade benchmark).
```bash
cd surfaces/pos-uithing-nuxt && export PATH="/opt/homebrew/bin:$PATH" && npx nuxi typecheck && npx vitest run
```
