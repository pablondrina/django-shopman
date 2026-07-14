# QA exploratório manual — Backstage (pré-alpha) — 2026-07-13

Réplica, para as superfícies de operador, do QA exploratório do storefront (2026-07-11). Bateria de
**12 agentes em 2 ondas** contra a stack real de dev (Django `:8000` + os 5 apps Nuxt: Central
`:3001`, PDV `:3002`, KDS `:3003`, Gestor `:3004`, Fournil `:3005`), operador admin/PIN 1234,
banco seedado Nelson. Relógio do teste: **seg 2026-07-13, ~10h–14h BRT (loja ABERTA)**.

- **Onda B (fluxos por app):** B1 POS/descontos/pagamento/comandas · B2 KDS/expedição · B3
  Gestor/cancelamentos · B4 Produção/planejamento/faltas · B5 Fechamento de caixa/turno · B6
  jornada cross-app.
- **Onda C (cenários/personas):** C1 operador novato + permissões · C2 tempo/horários/TTLs · C3
  variações extremas de pedido · C4 rajada/corrida/dupla ação · C5 falhas e recuperação · C6
  **continuidade e copy fim-a-fim** (lente nova do Pablo: transições cujo destino não recebe
  adequadamente — em fluxo, ações disponíveis e copy).

Achados-manchete **re-verificados independentemente** por mim (leitura de código + inspeção do DB +
teste vivo no browser), separando bug real de artefato de concorrência (12 agentes no MESMO banco
SQLite e na MESMA sessão de browser). Relatórios brutos por agente em `scratchpad/findings/B{1..6}-*.md`
e `C{1..6}-*.md`.

### Caveats de ambiente (importam para staging!)

- **Nenhum worker de directives rodava** na stack de QA: `confirmation.timeout`/`payment.timeout`
  são do `process_directives --watch` (ADR-003), que o `maintenance_worker` **não cobre** — são
  dois workers distintos. ⚠️ **Conferir o spec do deploy**: se staging/prod só sobe o
  `maintenance_worker`, auto-confirm, auto-cancel e timeout de PIX nunca disparam.
- Em dev os 6 apps compartilham UMA sessão Django (cookie por host `127.0.0.1`; portas não isolam).
  Isso amplificou o achado do lock global (P1 abaixo) — que é real também em prod, porque o cookie
  `.boulangerie` cross-subdomínio produz a mesma sessão única por dispositivo, **por design**.
- "database is locked" sob rajada = SQLite dev; some no Postgres. O que NÃO some está marcado.

---

## Veredito

O esqueleto é bom: SSE entrega pedido novo ao Gestor/KDS em segundos, idempotência segurou TODAS as
variações de duplo-clique/replay, a cascata de cancelamento em estados válidos funciona (KDS +
estoque + notificação + estorno), a contagem cega é cega de ponta a ponta e a matemática do
fechamento bate ao centavo. **Mas a exploração encontrou 2 P0 e um conjunto denso de P1 que os
testes pré-definidos não pegam**, porque moram exatamente nas COSTURAS: promessas de uma tela que a
tela seguinte não cumpre, confirmação otimista sem canal de retorno à origem, e dois pipelines de
preço (review × commit) que divergem. A lente de "falha de continuidade" foi a mais produtiva da
bateria — o bug-semente do Pablo era um empilhamento de 3 falhas dessa família.

---

## P0 — Trava a operação

### 1. Venda-fantasma no PDV: "Pedido criado", dinheiro na gaveta — e o sistema cancela em silêncio
Confirmado 3× independentes (B1-4, C5-1, C6-01) + **5 pedidos reais no banco de hoje**
(PDV-260713-G38/T18/S02/M26/H09: `payment.tenders[].status="received"`, `cash_shift_id` gravado,
status `cancelled` por `auto_reject_unavailable` no MESMO segundo).

O grid do PDV não indica esgotado e a `review_sale` não valida disponibilidade; o `close_sale`
responde `ok:true` + recibo, e o gate de estoque roda DEPOIS, no lifecycle
(`shopman/shop/lifecycle.py:806` `_check_availability` → cancela). O POS **não tem sino nem SSE**
(grep `EventSource|alerts` em `surfaces/pos-nuxt` = zero) — o operador nunca fica sabendo; entrega
o produto, registra o dinheiro, e o pedido morre. O aviso vira `OperatorAlert` com tipo fora das
choices (`"rejected_unavailable"` cru, meio inglês — `lifecycle.py:805,882` vs
`shopman/backstage/models/alerts.py`), visível só no sino do Gestor/Fournil, soterrado por alertas
de "Notificação falhou" — que, aliás, **sempre** falharão em venda de balcão (sem telefone) e
geram ruído a cada ocorrência. Não existe fluxo de devolução do dinheiro.

**Correção sugerida:** decidir disponibilidade ANTES do commit no canal `pdv` (422 acionável na
review/close) **ou** configurar o balcão para nunca auto-rejeitar (o item já saiu fisicamente) —
ver Questão 1; + push de status pós-venda no POS; + não enfileirar notificação sem destinatário.
`[CANONIZAR]` venda POS de item esgotado nunca responde ok silencioso.

