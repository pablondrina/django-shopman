# Storefront Nuxt parity action plan

**Status:** plano de acao; nao implementar antes de aprovacao explicita  
**Data:** 2026-05-14  
**Escopo:** storefront Nuxt v4 como porte da referencia madura Django/Penguin
**Canon:** projections/API/backend em `shopman/storefront`, core/orquestrador Shopman e contrato em `docs/reference/storefront-surface-parity-contract.md`
**Referencia de implementacao:** `shopman/storefront/templates/storefront` e fluxos Django/Penguin, apenas para descoberta de paridade de UX/copy/recovery
**Alvo:** `surfaces/storefront-nuxt`

## Regra de execucao

- Django/Penguin e referencia de implementacao completa/madura, nao canon de dominio. Nuxt e adaptador visual/UX sobre contratos, projections e endpoints existentes.
- Nao criar alias, rotas duplicadas ou camada de compatibilidade ad hoc. Quando uma URL publica precisar existir, ela deve ser a unica rota publica daquela tela. Arquivos/codigo em ingles; URL publica em portugues somente via `definePageMeta({ path })`.
- Nao inventar promessa operacional em copy. Texto sobre disponibilidade, horario, pagamento, preparo, entrega, tracking e recuperacao deve vir de projection/backend ou, enquanto o contrato backend nao existir, da referencia Django/Penguin como material de descoberta.
- Toda acao destrutiva ou sensivel precisa de confirmacao proporcional ao risco, foco acessivel e estado final reconciliado com backend.
- Cada WP deve adicionar ou ajustar testes antes/junto da implementacao. P0/P1 sem teste automatizado bloqueia.
- Browser local e obrigatorio para WPs com UI. Rodar em `http://127.0.0.1:3000` com Django em `http://127.0.0.1:8000`.
- Nao usar atalhos de "compatibilidade" para esconder perda de contrato. Corrigir a fonte, projection, endpoint ou componente certo.

## Ordem recomendada

1. WP-00: baseline executavel e guardrails.
2. WP-01: auth, trust device, access links e welcome gate.
3. WP-02: conta, memoria, preferencias, dados e enderecos.
4. WP-03: checkout payload, passos e confiabilidade transacional.
5. WP-04: pagamento, recovery e confirmacao.
6. WP-05: tracking, historico, pedido ativo, reorder e estoque.
7. WP-06: home, menu, catalogo e PDP ricos.
8. WP-07: copy factual e omotenashi canonico.
9. WP-08: design system Nuxt e refinamento mobile.
10. WP-09: PWA, offline, gestos e haptic.
11. WP-10: QA Browser, a11y, performance e release gate.

## WP-00 - Baseline executavel e guardrails de paridade

**IDs cobertos:** todos, com foco em `NUXT-ROUTE-001`, `A11Y-ACTION-001`, `COPY-FACT-001`, `CHECKOUT-PAYLOAD-001`, `REORDER-001`, `AUTH-SESSION-002`.

**Objetivo:** transformar lacunas ainda soltas em testes/ledger executaveis antes de mexer nas telas.

**Contexto atual:**

- O contrato base esta em `docs/reference/storefront-surface-parity-contract.md`.
- O ledger esta em `docs/reference/storefront-surface-porting-ledger.json`.
- A suite atual esta em `shopman/storefront/tests/test_storefront_nuxt_parity_contract.py`.
- Alguns IDs existem no contrato mas ainda nao sao testados de forma explicita por ID, principalmente `CHECKOUT-PAYLOAD-001`, `REORDER-001`, `COPY-FACT-001`, `A11Y-ACTION-001` e `AUTH-SESSION-002`.

**Escopo provavel:**

- `docs/reference/storefront-surface-parity-contract.md`
- `docs/reference/storefront-surface-porting-ledger.json`
- `shopman/storefront/tests/test_storefront_nuxt_parity_contract.py`
- opcional: novos testes focados em `shopman/storefront/tests/api/`

**Entregas:**

- Cada P0/P1 relevante para o Nuxt com teste ou verificacao estatica explicita.
- Guardrail "sem alias/compatibilidade": page files em ingles, URLs publicas canonicas, sem `alias:` e sem rotas inglesas paralelas.
- Guardrail de actions sensiveis: logout, trocar conta, excluir conta, revogar dispositivo, excluir endereco, cancelar pedido, liberar reserva e substituir carrinho por reorder.
- Guardrail de copy factual: frases operacionais proibidas/local-only mapeadas para projection/backend ou referencia Django/Penguin documentada.

**Aceite:**

- `python -m pytest shopman/storefront/tests/test_storefront_nuxt_parity_contract.py -q` passa.
- O teste falha se alguem reintroduzir `alias:`, page file em portugues, rota inglesa publica paralela ou acao sensivel direta sem modal.
- O ledger aponta arquivos atuais e existentes.

**Prompt autocontido:**

```text
Estamos no repo django-shopman. Antes de implementar novas correcoes no storefront Nuxt v4, endureca o baseline executavel de paridade.

Contexto:
- Django/Penguin e referencia de implementacao madura do porte; o canon e projection/API/backend.
- O contrato esta em docs/reference/storefront-surface-parity-contract.md.
- O ledger esta em docs/reference/storefront-surface-porting-ledger.json.
- A suite de paridade esta em shopman/storefront/tests/test_storefront_nuxt_parity_contract.py.
- Regras obrigatorias: sem alias, sem rotas duplicadas de compatibilidade, arquivos/codigo em ingles, URLs publicas canonicas via definePageMeta({ path }) quando necessario.

Tarefa:
1. Mapeie todos os IDs P0/P1 ainda sem teste explicito no arquivo de paridade.
2. Adicione guardrails para CHECKOUT-PAYLOAD-001, REORDER-001, COPY-FACT-001, A11Y-ACTION-001 e AUTH-SESSION-002.
3. Garanta que o ledger aponta para referencias de implementacao, backend contracts, arquivos Nuxt e verificacoes existentes.
4. Nao implemente comportamento de produto neste WP; apenas contratos, testes e ledger.

Aceite:
- python -m pytest shopman/storefront/tests/test_storefront_nuxt_parity_contract.py -q passa.
- O teste falha se houver alias de rota, page file em portugues, rota inglesa publica paralela ou acao sensivel sem confirmacao.
- O teste falha se copy operacional local inventada nao estiver coberta por projection/backend ou referencia Django/Penguin documentada.
```

