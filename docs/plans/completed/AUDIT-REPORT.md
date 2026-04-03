# Audit Report — Shopman Excellence Review

**Data**: 2026-04-01  |  **Escopo**: dev-local (excl. deploy)  |  **Auditor**: Claude Opus 4.6

---

## Resumo Executivo

- **🔴 Críticos: 5**  |  **🟠 Importantes: 9**  |  **🟡 Menores: 8**  |  **💡 Sugestões: 7**  |  **✅ Destaques: 12**

O Shopman tem uma **arquitetura Core sólida e bem projetada** — o ordering pipeline, o sistema de
directives, e a cascata de confirmação/pagamento/estoque são de nível profissional. O App consome
~80% das capacidades do Core, com cobertura de testes forte (~2.400+ testes). Os achados críticos
se concentram em **3 áreas**: cálculos monetários inconsistentes nos modifiers, webhook de pagamento
sem atomicidade, e status inválido no LoyaltyEarnHandler.

---

## 1. CORE SUBUTILIZADO

### Capacidades Não Importadas pelo App

| Módulo | Capacidade | Avaliação |
|--------|-----------|-----------|
| **offering** | `CatalogService` facade (get, price, expand, validate) | 🟠 App importa modelos direto, bypassa o service. Perde encapsulamento e cache futuro. |
| **offering** | `CatalogService.expand()` (BOM explosion de bundles) | 🟠 Só em testes. Bundles existem no seed mas expand() não roda em produção. |
| **stocking** | `StockHolds` lifecycle (hold→confirm→fulfill→release) | 🟠 Hold criado pelo handler, mas `confirm()`, `fulfill()`, `release_expired()` nunca chamados em produção. Holds expiram naturalmente. |
| **stocking** | `StockMovements` (receive, issue, adjust) | 🟡 Nenhum ponto de entrada manual para receber mercadoria ou ajustar estoque. Aceitável se todo estoque vem de Crafting. |
| **stocking** | `StockAlert` automation periódica | 🟡 `check_and_alert()` existe mas sem task periódica (Celery Beat). Alertas dependem de trigger manual. |
| **stocking** | `Batch` / lot tracking | 🟡 Modelo existe, nunca instanciado. Rastreabilidade de lotes não implementada. |
| **crafting** | `CraftQueries.suggest()` (demanda → sugestões) | 🟠 Só acessível via `python manage.py suggest_production` (CLI). Não está no dashboard. |
| **crafting** | `CraftQueries.needs()` (BOM explosion → insumos) | 🟡 Só em testes. Operador não tem visão "o que preciso comprar amanhã". |
| **crafting** | `CraftQueries.expected()` (planejado vs realizado) | 🟡 Não usado. Sem tracking de eficiência de produção. |
| **crafting** | `CraftPlanning.adjust()` (modificar WO ativa) | 🟡 App faz void+replan em vez de adjust. Perde histórico de ajuste. |
| **crafting** | `WorkOrderItem` analytics (waste, consumo) | 🟡 Ledger criado pelo `close()` mas nunca consultado. Sem dashboard de desperdício. |
| **customers** | `CustomerMergeService` | 🟠 Não integrado. Clientes duplicados não podem ser mesclados. |
| **customers** | `ConsentRecord` (opt-in/opt-out tracking) | 🟠 Importado em notification.py mas nunca instanciado. Opt-out funciona via `CommunicationConsent` separado. |
| **customers** | `RFM scoring` completo | 🟡 Parcialmente usado (insights read-only). Segmentação ativa não implementada. |

### Decisões Conscientes (OK)

| Capacidade | Razão |
|-----------|-------|
| `StockPlanning.plan/replan` | Planejamento de estoque delegado ao Crafting |
| `offering.contrib.suggestions` | Listado no ROADMAP P1 como próximo passo |
| Loyalty UI completa | Listada no ROADMAP P2 |
| Payment split/multi-payment | Core suporta, mas use case de PME artesanal não requer |

---

## 2. HANDLERS & PIPELINE

### ✅ Destaques

