# GO-LIVE-ALPHA-AUDIT — Auditoria de prontidão para o alpha

> **STATUS (2026-07-02): ✅ CORRIGIDO.** Todos os lotes 1–6 foram implementados com
> teste reproduzindo cada bug antes do fix (suíte completa verde). Residuais que
> NÃO entraram (baixo risco, pós-alpha): templates de e-mail/SMS lidos do Admin
> (hoje só ManyChat lê o DB), backend WhatsApp Meta plugável, re-geocodificação
> server-side de lat/lng, sinal de offline no polling de pagamento do Nuxt,
> rate-limit do checkout contando tentativas inválidas. Decisões que seguem com
> o Pablo: impressão física (kiosk print vs KDS-only), NFC-e para venda online
> (S5), e2e homolog Focus NFe (token disponível — plugar env e rodar), staging
> sem PII real. Falso positivo confirmado: SSE /gestor/events já era gateado por
> staff via ShopmanChannelManager (EVENTSTREAM_CHANNELMANAGER_CLASS).

> **Data:** 2026-07-02 · **Método:** 7 auditorias paralelas de código (lifecycle/pagamentos,
> checkout/delivery, fiscal, estoque/produção, notificações/impressão, auth/operador, KDS),
> com verificação cruzada contra testes existentes e spot-check manual dos críticos.
> **Baseline:** `make test` 2297 passed · `make lint` verde (após 2 correções triviais de lint).
>
> **Veredito: a fundação é sólida, mas o sistema NÃO está pronto para o alpha.**
> Os defeitos concentram-se nas *costuras do orquestrador* — o padrão recorrente é
> **fail-open com log em vez de fail-loud com alerta** — e na camada de dinheiro periférica
> (taxa de entrega, loyalty, cupom, troco). O Core (Stockman, Payman, Orderman, Doorman)
> foi verificado e está genuinamente robusto.

## O que está verificado e SÓLIDO (não mexer)

- **Payman**: mutações atômicas com lock, captura única, refund limitado, reconcile correto.
- **Webhooks**: EFI (token+HMAC), Stripe (assinatura), iFood (HMAC) — todos fail-closed; replay
  guard durável; race "pagou depois de cancelar" tratado com refund + alerta, testado.
- **Stockman core**: hold com re-check sob `select_for_update`, `F()` + CheckConstraint no banco,
  testes de concorrência reais. Overselling clássico (2 cliques na última unidade) bem resolvido.
- **Checkout**: preço 100% server-side, commit idempotente (lock + cache de resposta), cupom
  re-validado no commit, double-submit mitigado por design.
- **Doorman/OTP**: HMAC-SHA256, 3 camadas de rate-limit, comparação constant-time, magic links
  single-use com hash, session fixation coberto, deploy check E010 fail-closed.
- **Emissão fiscal**: idempotência sólida (sem cenário realista de nota duplicada).
- **Backstage**: nenhum endpoint de operador sem permissão explícita; IDOR de pedido/conta fechado.

---

## 🔴 BLOQUEADORES (não fazer alpha sem corrigir)

### Dinheiro

1. **Taxa de entrega nunca é cobrada no storefront.** `DeliveryFeeModifier` grava só
   `session.data["delivery_fee_q"]`; `Order.total_q` = soma das linhas; PIX/cartão/fiscal usam
   `order.total_q`. Cliente vê R$ 56 no finalizar (`cart.py grand_total_q`), QR PIX sai R$ 50.
   Só o POS injeta linha `__DELIVERY_FEE__` ([modifiers.py:539](../../../shopman/shop/modifiers.py),
   [commit.py:342](../../../packages/orderman/shopman/orderman/services/commit.py),
   [payment.py:54](../../../shopman/shop/services/payment.py)). Perda direta em todo delivery.
2. **Loyalty: desconto sem débito.** `checkout_data["loyalty"]` não está na lista de propagação
   do `_do_commit` → `services/loyalty.py` retorna cedo → pontos nunca debitados = desconto
   infinito repetível. Bug secundário: débito (se propagado) usaria saldo integral sem clamp ao
   desconto dado. ([commit.py:298-305](../../../packages/orderman/shopman/orderman/services/commit.py))
3. **EFI: conversão float de centavos.** `int(float(v) * 100)` trunca (4.35→434) em
   [payment_efi.py:253](../../../shopman/shop/adapters/payment_efi.py) (capture-check/recuperação
   **sempre falha** p/ ~metade dos valores) e `:331` (refund com drift de 1 centavo → segundo
   refund rejeitado, ruído permanente). Fix: `Decimal`, como `_amount_to_q` já faz.