## WP-01 - Auth, trust device, access links e welcome gate

**IDs cobertos:** `AUTH-PHONE-BR-001`, `AUTH-PHONE-BR-002`, `AUTH-SESSION-001`, `AUTH-SESSION-002`, `AUTH-OTP-001`, `AUTH-DEVICE-TRUST-001`, `AUTH-ACCESS-LINK-001`, `AUTH-WELCOME-GATE-001`, `AUTH-PHONE-INTL-001`.

**Objetivo:** portar o fluxo de entrada recorrente do Penguin sem perder telefone, sessao, skip-OTP seguro, links de acesso e confirmacao de nome.

**Contexto atual:**

- Nuxt login: `surfaces/storefront-nuxt/app/pages/login.vue`.
- Shell/session: `AppHeader.vue`, `ShopBottomTabs.vue`, `useShopSession.ts`.
- Backend auth API: `shopman/storefront/api/auth.py`.
- Penguin auth: `shopman/storefront/templates/storefront/login.html`, `partials/auth_verify_code.html`, `partials/auth_confirmed.html`, `partials/auth_trusted_greeting.html`.
- Django trust/access/welcome: `shopman/storefront/views/auth.py`, `views/access.py`, `views/welcome.py`, `middleware.py`.
- URLs canonicas Django: `/a/`, `/auth/access/<token>/`, `/auth/device-check/`, `/auth/trust-device/`, `/bem-vindo/`.

**Escopo provavel:**

- `surfaces/storefront-nuxt/app/pages/login.vue`
- `surfaces/storefront-nuxt/app/pages/welcome.vue` se rota Nuxt unica for necessaria, com `path: '/bem-vindo'`
- `surfaces/storefront-nuxt/server/routes/auth/[...path].ts`
- decisao explicita para access links: Django continua dono canonico de `/a/` e `/auth/access/<token>/`, ou Nuxt assume rota canonica unica; sem shim, alias ou rota duplicada
- `shopman/storefront/api/auth.py`
- `shopman/storefront/api/urls.py`
- testes em `shopman/storefront/tests/api/test_auth_session.py`, `test_auth_intents.py`, `test_storefront_nuxt_parity_contract.py`

**Entregas:**

- UI de OTP valida exatamente 6 digitos enquanto backend exigir 6.
- Telefone BR `55 43 984049009` e variantes seguem para backend sem truncar e verificam usando o telefone normalizado retornado.
- Modo internacional explicito quando habilitado; nunca confundir DDI com DDD.
- Trust device completo: checagem de dispositivo confiavel, skip-OTP seguro, consentimento apos OTP para confiar, cookie HttpOnly pelo backend.
- Access links preservam sessao e destino seguro para rotas Nuxt sem expor ref adivinhado; a propriedade da rota fica canonica em uma superficie, sem duplicacao.
- Welcome gate Nuxt para usuario autenticado sem nome, sem bloquear API/static/logout/POST.
- Sessao autenticada nao e sobrescrita por home anonima.

**Aceite:**

- Telefone `55 43 984049009` autentica como `+5543984049009`.
- Usuario com cookie autenticado nao ve "Entrar" no header/bottom tabs apos reload.
- Usuario sem nome cai em `/bem-vindo` antes de paginas GET da loja e volta ao `next` apos salvar.
- Trust device so pula OTP com cookie valido e cliente correto.
- Access link com `next=/tracking/<ref>` cria sessao e navega para destino seguro Nuxt.
- `python -m pytest packages/utils/shopman/utils/tests/test_phone.py shopman/storefront/tests/api/test_auth_session.py shopman/storefront/tests/test_auth_intents.py shopman/storefront/tests/test_storefront_nuxt_parity_contract.py -q` passa.
- Browser: `/login?next=/checkout`, trust device, `/bem-vindo`, header/bottom tabs sem estado stale.

**Prompt autocontido:**

```text
Implemente a paridade de auth do storefront Nuxt v4 usando Django/Penguin como referencia madura de UX/fluxo.

Contexto:
- Django/Penguin nao e canon de dominio; e referencia de implementacao. Nao invente fluxo novo quando projection/API/backend ou a referencia madura ja cobrem o caso.
- Nuxt login atual: surfaces/storefront-nuxt/app/pages/login.vue.
- Estado de sessao Nuxt: useShopSession.ts, AppHeader.vue, ShopBottomTabs.vue.
- Backend API: shopman/storefront/api/auth.py e shopman/storefront/api/urls.py.
- Fluxos canonicos Django: views/auth.py, views/access.py, views/welcome.py, middleware.py.
- Templates canonicos: login.html, auth_verify_code.html, auth_confirmed.html, auth_trusted_greeting.html, welcome.html.
- Contratos: AUTH-PHONE-BR-001/002, AUTH-SESSION-001/002, AUTH-OTP-001, AUTH-DEVICE-TRUST-001, AUTH-ACCESS-LINK-001, AUTH-WELCOME-GATE-001, AUTH-PHONE-INTL-001.
- Regra: sem alias, sem rota duplicada de compatibilidade. Arquivos/codigo em ingles; URL publica unica em portugues se existir.

Tarefa:
1. Alinhe OTP para exatamente 6 digitos e copy baseada na resposta real do backend.
2. Preserve telefone digitado sem truncamento e use o phone normalizado retornado para verify.
3. Adicione suporte explicito a telefone internacional sem quebrar Brasil como default.
4. Porte trust device: device check, skip-OTP seguro e consentimento para salvar dispositivo depois de OTP.
5. Garanta access links seguros para destinos Nuxt.
6. Implemente welcome gate para cliente autenticado sem nome/sujo.
7. Garanta que home anonima nao sobrescreve sessao autenticada.
8. Adicione testes de API, contrato Nuxt e smoke Browser.

Aceite:
- Usuario autenticado nunca ve CTA "Entrar" apos reload SSR.
- Trust device so pula OTP com cookie valido e cliente correto.
- /bem-vindo nao bloqueia API/static/logout/POST.
- Access link sanitiza next e nao vaza pedido por ref adivinhado.
- Testes focados passam e npm run build passa em surfaces/storefront-nuxt.
```

## WP-02 - Conta, memoria do cliente, preferencias, dados e enderecos