- **Registro centralizado** em `setup.py` com topic constants — zero magic strings na registry
- **Timeout handlers** verificam condição antes de agir e reagendam se necessário (`confirmation.py:42-46`, `payment.py:255-258`)
- **Idempotência excelente** na maioria: StockHoldHandler usa rev check (`stock.py:71-75`), PaymentCaptureHandler verifica PaymentService antes de capturar, ConfirmationTimeout só age em status NEW
- **Fallback chain** de notificações funcional: manychat → sms → email → console, com escalação para OperatorAlert após 5 tentativas
- **Sem dependências circulares** entre handlers

### Achados

| # | Sev. | Achado | Evidência | Impacto |
|---|------|--------|-----------|---------|
| H1 | 🔴 | **LoyaltyEarnHandler usa status "completed"** em vez de "done" | `loyalty.py:44,59,66,86` — Directive.status choices são: queued, running, done, failed. "completed" não é válido. | Directive fica em status não-reconhecido. Queries por `status="done"` não encontram. Pode causar retry infinito dependendo do runner. |
| H2 | 🟠 | **LoyaltyEarnHandler sem idempotência** | `loyalty.py:62-86` — nenhum check se pontos já foram dados para este pedido | Se directive retried, pontos duplicados. |
| H3 | 🟠 | **STOCK_RELEASE topic sem handler** | `topics.py:11` define, `presets.py:103,148` usa em on_cancelled, mas nenhum handler registrado | Non-blocking porque `_on_cancelled()` em hooks.py libera holds via backend. Mas directive fica "queued" eternamente. |
| H4 | 🟠 | **Fiscal/Accounting handlers fazem `raise RuntimeError` após salvar status "failed"** | `fiscal.py:64,107`, `accounting.py:57` | Raise após save causa double-processing ou log confuso. Status já salvo, raise é redundante. |
| H5 | 🟡 | **Payment handlers (6 total) não logam nada** | `payment.py:12` importa logging mas 0 chamadas | Diagnóstico de falhas de pagamento depende exclusivamente de Directive.last_error. |

---

## 3. TRANSIÇÕES DE STATUS

### Mapa Completo

```
NEW ──→ CONFIRMED ──→ PROCESSING ──→ READY ──→ DISPATCHED ──→ DELIVERED ──→ COMPLETED
  │         │             │                        │             │             │
  └→ CANCELLED  └→ CANCELLED  └→ CANCELLED          └→ RETURNED   └→ RETURNED   └→ RETURNED
                                                                                    │
                                                                               COMPLETED ←┘
```

### ✅ Destaques

- **Todas as transições** usam `Order.transition_status()` com `select_for_update()` — nenhuma mutação direta de `order.status`
- **OrderEvent emitido** em cada transição, com actor tracking (operator, auto_confirm, kds, webhook)
- **Signal `order_changed`** dispara pipeline de directives para cada status
- **Payment guard** bloqueia CONFIRMED→PROCESSING se pagamento pendente (`pedidos.py:344-347`)
- **15 pontos de transição** auditados, todos com guards e eventos

### Achados

| # | Sev. | Achado | Evidência | Impacto |
|---|------|--------|-----------|---------|
| T1 | 🟡 | **READY→CANCELLED não existe** | `order.py:53` — READY permite apenas [DISPATCHED, COMPLETED] | Se problema descoberto com pedido pronto (ex: contaminação), operador não pode cancelar diretamente. Requer hack admin. |
| T2 | 💡 | **COMPLETED é "terminal" mas permite RETURNED** | `order.py:57,60` | Intencional (devoluções pós-venda), mas TERMINAL_STATUSES=[COMPLETED,CANCELLED] pode confundir. |

---

## 4. FLUXO FINANCEIRO

### ✅ Destaques

- **CommitService** usa `monetary_mult()` corretamente (`commit.py:311`)
- **ItemPricingModifier** usa `monetary_mult()` corretamente (`pricing.py:73-75`)
- **SessionTotalModifier** soma `line_total_q` corretamente (`pricing.py:97`)
- **Todos valores monetários** são `int` em centavos com sufixo `_q` — nenhum `float` para dinheiro nos modelos
- **PaymentService** valida `amount_q > 0` e `capture ≤ authorized` (`service.py:92, 205`)