### 2. Expedição do KDS está quebrada: nenhum pedido pode ser despachado/concluído pela UI
Confirmado por B2 na UI real + verificado por mim no código. Todo card da estação Expedição
renderiza como ticket de PREPARO (timer "NaNh", checkboxes fantasmas) e "Finalizar" → 404 "Ticket
não encontrado". Causa: o type guard `isExpeditionCard`
(`surfaces/kds-nuxt/app/presentation/board.ts:57`) testa `!("items" in card)`, mas a projection
passou a incluir `items` em todo card de expedição (commit `86229186`,
`shopman/backstage/projections/kds.py:91`) — o guard falha para 100% dos cards e o "Finalizar"
posta o **pk do Order no namespace de KDSTicket** (risco de bumpar ticket alheio se os pks
colidirem). A estação inteira está inoperável. **Correção:** discriminador estável (campo `kind`
explícito na projection). `[CANONIZAR]` contrato de tipo dos cards de expedição.

---

## P1 — Corrigir antes dos usuários internos

### Autorização gerencial no PDV (o bug-semente, em 3 camadas)

O caso relatado pelo Pablo ("desconto → 'gerente precisa autorizar' → sem caminho na UI") é um
empilhamento verificado:

- **(a) Promoção automática é lida como override do operador** (B1-2, B6-12). O persist→reload da
  comanda "assa" o preço promocional no `unit_price_q`; `derive_price_overrides`
  (`shopman/shop/services/pos.py:1355-1378`) compara com o preço canônico SEM promoções
  (`OffermanPricingBackend.get_price`) e marca `price_overridden=True` → **toda comanda com item em
  promoção ("Semana do Pão") exige gerente**, sem nenhum desconto manual — e a auditoria grava
  `price_approved_by` mentiroso. Desconto em linha D-1 também SEMPRE exige gerente
  (`pos.py:1168-1173`) — a janela noturna força o fluxo.
- **(b) O diálogo nunca reabre após rejeição** (B1-1, previsto por código e reproduzido na UI).
  `onManagerAuthorize` grava credenciais e fecha o diálogo ANTES do servidor validar
  (`PosPaymentWorkspace.vue:235-240`); `approvalBlocking` só checa não-vazio (`:146-150`);
  o `catch` do close vira toast (`usePosSale.ts:1069`) e o `manager_approval_invalid` (com
  `recovery` que a UI descarta) deixa o CTA em "Validar" re-enviando as MESMAS credenciais erradas
  para sempre. O `PosManagerAuthDialog` até tem prop `error` desenhada para esse retry — não é
  conectada. Escape acidental: sair e voltar ao checkout (nada sugere isso).
