# Auditoria de Excelência — Suíte Django Shopman

> Data: 2026-07-03 · Método: 16 auditorias paralelas (1 por app do kernel, 2 pelo
> orquestrador, 1 pelas superfícies Django, 5 pelos apps Nuxt, 1 transversal), cada
> achado com evidência `file:line`, severidade P0–P3 e nota de maturidade 1–5 por
> dimensão. Objetivo: **nivelar a suíte por cima** — encontrar o que puxa a média
> para baixo e o caminho para a excelência.

> Status de cobertura: 16/16 recortes consolidados.

---

## 1. Veredito em uma frase

A suíte é **madura e defensiva bem acima da média pré-go-live** — o Core transacional
(payman, doorman, orderman, o motor de directives/webhooks) é de qualidade rara, com
idempotência real, ledgers imutáveis e dinheiro que nunca some em silêncio. O que
impede a nota de excelência não é rot sistêmico: são **seis padrões transversais**
concentrados e corrigíveis, sendo o mais grave um **único desvio de perímetro** que
sozinho rebaixa a nota de segurança de 4 apps do kernel.

---

## 2. Mapa de maturidade

Nota geral (média das dimensões auditadas). ⬛ = dimensão que puxa para baixo.

### Kernel (packages/)

| App | Seg | Conf | Arq | Util | Test | Geral |
|---|---|---|---|---|---|---|
| **payman** | 4 | 5 | 5 | 5 | 5 | **4.8** ⭐ |
| **doorman** | 4 | 4 | 5 | 5 | 4 | **4.4** ⭐ |
| **fiscalman** | 4 | 4 | 4 | 4 | 4 | **4.0** |
| utils | 4 | 4 | 4 | 4 | 3 | 3.8 |
| orderman | 2⬛ | 3.5 | 4.5 | 4 | 4 | 3.6 |
| guestman | 2⬛ | 4 | 4 | 3.5 | 4 | 3.5 |
| stockman | 2⬛ | 4 | 4 | 4 | 3 | 3.4 |
| offerman | 3 | 3 | 4 | 3 | 4 | 3.4 |
| craftsman | 2⬛ | 3 | 4 | 4 | 3 | 3.2 |
| buyman | 3 | 4 | 4 | 2* | 3 | 3.2* |
| refs | 3 | 3 | 3 | 2⬛ | 4 | 3.0 |

\* buyman util=2 é escopo Fase 1 deliberado, não defeito.

### Orquestrador (shopman/shop) e superfícies Django

| Área | Seg | Conf | Arq | Util | Test | Geral |
|---|---|---|---|---|---|---|
| shop — periferia (webhooks/adapters/handlers) | 4.5 | 4 | 4 | 4.5 | 4 | **4.3** ⭐ |
| storefront (Django, headless) | 4.5 | 4.5 | 4 | 4.5 | 4.5 | **4.4** ⭐ |
| backstage (Django, headless) | 4 | 4.5 | 4.5 | 4.5 | 4.5 | **4.4** ⭐ |
| shop — núcleo (lifecycle/services/rules) | 4 | 3.5 | 3.5 | 4 | 4 | 3.8 |

### Superfícies Nuxt

| App | UX/Omotenashi | A11y | Robustez | Consist. | Util | Geral |
|---|---|---|---|---|---|---|
| **storefront (cliente)** | 4.5 | 4.5 | 4 | 4 | 5 | **4.4** ⭐ |
| production (fournil) | 4 | 3.5 | 3⬛ | 4 | 4 | 3.7 |
| kds | 4 | 3 | 3⬛ | 4 | 4 | 3.6 |
| pos | 3 | 3.5 | 3.5⬛ | 4 | 4 | 3.6 |
| orders (gestor) | 3 | 3 | 3⬛ | 4 | 4 | 3.4 |

> Assimetria reveladora: o app **do cliente** (o mais exposto ao negócio) é o mais
> maduro dos cinco; os gaps de resiliência de rede (Padrão C) e de omotenashi de TTL
> (Padrão D) estão concentrados nos **apps do operador**. O storefront prova que os
> padrões corretos (fila serial otimista, `expected_total_q` anti-surpresa, TTLs
> vivos, `useOverlayLock` com foco, sinal de offline no pagamento) já existem na casa
> — os operadores precisam herdá-los.

### Plataforma (transversal)