### Achados

| # | Sev. | Achado | Evidência | Impacto |
|---|------|--------|-----------|---------|
| F1 | 🔴 | **4 discount modifiers usam `unit_price * int(qty)` em vez de `monetary_mult()`** | `modifiers.py:78` (D1), `:189` (Discount), `:283` (Employee), `:330` (HappyHour) | `int(qty)` trunca quantidades fracionárias. Ex: qty=2.5, price=1000 → `1000*2=2000` em vez de `2500`. Perda de R$5 por linha. |
| F2 | 🔴 | **Refund calcula `int(unit_price_q * qty)` sem monetary_mult** | `returns.py:67` | Mesma classe de bug que F1. Refund pode ser menor que o correto para qty fracionária. |
| F3 | 🟠 | **Webhook PIX usa `float` para converter valor** | `webhooks.py:136` — `int(round(float(valor) * 100))` | Float precision: `float("19.99") * 100 = 1998.9999...` → `round()` salva na maioria dos casos, mas `Decimal` seria correto. |
| F4 | 🟡 | **Seed usa `int(price * (1+markup))` sem monetary_mult** | `seed.py:357,717` | Dados de seed podem ter centavos incorretos. Baixo impacto (dev only). |

**Nota sobre F1**: Em padaria artesanal, qty fracionária (0.5 kg, 1.5 unidades) é cenário real.
O `monetary_mult()` do Core existe exatamente para isso — usa `ROUND_HALF_UP` com `Decimal`.

---

## 5. NOTIFICAÇÕES

### ✅ Destaques

- **Fallback chain funcional**: manychat → sms → email, com retry até 5x e escalação para OperatorAlert
- **Opt-out model correto**: default=ON, bloqueia só com OPTED_OUT explícito
- **Template resolver com cache** (300s TTL), fallback DB → hardcoded → generic
- **6 backends** implementados (email, sms, manychat, whatsapp, webhook, console), todos retornando `NotificationResult`
- **12 email templates específicos** em HTML

### Achados

| # | Sev. | Achado | Evidência | Impacto |
|---|------|--------|-----------|---------|
| N1 | 🟠 | **4 templates usados em código sem fallback definido** | `order_rejected` (pedidos.py:313), `order_cancelled_by_customer` (tracking.py:369), `payment.reminder` (payment.py:220), `production_cancelled` (_stock_receivers.py:64) | Se DB template não existe, mensagem cai no generic com possíveis placeholders visíveis `{reason}`. |
| N2 | 🟠 | **Recipient resolution retorna phone para email backend** | `notification.py:270` — fallback de email resolve para phone se email ausente | Email backend recebe phone como destinatário → falha silenciosa ou email inválido. |
| N3 | 🟡 | **Template formatting silencioso** | `template_resolver.py:219-221` — `_safe_format()` deixa `{placeholder}` literal se variável ausente | Cliente pode ver `{copy_paste}` na mensagem se contexto incompleto. |
| N4 | 🟡 | **Sem log quando recipient ausente** | `notification.py:99` — `last_error` setado mas sem `logger.info/warning` | Difícil diagnosticar por que backend foi pulado na chain. |

---

## 6. UX / TEMPLATES

### ✅ Destaques

- **HTMX + Alpine.js** bem separados: hx-* para servidor, x-data/@click para DOM local
- **Touch targets ≥44px** com `min-height: var(--touch-min)` nos botões principais
- **inputmode correto**: `tel` no telefone, botões com aria-label
- **Loading states** em add-to-cart: `hx-on::before-request` com spinner + text change
- **Empty states** implementados: carrinho vazio com CTA "Ver Cardápio"
- **Double-submit prevention** no checkout: `:disabled="submitting"` com spinner

### Achados