4. **Refund no gateway antes do registro local, com `except PaymentError: pass`**
   ([payment_efi.py:329-340](../../../shopman/shop/adapters/payment_efi.py), payment_stripe.py:224-235).
   Registro local falhando → Payman ainda mostra saldo → segundo trigger autoriza **refund duplo**
   no gateway. EFI não tem webhook de devolução p/ auto-corrigir.
5. **Webhook EFI retorna 200 com erro de processamento** ([efi.py:120-135](../../../shopman/shop/webhooks/efi.py))
   → EFI não reentrega → captura nunca registrada → timeout de pagamento **auto-cancela pedido pago
   sem refund**. Fix: 5xx quando `errors > 0` + consultar `check_gateway_status` antes de auto-cancel.

### Fiscal (NFC-e)

6. **Toda falha de emissão é terminal** — handler faz `DirectiveTerminalError` para qualquer
   `success=False`, inclusive timeout/5xx ([handlers/fiscal.py:61,95](../../../shopman/shop/handlers/fiscal.py)).
   `DirectiveTransientError` (retry/backoff) existe e não é usada. Zero testes dos handlers fiscais.
7. **Nota órfã sem reconciliação**: timeout pós-POST com SEFAZ autorizando → retry com mesmo `ref`
   → 422 "referência já utilizada" → falha eterna. `FocusNFeBackend.query_status` existe e **nunca
   é chamado em produção**. Inverso também: `success = ... or bool(access_key)`
   ([fiscal_focusnfe.py:382](../../../shopman/shop/adapters/fiscal_focusnfe.py)) pode carimbar
   "authorized" sem autorização.
8. **Delivery no POS com taxa quebra a emissão sempre**: `_build_fiscal_items` não filtra
   `__DELIVERY_FEE__` → sem NCM → falha terminal determinística.
9. **Emissão para pedido cancelado é possível** (handler não checa `order.status`; requeue só
   checa chave) e **falha de cancelamento de NFC-e é invisível** (projection só olha topic de emit;
   não há requeue de cancel). Nota válida em pé para venda cancelada = passivo fiscal.

### Estoque

10. **Hold expirado é adotado no commit + fulfill falha em silêncio.** `find_by_reference` não
    filtra `expires_at` (o `find_active_by_reference` correto existe e não é usado aqui);
    `stock.fulfill` com `HOLD_EXPIRED` só loga ([services/stock.py:143-172,232-244](../../../shopman/shop/services/stock.py)).
    Cenário: 35min no checkout → paga PIX → pedido confirmado **sem baixa de estoque** e a unidade
    pode ter sido vendida a outro. Fix: `find_active_by_reference` + renovar TTL no commit +
    OperatorAlert em falha de fulfill.

### Operação (KDS)

11. **Bump multi-estação retorna 400 em sucesso**: `complete_ticket` retorna
    `on_all_tickets_done()` e a facade trata False como erro → todo pedido misto (croissant+café,
    2 estações do seed) mostra toast "Falha na ação" + card fantasma no primeiro bump
    ([shop/services/kds.py:374-390](../../../shopman/shop/services/kds.py), backstage/services/kds.py:37-45).
12. **Recall cria ticket zumbi**: `reopen_ticket` reabre o ticket mas READY→PREPARING não existe
    nas `DEFAULT_TRANSITIONS` → ticket reaberto nunca mais pode ser concluído (caso de uso
    principal do recall, pedido de 1 ticket).
13. **Ticket cancelado bloqueia auto-READY para sempre**: `on_all_tickets_done` não exclui
    `cancelled` — comanda com reprint (unfire+fire) nunca vai a READY. Fix de 1 linha.

### Segurança

14. **HTTP Basic Auth ativo em toda a API** (DRF default sem `DEFAULT_AUTHENTICATION_CLASSES` em
    [config/settings.py:646](../../../config/settings.py)): brute-force online de senha staff sem
    lockout, bypass do 2FA do Admin e do CSRF nos endpoints de operador. Fix de 2 linhas:
    `["rest_framework.authentication.SessionAuthentication"]`.

### Notificações

15. **Elo "sms" da cadeia de notificações de pedido é peso morto** — adapter Twilio lê settings
    top-level que não existem (`is_available()` sempre False); Comtele só existe para OTP.
    Com ManyChat off e cliente sem e-mail: templates não-ativos (`order_confirmed`,
    `order_received`, `payment_confirmed`) são marcados **done silenciosamente** — cliente não
    recebe nenhum sinal do pedido. Fix: plugar Comtele como adapter de notificação e/ou promover
    `order_confirmed` a template ativo.

---