| Segurança | Deploy | CI | Observabilidade | Dados | Docs |
|---|---|---|---|---|---|
| 4.0 | 3.5 | 4.0 | 2.5 ⬛ | 3.0 | 3.0 |

---

## 3. Os seis padrões transversais (o que nivelar)

O valor de cruzar 16 auditorias é ver que **quase todo P0/P1 pertence a um de seis
padrões**. Atacar o padrão (não o sintoma isolado) é o que eleva a suíte por cima.

### Padrão A — Perímetro das APIs do kernel *(a causa nº 1, um único conserto)*

`config/settings.py` deixa o DRF em `DEFAULT_PERMISSION_CLASSES=[IsAuthenticated]`, e
`config/urls.py` monta as APIs REST de vários pacotes do kernel. **Clientes do
storefront viram usuários Django autenticados** (login OTP chama `login()` —
`doorman/services/verification.py:304-317`). Resultado: qualquer cliente logado
alcança dados e escrita do kernel — e **nenhuma superfície Nuxt consome essas rotas**
(elas usam as projections gateadas do storefront/backstage). É superfície de ataque
pura, sem utilidade.

| Rota | Exposição | Sev |
|---|---|---|
| `/api/orderman/` (`SessionViewSet`) | ler/`modify`/`commit` **qualquer** sessão, inclusive comandas POS; commit pula `required_checks` de estoque | **P0** |
| `/api/customers/` (guestman) | enumerar/ler/editar **toda** a base de PII (nome/telefone/e-mail/endereço) | **P0** |
| `/api/stockman/` | `receive`/`issue` — inflar/zerar estoque; ler todo o ledger | **P1** |
| `/api/craftsman/` | `plan/finish/void` + ler BOM (segredo de negócio) | **P1** |
| `/api/offerman/` | `AllowAny` público — vaza listings não publicados e campos operacionais | **P2** |

**Conserto único:** desmontar as rotas `/api/<kernel>/` do deployment (nenhuma tem
consumidor) **ou** default global `IsAdminUser` + escopo por dono. Isso sozinho sobe
orderman/guestman/stockman/craftsman de Seg **2 → 4+**.
Evidências: `config/urls.py:98-102`, `config/settings.py:661-666`,
`orderman/api/views.py:142-146`, `guestman/api/views.py:53`, `stockman/api/views.py:54`,
`craftsman/api/views.py:53`, `offerman/api/views.py:146`.

### Padrão B — Integridade de dinheiro/estado com falha silenciosa ou não-durável

O Core acerta a idempotência quase toda; os furos restantes são pontuais mas sérios:

- **[P1] Refund de cancelamento falha em silêncio** — `payment.refund` engole exceção
  do gateway com só `logger.warning` e `_settle_cancelled_payment` não alerta nem faz
  retry: PIX capturado, cancelado, refund falha no gateway = dinheiro retido sem
  ninguém saber. O padrão certo já existe no `stock.fulfill` (alerta `critical`).
  `shop/services/payment.py:266-267`, `shop/lifecycle.py:403-407`.
- **[P1] Lifecycle não é durável** — `order_changed → on_commit(dispatch)` roda
  síncrono; crash/deploy entre o COMMIT e o callback perde a fase inteira: pedido
  órfão em `NEW`, sem hold, sem confirmação, sem sweeper que o recupere.
  `shop/apps.py:186`, `shop/lifecycle.py:158-231`.
- **[P1] Colisão de `seq` em `emit_event`** — a proteção usa
  `select_for_update().aggregate()`, mas o Django **remove o FOR UPDATE de
  aggregates** (verificado no 6.0.6). Webhook × ação de operador emitindo evento
  concorrente colidem no unique `(order, seq)` → `IntegrityError` → 500.
  `orderman/models/order.py:298-300`, `session.py:277-281`.
- **[P1] Ponte craftsman→stockman com SET absoluto sobre quant compartilhado** — o
  quant planejado agrega todas as WOs do mesmo (sku, data, posição); `_handle_voided`
  zera o quant inteiro. A consolidação da matriz de produção voida duplicatas → zera
  supply planejado com WO ativa, de forma determinística.
  `craftsman/contrib/stockman/handlers.py:193-197,310-321`.
- **[P2] Ledger de produção é best-effort pós-commit sem retry** — handlers engolem
  exceção como "non-fatal": WO fica FINISHED com insumos não baixados; `finish` é
  terminal e não reexecuta. `craftsman/contrib/stockman/handlers.py:154-159` (e 5
  outros pontos).