| # | Sev. | Achado | Evidência | Impacto |
|---|------|--------|-----------|---------|
| U1 | 🟠 | **`document.getElementById` em 8 locais** (proibido por CLAUDE.md) | `checkout.html:396,435`, `base.html:355`, `payment.html:218`, `_header.html:36`, `auth_verify_code.html:48-49`, `pos/index.html:158` | Viola convenção. Deveria usar `$refs` (Alpine) ou `$el.querySelector`. |
| U2 | 🟠 | **Zero `hx-on::response-error` em todo o storefront** | Grep retorna 0 resultados em templates/ | Erros HTTP 4xx/5xx silenciosos. Rede instável = UX quebrada sem feedback. |
| U3 | 🟡 | **`classList.add/remove` em hx-on callbacks** | `product_detail.html:181-182`, `product_card.html:70-71,93-94`, `base.html:362-364`, `menu.html:140-145` | Viola convenção CLAUDE.md. Dentro de `hx-on::` é borderline aceitável (atrelado a request), mas `menu.html:140-145` é IntersectionObserver callback — aceitável pela exceção documentada. |
| U4 | 🟡 | **`onclick="window.location.reload()"` em offline.html** | `offline.html:52` | Viola convenção (onclick proibido). Caso edge (offline page), mas deveria usar Alpine. |

---

## 7. ADMIN / OPERADOR

### ✅ Destaques

- **CRUD completo** para Shop, Product, Promotion, Coupon, Batch, Position, OperatorAlert
- **Readonly fields** protegem dados críticos (DayClosing totalmente readonly, Fulfillment inline sem delete)
- **Bulk actions**: enable/disable channels, cancel orders, acknowledge alerts
- **Dashboard KPIs**: receita, pedidos por status, trend vs ontem/semana, produção, estoque D-1
- **Gestor de Pedidos** com cards por status, filtros, confirm/reject/advance, payment guard
- **Catálogo**: reorder drag-and-drop, toggle disponibilidade por canal
- **KDS**: 4 estações, auto-advance PROCESSING→READY, dispatch/complete
- **POS**: busca cliente, carrinho, pagamento balcão

### Achados

| # | Sev. | Achado | Evidência | Impacto |
|---|------|--------|-----------|---------|
| A1 | 🟡 | **Dashboard D-1 stock faz queries em loop** | `dashboard.py:~511` — lookup de Product dentro de loop de 8 items | N+1 para poucos items. Baixo impacto mas antipático. |
| A2 | 💡 | **Directives sem UI de retry manual** | Directives falhados visíveis no admin list, mas sem ação "Retry" | Operador precisa de shell para reprocessar directive falhado. |

---

## 8. SEGURANÇA ANTI-FALHAS

### ✅ Destaques

- **CommitService**: `@transaction.atomic` + `select_for_update()` + idempotency key (`commit.py:115-166`)
- **PaymentService**: todos os 5 métodos (authorize, capture, refund, cancel, fail) com `@transaction.atomic` + lock
- **StockHolds**: hold/confirm/release com `select_for_update()` em Quant (`holds.py:110-114`)
- **Order.transition_status**: `select_for_update()` para concorrência (`order.py:217`)
- **Session key**: 60 bits de entropia via `secrets.choice()` (`ids.py:34`)
- **CSRF**: cookie secure + rotate after login
- **Webhook auth**: EFI HMAC, Stripe signature, iFood token, WhatsApp `hmac.compare_digest()`
- **Rate limiting**: OTP 5/15min, access link 5/15min, web auth 3/10min

### Achados

| # | Sev. | Achado | Evidência | Impacto |
|---|------|--------|-----------|---------|
| S1 | 🔴 | **Webhook `_process_order_payment()` NÃO é atômico** | `webhooks.py:128-140` — check status (131), save (138), fire hooks (140) sem transaction | Race condition: webhook duplicado do EFI pode passar check simultâneo. Resultado: `on_payment_confirmed()` dispara 2x → stock commit duplicado, notificações duplicadas. |
| S2 | 🔴 | **Stripe webhook `_trigger_order_hooks()` sem atomicidade** | `webhooks.py:733-766` | Mesma classe de bug que S1. |
| S3 | 🟡 | **Checkout session update sem lock** | `checkout.py:140-143` — `OmniSession.objects.get()` sem `select_for_update()` antes de save | Race condition teórica com 2 tabs no mesmo carrinho. Baixa probabilidade. |
| S4 | 💡 | **API throttle rates não configurados em settings.py** | `ordering/api/views.py:75-96` define scopes, mas `DEFAULT_THROTTLE_RATES` não encontrado em `settings.py` | DRF usa defaults permissivos. Deveria ter rates explícitos. |