- **(c) O gerente "oficial" não consegue aprovar** (C1-02). O grupo Gerente do `setup_groups`
  **não tem** `backstage.adjust_cashshift` (nem `manage_operators`) — exatamente o que
  `_verify_manager_pin` exige (`pos.py:1156`). Gerente de RBAC com PIN correto recebe "Aprovação
  gerencial inválida"; só a `marina` do seed funciona (perms diretas). Bônus: o diálogo pede "Nome
  do gerente" mas casa **username exato case-sensitive** sem picker (C1-04), e cada typo do caixa
  consome o **lockout do PinCredential do gerente** — 5 erros travam o gerente em TODAS as
  superfícies por 5 min, em silêncio (C1-05; as mensagens de "PIN errado", "travado" e "sem
  permissão" são idênticas).

`[CANONIZAR]` (1) comanda com promoção ativa não exige gerente; (2) grupo Gerente aprova override;
(3) rejeição de PIN reabre o diálogo com o recovery.

**Status da correção (branch `fix/backstage-qa-p0`, 2026-07-13):**
- **(c) grupo Gerente** ✅ corrigido (`setup_groups.py` ganhou `adjust_cashshift`+`manage_operators`;
  Fase 0 do seed).
- **(b) diálogo reabre após PIN recusado** ✅ corrigido (commit `d5b98f86`) + **e2e VERIFICADO
  (2026-07-14, destravado pelo C1-01):** comanda #1008 com desconto de linha 90% (> piso R$5) →
  "Autorizar e validar" → admin + PIN 9999 → o diálogo REABRE inline com o recovery do servidor
  ("Revise o gerente e o PIN, ou reduza o desconto / ajuste o preço."), credenciais limpas (não vira
  toast nem trava no "Validar"); admin + PIN 1234 → finaliza (PDV-260714-L00). ⚠️ Observação colhida
  no teste: a review/pagamento cobrou **R$ 0,13** para uma linha de R$ 13 com 90% off (parcial do
  carrinho R$ 1,30) — o desconto foi aplicado ~2× (persist→reload "assa" o preço já descontado e o
  modifier re-desconta). É a MESMA família do bug-semente (a): o pipeline re-aplica sobre o preço
  frozen. Ver item (a) abaixo.
- **(a) promoção lida como override** ✅ **CORRIGIDO (2026-07-14, commit `0e2df777`).** O gate deixou
  de comparar o `unit_price_q` com o catálogo puro (que flagava toda linha em promoção/D-1/happy-hour,
  cujo preço com desconto foi "assado" pelo persist→reload). Passou a marcar `price_overridden` **só
  quando há a intenção EXPLÍCITA do operador** (`price_overridden` do numpad "Preço", `posIntent.ts:101`)
  **somada a um preço fora do catálogo** (ou SKU sem âncora). Descontos automáticos de sistema não
  carregam essa intenção → não disparam gerente nem congelam a linha (some o `price_approved_by`
  mentiroso). **Segurança preservada e verificada:** um preço rebaixado SEM a intenção não congela a
  linha (só o flag derivado congela em `build_session_ops`) e o `ItemPricingModifier` (POS é sempre
  `internal`, confirmado) reprecifica de volta ao catálogo − descontos legítimos no commit — não há
  subfaturamento a guardar; um override genuíno abaixo do legítimo AINDA exige gerente. Optou-se por
  ESTE approach (intenção + backstop de repricing) em vez de recomputar o preço efetivo do pipeline
  dentro do gate, porque o `DiscountModifier` (promoções/cupom/coleção/aniversário/best-wins) é
  inviável de replicar sem drift. Cobertura: `test_pos_line_discount.py` (preço assado D-1 e promoção
  NÃO exige; override com intenção exige; preço baixo sem intenção não é gate) + `review_sale`
  ponta-a-ponta no `pdv` seedado (baked→False, override→True). ⚠️ **Nota:** a divergência de valor
  observada no e2e do B1-1 (R$1,30 no carrinho vs R$0,13 na review, desconto MANUAL ~2×) é bug
  SEPARADO da família "review×commit divergem" (B1-3) — este fix não a cobre.

### Dinheiro: review × commit divergem e o caixa herda a diferença

- **Desconto prometido no review é ignorado no commit em linhas frozen** (B1-3, pedido real
  PDV-260713-T18): tela cobra R$ 0,00, pedido grava R$ 26,35 e
  `_reconcile_order_payment_to_total` (`pos.py:299-303`) "reconcilia" o pagamento para cima em
  silêncio. Causa: `ManualDiscountModifier` exclui linhas `_price_is_frozen`
  (`shopman/shop/modifiers.py:920+`), e por (a) acima as linhas promocionais chegam todas frozen.
- **Repricing silencioso review→close** (C6-07): review R$ 13,00 → pedido fecha R$ 11,05
  (`pos_reconciled_from_amount_q: 1300`), resposta do close sem aviso e **recibo congelado com o
  total da review** (`usePosSale.ts:1040-1054`) — operador cobra 13, caixa espera 11,05.
- **Tender default com total zero** (B1-7): `paymentTotalQ = review?.total_q || cartTotalQ(...)`
  (`usePosSale.ts:222`) — zero é falsy, injeta o total PRÉ-desconto na linha de pagamento.
- **Sangria sem teto nem alçada** (B5-1): aceitou R$ 99.999 num caixa de ~R$ 309, sem comparação
  com o esperado nem PIN gerencial (`shopman/backstage/services/pos.py:49-80`) — a infra de alçada
  já existe para desconto.
- **Contagem cega errada é beco** (B5-2): turno fechado não reabre; Admin readonly; o "ajuste
  pós-fechamento" não recalcula `expected/difference` (`models/cash_register.py:138-237`) e o
  Admin nem aceita ajuste negativo (`admin/cash_register.py:87-94`). Não existe estado
  "divergência resolvida" nem alerta de divergência.
- **Fechamento do dia irreversível com efeitos físicos** (B5-3): 2º POST → 409; Admin bloqueia
  delete até para superuser (`admin/closing.py:42-49`); os movimentos de estoque D-1/perda
  (`services/closing.py:44-63`) não têm undo. Só shell.

`[CANONIZAR]` total da tela == `Order.total_q` == pagamento, em toda venda com
desconto/promoção/D-1; fechamento com contagem vazia/lixo rejeitado (C5-7: `{"counted":{"cash":"abc"}}`
fechou o turno com contagem 0).

### Encomendas: a cozinha e o cliente vivem no dia errado

Confirmado 3× (B2-3, C2-1 exercitado com pedido real, C6-03 seguido fim-a-fim). Encomenda para
+1/+3 dias auto-confirma em 5 min e: dispara **KDSTicket imediatamente** (SLA de 5 min correndo,
sem NENHUM campo de data no ticket — `shopman/backstage/projections/kds.py:52-74`), move o pedido
para `preparing` HOJE, manda "estamos preparando" ao cliente 3 dias antes, e o tracking promete
"fica pronto por volta das 11:17 [de HOJE]" + "pode retirar quando quiser" (ETA ignora
`delivery_date` — `shopman/storefront/presentation/order_tracking.py:602-608`). Gestor não mostra
data/slot/badge de encomenda em card nem detalhe (`order_queue.py` não lê
`delivery_date`/`is_preorder`). O contraste que prova a incongruência: o ESTOQUE é preorder-aware
(hold planned com `target_date` correto). Com `max_preorder_days=30`, o board da cozinha pode
afogar em tickets "atrasados" de semanas. Causa central: `_on_confirmed` →
`_dispatch_physical_work` incondicional (`shopman/shop/lifecycle.py:404`), sem consciência de data.
**Correção:** reter o dispatch físico até a manhã do `delivery_date` (directive agendada) + expor
data/slot em ticket, card e tracking. `[CANONIZAR]` preorder não aparece no KDS antes do dia.

### Cancelamento e estorno: o dinheiro não tem caminho de volta

- **Cancelar pedido pronto/despachado/entregue é no-op silencioso** (B3-1, pedido real pago
  Z89): POST → 200 `{"ok":true}`, diálogo fecha, nada muda — `cancel()` retorna `False`
  (`shopman/shop/services/cancellation.py:44-50`), `cancel_order` ignora o retorno
  (`operator_orders.py:225-246`), a view finge sucesso (`operations.py:849-868`). O operador
  acredita que cancelou, que o cliente foi avisado e que o estorno saiu.
- **Não existe superfície de devolução/estorno** (B3-2): o core tem `RETURNED` completo
  (`lifecycle.py:526-531` — revert stock + refund + fiscal + notificação) e a máquina permite
  DISPATCHED/DELIVERED/COMPLETED→RETURNED; zero endpoints/botões. Cortesia/reembolso parcial: idem.
- **Estorno que FALHA fica invisível no pedido** (B6-3, pedido real L77): intent seguiu `captured`,
  o alerta CRÍTICO (copy ótima) existe só no sino, soterrado em ruído, sem CTA; o detalhe do pedido
  cancelado mostra "PIX·captured" sem nenhum aviso.
- **Cancelamento iFood degrada para texto livre quando o fetch de códigos falha** (B3-3): com a
  lista vazia o pedido vira "canal comum" (`OrderReasonDialog.vue:35`), o cancel segue sem
  `cancellation_code` — em prod, cancela local e o iFood mantém o pedido.

`[CANONIZAR]` cancel inválido → 409 com motivo; pedido pago cancelado exibe estado do estorno.

### Produção → estoque: a fornada não chega à vitrine

- **Fornada finalizada cai na posição "Vitrine D-1 (ontem)"** (B4-1 + B6-2, 2 WOs reais, 100% do
  "recebido de produção" de hoje): `Position.objects.filter(is_saleable=True).first()` sem
  order_by (`packages/craftsman/shopman/craftsman/contrib/stockman/handlers.py:500`) devolve
  `ontem` (alfabético) — posição EXCLUÍDA dos escopos de venda. Fournil diz "concluída", Gestor diz
  "100%", e a vitrine segue vendendo nada. Pão fresco entra no bucket de desconto D-1.
- **Guardrail de insumos = falso positivo crônico + consumo que nunca acontece** (B4-2): toda
  receita consome `MASSA-*` (pré-preparo), que nunca tem Quant nem é produzível pela UI → TODO
  finish abre o modal "Insumos insuficientes" e o operador aprende a forçar sempre; enquanto isso
  `_consume_materials` skipa em silêncio → **farinha/água/fermento nunca baixam por produção** — o
  ledger de insumos é ficção (o guardrail do WP-B5b está neutralizado na prática).
- **Quantidade do finish sem validação** (B4-3): 999999 passa (valida materiais pelos `started`,
  não pelo pedido do finish; `execution.py:63-74` sem teto) e viraria estoque vendável fantasma.
- **Reduzir planejado abaixo do comprometido = 500 + beco** (B4-4): `CraftError [COMMITTED_HOLDS]`
  vaza cru (`operations.py:1098-1104` não captura), toast "Tente de novo" que nunca vai funcionar,
  sem menção às encomendas.

`[CANONIZAR]` finish credita na posição vendável canônica; finish consome matéria-prima explodindo
sub-receitas.

### Corridas que perdem venda ou cegam a cozinha

- **Duas abas na mesma comanda: fechamento sobrescreve com snapshot velho** (C4-1, pedido real
  S02): item lançado na outra aba some do pedido e da cobrança, sem aviso — `close_sale` faz
  replace sem checar `Session.rev` (`shopman/shop/services/pos.py:254`; o campo existe e não é
  usado; idem no save, B1-10). A aba perdedora do fechamento duplo cai em limbo "não salvo" com
  retry eterno de 5s e orientação errada (C4-3).
- **Gestor-cancela × KDS-bumpa** (C4-2): bump 500 cru, ticket fica `done` num pedido `cancelled`
  (save antes da transição, `shop/services/kds.py:455-462`, sem atomicidade/lock), aparece em
  `recent_done` como venda normal e o alerta de cancelamento à cozinha nunca acontece. Não é
  artefato de SQLite.
- **"Avançar" sem guard de estado esperado** (B3-8): clique sobre tela defasada pulou etapa
  (confirmado→ready num clique); aceitar `expected_status` e responder 409 como o confirm já faz.
- **Remover item já enviado à cozinha** (B1-5): sem PIN de gerente (o gate existe e não está
  ligado a este caminho), ticket KDS fica órfão `pending`, e a comanda esvaziada fica marcada "não
  pago" no board sem evidência navegável.

### Sessão, lock e recuperação: o operador cai no lugar errado

- **Auto-lock de UM app tranca TODOS** (B6-1): `ACTIVE_OPERATOR_SESSION_KEY` é global na sessão
  (`shopman/backstage/services/operator.py:32`); o idle de 60s do POS derruba Gestor/KDS no meio
  da ação, e quem desbloqueia por último em qualquer app vira o operador atribuído de todos.
  Real também em prod (cookie único por design). Ver Questão 4.
- **POS travado mostra tela de LOGIN em vez do PIN** (C1-01 + C5-3): `needsLogin =
  Boolean(error.value)` (`surfaces/pos-nuxt/app/app.vue:54`) engole o 403 "Estação travada";
  em dispositivo fresco é login-loop sem saída; depois de logado, cada clique vira toast infinito
  sem nunca abrir o gate. O POS é o único app fora do `OperatorLock` compartilhado (ver seção
  Crachá).
  **✅ CORRIGIDO (2026-07-14, commit `addb2ed2`):** o PDV foi alinhado ao lock compartilhado
  (operator-kit `useOperatorLock`). `usePosOperatorLock` passou a compor o kit: sessão de dispositivo,
  operador ativo, must-change e elegíveis vêm de `operator/session/` e `operator/eligible/?perm=`,
  INDEPENDENTES do `/pos/` — exatamente como nos outros 4 apps. `needsLogin` virou `!authenticated`
  (device_user ausente); `PosLockScreen` renderiza em `authenticated && (locked || mustChange)` com
  `:operators="eligible"`. O PDV mantém auto-lock por ociosidade (kiosk) e erro de PIN inline. Verificado
  e2e (:3002): travado+sessão → picker de PIN (não login); unlock admin/1234 → board; travar → volta ao
  picker, nunca login; happy path intacto. Destravou o e2e do B1-1.
- **Blip de rede no KDS = tela de login** (C5-2): refetch de `operator-session` que falha por REDE
  anula a sessão conhecida e o shell conclui "não autenticado" — cozinha com wi-fi instável perde
  o board; beco até a rede voltar.
- **Re-gate de sessão expirada nos writes é código morto** (C5-4): `isUnauthenticatedError` espera
  401, DRF SessionAuthentication devolve 403 — o "Sua sessão expirou" do POS é inalcançável; os 4
  apps tratam writes com sessão morta como toast eterno.
- **5 endpoints 500 com traceback para IDs inexistentes** (C5-5): production
  start/finish/advance-step/void e KDS board por slug (`DoesNotExist` não capturado) — kiosk com
  board velho cai nisso em uso normal.
- **`mock-confirm` devolve sucesso sem confirmar nada** em pedido `new` (B6-4,
  `shopman/storefront/api/payment.py:181-188`) — em staging o QA lerá como "pagamento sumiu".
- **[Auditar] Tracking do cliente morre se a sessão for reciclada** (B6-5): o acesso anônimo
  depende 100% de `shopman_order_access_refs` na sessão (`customer_orders.py:562`); observado grant
  sumindo ao reaproveitar a sessão. Considerar token por-pedido assinado no URL.

---

## P2 — Fricção real (verificados; fix claro)

**Continuidade/copy (lente nova — os mais emblemáticos):**
- "Abrir no gestor" pós-venda leva ao **Django Admin** (parede de login; Admin é CRUD-only), não ao
  orders-nuxt — `usePosSale.ts:1058` (B1-8/C6-02; 3 agentes).
- Fechar o turno termina em NADA: o `result` da API é descartado (`usePosSale.ts:1296-1310`) — sem
  resumo, comprovante nem próximo passo (B5-15); sangria idem, sem confirmação nem comprovante
  (B5-19).
- Copy do caixa manda a conferência para "o gestor", mas o Gestor de Pedidos não tem tela de caixa;
  a conferência só existe no Admin (`PosCashPanel.vue:106,125,190` — B5-16). Divergência de
  contagem não gera alerta nem aparece em superfície nenhuma; o fechamento do dia grava
  `cash_shift_summary` e não o exibe (B5-17). O fechamento do dia inteiro (execução com escrita de
  estoque) vive SÓ no Admin; a API headless existe sem consumidor (B5-9).
- Observação do cliente chega ao KDS mas NÃO ao Gestor (`has_notes` só lê `kitchen_note`,
  `order_queue.py:548`) — quem confirma decide às cegas (C6-04, era P1 do agente; mantido alto).
- Pedido web perde o nome do produto: operador lê SKU cru ("2× BICHON") em Gestor/KDS — falta
  `name=` no add do carrinho (`cart_mutations.py:95-101`; B2-4/B6-15/C6-05).
- Comanda batizada no POS vira "00001012" no KDS e "00001010" como CLIENTE no Gestor (KDS nunca lê
  `tab_ref` — `kds.py:346-353`; B2-6/B6-14).
- Alertas anunciam e não roteiam: `order_ref` é texto morto, sem link; pedido auto-cancelado nem
  está no board — investigar = digitar URL (C6-08). Ack zera badge sem o problema sumir (C6-09).
  Central é cega: sem sino/badges/contagens; 31 alertas pendentes (1 CRÍTICO) invisíveis no hub
  (B6-17/C6-10); e o tile "Loja online" é um link morto (relativo à origin do hub — `hub.py:38`,
  B6-6).
- Promessas incondicionais: "os itens vão para a cozinha" (fire pode descartar itens em silêncio —
  `shop/services/kds.py:135,178-197`); "o cliente é avisado" (sem canal → 5 retries → alerta)
  (C6-11/12).
- "Marcar pronto" no Gestor não fecha o ticket do KDS (B2-2/B3-5 — cozinha produz pedido que já
  saiu; 2 ocorrências reais no banco) — na fronteira P1/P2; fix espelho do `cancel_tickets`.

**Gestor:**
- Barra de ações do detalhe ignora o estado: Confirmar/Recusar/Avançar/Cancelar sempre visíveis
  (v-if do Avançar é um typo sempre-true — `[ref].vue:137-153`; B3-4); pedido cancelado segue
  "vivo" com ações no-op (B6-10).
- Auto-cancel por timeout de pagamento é invisível (card some do quadro sem alerta; prazo de
  pagamento sem countdown — B3-6); auto-conclusão de entrega (ETA+30min) idem (B3-12).
- Sem histórico: cancelado/concluído inencontrável; `recent_history` existe sem consumidor (B3-7 +
  C1-06 — inclui reimpressão de recibo e "quanto vendi hoje" sem caminho).
- Pago vs não-pago indistinguíveis no card (chip "PIX" igual para captured e pending — B6-9);
  board SSE reordena sob o dedo (risco de misclick em Recusar — B6-11); 403 de lock vira "Pedido
  não encontrado" no detalhe e "Reconectando…"+"Ao vivo" verde no board (B3-9/B6-7); um clique com
  rede caída apaga o quadro inteiro (recupera ≤30s — C5-6); pedido fora do expediente mostra
  countdown "665:00" em M:SS (deadline honesto no backend, projection descarta
  `deferred_until`/`outside_business_hours` — C2-2); countdown chega a 0:00 e congela mentindo
  (C2-3); timeline vaza "Created" e JSON cru (C6-14); abas Catálogo/Expositores visíveis para quem
  não tem permissão — 403 cru até para a gerente do seed (C1-07).
- iFood: stale alert (30 min) dispara no exato minuto em que o hold de estoque expira (30 min), e
  confirmar depois não re-valida disponibilidade (C2-4 — ajustar defaults do seed).

**PDV:**
- Desconto de 150% aceito e clampado em silêncio (B1-6); desconto de pedido 100% (venda grátis)
  NÃO exige gerente com threshold=0 enquanto preço R$ 0 sempre exige — duas estradas para o mesmo
  resultado, uma só com cadeado (C3-1; ver Questão 2).
- Caixa fechado em outra estação: erro só no submit, sem CTA de abrir caixa, sidebar stale (o
  backend manda `focus`/`recovery` e a UI ignora — B1-9).
- Comanda esquecida com itens (até disparados) é DELETADA em silêncio após 48h pelo
  `cleanup_stale_sessions` (B1-11 — viola a regra de TTL transparente).
- Venda de balcão sem comanda vive só em memória: F5 = perda total silenciosa (C4-4); fundo de
  troco negativo clampado a R$ 0 sem erro (B5-6); reabrir caixa aberto descarta o novo fundo com
  ok=true (B5-7); multi-terminal inoperável e o 409 promete "selecione outro terminal" que não
  existe (B5-8); fechar turno com comandas abertas/não pagas não avisa (B5-5); fechar o DIA com
  turno aberto passa em silêncio (B5-4); "Vendas hoje" não corresponde ao turno multi-dia (B5-10).
- Telefone inválido persiste verbatim (`"+1-800-EVIL"` → 201; fallback `normalize_phone(x) or raw`
  — C3-2) e `notes` do cliente entra 100% cru (sem XSS ao vivo — Vue escapa — mas `Card.vue` tem
  `v-html` de pé de coelho e caminhos server-side futuros ficariam expostos; C3-3).

**Produção:**
- Primeiro "Avançar passo" é no-op e pode REGREDIR o passo exibido (off-by-one meta×tempo —
  B4-5); 5 fornadas de ontem presas em "started" invisíveis na visão Hoje ("0 EM PROCESSO" —
  B4-7); estornar WO com pedidos comprometidos desfaz o vínculo em silêncio, sem alertar o Gestor
  (B4-8); sugestão usa o weekday de HOJE, não da data-alvo, e "—" sem explicação (B4-9); alerta
  diz que a produção "falhou" quando foi concluída com force (B4-10); lock de estação vira
  "Estamos tentando reconectar sozinhos" sem reabrir o gate (B4-6); fechamento de ontem nunca
  feito e nada cobra (C2-5).
- Vocabulário divergente no mesmo app: dashboard hardcoda "Novo"/"Despachado" vs canônico
  "Recebido"/"Saiu para entrega" (C6-13); becos mudos em estados vazios (KDS "Nenhuma estação
  configurada.", plan "Nenhuma receita ativa." — C6-16).
- Kit de resiliência existe e não é usado: `retryWithBackoff`/`isTransientError` com zero usos nos
  5 apps; OfflineBanner só reage a `navigator.onLine` (C5-8); erros de corrida vazam
  `str(exc)`/500 fora do dialeto (`CommitError.in_progress`, `InvalidTransition` — C4-5, parte
  real).

## P3 — Polimento (amostra; detalhe nos relatórios por agente)

Copy/dialeto: status em inglês em toasts/alertas ("status: cancelled", "rejected unavailable");
"PAGO R$ 0,00" quando é dinheiro físico recebido (renomear "Recebido"); "Em Preparo" vs "Em
preparo"; travessão largo em copy viva (inclusive do cliente); "Order not found"/JSON parse em
inglês; 404 dos 5 apps é a página crua do Nuxt em inglês (nenhum tem `error.vue`; rota pt-br velha
de kiosk cai feio); erros KDS sem instrução. Fluxo: keypad de PIN ignora teclado físico; botão
"Cancelar" morto na troca forçada de PIN; scan de crachá inválido é ignorado em silêncio e crachá
sem permissão fala linguagem de PIN; abrir comanda com ref inexistente CRIA comanda fantasma no
board; cancelar já-cancelado devolve 200 falso; nota de pedido aceita 100KB; timer do KDS não se
relaciona com a promessa (zumbis de ontem no topo para sempre; cancelado não-reconhecido some em
10min sem ack); telefone cru como identidade em banners do KDS; "Taxa de entrega" listada como
item; filtros/busca perdidos na volta detalhe→fila; data do Fournil fora da URL (kiosk não
bookmarka "amanhã"); hydration mismatch no Gestor e Fournil; SSE com sessão morta reconecta em
loop; gate de lock inconsistente entre reads (POS/Gestor 403, KDS index 200 — C1-08/C5-15);
Transferir itens só lista comandas ocupadas; bundle com componente fracionário sumiria do ticket
(`int()` trunca — latente); troco sem teto (R$ 100.000 → troco R$ 99.990 sem aviso); mistura de
desconto linha+pedido reporta desconto > subtotal; `date.today()` residual em fallback de
`pickup_slots.py:44`.

---

## Crachá e telas de PIN (perguntas do Pablo, verificadas)

1. **"Digitar o nome do gerente" confere — e é o username de login**, não o nome (match exato,
   case-sensitive). Recomendação: picker de gerentes elegíveis (o endpoint
   `operator/eligible/?perm=` já existe e a tela de lock já usa picker) — o PIN continua sendo o
   segredo; melhor ainda, aceitar **crachá do gerente** no diálogo de autorização.
2. **Telas de PIN: compartilhadas em KDS/Gestor/Produção** (`OperatorLock` do operator-kit; backend
   unificado em `operations.py:314+`). **O POS reimplementou a própria**
   (`PosLockScreen`/`usePosOperatorLock`/`PosPinChange`) — e a duplicação já cobra: o lock do POS
   não tem crachá e tem os bugs C1-01/C5-3. A Central não tem lock de operador. Recomendação:
   migrar o POS para o componente compartilhado.
3. **Crachá: o backend está completo e o scan FUNCIONA — testei ao vivo.** Emiti um crachá via
   shell (`PinCredential.issue_badge(user)` → token de 24 hex), simulei o leitor na tela de lock do
   Gestor (o leitor é keyboard-wedge: campo oculto sempre focado captura a digitação rápida +
   Enter) e a estação destravou com o operador certo no primeiro scan. A copy da tela já promete
   "Passe o crachá no leitor". **Porém não "funciona plenamente" por 3 buracos:** (a) **não existe
   UI nem comando para emitir crachá** — `issue_badge` só é chamado em testes; impossível dar um
   crachá a alguém sem shell; (b) o POS (lock próprio) não aceita crachá; (c) o diálogo de
   autorização do gerente não aceita crachá.
   **Ritual para o Pablo testar fisicamente:** `cd ~/Dev/Claude/django-shopman && .venv/bin/python
   manage.py shell -c "from django.contrib.auth import get_user_model; from
   shopman.doorman.models import PinCredential; print(PinCredential.issue_badge(
   get_user_model().objects.get(username='admin')))"` → gerar um Code128 do token impresso →
   passar o leitor na tela de lock do KDS/Gestor/Fournil. (Emitir de novo revoga o anterior.)

---

## Positivos verificados (recomendo canonizar como regressão)

- **Idempotência exemplar:** `client_request_id` dedupe no close (curl + double-click; zero venda
  duplicada em todas as variações), bump/expedição replay no-op, double-cancel idempotente, fire
  duplo não duplica ticket, sangria dupla fechada na UI, `CashShift` com unique constraints.
- **SSE:** pedido novo → Gestor/KDS em ~5–10s sem reload; cancelamento cruzado Gestor→KDS cancela
  todos os tickets com banner + "Ciente"; fallback de poll honesto ("Atualização automática",
  ~35s); detalhe do Gestor atualiza ~10s.
- **Confirmação otimista com countdown visível** nos cards de ENTRADA (e deadline deferido para
  fora do expediente calculado certo no backend); timeout de PIX cancela e avisa o cliente em 15
  min fim-a-fim; tracking do cliente reflete avanços na hora.
- **Contagem cega de verdade:** painel nunca mostra o esperado; a resposta do close esconde
  expected/difference; matemática do fechamento verificada ao centavo contra o DB (incluindo
  adoção de venda órfã de outro terminal, correta).
- **Fluxos de produção:** plan cria Quant planejado com `target_date` (o mecanismo do P0 do
  storefront existe e funciona); finish→estoque→disponibilidade confirmado (11→17 un); estorno em
  planned/started com copy adequada; mise-en-place explode matéria-prima.
- **Presets de cancelamento (G2)** ponta a ponta (motivo chega ao cliente); gate de pagamento antes
  do preparo com mensagem clara; roteamento de tickets por estação correto; notas de cozinha (PR
  #42) e do cliente chegam ao ticket; XSS probes renderizam escapados; hub permission-aware com
  estado vazio que orienta; login do operador com rate-limit amigável; auto-lock do POS preserva a
  venda por baixo do lock; recuperação de comanda pós-queda de rede OK.

---

## Artefatos deixados no banco (transparência)

Pedidos QA: PDV-260713-{P59,T18,T14,C97,Q69,E70,G38,S02,M26,H09,D00,X44,J69*}, WEB-260713-{Z83
auto-cancelado, K39 ready c/ ticket 316 pending, Z89 dispatched pago, N55 ready, L77 cancelado
c/ estorno pendente, A96 new sem intent, X93/P03/K57/C56/K16/M54/J02/P24/M05/C72},
WEB-260712-{E98,K03} cancelados. Comandas: #1012 aberta não paga (evidência B6), #NOPE limpa.
WOs: WO-2026-22628/22629 concluídas com estoque na posição `ontem` (evidência P1). Turno 90
fechado (diff −945, evidência B5), turno 92 ABERTO ao final; DayClosing de teste deletado (só
resta 11/07). Movimentos QA de caixa com efeito líquido zero. Usuários `qa-*` todos deletados;
admin/PIN intocados; crachá de teste emitido e usuário removido.

---

## Questões incontornáveis (decisão do Pablo)

**1. Venda de balcão × disponibilidade (P0-1).** ✅ **DECIDIDO (2026-07-13): (b)** — o canal `pdv`
nunca auto-rejeita (a venda vale; o estoque ajusta por reconciliação); a validação na review é
AVISO, não gate. No balcão o item já saiu fisicamente da vitrine.

**2. Política de descontos e aprovação gerencial.** ✅ **DECIDIDO (2026-07-13):** threshold **default
R$ 5,00 (500q)** (no `config/settings.py`; a suíte fixa `0` como baseline hermético e testa via
`override_settings`), com as regras de aprovação **admin-configuráveis** (RuleConfig) como direção —
threshold + condições (price override, total R$ 0, D-1) editáveis. UX do diálogo (picker de gerente
+ crachá) segue recomendada.

**3. Encomendas × cozinha.** ✅ **DECIDIDO (2026-07-13):** roteamento em três destinos por TEMPO,
não dispatch imediato único. Ver [docs/plans/ENCOMENDA-ROUTING-PLAN.md](../plans/ENCOMENDA-ROUTING-PLAN.md).
Resumo: encomenda com lead time disponível → Planejamento de Produção (demanda); pós-lead-time e
antes do estoque realizado → Gestor em espera ("fermata"); contra estoque realizado → KDS/picking.

**4. Lock de operador: global ou por app?** ✅ **DECIDIDO (2026-07-13): (b) escopo por superfície.**
`active_operator` passa a ser por superfície (`active_operator:pos`, `:kds`, …) — o idle de um app
não derruba os outros e a atribuição de operador deixa de vazar entre apps. (Aplica-se ao achado
B6-1.)

**5. Onde vive a conferência de caixa e o fechamento do dia?** ✅ **DECIDIDO (2026-07-13): micro-app
Nuxt "Pontos de Venda"** (precedente Odoo), domínio próprio de PDV/caixa: lista os terminais
cadastrados (`POSTerminal`), controla sessões de caixa (`CashShift`) — abrir/fechar, ver se há
sessão aberta —, conferência de divergência, reabertura supervisória e relatórios. É a **porta de
entrada do PDV** (abre a sessão aqui → opera o registro). Consolida a família B5 + o multi-terminal
(B5-8) + os relatórios sem caminho (C1-06). É a **porta de entrada do PDV** (abre a sessão aqui →
opera o registro), o que também mata o beco "abra o caixa antes de vender" (B1-9).

✅ **Fronteira e OBRIGATORIEDADE decididas (2026-07-13):** a contagem dos **não vendidos** mora no
domínio de **produção** (Fournil); a conferência de **caixa** no Pontos de Venda. **Forma:**
provavelmente uma **reforma na entrada do pos-nuxt** (camada de sessão/terminal antes do registro,
modelo Odoo num app só), não necessariamente um app novo — decisão de implementação do WP. O
fechamento do dia (caixa **+** não vendidos) é **obrigatório e diário**, garantido por **interlock
DURO**: o caixa não abre para um novo **dia operacional** (calendário real — a loja opera **Seg–Sáb**
e fecha **domingo**, então o "dia anterior" pula domingo) enquanto o dia operacional anterior não
estiver 100% fechado. O sistema **conduz** para o passo que
falta a partir de onde o operador estiver — ao fechar o caixa, já convida a fechar os não vendidos;
ao tentar abrir o caixa, se faltou, roteia na hora para o app correto (nunca um beco). **Grounding:**
o não vendido de hoje É o insumo do D-1 de amanhã (`shopman/backstage/services/closing.py:44-60`,
classificação `d1` → posição "ontem"; `loss` → baixa) e é o que transiciona fresco → D-1/perda; sem
ele, o estoque de ontem conta como fresco hoje (deriva de contabilidade). Detalhar no WP do Pontos
de Venda (interlock + guided-close cross-app com o Fournil). Corrige C2-5 (fechamento de ontem nunca
feito e nada cobra).

**6. Trabalho pós-QA.** Os demais P1/P2 têm fix claro e não dependem de decisão — posso encaminhar
em lotes (sugestão de ordem: P0s → cluster gerencial → dinheiro/caixa → encomendas → estorno →
produção/estoque → corridas → sessão/erros) quando você aprovar.