**IDs cobertos:** `CUSTOMER-MERGE-001`, `CUSTOMER-HISTORY-001`, `CUSTOMER-MEMORY-001`, `CUSTOMER-DEVICE-MGMT-001`, `CUSTOMER-ADDRESS-FALLBACK-001`, `CUSTOMER-ACCOUNT-DELETE-001`, `CUSTOMER-CONSENT-PREFS-001`, `CUSTOMER-DATA-EXPORT-001`, `CUSTOMER-LOYALTY-DETAIL-001`.

**Objetivo:** fazer a conta Nuxt deixar de ser painel parcial e virar a memoria operacional que a versao Penguin ja tinha.

**Contexto atual:**

- Nuxt conta: `surfaces/storefront-nuxt/app/pages/account.vue`.
- Modal endereco: `AddressFormModal.vue`, `AddressAutocomplete.vue`.
- Backend account API: `shopman/storefront/api/account.py`, `api/urls.py`.
- Projections: `shopman/storefront/projections/account.py`, `order_history.py`.
- Penguin: `account.html`, `partials/profile_display.html`, `profile_form.html`, `address_picker.html`, `device_list.html`, `food_prefs.html`, `notification_prefs.html`.
- Bug historico: `place_id` ausente nao pode causar `NOT NULL constraint failed`.

**Escopo provavel:**

- `surfaces/storefront-nuxt/app/pages/account.vue`
- `surfaces/storefront-nuxt/app/components/AddressFormModal.vue`
- `surfaces/storefront-nuxt/app/components/AddressAutocomplete.vue`
- `surfaces/storefront-nuxt/app/types/shopman.ts`
- `shopman/storefront/api/account.py`
- `shopman/storefront/projections/account.py`
- testes em `shopman/storefront/tests/api/test_account_summary.py`, `test_account_addresses.py`, `test_guestman_order_history.py`, `packages/guestman/.../test_merge.py`

**Entregas:**

- Perfil/nome/telefone/endereco/preferencias persistem no backend antes de aparecerem como memoria de UI.
- Endereco salva com autocomplete, CEP ou manual sem exigir `place_id` quando fallback canonico e permitido.
- Toggling real de preferencias alimentares e notificacoes.
- Exportacao LGPD disponivel e testada.
- Exclusao de conta com modal forte, confirmacao textual ou checkbox, logout e shell sem dados pessoais.
- Fidelidade detalhada quando projection entregar tier, pontos, carimbos, cartela e transacoes.
- Historico de pedidos da conta correta por `customer_ref` e telefone canonico.

**Aceite:**

- Falha de PATCH/POST nao atualiza UI local como sucesso.
- Pedido criado no checkout aparece no historico da conta correta.
- Endereco manual sem `place_id` salva por fallback e volta no checkout.
- Preferencias e notificacoes persistem e refletem retorno da API.
- Export baixa JSON canonico.
- Excluir conta limpa sessao, dados locais e shell.
- Testes de account/address/merge/history passam.

**Prompt autocontido:**

```text
Implemente a paridade da conta Nuxt com a conta Django/Penguin.

Contexto:
- Nuxt conta: surfaces/storefront-nuxt/app/pages/account.vue.
- Componentes de endereco: AddressFormModal.vue e AddressAutocomplete.vue.
- Backend: shopman/storefront/api/account.py, projections/account.py, projections/order_history.py.
- Canonico Penguin: account.html e partials profile_display.html, profile_form.html, address_picker.html, device_list.html, food_prefs.html, notification_prefs.html.
- Contratos: CUSTOMER-MERGE-001, CUSTOMER-HISTORY-001, CUSTOMER-MEMORY-001, CUSTOMER-DEVICE-MGMT-001, CUSTOMER-ADDRESS-FALLBACK-001, CUSTOMER-ACCOUNT-DELETE-001, CUSTOMER-CONSENT-PREFS-001, CUSTOMER-DATA-EXPORT-001, CUSTOMER-LOYALTY-DETAIL-001.

Tarefa:
1. Garanta que memoria de UI so aparece apos persistencia backend.
2. Feche todos os caminhos de endereco: autocomplete, CEP/manual, default, delete, edit.
3. Porte toggles de preferencias alimentares e notificacoes.
4. Exponha exportacao LGPD.
5. Implemente exclusao de conta com confirmacao forte e limpeza de sessao.
6. Renderize fidelidade detalhada quando dados existirem.
7. Garanta historico por customer_ref/telefone canonico.
8. Adicione testes de API e paridade Nuxt.

Aceite:
- Nenhum sucesso local falso em falha de persistencia.
- Endereco sem place_id nao quebra.
- Pedido web aparece no historico do cliente correto.
- Acoes destrutivas exigem modal e foco acessivel.
- Testes focados passam e npm run build passa.
```

## WP-03 - Checkout payload, passos e confiabilidade transacional

**IDs cobertos:** `CHECKOUT-IDEMP-001`, `CHECKOUT-PAYLOAD-001`, `CHECKOUT-SWITCH-ACCOUNT-001`, `CHECKOUT-STEP-INVARIANTS-001`, `CUSTOMER-HISTORY-001`, `RATE-LIMIT-RECOVERY-001`.

**Objetivo:** fazer o checkout Nuxt operar com o mesmo contrato transacional robusto do backend/Penguin.

**Contexto atual:**

- Nuxt checkout: `surfaces/storefront-nuxt/app/pages/checkout.vue`.
- Componentes: `CheckoutDatePicker.vue`, `CheckoutStep.vue`, `AddressFormModal.vue`.
- Backend checkout: `shopman/storefront/api/views.py`, `api/serializers.py`, `projections/checkout.py`, `services/checkout.py`.
- Penguin checkout: `shopman/storefront/templates/storefront/checkout.html`, `partials/checkout_order_summary.html`, `components/date_picker.html`, `partials/address_picker.html`.

**Escopo provavel:**

- `surfaces/storefront-nuxt/app/pages/checkout.vue`
- `surfaces/storefront-nuxt/app/components/CheckoutDatePicker.vue`
- `surfaces/storefront-nuxt/app/components/AddressFormModal.vue`
- `surfaces/storefront-nuxt/app/types/shopman.ts`
- `shopman/storefront/api/serializers.py`
- `shopman/storefront/api/views.py`
- testes em `shopman/storefront/tests/test_checkout_defaults.py`, `test_checkout_error_paths.py`, `test_concurrent_checkout.py`, `test_loyalty_checkout.py`, `test_slot_validation.py`, `tests/web/test_web_checkout.py`