- **[P2] `stock.hold()` não é idempotente** — re-dispatch sobrescreve `hold_ids`,
  deixa holds órfãos = dupla reserva até o backstop de 48h. `shop/services/stock.py:145`.
- **[P2] `ensure_payment_captured` fail-open** — com `Shop.defaults` corrompido, o
  except instancia `ChannelConfig()` default (`post_commit`) e libera CONFIRMED sem
  captura. `shop/lifecycle.py:128-131`.

### Padrão C — Resiliência de rede nas superfícies Nuxt (omotenashi de conexão)

Repetido **nos quatro apps operador auditados**, é o que puxa a robustez do frontend
para 3/5. Uma padaria tem wi-fi instável; hoje a falha aparece como tela mentirosa.

- **[P1] 401 no meio do turno é beco sem saída** — nenhum app tem interceptor global
  de 401/403; a sessão só é lida no load. Sessão Django expira → banner "Sem conexão —
  reconectando…" para sempre, `OperatorLogin` nunca reaparece, rascunho de venda se
  perde. (kds, pos, orders, production — todos.)
- **[P1] POS não trata offline nem autosave falho** — autosave faz `.catch(()=>{})`:
  operador lança itens numa comanda que não está sendo salva, sem aviso; nenhum
  listener `online/offline`. `pos/usePosSale.ts:866`.
- **[P1] PIX fica "aguardando confirmação" para sempre no POS** — nenhum polling do
  status; a confirmação nunca chega na tela, cliente parado no balcão.
  `pos/PosPaymentResult.vue:2-5`.
- **[P1] SSE degrada em silêncio** — no gestor, se o deploy aponta para `api.` o
  realtime cai para poll de 30s sem nenhum indicador; `onerror` vazio. Pedido iFood
  novo pode levar 30s+ sem sinal. `orders/useOrdersBoard.ts:35-45`.
- **[P2] Sem refetch ao acordar** — nenhum app escuta `visibilitychange`; tablet que
  dormiu espera o próximo tick com dados velhos.
- **Conserto de padrão:** um plugin `$fetch` compartilhado (interceptor 401 → reabre
  gate de operador; timestamp do último sucesso → banner por idade do dado;
  refetch em `visibilitychange`), promovido a pacote comum das 5 superfícies.

### Padrão D — Omotenashi de TTL e feedback ainda com vácuos pontuais

A regra do projeto ("todo TTL que afeta alguém precisa de UI explícita";
"feedback nunca no vácuo") está quase toda cumprida, com exceções concretas:

- **[P1] Prazo da confirmação otimista é invisível** no gestor — grep por
  countdown/deadline/prazo = 0; a projection nem carrega o deadline. O cliente do
  balcão não vê quanto tempo o operador tem para cancelar. `orders/OrderCard.vue:79-85`.
- **[P1] Kiosk FORNADAS nunca vira a data à meia-noite** — TV ligada de madrugada
  amanhece exibindo as fornadas de ontem com o chip "Hoje" ativo. `production/painel.vue:33-34`.
- **[P1] Beep de pedido novo no KDS pode tocar mudo** — `AudioContext` sem `resume()`
  por gesto; autoplay policy deixa suspenso. Numa cozinha que depende do som = pedido
  perdido. `kds/useKdsBoard.ts:29-45`.
- **[P1] Painel do cliente KDS promete "ao vivo" mesmo congelado** — bolinha verde
  incondicional; ignora `error`. `kds/retirada.vue:36-39`.
- **[P2] Erro de poll apaga o quadro inteiro** (kds/orders/production) — `v-else-if
  error` esconde dados stale ainda válidos. Dado velho visível > tela vazia.
- **[P1] Cupom inválido morre em silêncio no checkout do cliente** — `submitCoupon`
  sem `catch`; spinner para e nada aparece (unhandled rejection). Único P1 do
  storefront. `storefront/finalizar.vue:182-201`, `useCartState.ts:293-309`.
- **[P2] Páginas de conta sem estado de erro** — falha de API renderiza empty state
  falso ("Você ainda não tem pedidos"); o padrão certo já existe em `conta/favoritos.vue`.