---

## 9. OBSERVABILIDADE

### Achados

| # | Sev. | Achado | Evidência | Impacto |
|---|------|--------|-----------|---------|
| O1 | 🟠 | **6 de 14 handlers não logam nada** | `payment.py` (0 logs), `customer.py` (0 logs), `accounting.py` (0 logs), `fiscal.py` (0 logs) — todos importam `logging` sem usar | Falhas de pagamento/customer/fiscal só diagnosticáveis via Directive.last_error. Sem contexto de handler_name, duration, tentativa. |
| O2 | 🟡 | **Nenhum handler loga duração de execução** | Nenhum `time.time()` ou similar em handlers/ | Sem métricas de performance. Impossível detectar handler lento. |
| O3 | 💡 | **Audit trail fragmentado** | OrderEvent para status + Directive para async, mas sem view unificada | Reconstruir história completa de um pedido requer 3 queries (Order, OrderEvent, Directive). |

---

## 10. SEED & TESTABILIDADE

### ✅ Destaques

- **Seed realista** (1394 linhas): 13 produtos, bundles, coleções, 12+ clientes, 7 dias de pedidos em fases variadas, 4 estações KDS, fulfillments, loyalty, notification templates
- **~2.400+ testes** (567 core + 76 app test files)
- **29 testes E2E/integração** cobrindo: session→commit→directives, web pickup/delivery, pre-order, production→stock, balcão anônimo/identificado
- **Testes de regressão** para bugs corrigidos (hx-target stale, Alpine binding, etc.)

### Achados

| # | Sev. | Achado | Evidência | Impacto |
|---|------|--------|-----------|---------|
| TE1 | 💡 | **Sem teste E2E para webhook PIX duplicado** | Não encontrado em test files | O bug S1 (race condition) não tem cobertura. |
| TE2 | 💡 | **Sem teste para discount modifiers com qty fracionária** | Não encontrado | Os bugs F1-F2 não têm cobertura. |

---

## 11. CONSISTÊNCIA ARQUITETURAL

### ✅ Destaques

- **Handlers**: padrão consistente (extract payload → load objects → logic → set status)
- **Backends**: todos implementam protocolos de `protocols.py` com `NotificationResult`/similar return types
- **Presets**: 4 presets completos (pos, remote, marketplace, whatsapp) com pipelines bem definidos
- **ChannelConfig cascata**: Channel → Shop.defaults → ChannelConfig.defaults() — elegante

### Achados

| # | Sev. | Achado | Evidência | Impacto |
|---|------|--------|-----------|---------|
| C1 | 🟠 | **Web checkout (156 linhas) duplica lógica do API checkout (60 linhas)** | `checkout.py:84-240` vs `api/views.py:117-192` — phone normalization, address parsing, customer lookup duplicados | Bugs fixados num lugar podem não ser fixados no outro. Deveria existir `CheckoutService` compartilhado. |
| C2 | 🟡 | **Business logic em views** | `checkout.py:193-226` — validação de delivery date/cutoff (deveria ser validator), `checkout.py:152-174` — parsing de endereço (deveria ser service) | Acoplamento view↔domain. Mais difícil de testar unitariamente. |

---

## 12. ELEGÂNCIA & SIMPLICIDADE

### ✅ Destaques

- **Zero dead code significativo** — nenhum módulo inteiro sem uso
- **Naming consistente**: `_q` para centavos, `ref` para identificadores (por CLAUDE.md)
- **Módulos enxutos**: maior handler tem 429 linhas (stock.py), maioria <200
- **Topics como constantes** em `topics.py` — sem magic strings na registry

### Achados