## 🟠 ALTOS (primeira semana do alpha, ou antes se tocar no fluxo)

- **Cupom `max_uses` decorativo**: `uses_count` nunca incrementa em nenhum código. Incrementar com
  `F()` no commit ([models/promotions.py:83-95](../../../shopman/storefront/models/promotions.py)).
- **Zona/taxa de entrega burlável via API**: endereço só-texto passa sem verificação de cobertura e
  taxa zero (sem `delivery_zone_error` → rule não bloqueia); lat/lng do cliente é confiado sem
  re-geocodificação ([api/views.py:182-194](../../../shopman/storefront/api/views.py), modifiers.py:549-551).
- **`change_for` (troco) descartado**: Nuxt coleta e envia; `CheckoutSerializer` não tem o campo;
  pedido em dinheiro fica sem `payment.method` em `order.data`. O caminho legado fazia certo.
- **WO over-yield credita ZERO**: finish com rendimento > planejado → `realize` tenta Move negativo
  → exceção "non-fatal" → nada entra no estoque (nem o planejado); insumos já consumidos
  ([contrib/stockman/handlers.py:427-449](../../../packages/craftsman/shopman/craftsman/contrib/stockman/handlers.py),
  planning.py:133-139).
- **WO under-yield deixa fantasma prometível**: resíduo fica eterno em `batch='started'` →
  `in_production` → prometível sob `planned_ok`; perda (WASTE) nunca vai ao ledger.
- **Adoção com overshoot consome qty do hold, não do pedido** → baixa maior que a venda
  ([services/stock.py:269-283](../../../shopman/shop/services/stock.py)).
- **Cancelamento pós-fulfill não devolve estoque** (só RETURNED devolve; decidir por tipo de item).
- **Comanda descartada deixa tickets vivos na cozinha** (`clear_pos_tab` não cancela KDSTickets).
- **Caixa multi-terminal**: `close()` soma pedidos cash não-tagueados de TODOS os terminais do
  canal → contas não batem com 2 terminais ([cash_register.py:150-184](../../../shopman/backstage/models/cash_register.py)).
  E `ajuste` só aceita valor positivo (sem registrar falta/quebra).
- **POS: reconcile de tenders desconta o troco da ÚLTIMA linha, não da linha de dinheiro**
  ([pos.py:1574-1588](../../../shopman/shop/services/pos.py)): venda mista `[cash 50, pix 20]` p/
  total 60 corta o excedente do PIX (que a maquininha capturou inteiro) → `expected_amount_q` do
  turno superestimado (falta falsa imputada ao operador) e totais do fechamento errados. Troco só
  existe em dinheiro — descontar exclusivamente de tenders cash.
- **POS: cancelar venda recente não devolve estoque** (caso concreto do "cancelamento
  pós-fulfill": canal pdv faz fulfill no ato → `release` é no-op silencioso → todo cancelamento
  na janela de 5min deixa o sistema abaixo do físico, deriva invisível ao fechamento).
- **POS: `cancel_recent_order` sem escopo** ([pos.py:883-904](../../../shopman/shop/services/pos.py)):
  operador só com `operate_pos` cancela pedido de QUALQUER canal (web/iFood — contornando
  `manage_orders` e o fluxo de cancellation_code), de outro terminal, e até venda de turno JÁ
  FECHADO (expected/difference armazenados ficam errados, sem movimento de devolução).
- **Crons de manutenção não agendados no app spec** (`release_expired_holds`, `cleanup_d1`,
  `cleanup_stale_planning`, `cleanup_stale_sessions`) — só worker + migrate no `.do/*.yaml`.
- **SSE `/gestor/events/...` sem autenticação** (order_ref/status/contagens a anônimos).
- **Dupla execução de directive** (dispatcher on_commit não trava a linha que o poller processa):
  risco de notificação/emissão dupla com web+worker — mitigar travando no callback.
- **Pagamento em intent "irmão" invisível** (dois intents por race de initiate → pedido preso
  "aguardando pagamento" com dinheiro capturado; sem lock na criação de intents).
- **`order.data.payment.status` confiável demais**: sem `intent_ref`, "paid" vindo de `set_data`
  da sessão (API autenticada) é aceito pelo lifecycle. Trust boundary a fechar pós-alpha.

## 🟡 MÉDIOS/BAIXOS (selecionados; lista completa nos relatórios dos auditores)

- Fiscal: CPF sem validação de dígito (rejeição SEFAZ assíncrona — validar cedo/inline);
  desconto manual sem rateio por item (risco de rejeição — validar em homolog); débito declarado
  como crédito (POS só tem `card`→`03`); NCM não obrigatório antes da venda (sem gate no catálogo);
  devolução parcial cancela a nota inteira por 2 caminhos concorrentes (decidir com contador).