**Entregas:**

- Payload final canonico: fulfillment, delivery/pickup, data, slot, saved address id, structured address, `place_id`, coordenadas, complemento, instrucoes, payment method, loyalty e observacoes.
- Idempotency key estavel por tentativa e renovada apenas quando apropriado.
- Recovery pos-criacao: se pedido foi criado e navegacao falhou, mostrar pedido e proxima acao.
- Trocar conta preserva carrinho, exige modal e volta para login com `next=/checkout`.
- Invariantes de etapa: pickup nao pede endereco; delivery nao avanca sem endereco valido; passos bloqueados nao simulam progresso.
- Rate limit de checkout mostra espera/retry/contato.

**Aceite:**

- Teste estatico ou unitario prova que Nuxt envia nomes canonicos do serializer.
- Retry do submit nao cria pedido duplicado.
- Delivery sem endereco nao chega ao POST final.
- Pickup nao renderiza etapa de endereco.
- Falha 429 mostra estado de recuperacao, nao toast generico.
- Browser mobile: fluxo anonimo redireciona para login, volta ao checkout, revisa pedido e respeita gate de pagamento.

**Prompt autocontido:**

```text
Endureca o checkout Nuxt v4 para paridade transacional com Django/Penguin.

Contexto:
- Nuxt checkout: surfaces/storefront-nuxt/app/pages/checkout.vue.
- Backend contrato: shopman/storefront/api/views.py, api/serializers.py, projections/checkout.py.
- Referencia Penguin: templates/storefront/checkout.html, partials/checkout_order_summary.html, components/date_picker.html, partials/address_picker.html.
- Contratos: CHECKOUT-IDEMP-001, CHECKOUT-PAYLOAD-001, CHECKOUT-SWITCH-ACCOUNT-001, CHECKOUT-STEP-INVARIANTS-001, RATE-LIMIT-RECOVERY-001.

Tarefa:
1. Audite o serializer/backend para listar os campos canonicos aceitos.
2. Ajuste o payload Nuxt para enviar todos os campos canonicos relevantes.
3. Garanta idempotency key estavel por tentativa e recovery quando pedido ja foi criado.
4. Feche invariantes de passos: pickup sem endereco; delivery sem avanco se endereco invalido.
5. Preserve carrinho ao trocar conta e exija confirmacao.
6. Adicione recovery para 429 e erros de commit.
7. Adicione testes cobrindo payload, idempotencia e step invariants.

Aceite:
- Testes de checkout existentes e novos passam.
- python -m pytest shopman/storefront/tests/test_storefront_nuxt_parity_contract.py -q passa.
- npm run build passa em surfaces/storefront-nuxt.
- Browser mobile valida login -> checkout -> review -> submit/recovery.
```

## WP-04 - Pagamento, recovery e confirmacao

**IDs cobertos:** `PAYMENT-GATE-001`, `PAYMENT-NUXT-001`, `PAYMENT-RECOVERY-001`, `PAYMENT-ERROR-DETAIL-001`, `ORDER-CONFIRMATION-001`, `RATE-LIMIT-RECOVERY-001`.

**Objetivo:** tratar pagamento como fluxo critico com next action clara, nao apenas uma pagina bonita.

**Contexto atual:**

- Nuxt payment: `surfaces/storefront-nuxt/app/pages/order/[ref]/payment.vue`.
- Nuxt confirmation: `surfaces/storefront-nuxt/app/pages/order/[ref]/confirmation.vue`.
- Backend payment: `shopman/storefront/api/payment.py`, `projections/payment.py`.
- Penguin payment: `_payment_pix.html`, `_payment_card.html`, `partials/payment_status.html`, `payment.html`, `order_confirmation.html`.
- Tracking ja aplica gate com `requires_payment_gate` quando backend exige.

**Escopo provavel:**

- `surfaces/storefront-nuxt/app/pages/order/[ref]/payment.vue`
- `surfaces/storefront-nuxt/app/pages/order/[ref]/confirmation.vue`
- `surfaces/storefront-nuxt/app/types/shopman.ts`
- `shopman/storefront/api/payment.py`
- `shopman/storefront/projections/payment.py`
- testes em `shopman/storefront/tests/web/test_web_payment.py`, `test_projections_payment.py`, `test_web_order_tracking.py`

**Entregas:**

- PIX: copiar com fallback, selecao manual, erro claro e retry.
- Cartao hosted checkout: estado e CTA canonicos, erro de gateway, cancelado/expirado/stale generation.
- Polling com estado de falhas repetidas e botao "Atualizar".
- `payment.error_message`, `promise.recovery`, `promise.next_event`, `deadline_at` e stale state visiveis como proxima acao.
- Confirmacao Nuxt com resumo, ETA, tracking, share e suporte; ou decisao documentada de aposentadoria se nao for usada.
- 429 em payment/status com espera/retry.

**Aceite:**

- `/pedido/<ref>/pagamento` cobre PIX, card, pendente, expirado, erro, cancelado e pago.
- Clipboard negado nao quebra fluxo.
- Tracking de pedido digital pendente redireciona para payment gate ate liberar.
- Browser smoke em payment desconhecido e payment real/fixture sem console error.
- Testes de payment/tracking passam.

**Prompt autocontido:**

```text
Implemente a camada de confianca de pagamento no storefront Nuxt.

Contexto:
- Nuxt payment: surfaces/storefront-nuxt/app/pages/order/[ref]/payment.vue.
- Nuxt confirmation: surfaces/storefront-nuxt/app/pages/order/[ref]/confirmation.vue.
- Backend: shopman/storefront/api/payment.py e projections/payment.py.
- Canonico Penguin: _payment_pix.html, _payment_card.html, partials/payment_status.html, payment.html, order_confirmation.html.
- Contratos: PAYMENT-GATE-001, PAYMENT-NUXT-001, PAYMENT-RECOVERY-001, PAYMENT-ERROR-DETAIL-001, ORDER-CONFIRMATION-001, RATE-LIMIT-RECOVERY-001.

Tarefa:
1. Renderize todos os estados relevantes da projection de payment.
2. Adicione recovery para copiar PIX, polling, gateway error, expirado, cancelado, stale generation e 429.
3. Garanta que error_message, recovery, next_event e deadlines aparecem como proxima acao.
4. Complete a rota de confirmacao Nuxt ou documente e teste sua aposentadoria.
5. Adicione testes e Browser smoke.

Aceite:
- Payment digital pendente nao cai em tracking final.
- Clipboard negado oferece copia manual.
- Polling falho mostra atualizar/retry.
- Testes web/API de payment e tracking passam.
- npm run build passa.
```

