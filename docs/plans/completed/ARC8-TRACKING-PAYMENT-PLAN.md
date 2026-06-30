# Arc 8 — Tracking + Pagamento (Storefront Nuxt redesign)

**Superfície:** `surfaces/storefront-uithing-nuxt` (Nuxt 4 + UI-Thing/reka-ui)
**Branch:** `redesign/surface-excellence`
**Status inicial:** as duas telas já existem (`tracking/[ref].vue` 422 linhas, `pedido/[ref]/pagamento.vue` 184 linhas) e funcionam ponta-a-ponta. Arc 8 **fecha as lacunas** vs. o padrão dos Arcs 0–7, não constrói do zero.

---

## Auditoria (resumo)

### Backend (SAGRADO — nada muda)
- **Tracking:** `GET /api/v1/tracking/<ref>/` → `OrderTrackingSerializer`. Status é string canônica (`new|confirmed|preparing|ready|dispatched|delivered|completed|cancelled|returned`); UI deriva de `display_status_key` + copy. Promise state machine com `tone`, `deadline_at`, `timer_mode` (`none|countdown`), `deadline_action`, `requires_active_notification`. Contrato pinado em `test_remote_multisurface_contract`.
- **Pagamento:** `GET /api/v1/payment/<ref>/` (projection), `/status/` (poll → `is_paid/is_cancelled/is_expired/is_terminal/should_redirect`), `POST /mock-confirm/` (DEBUG). PIX via Efí (`pix_qr_code` base64, `pix_copy_paste`, `pix_expires_at`), cartão via Stripe Checkout (`checkout_url`). `payment_status ∈ {pending,authorized,captured,null}`; `promise.state ∈ {paid,cancelled,expired,pix_payment_requested,card_checkout_requested,...}`.
- **Roteamento pós-checkout:** PIX com `starts_payment_after_store_confirmation=True` → `/tracking/<ref>`; senão (e cartão sempre) → `/pedido/<ref>/pagamento`.
- **Cartão é DELEGADO (PCI SAQ A):** zero captura no app; webhook é o único retorno confiável. Em dev: `mock-confirm`.
- **Ações:** `POST orders/<ref>/cancel`, `POST orders/<ref>/rate`, `GET orders/<ref>/conversation` (superfície agêntica — fora do escopo storefront; "conversa" no storefront = deep-link WhatsApp `whatsapp_url`).

### Frontend
- **Legado (Django templates):** PIX com QR + copia-e-cola + **countdown m:ss vivo + barra de progresso** (vermelha <30%) + polling 5s; tracking com timeline + SSE+polling.
- **Nuxt atual:** ambas as telas consomem os tipos certos (`app/types/shopman.ts` completo). Padrão da casa: lógica pura em `app/presentation/*.ts` + vitest, `<script setup>` fino.

### Lacunas encontradas (o trabalho do Arc 8)
1. **Sem `presentation/payment.ts` e `presentation/order_tracking.ts`** e **sem testes** — única dívida estrutural vs. Arcs 0–7. Toda a lógica (tone→variante/ícone/classe, ordenação de ações, filtro de rows, cálculo de step da timeline, detecção de estado terminal) está inline nos `.vue`.
2. **BUG no poll de pagamento** (`pagamento.vue:26`): guarda terminal compara `payment_status` contra `['paid','cancelled','expired']` — mas esses são valores de `promise.state`, não de `payment_status`. A guarda nunca dispara → poll infinito mesmo após pago. Corrigir para `promise.state`.
3. **Timeouts transparentes (princípio travado) ausentes:**
   - Pagamento: `pix_expires_at` é renderizado como ISO cru ("Expira em 2026-06-13T..."). Falta **countdown vivo + barra** ancorado em `server_now_iso` (o legado tinha).
   - Tracking: `confirmation_expires_at` / `promise.deadline_at` com `timer_mode==='countdown'` não renderizam **nenhum timer vivo**.
4. **Typo de copy:** "Recuperacao" → "Recuperação" (`pagamento.vue:145`).
5. Cartão (Stripe): fluxo mínimo ("Checkout hospedado" / "Abrir pagamento") — funcional p/ SAQ A, mas copy fria e sem explicar "você será redirecionado; confirmamos automaticamente".

---

## Plano em sub-arcos

### 8a — Pagamento: presentation + countdown PIX vivo (timeouts transparentes)
- Novo `app/presentation/payment.ts` (puro): `paymentTone→variant/icon`, `isTerminalState(promise.state)`, `paymentCountdown(expiresAt, serverNowIso, clientNow)` → `{ remainingMs, mmss, pct, isUrgent, isExpired }`, ordenação/variante de ações.
- Corrigir o BUG do poll (usar `promise.state`).
- UI: countdown vivo + barra de progresso para `pix_expires_at` (urgência <~20%), ancorado no offset `server_now_iso`.
- Fix typo "Recuperação".
- `tests/paymentPresentation.test.ts` (vitest).
- **Verificar ao vivo** (375px, console limpo, GET 200; poll para de pollar em terminal).

### 8b — Tracking: presentation + countdown de deadline vivo
- Novo `app/presentation/orderTracking.ts` (puro): `promiseTone→panelClass/iconClass/icon`, `statusPanelActions(...)`, `visiblePromiseRows(...)` (sem string-matching frágil — usar critério explícito), `progressTimelineStep(steps)`, `pollIntervalMs(stale)`, e o mesmo helper de countdown compartilhado p/ `confirmation_expires_at`/`deadline_at` quando `timer_mode==='countdown'`.
- UI: timer vivo no painel de status quando há deadline em contagem.
- `.vue` vira casca fina chamando a presentation.
- `tests/orderTrackingPresentation.test.ts` (vitest).
- **Verificar ao vivo** (375px, pedido de teste WEB-260612-703Z, console limpo, poll respeita `is_active`).

### 8c — Cartão (Stripe) polish
- Copy acolhedora SAQ A: explica redirecionamento + "confirmamos sozinhos quando o pagamento cair" (webhook). Estado "aguardando confirmação" claro.
- Sem captura no app (mantém delegação). Em dev sem credenciais Stripe → flagar verificação e-2-e p/ reviewer local; verificar o caminho de UI com dados mockados.

### 8d — Ações (cancelar/avaliar) + e2e final
- Verificar `cancel` e `rate` ao vivo (POST 200, idempotência, toasts). "Conversa" = WhatsApp deep-link.
- Acessibilidade: alvos ≥40px, contraste, heading grande, copy acolhedora (server-driven OmotenashiCopy).
- Gate final: `npx vitest run` + `npx nuxt build` (dentro do surface) e `.venv/bin/pytest shopman/storefront/tests` (raiz).

## Gates (sempre)
- Surface: `npx vitest run` + `npx nuxt build` (de dentro de `surfaces/storefront-uithing-nuxt`).
- Backend: `.venv/bin/pytest shopman/storefront/tests` (da raiz).
- Commit por tela. Co-author: Claude Fable 5.
- Neutro primeiro; theming por último.