| # | Sev. | Achado | Evidência | Impacto |
|---|------|--------|-----------|---------|
| E1 | 🟡 | **Magic strings para status em views** | `pedidos.py:33-35` — `"confirmed"`, `"processing"`, `"ready"` hardcoded em NEXT_STATUS_MAP | Deveria usar `Order.Status.CONFIRMED` etc. |
| E2 | 🟡 | **5 handlers com >100 linhas** | `stock.py:handle()` 253 linhas, `notification.py:handle()` 296 linhas, `customer.py:handle()` 216 linhas | Funções longas, mas cada uma lida com cenários legítimos. Refactoring possível (ex: NotificationHandler → Order + System). |
| E3 | 🟡 | **3 imports de logging não utilizados** | `payment.py:12`, `customer.py:9`, `accounting.py:9` | Dead imports. Menor, mas indica que logging foi planejado e esquecido. |

---

## Comparação com Benchmarks

| Aspecto | Shopman | Toast/Shopify/iFood | Gap? |
|---------|---------|---------------------|------|
| **Pipeline de pedidos** | Directives async, idempotência, fallback chain | Comparável (Toast: ticket routing, Shopify: fulfillment API) | Sem gap significativo |
| **Estado financeiro** | Centavos int, monetary_mult, audit trail | Padrão indústria (Stripe: minor units) | **Gap nos modifiers** (F1-F2) |
| **Notificações** | Multi-backend, fallback, opt-out, templates | iFood: push + email; Take.app: WhatsApp-first | **Gap em templates faltantes** (N1) |
| **Storefront mobile** | HTMX + Alpine, touch targets, loading states | iFood: app nativo; Take.app: PWA otimizada | **Gap em error handling** (U2) |
| **Admin/operação** | Unfold admin, gestor de pedidos, KDS, POS | Toast: purpose-built KDS; Square: integrated POS | Comparável para PME artesanal |
| **Webhook safety** | Auth HMAC/signature, intent dedup via PaymentService | Stripe: idempotency keys built-in; iFood: order dedup | **Gap na atomicidade** (S1-S2) |
| **Observabilidade** | Directive status + OrderEvent + OperatorAlert | Toast: Datadog integration; Shopify: structured logging | **Gap em logging** (O1-O2) |
| **Estoque/Produção** | Hold lifecycle, WO plan/close, D-1 | Toast: basic inventory; Square: detailed stock | Core supera, mas **UI subutiliza** |
| **Loyalty** | Core completo (tiers, stamps, earn/redeem) | Shopify: plugin; iFood: cashback | **Core pronto, UI não exposta** (ROADMAP P2) |
| **Customer merge** | Core suporta, App não integra | Shopify: merge built-in; Toast: dedup alerts | **Gap real** para operação diária |

---

## Veredicto

O Shopman é um **sistema bem arquitetado para negócios artesanais PME**, com um Core que
rivaliza (e em alguns aspectos supera) soluções comerciais no domain modeling — o pipeline de
directives, a cascata de confirmação, e o fluxo financeiro em centavos são de nível profissional.

**Onde é excelente:**
- Ordering pipeline (directives, idempotência, timeout handlers)
- Separação Core/App (Core é sagrado, App é orquestrador)
- Cobertura de testes (~2.400+) com E2E realistas
- Admin operacional completo (gestor, KDS, POS, dashboard)
- Seed script que cria cenário realista para dev

**Onde precisa de atenção imediata (5 críticos):**
1. `monetary_mult()` **não usado nos 4 discount modifiers** — rounding/truncation bugs em qty fracionárias
2. **Refund calculation** sem `monetary_mult()` — mesma classe de bug
3. **Webhook payment** sem `@transaction.atomic` — race condition real com duplicatas
4. **LoyaltyEarnHandler** com status `"completed"` inexistente — directives perdidas
5. **Stripe webhook** mesma falta de atomicidade

**O que separa de primeira linha:**
- Ausência de `hx-on::response-error` no storefront (UX frágil em rede instável)
- Logging esparso nos handlers (dificulta diagnóstico em produção)
- Core features prontas mas não expostas na UI (suggestions, needs, merge, batch tracking)
- Checkout logic duplicada entre web e API

**Recomendação**: Corrigir os 5 críticos antes de qualquer deploy. Os 9 importantes podem
ser tratados em sprints incrementais. O ROADMAP P1/P2 já endereça as principais lacunas de
UI (availability, loyalty). O sistema está a **2-3 sprints de qualidade production-ready**
para o público-alvo (padarias, confeitarias, cafeterias artesanais).