## WP-05 - Tracking, historico, pedido ativo, reorder e estoque

**IDs cobertos:** `TRACKING-001`, `TRACKING-PROMISE-LIVE-001`, `TRACKING-RATING-001`, `REORDER-001`, `ORDER-HISTORY-FILTER-001`, `ACTIVE-ORDER-BADGE-001`, `CART-STOCK-ERROR-001`, `RATE-LIMIT-RECOVERY-001`.

**Objetivo:** preservar o ciclo de vida pos-pedido da versao Penguin: acompanhar, avaliar, repetir e recuperar falhas item a item.

**Contexto atual:**

- Nuxt tracking: `surfaces/storefront-nuxt/app/pages/tracking/[ref].vue`.
- Nuxt reorder: `useReorder.ts`, `ReorderConflictModal.vue`.
- Nuxt cart/stock: `useCartState.ts`, `cart.vue`, `CartLineItem.vue`.
- Nuxt navigation: `ShopBottomTabs.vue`.
- Backend tracking/history: `shopman/storefront/api/tracking.py`, `projections/order_tracking.py`, `projections/order_history.py`, `services/orders.py`.
- Penguin: `order_tracking.html`, `order_history.html`, `partials/order_live.html`, `partials/order_status.html`, `partials/reorder_conflict_modal.html`, `partials/stock_error_modal.html`.

**Escopo provavel:**

- `surfaces/storefront-nuxt/app/pages/tracking/[ref].vue`
- `surfaces/storefront-nuxt/app/pages/account.vue`
- `surfaces/storefront-nuxt/app/components/ShopBottomTabs.vue`
- `surfaces/storefront-nuxt/app/composables/useReorder.ts`
- `surfaces/storefront-nuxt/app/components/ReorderConflictModal.vue`
- `surfaces/storefront-nuxt/app/composables/useCartState.ts`
- `shopman/storefront/api/tracking.py`
- `shopman/storefront/api/surface.py`
- `shopman/storefront/projections/order_tracking.py`
- `shopman/storefront/projections/order_history.py`
- testes em `tests/web/test_web_order_tracking.py`, `test_web_tracking.py`, `test_stock_error_ux.py`, `test_guestman_order_history.py`

**Entregas:**

- Tracking com status canonicos, countdown, freshness/stale state, recovery, next_event, deadline e SSE/polling.
- Rating pos-entrega quando `can_rate` vier da projection, sem duplicar voto.
- Historico com filtros `todos`, `ativos`, `anteriores`, status label/color e recompra por pedido.
- Bottom nav com badge de pedido ativo para cliente autenticado, atualizado periodicamente.
- Reorder com modo explicito append/replace, confirmacao quando substitui carrinho, skipped item a item com motivo.
- Erro de estoque/hold vira modal/feedback rico com itens afetados, nao apenas toast generico.
- Rate limit em tracking/reorder/cart com wait/retry/contact.

**Aceite:**

- Pedido ativo aparece no bottom nav sem reload manual.
- Pedido entregue com `can_rate` permite avaliar uma vez.
- Reorder com itens indisponiveis mostra nomes/motivos.
- Remover/liberar reserva exige confirmacao especifica.
- 409 de estoque mostra dados ricos.
- Testes de tracking/history/reorder/stock passam.

**Prompt autocontido:**

```text
Implemente paridade de tracking, historico, reorder e estoque no Nuxt.

Contexto:
- Nuxt tracking: surfaces/storefront-nuxt/app/pages/tracking/[ref].vue.
- Nuxt reorder: app/composables/useReorder.ts e ReorderConflictModal.vue.
- Nuxt cart: useCartState.ts, pages/cart.vue, CartLineItem.vue.
- Backend: api/tracking.py, api/surface.py, projections/order_tracking.py, projections/order_history.py, services/orders.py.
- Canonico Penguin: order_tracking.html, order_history.html, partials/order_live.html, order_status.html, reorder_conflict_modal.html, stock_error_modal.html.
- Contratos: TRACKING-001, TRACKING-PROMISE-LIVE-001, TRACKING-RATING-001, REORDER-001, ORDER-HISTORY-FILTER-001, ACTIVE-ORDER-BADGE-001, CART-STOCK-ERROR-001, RATE-LIMIT-RECOVERY-001.

Tarefa:
1. Complete tracking com promise live, stale/freshness, deadlines, recovery e next_event.
2. Complete avaliacao pos-entrega.
3. Complete historico com filtros e recompra por pedido.
4. Adicione badge de pedido ativo no bottom nav.
5. Enriqueça reorder com append/replace explicito e skipped item a item.
6. Troque erros pobres de estoque/hold por modal/feedback rico.
7. Adicione recovery para 429.
8. Teste tudo e rode Browser nas rotas relevantes.

Aceite:
- Testes de tracking/history/stock/reorder passam.
- Browser mostra tracking ativo, tracking finalizado, reorder com conflito e carrinho com erro de estoque.
- npm run build passa.
```

## WP-06 - Home, menu, catalogo e PDP ricos

**IDs cobertos:** `CATALOG-HAPPY-HOUR-001`, `CATALOG-FAVORITE-CATEGORY-001`, `CATALOG-SEARCH-NAV-001`, `HOME-LIVE-AVAILABILITY-001`, `PDP-RICH-DETAIL-001`, `NUXT-ROUTE-001`.

**Objetivo:** recuperar descoberta, disponibilidade real e riqueza de produto do Penguin sem copiar tokens visuais.

**Contexto atual:**

- Nuxt home/menu/PDP: `index.vue`, `menu.vue`, `menu/[category].vue`, `product/[sku].vue`.
- Componentes: `HeroCarousel.vue`, `ContextualBanners.vue`, `ProductCard.vue`, `ProductStepper.vue`, `PlannedHoldBadge.vue`.
- Backend projections: `projections/home.py`, `catalog.py`, `product_detail.py`, `services/product_cards.py`.
- Penguin: `home.html`, `menu.html`, `product_detail.html`, `partials/availability_preview.html`, `_catalog_item_grid.html`, `shop_status_badge.html`, `urgency_badge.html`, `stock_error_modal.html`.