- **[P2/P1] Multi-lote de produção (feature nova) tem furos** — segundo lote do mesmo
  SKU trava na largada; concluir com 2 lotes mistura quantidades (dialog sugere 60
  contra WO de 30 → ledger engole yield de 200%). `production/ProductionStageGrid.vue:250-312`.

### Padrão E — Hardening de credencial e postura de produção *(dívida de go-live)*

- **[P1] `OperatorLoginView` sem rate-limit/lockout/2FA** — brute-force de senha de
  staff/admin na API pública; o próprio docstring reconhece a dívida (coincide com o
  Lote C pendente do GO-LIVE-READINESS). `backstage/api/operations.py:311-339`.
- **[P1] Template de produção `.do/app.subdomains.yaml` ainda é staging** —
  `SHOPMAN_ENVIRONMENT=staging` + `payment_mock` + `SHOPMAN_EXPOSE_DEBUG_OTP=true`.
  Como E003/E010 só mordem em `production`, promover esse spec passaria no pre-deploy
  com pagamento mock e OTP logado. `.do/app.subdomains.yaml:146,173-179`.
- **[P1] Sem `AUTH_PASSWORD_VALIDATORS`** — grep vazio; senhas de staff aceitam
  qualquer coisa e `check --deploy` não acusa.
- **[P1] Zero error tracking** — nenhum Sentry/Rollbar; um 500 no checkout só aparece
  se alguém lê o log do DO. Observabilidade em 2.5 é a menor nota de plataforma.
- **[P2] `ifood_poll` sem lock de instância única** — duas instâncias (rolling
  deploy): a B acha o claim `in_progress` da A e **acka o evento**; se A falha, o
  pedido iFood se perde. `shop/services/ifood_events.py:143-153`.
- **[P2] `seed --flush` sem guard de produção** — `make seed` apaga tudo sem
  confirmação nem check de ambiente. `config/management/commands/seed.py`.
- **[P2] Sem lockfile Python** — Docker resolve ranges na hora; dois deploys do mesmo
  commit podem divergir.
- **[P2] PIN de operador com lockout não concorrência-safe** — burst paralelo passa o
  gate `is_locked` antes de qualquer lockout ser gravado. `doorman/pin_credential.py:147-175`.

### Padrão F — Seams dormentes, dead code e docs desatualizadas *(elegância)*

