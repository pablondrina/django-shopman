# COPY-OMOTENASHI-PLAN — registro como fonte única, configurável de verdade

Status: **em execução** (reformulado 2026-07-07). Substitui a abordagem anterior de
"deletar órfãs" — que se revelou errada: **órfã ≠ morta**. Uma chave sem tela é, quase
sempre, uma feature que existe e **hardcoda** a copy (drift) ou uma feature que foi
**especificada e não construída**. Deletar apaga a intenção e cimenta copy não-configurável.

Reversão feita (restaura 379 chaves): `159348e7`.

## Princípio (omotenashi-first)

**Toda copy de cliente é canônica no registro `OMOTENASHI_DEFAULTS` e chega à tela via
projection — configurável pelo operador no Admin/Unfold.** Um hardcode no template que
duplica (ou ignora) o registro é o defeito. A resolução correta é sempre **religar**
(registro → projection → Vue), nunca deletar a copy.

Exceções que podem ficar no template: `aria-label` dinâmico e microtexto puramente
estrutural sem valor de marca.

## Os três baldes (auditoria de 2026-07-07)

Cada chave sem tela caiu em um destes. A ação difere por balde.

### Balde A — feature EXISTE, tela hardcoda (drift) → **RELIGAR**
Verificado que a tela existe; a copy só foi reescrita no template. Religar via projection.
- **Segurança/dispositivos** (`conta/seguranca.vue`) → `DEVICE_LIST_*`, `DEVICE_REVOKE_*`, `ACCOUNT_TRUSTED_DEVICES_MESSAGE`, `DEVICE_TRUST_*`
- **Preferências de notificação** (`conta/preferencias.vue`) → `NOTIFICATION_PREFS_EMPTY`
- **Pagamento** (`pedido/[ref]/pagamento.vue`) → `PAYMENT_PAGE_*`, `PAYMENT_PIX_*`, `PAYMENT_WAITING*`, `PAYMENT_ERROR_*`, `PAYMENT_CARD_SECURITY_NOTE`, `PAYMENT_CONFIRMED`, `PAYMENT_REDIRECTING_*`, `PAYMENT_CANCELLED*`, `PAYMENT_DEADLINE_NOTICE`, `PAYMENT_ORDER_REF_LABEL`, `PAYMENT_TOTAL_LABEL`
- **Perfil** (`conta/perfil.vue`, tem email+nascimento) → `PROFILE_*`
- **Conta** (`conta/index.vue`) → `ACCOUNT_GREETING_PREFIX`, `ACCOUNT_PAGE_TITLE`, `ACCOUNT_DELETE_WARNING`
- **Checkout** → `CHECKOUT_SWITCH_ACCOUNT_*`, `CHECKOUT_WHEN_REQUIRED`, `CHECKOUT_CONFIRM_CTA`, `CHECKOUT_LOYALTY_SAVINGS_PREFIX`, `MIN_ORDER_WARNING*`
- **Tracking** → `TRACKING_CANCEL_*`, `TRACKING_DELIVERY_HEADING`, `TRACKING_ACTION_*`, `TRACKING_AUTO_CONFIRM_*`, `TRACKING_ETA_PREFIX`, `TRACKING_PAYMENT_*`, `TRACKING_RATE_THANKS`, `TRACKING_PAGE_META_DESCRIPTION`
- **Empty states / avisos** → `HISTORY_EMPTY`, `ADDRESSES_EMPTY`, `LOYALTY_UNAVAILABLE`, `CART_UNAVAILABLE_BANNER`, `PICKUP_READY_NOTICE`, `PRODUCT_OUT_OF_STOCK`, `PRODUCT_SCHEDULED_UNAVAILABLE`
- **Home "Como Funciona" (detalhe)** → `HOW_DELIVERY_*`, `HOW_QUALITY_MESSAGE`, `HOW_PREORDER_MESSAGE`, `HOW_TRACKING_MESSAGE`
- **Login** → `LOGIN_CHANGE_PHONE_*`, `LOGIN_WELCOME_BACK`
- **Kintsugi (recuperação/omotenashi)** → `KINTSUGI_*` (erros de CEP, cancelamento recusado, rate-limit, falta/substituto) — verificar tela a tela

### Balde B — superseto (feito de outro jeito) → **RECONCILIAR**
A feature existe, mas construída por hardcode/f-string em vez do registro. Fazer a
implementação atual **resolver do registro**.
- `SHOP_STATUS_*` → hoje montado por f-string em `shop_status.py`; passar a resolver as chaves.
- `WELCOME_*` → o passo inline "Como podemos te chamar?" (login) substituiu a página welcome;
  reconciliar (o passo do login deveria consumir `WELCOME_*` ou consolidar em `LOGIN_NAME_*`).
- `URGENCY_BANNER_MESSAGE` / `CLOSING_AWARENESS_*` → aviso de "fechamos em X"; reconciliar com o que a home mostra.

### Balde C — especificada e NÃO construída → **BACKLOG** (nunca deletar; é a spec)
Copy detalhada de features sem tela. Vira backlog explícito para o Pablo decidir
construir ou arquivar conscientemente. Ver `COPY-BACKLOG-UNBUILT.md`.
- `CONFIRMATION_*` — tela de confirmação/celebração pós-pedido (com **Compartilhar**).
- `KINTSUGI_PLANNED_OFFER` — **pré-reserva** do próximo lote.
- `TRACKING_PROMISE_*_ACTIVE_NOTIFICATION` — indicador "também avisamos por canal ativo".
- `TRACKING_DELIVERED_YOIN` — delícia pós-entrega ("Bom apetite. Até a próxima.").
- `BIRTHDAY_BANNER_*` — banner de aniversário.

## Método de religação (padrão validado na home)

Por tela: (1) adicionar o campo `CopyEntryProjection` à projection da tela (Python);
(2) resolver do registro com `_copy_entry`/`build_copy`; (3) tipar no `types/shopman.ts`;
(4) consumir no Vue removendo o hardcode; (5) alinhar o wording do registro ao melhor
texto; (6) build + testes + verificação de tela.

## Burndown (guardrail)

`docs/plans/copy-wiring-backlog.txt` lista todas as chaves ainda não religadas. O teste
`test_copy_wiring_backlog_only_shrinks` falha se surgir uma chave sem tela **fora** do
backlog (impede novo drift) — e o backlog só pode **encolher**. Cada PR de religação
remove linhas do backlog.

## Sequência (uma tela por PR, com verificação)

Home ✅ · Produto ✅ · Tracking(kicker) ✅ → Pagamento → Segurança → Perfil → Conta →
Preferências → Checkout(switch/min) → Empty states → Kintsugi → Home(how detalhe) → B(reconciliar).
Balde C fica no backlog até decisão de produto.