**Escopo provavel:**

- `surfaces/storefront-nuxt/app/pages/index.vue`
- `surfaces/storefront-nuxt/app/pages/menu.vue`
- `surfaces/storefront-nuxt/app/pages/menu/[category].vue` com objetivo de remover shim se a projection parar de emitir rota legada
- `surfaces/storefront-nuxt/app/pages/product/[sku].vue`
- `surfaces/storefront-nuxt/app/components/ProductCard.vue`
- `surfaces/storefront-nuxt/app/types/shopman.ts`
- `shopman/storefront/projections/catalog.py`
- `shopman/storefront/projections/product_detail.py`
- testes em `test_catalog_projection_ifood.py`, `test_home_reorder.py`, `test_happy_hour_badge.py`, `test_favorite_category.py`, `tests/web/test_projections_product_detail.py`

**Entregas:**

- Home com disponibilidade real/atualizavel e copy factual.
- Menu com happy hour ativo/inativo, categoria favorita, busca accent-insensitive, `aria-live`, rail sem sobreposicao e scroll-spy/centering.
- Remocao de rota shim/compat se `/menu/<category>/` estiver sendo usado apenas para cobrir URL emitida errada; corrigir emissao na projection.
- PDP renderiza componentes/combo, ingredientes, alergenos/dieta, tabela nutricional, conservacao, serve, trace notice e disponibilidade/hold.
- Icones vindos do backend passam por allowlist/fallback Nuxt.

**Aceite:**

- Browser mobile em home/menu/PDP sem sobreposicao.
- Zero warning de rota inexistente e zero warning de icone invalido.
- Busca sem acento encontra item com acento.
- Categoria favorita e happy hour aparecem apenas quando projection sustenta.
- PDP rica cobre campos da projection.
- Testes de projection/paridade passam.

**Prompt autocontido:**

```text
Complete paridade de home, menu, catalogo e PDP do storefront Nuxt.

Contexto:
- Nuxt: pages/index.vue, pages/menu.vue, pages/menu/[category].vue, pages/product/[sku].vue.
- Componentes: HeroCarousel.vue, ContextualBanners.vue, ProductCard.vue, ProductStepper.vue.
- Backend: projections/home.py, catalog.py, product_detail.py, services/product_cards.py.
- Canonico Penguin: home.html, menu.html, product_detail.html, availability_preview.html, _catalog_item_grid.html, shop_status_badge.html, urgency_badge.html.
- Contratos: CATALOG-HAPPY-HOUR-001, CATALOG-FAVORITE-CATEGORY-001, CATALOG-SEARCH-NAV-001, HOME-LIVE-AVAILABILITY-001, PDP-RICH-DETAIL-001, NUXT-ROUTE-001.
- Regra: sem alias/compatibilidade. Corrigir projection/URL emitida em vez de manter shim quando possivel.

Tarefa:
1. Use todos os sinais relevantes de home/catalog/PDP projections.
2. Renderize happy hour, categoria favorita e disponibilidade real sem copy inventada.
3. Corrija busca, rail, scroll-spy e aria-live.
4. Complete PDP rica: componentes, ingredientes, alergenos, dieta, nutricao, conservacao, serve e trace notice.
5. Normalize icones por allowlist/fallback.
6. Elimine warnings de rota e shims desnecessarios.
7. Teste e valide no Browser mobile.

Aceite:
- Browser home/menu/PDP sem sobreposicao, route warning ou icon warning.
- Testes de catalog/PDP/home passam.
- npm run build passa.
```

## WP-07 - Copy factual e omotenashi canonico

**IDs cobertos:** `COPY-SOURCE-001`, `COPY-FACT-001`, `HOME-LIVE-AVAILABILITY-001`, `PAYMENT-ERROR-DETAIL-001`, `TRACKING-PROMISE-LIVE-001`.

**Objetivo:** parar de ajustar frases manualmente e criar uma fonte canonica de copy operacional para Nuxt.

**Contexto atual:**

- Copy Nuxt esta espalhada por `pages` e `components`.
- Penguin usa templates/partials e tags omotenashi.
- Referencias: `docs/reference/omotenashi-audit-framework.md`, `docs/reference/design-surface-filter.md`, `docs/reference/surface-excellence-review-framework.md`.
- Problema ja observado: frases melosas/falsas, como prometer fornada fora do horario.

**Escopo provavel:**

- `surfaces/storefront-nuxt/app/pages/*.vue`
- `surfaces/storefront-nuxt/app/components/*.vue`
- possivel novo util: `surfaces/storefront-nuxt/app/utils/copy.ts`
- projections/API se copy precisa vir do backend
- testes em `test_storefront_nuxt_parity_contract.py`, `test_omotenashi_cold_strings.py`, `test_omotenashi_invariants.py`

**Entregas:**

- Inventario de copy operacional Nuxt.
- Remocao de promessas nao sustentadas por projection.
- Copy de disponibilidade, preparo, pagamento, entrega, tracking, suporte e recovery baseada em dados.
- Linguagem seca, elegante e hospitaleira: omotenashi sem performar fofura.
- Guardrail contra palavras/frases proibidas ou claims temporais sem fonte.

**Aceite:**

- Nenhuma copy afirma producao, fornada, tempo real, estoque, entrega ou pagamento sem campo correspondente.
- Textos de erro/recovery indicam proxima acao.
- Teste de paridade/copy falha em claims proibidos.
- Browser revisado em home/menu/cart/checkout/login/payment/tracking.

**Prompt autocontido:**

```text
Refatore a copy operacional do storefront Nuxt para seguir projections/backend, o framework de omotenashi do projeto e a referencia Django/Penguin quando ainda nao houver contrato backend.

Contexto:
- Copy Nuxt esta em surfaces/storefront-nuxt/app/pages e components.
- Referencia anterior esta em shopman/storefront/templates/storefront e partials; ela nao e canon de dominio.
- Frameworks: docs/reference/omotenashi-audit-framework.md, design-surface-filter.md, surface-excellence-review-framework.md.
- Contratos: COPY-SOURCE-001 e COPY-FACT-001.
- O objetivo nao e deixar texto fofo; e ser factual, elegante e util.

Tarefa:
1. Inventarie copy operacional do Nuxt.
2. Remova claims nao sustentados por projection/backend.
3. Centralize ou documente fontes de copy para evitar textos paralelos por tela.
4. Ajuste recovery/error copy para sempre indicar proxima acao.
5. Adicione guardrails de teste para claims proibidos.
6. Valide no Browser.

Aceite:
- Sem promessas falsas de horario, fornada, preparo, estoque, pagamento ou tracking.
- Textos permanecem humanos, curtos e profissionais.
- Testes de copy/paridade passam.
- npm run build passa.
```