- Checkout: total pode mudar entre tela e commit sem aviso (sem `expected_total_q`); slot de
  entrega não validado (só pickup); percentual de promoção sem clamp (>100% → total negativo);
  polling de pagamento sem sinal de offline; rate-limit 3/min conta tentativas inválidas.
- Notificações: templates do Admin só afetam ManyChat (email/SMS hardcoded); `preorder_reminder`
  sem template em lugar nenhum (cliente recebe string crua); WhatsApp Meta não plugável sem código
  (`whatsapp` rejeitado pelo ChannelConfig; adapter nunca registrado); dedupe check-then-create
  sem unique constraint; timeout do provedor pode duplicar mensagem cross-canal.
- OTP: cadeia para telefone é só Comtele — provedor fora do ar = login impossível, sem alerta.
- KDS: item sem estação é dropado só com log (parcial → READY sem a cozinha ver o item);
  fire sem lock/constraint (double-tap pode duplicar tickets); falha de 1 poll esconde o board
  15s; `KDSInstance` CASCADE apaga histórico de tickets.
- Config morta: `hold_ttl_minutes` do ChannelConfig nunca lido; `safety_margin` não aplicado no
  reserve; `planned_hold_ttl_hours` aceito e ignorado; backends `webhook`/`push` validados mas
  nunca registrados.
- POS/Caixa: venda em voo durante o fechamento fica órfã de turno (close sem lock; dinheiro na
  gaveta sem contrapartida); `cash_shift_id` é client-writable (`setdefault`) e `null` +
  catch-all pode dobrar a mesma venda em 2 turnos; `date.today()` (TZ do host) misturado com
  `timezone.localdate()` no fechamento do dia — em servidor UTC, fechar após 21h BRT grava
  a data de amanhã com sumários vazios; COD acertado no dia seguinte não entra em NENHUM
  DayClosing; `parse_money_to_q` devolve 0 silencioso p/ entrada inválida no fechamento cego;
  replay de `client_request_id` pode devolver pedido cancelado como `ok: true`; `close()` exclui
  `cancelled` mas não `returned`.

## ⚠️ GAPS de expectativa (decisão do Pablo, não bug)

1. **Impressão física NÃO existe.** Todo caminho é `window.print()` do browser (recibo POS 80mm é
   protótipo web declarado; cozinha é KDS-first — e o KDS é robusto: ticket em DB, SSE+poll).
   Para "impressões valendo" no alpha: validar kiosk `--kiosk-printing` com a impressora real,
   ou aceitar cozinha=KDS e recibo=digital.
2. **Venda online (storefront/iFood) não emite NFC-e** — `issue_document` só nasce no POS
   (escopo S5). Alpha com "notas em tudo" exige antecipar isso ou aceitar o recorte.
3. **Staging expõe OTP no corpo da resposta** (`SHOPMAN_EXPOSE_DEBUG_OTP` default em staging) —
   decisão consciente, mas exige staging sem PII real / atrás de allowlist.
4. **`surfaces/backstage-nuxt/` é órfão** (331MB de node_modules/.nuxt/.output, zero fonte) — apagar.

## Lotes de correção propostos (aprovação por lote)

- **Lote 1 — Dinheiro** (bloqueadores 1–5 + cupom/zona/troco): taxa de entrega como linha no
  commit do storefront (mesmo padrão do POS), propagar+clampar loyalty, Decimal na EFI, refund
  fail-loud, webhook EFI 5xx-on-error + gateway-check antes de auto-cancel.
- **Lote 2 — Fiscal** (6–9 + CPF/NCM): transient vs terminal, `query_status` como reconciliação
  (retry pós-timeout + sweep), filtrar/tratar `__DELIVERY_FEE__`, bloquear emissão p/ cancelado,
  visibilidade de cancel falho.
- **Lote 3 — Estoque/Produção** (10 + over/under-yield + overshoot + revert pós-fulfill):
  `find_active_by_reference` + TTL renovado + OperatorAlert; `realize` p/ actual>planned; WASTE
  no ledger; `min(remaining, hqty)` na adoção.
- **Lote 4 — KDS/Operação** (11–13 + tickets órfãos + caixa: reconcile de troco na linha cash,
  revert de estoque + escopo no cancel recente do POS, multi-terminal, timezone do fechamento).
- **Lote 5 — Segurança/Config** (14 + SSE auth + crons no app spec + Comtele nas notificações).
- **Lote 6 — Resiliência/polimento** (médios/baixos).