Contra a própria regra do repo ("zero seams dormentes sem dono/prazo", "zero
residuals"). Não é bug, é o que separa "bom" de "excelente".

- **refs**: ~60% da superfície sem consumidor + 3 P1 nas promessas centrais das
  docstrings (unicidade sem `UniqueConstraint` no banco; `validator`/`allowed_targets`
  configurados e nunca enforçados; `deactivate_scope` vazio desativa tudo global).
  **Decisão pré-go-live:** enforçar o que sobrevive, apagar o resto.
- **[P2] Cluster de middleware morto** em `shop/middleware.py` (3 classes duplicadas,
  uma com `import` de módulo inexistente → `ModuleNotFoundError` se wirada).
- **Testes de concorrência nunca rodam** (stockman e craftsman) — skip permanente em
  SQLite; o CI tem Postgres mas `make test-<pkg>` usa settings SQLite. Exatamente a
  dimensão crítica (double-spend, invariante do ledger) fica sem cobertura ativa.
- **[P2] Bulk actions de offerman via `queryset.update()`** — pulam `save()` →
  `product_updated`/`availability_changed` nunca disparam → canais externos (iFood)
  não retraem produto despublicado em massa. `offerman/contrib/admin_unfold/admin.py:464-482`.
- **[P1] Autofill de preço no admin quebrado por wiring ausente** — operador pode
  salvar ListingItem sem preço, sem aviso. `utils/admin/views.py:16-21` (não montada
  em `config/urls.py`).
- **~40 componentes ui-thing mortos por app Nuxt** + violações da própria escala de
  design (rounded-lg/xl avulsos, ring em seleção, touch targets <44px) + input de
  crachá `aria-hidden` porém focável (WCAG 4.1.2) nos 4 apps.
- **Mock fiscal quebrado** (`ImportError`) e `handle_webhook` legado morto no Stripe.
- **CLAUDE.md estruturalmente desatualizado**: diz "9 packages" (são 11 — buyman,
  fiscalman), descreve 57 templates storefront e árvores HTMX que não existem mais
  pós-cutover headless, não menciona `surfaces/`.

---

## 3.5 Itens deferidos — progresso (2026-07-04)

Após as ondas, ataque dos itens antes deferidos:
- ✅ **Retry automático de estorno via Directive** — `PAYMENT_REFUND` + handler; falha
  transiente enfileira retry com backoff, terminal alerta já, exhaustão alerta. (4 testes)
- ✅ **Deadline/countdown da confirmação otimista no gestor** — projection expõe
  `confirmation_deadline_iso`+`action` (batch, sem N+1); OrderCard renderiza countdown
  M:SS que tica. (10 testes backend + 3 vitest)
- ✅ **Refetch ao acordar** (`visibilitychange`/`online`) no KDS e no gestor (produção
  já tinha via `useAdaptivePoll`).
- ✅ **PIX polling no POS** — destravado: novo `POSPaymentStatusView` gateado por
  `operate_pos` (reusa `build_payment_status`, por-order) + `usePosSale` polla até
  `is_paid`/terminal e troca o proof por "Pagamento PIX confirmado". (3 testes backend
  + typecheck). Verificação do fluxo PIX ponta-a-ponta ainda pede a stack viva.
- ⏳ **Ainda deferido** (baixo valor / infra / precisa stack): staleness "idade do dado"
  banner, poda dos componentes ui-thing mortos, `refs` UniqueConstraint (caminho
  dormente sem escritor — não gold-platear), lockfile Python, helper de RMW `order.data`,
  concorrência no CI (Postgres).

## 4. Plano de nivelamento (ondas)

### Onda 0 — Bloqueadores de release (P0 + P1 de segurança) · ✅ CONCLUÍDA (2026-07-03)
1. ✅ **Perímetro das APIs do kernel fechado** (Padrão A) — desmontadas as 6 rotas de
   CRUD (`api/orderman|offerman|stockman|craftsman|customers|payments`) do
   `config/urls.py`; guardrail `shopman/shop/tests/test_api_perimeter.py` trava a
   re-introdução. *Uma decisão, resolveu 2 P0 + 2 P1 + 1 P2.* (8 testes)
2. ✅ **Rate-limit no `OperatorLoginView`** (Padrão E) — 5/min por-username (lockout de
   conta, funciona sobre JSON do BFF) + 30/min por-IP (teto generoso p/ NAT da loja),
   429 amigável. (10 testes, incl. caminho JSON e isolamento por conta)
3. ✅ **`.do/app.subdomains.yaml` → produção** — `SHOPMAN_ENVIRONMENT=production`,
   `EXPOSE_DEBUG_OTP=false`, `ALLOW_MOCK_PAYMENT_ADAPTERS=false`. Verificado por
   simulação: modo produção engaja os guardrails de boot + E003, abortando o
   PRE_DEPLOY até adapters/segredos reais entrarem.
4. ✅ **`AUTH_PASSWORD_VALIDATORS`** (4 defaults, min 10) + guard de `seed --flush`
   (recusa em produção sem `--force`). (6 testes)

> Regressão: baseline da suíte de framework = 113 falhas pré-existentes (poluição ao
> rodar tudo num processo — dívida documentada); com as mudanças, **as mesmas 113** +
> 18 testes novos verdes. Zero regressões introduzidas.

### Onda 1 — Integridade de dinheiro e dados (P1 Core) · ✅ CONCLUÍDA (2026-07-03)
5. ✅ Refund silencioso → `OperatorAlert` crítico (exceção E `success=False`); retry
   automático via Directive fica como follow-up. (3 testes)
6. ✅ Colisão de `seq` → helper `create_sequenced_event` com retry otimista em
   `IntegrityError`; Order/Session.emit_event delegam. (2 testes de corrida)
7. ✅ Durabilidade do lifecycle → marcador `order.data.lifecycle.on_commit=done` +
   comando `sweep_stuck_orders` (re-dispatch idempotente) no `maintenance_worker`. (5+1)
8. ✅ Ponte craftsman→stockman → DELTA por WO (`previous_quantity` no sinal; void
   subtrai a contribuição da WO). (3 testes de WOs coexistentes)
9. ✅ `cart_context` → delega a `CatalogService.unit_price(qty)` (cascade correto +
   is_sellable + validade). (4 testes)
10. ✅ Anonimização LGPD → `purge_pii` (guestman: ContactPoints/identidades/CPF/
    metadata) + `forget_customer` (doorman: User + devices). (4 testes)
11. ✅ **Sentry** opt-in à prova de ausência + guardas: `stock.hold` idempotente e
    `ensure_payment_captured` fail-closed. (5 testes)

> Regressão: todos os testes novos/tocados verdes (103 no framework + por-pacote);
> as 113 falhas de baseline (poluição pré-existente) permanecem inalteradas.

### Onda 2 — Resiliência e omotenashi das superfícies (P1 frontend) · ✅ PARCIAL (2026-07-04)
Verificação: os apps Nuxt não têm runner e2e aqui; a lógica pura foi coberta por
**vitest** e os componentes por **vue-tsc** (typecheck limpo). Itens de fluxo que
exigem a stack viva (PIX real, expiração de sessão de verdade) ficam com nota.
12. ✅ **401 no meio do turno reabre o gate** — `onResponseError` no `useFetch` dos
    boards (kds, orders, production×3) → `refreshNuxtData("operator-session")`. POS
    (auth divergente): guarda de reentrância em submitSale/openTab/reviewCheckout.
13. ✅ POS autosave "não salvo" + retry (chip âmbar); ✅ reentrância. ⏳ **PIX polling
    deferido** — precisa de endpoint de status POS (não existe; só o do storefront) +
    verificação do fluxo PIX na stack viva.
14. ⏳ Gestor deadline/countdown + paridade board↔detalhe — **deferido** (precisa do
    deadline na projection Django + verificação visual).
15. ✅ KDS: priming do beep por gesto (AudioContext único + `soundBlocked` visível).
16. ✅ Produção: rollover de data à meia-noite (`resolveDayRollover`, 4 vitest) +
    os dois furos do multi-lote (conclusão mira a WO certa; iniciar 2º lote).

> Deferido de Onda 2 (precisa da stack viva p/ verificar): PIX polling no POS,
> deadline/countdown do gestor, indicador de staleness por idade do dado, refetch em
> `visibilitychange`, poda dos ~40 componentes ui-thing mortos por app.

### Onda 3 — Excelência e higiene (P2/P3) · ✅ PARCIAL (2026-07-04)
17. ✅ **`refs`**: `deactivate_scope` recusa wipe global (scope vazio/incompleto) — o
    P1 perigoso (caminho real do day-close). ⏳ `UniqueConstraint` no banco + enforce
    do `validator` em `attach()` **deferidos** (caminho dormente sem consumidor —
    o próprio audit orienta "não gold-platear dormente"; fazer se ganhar escritor).
18. ⏳ Suítes de concorrência (stockman/craftsman) no Postgres do CI — **deferido**
    (mudança de CI/infra, não verificável sem Postgres local).
19. ✅ Dead code: cluster de middleware morto removido (com import quebrado). ⏳ mocks
    quebrados + ~40 componentes/app + seams dormentes — deferido (poda incremental).
20. ✅ Bulk actions de offerman via `save()`/sinais (iFood retrai despublicado);
    ✅ lock lógico do `ifood_poll` (claim `in_progress` não acka). ⏳ lockfile Python +
    helper de RMW de `order.data` — deferido (infra + refactor sistêmico).
21. ✅ CLAUDE.md à realidade headless (9→11 packages, `surfaces/`, cutover).

---

## 5. Reconhecimento — o que já é excelente (nivelar por cima significa preservar)

- **payman** (4.8): ledger imutável, máquina de estados em duas camadas, reconciliação
  contra snapshots cumulativos, idempotência em toda borda. A memória "precisa
  amadurecer" está **desatualizada**.
- **doorman** (4.4): zero segredo em plaintext, `compare_digest` em tudo, OTP com
  defesa em profundidade, sessão sem fixation.
- **shop periferia** (4.3): idempotência de webhook durável em DB, filosofia "mesma via
  dev/prod", drift de dinheiro nunca silencioso, PIX pago com webhook perdido é curado
  no timeout, motor de directives completo sem Celery.
- **storefront/backstage Django** (4.4): autorização por permissão em cada endpoint,
  gate de acesso a pedido testado, caixa cego auditável, preço sempre server-side.
- Nos apps Nuxt: escrita otimista com fila serial e rollback (kds/pos), presentation
  puro testado, caixa cego anti-fraude, painel Solari com timer que sobrevive a sleep.

O contraste é a lição central: as superfícies Django provam que **o modelo de
autorização correto já existe na casa** — os `/api/<kernel>` são o desvio, não o padrão.