## WP-08 - Design system Nuxt e refinamento mobile fino

**IDs cobertos:** `MOBILE-LAYOUT-001`, `A11Y-ACTION-001`, `CATALOG-SEARCH-NAV-001`, `PDP-RICH-DETAIL-001`, `PWA-OFFLINE-001` parcialmente.

**Objetivo:** aproximar a experiencia visual da qualidade Penguin usando linguagem canonica Nuxt UI, sem portar tokens Penguin/Oxbow.

**Contexto atual:**

- Nuxt UI e Tailwind estao em `surfaces/storefront-nuxt`.
- Problemas ja observados: excesso de icones, copy visualmente melosa, gradientes em excesso, cards demais, desalinhamentos, accordions com padding insuficiente, busca/pills sobrepostas, badges/botoes com tamanhos inconsistentes.
- Design refs: `docs/reference/design-surface-filter.md`, `surface-excellence-review-framework.md`.

**Escopo provavel:**

- `surfaces/storefront-nuxt/app/assets/css/main.css`
- `surfaces/storefront-nuxt/app/app.config.ts`
- `components/AppHeader.vue`, `ShopBottomTabs.vue`, `ProductCard.vue`, `CartLineItem.vue`, `HeroCarousel.vue`, `ContextualBanners.vue`, `CheckoutStep.vue`
- rotas principais: home, menu, PDP, cart, checkout, login, account, payment, tracking

**Entregas:**

- Sistema de densidade coerente: paddings, gaps, badges, buttons, cards, steppers, accordions, modals.
- Reducao de iconografia decorativa; icone apenas quando ajuda reconhecimento/acao.
- Gradiente reservado para poucos pontos de hierarquia; cards principais brancos/elevated sobre fundo da pagina.
- Mobile-first sem sobreposicao, texto cortado ou controles fora de alinhamento.
- Acoes destrutivas/sensiveis com modais consistentes, foco e labels.
- Header/bottom nav consistentes com autenticacao, carrinho e pedido ativo.

**Aceite:**

- Browser screenshots mobile e desktop para rotas principais sem sobreposicao.
- Console limpo.
- Textos cabem em botoes/cards.
- Sem abuso de cards dentro de cards.
- Sem one-note palette nem gradiente dominante fora de pontos focais.
- npm run build passa.

**Prompt autocontido:**

```text
Faca refinamento visual fino do storefront Nuxt usando linguagem canonica Nuxt UI, sem portar tokens Penguin/Oxbow.

Contexto:
- O objetivo e portar a experiencia Penguin sem perdas, mas com design canonico Nuxt.
- Arquivos principais: app/assets/css/main.css, app.config.ts, components e pages em surfaces/storefront-nuxt/app.
- Problemas conhecidos: desalinhamentos, busca/pills sobrepostas, accordion sem padding, excesso de icones, gradientes em excesso, badges/botoes inconsistentes, cards demais.
- Referencias: docs/reference/design-surface-filter.md e surface-excellence-review-framework.md.

Tarefa:
1. Audite home/menu/PDP/cart/checkout/login/account/payment/tracking em mobile-first.
2. Normalize paddings, gaps, badges, buttons, steppers, accordions e modals.
3. Reduza iconografia decorativa e gradientes desnecessarios.
4. Garanta cards brancos/elevated onde o fundo ja tem gradiente.
5. Garanta que texto nao sobrepoe nem corta.
6. Valide com Browser screenshots mobile e desktop.

Aceite:
- Rotas principais sem sobreposicao visual.
- Console limpo.
- Acoes sensiveis continuam com modal.
- npm run build passa.
```

## WP-09 - PWA, offline, gestos e haptic

**IDs cobertos:** `PWA-OFFLINE-001`, `MOBILE-GESTURES-HAPTIC-001`, `ACTIVE-ORDER-BADGE-001` parcialmente.

**Objetivo:** recuperar a sensacao mobile-first da versao Penguin e preparar o caminho para futura superficie Ionic sem perder contratos.

**Contexto atual:**

- Nuxt SW: `surfaces/storefront-nuxt/server/routes/sw.js.get.ts`.
- Nuxt manifest: `server/routes/manifest.json.get.ts`.
- Nuxt offline: `app/pages/offline.vue`, `plugins/service-worker.client.ts`.
- Penguin PWA: `shopman/storefront/views/pwa.py`, `templates/storefront/offline.html`, `static/js/gestures.js`, `static/storefront/js/haptic.js`.
- O manifest Nuxt ainda esta generico/hardcoded como Shopman.

**Escopo provavel:**

- `surfaces/storefront-nuxt/server/routes/manifest.json.get.ts`
- `surfaces/storefront-nuxt/server/routes/sw.js.get.ts`
- `surfaces/storefront-nuxt/app/pages/offline.vue`
- `surfaces/storefront-nuxt/app/plugins/service-worker.client.ts`
- possiveis novos composables/plugins: `useHaptics.ts`, `gestures.client.ts`
- assets PWA em `public` se necessario

**Entregas:**

- Manifest com branding real da loja quando possivel; icones adequados 192/512/maskable; theme/background coerentes.
- Offline fallback para navegação segura; network-only para carrinho, checkout, auth, payment, tracking e APIs sensiveis.
- Safe-area verificada em bottom nav/sticky bars.
- Pull-to-refresh controlado para rotas adequadas, edge back/swipe dismiss quando nao conflitar com browser/acessibilidade.
- Haptic feedback com fallback quando `navigator.vibrate` nao existe.
- Sem cachear dados sensiveis.

**Aceite:**

- Browser/PWA smoke: manifest carrega, offline page carrega, SW nao intercepta POST/API sensivel.
- Mobile safe-area sem cortar bottom nav/sticky CTA.
- Gestos nao bloqueiam input, scroll, modais ou acessibilidade.
- npm run build passa.

**Prompt autocontido:**

```text
Complete PWA, offline, gestos e haptic do storefront Nuxt em paridade com Django/Penguin.

Contexto:
- Nuxt PWA atual: server/routes/manifest.json.get.ts, sw.js.get.ts, app/pages/offline.vue, plugins/service-worker.client.ts.
- Referencia Penguin: shopman/storefront/views/pwa.py, templates/storefront/offline.html, static/js/gestures.js, static/storefront/js/haptic.js.
- Contratos: PWA-OFFLINE-001 e MOBILE-GESTURES-HAPTIC-001.

Tarefa:
1. Gere manifest com branding real e icones adequados.
2. Ajuste service worker para offline fallback sem cachear dados sensiveis.
3. Valide safe-area em bottom nav/sticky bars.
4. Porte gestos mobile uteis sem quebrar acessibilidade.
5. Adicione haptic feedback com fallback.
6. Teste Browser/PWA e build.

Aceite:
- Manifest e SW funcionam em local.
- Offline fallback aparece para navegacao permitida.
- Checkout/cart/auth/payment/tracking permanecem network-only.
- Gestos nao bloqueiam inputs/modais.
- npm run build passa.
```

## WP-10 - QA Browser, a11y, performance e release gate

**IDs cobertos:** todos, com foco final em `MOBILE-LAYOUT-001`, `A11Y-ACTION-001`, `PWA-OFFLINE-001`, `NUXT-ROUTE-001`, `COPY-FACT-001`.

**Objetivo:** fechar a implementacao com criterio repetivel, nao com impressao subjetiva.

**Contexto atual:**

- O Browser local e obrigatorio para a superficie Nuxt.
- Rotas principais: `/`, `/menu`, `/produto/<sku>`, `/cart`, `/checkout`, `/login?next=/checkout`, `/conta`, `/sair`, `/pedido/<ref>/pagamento`, `/pedido/<ref>/confirmacao`, `/tracking/<ref>`, `/offline`.
- Build: `cd surfaces/storefront-nuxt && npm run build`.
- Testes: suites de storefront, auth, account, checkout, tracking, payment, paridade e phone.

**Escopo provavel:**

- docs de relatorio final em `docs/reports/storefront-nuxt-parity-final-qa-2026-05-14.md`
- Browser local
- testes automatizados
- pequenos ajustes finais apenas se bloquearem aceite

**Entregas:**

- Relatorio final de QA com rotas navegadas, viewport mobile/desktop, console, screenshots/observacoes, erros e decisoes.
- Checklist de a11y para foco, labels, modais, destructive actions, aria-live e teclado basico.
- Checklist de performance/SEO: title/head, JSON-LD, imagens com dimensoes/sizes, LCP obvio, manifest.
- Zero P0/P1 aberto.
- Lista pequena de P2/P3 se sobrar, com justificativa.

**Aceite:**

- Browser nas rotas principais sem hydration mismatch, route warning, icon warning ou console error novo.
- `npm run build` passa.
- Testes focados passam.
- Relatorio salvo em `docs/reports/`.
- A superficie pode ser avaliada contra o framework sem depender de memoria da conversa.

**Prompt autocontido:**

```text
Execute o QA final do storefront Nuxt v4 apos os WPs de paridade.

Contexto:
- Nuxt em surfaces/storefront-nuxt, dev server esperado em http://127.0.0.1:3000.
- Django backend esperado em http://127.0.0.1:8000.
- Browser local e obrigatorio.
- Rotas: /, /menu, /produto/<sku>, /cart, /checkout, /login?next=/checkout, /conta, /sair, /pedido/<ref>/pagamento, /pedido/<ref>/confirmacao, /tracking/<ref>, /offline.
- Framework: docs/reference/surface-excellence-review-framework.md.
- Contrato: docs/reference/storefront-surface-parity-contract.md.

Tarefa:
1. Rode testes focados de phone, auth, account, checkout, payment, tracking, stock, paridade.
2. Rode npm run build em surfaces/storefront-nuxt.
3. Navegue com Browser nas rotas principais em mobile e desktop.
4. Registre console warnings/errors, layout, foco, labels, modais, PWA/offline e performance/SEO basico.
5. Corrija apenas bloqueadores pequenos encontrados no QA.
6. Salve relatorio final em docs/reports/storefront-nuxt-parity-final-qa-2026-05-14.md.

Aceite:
- Zero P0/P1 aberto.
- Console limpo nas rotas auditadas.
- Relatorio final salvo.
- Build e testes passam.
```

## Comandos de verificacao base

```bash
python -m pytest \
  packages/utils/shopman/utils/tests/test_phone.py \
  packages/guestman/shopman/guestman/tests/test_merge.py::TestMergeOrders \
  shopman/storefront/tests/api/test_auth_session.py \
  shopman/storefront/tests/api/test_account_addresses.py \
  shopman/storefront/tests/api/test_account_summary.py \
  shopman/storefront/tests/test_auth_intents.py \
  shopman/storefront/tests/test_checkout_defaults.py \
  shopman/storefront/tests/test_checkout_error_paths.py \
  shopman/storefront/tests/test_concurrent_checkout.py \
  shopman/storefront/tests/test_loyalty_checkout.py \
  shopman/storefront/tests/test_slot_validation.py \
  shopman/storefront/tests/test_stock_error_ux.py \
  shopman/storefront/tests/test_storefront_nuxt_parity_contract.py \
  shopman/storefront/tests/web/test_web_checkout.py \
  shopman/storefront/tests/web/test_web_payment.py \
  shopman/storefront/tests/web/test_web_order_tracking.py \
  shopman/storefront/tests/web/test_web_tracking.py \
  -q
```

```bash
cd surfaces/storefront-nuxt
npm run build
```

## Definicao de pronto

- Todos os P0/P1 do contrato ligados ao Nuxt tem teste automatizado ou Browser gate documentado.
- Nenhuma rota de compatibilidade ou alias foi criada para esconder divergencia.
- Nuxt consome projections/backend canonicos e nao inventa fonte paralela para dados sensiveis.
- Acoes sensiveis possuem modal/foco/estado reconciliado.
- Copy operacional e factual.
- Browser mobile-first sem sobreposicao visual nas rotas principais.
- Console limpo.
- Build e testes passam.
