# AVAILABILITY-SALE-PRODUCTION-PLAN — disponibilidade × venda × produção

> Mandato (Pablo, 2026-07-14): "encomendas antecipadas devem conviver com pedidos
> normais e serem tratadas como cidadãs de primeiríssima classe". Este plano nasce
> de falhas reais de QA no staging e de uma decisão de produto explícita. Mudanças
> aqui são ESTRUTURAIS: cada WP volta ao Pablo antes de virar código.

## 0. Evidência (QA staging, 2026-07-14)

Fluxo: cliente adiciona 2 BAGUETE (sem estoque pronto, fornada planejada pra HOJE)
→ sacola aceita, linha em lista de espera (holds planejados `262/263/264`, target
`2026-07-14`, `expires_at=None`) → cliente FAZ LOGIN via access link (19:56) →
checkout de ENTREGA com `delivery_date=2026-07-15` (AMANHÃ — o registro
original supunha "hoje"; corrigido no WP-A com evidência do DB) → envio do
pedido (19:58:42) falha:

```
stock.hold: create_hold failed sku=BAGUETE qty=2.000 code=INSUFFICIENT_AVAILABLE
→ "BAGUETE ficou indisponível antes de concluirmos a sua reserva."
```

Leitura: o gate de commit (`lifecycle.secure_stock` → `stock.hold(require_all=True)`)
NÃO adotou os holds da sessão (fallback `create_hold` rodou para a qty INTEIRA) e o
`create_hold` novo esbarrou em indisponibilidade — plausivelmente nos PRÓPRIOS holds
órfãos do cliente, que seguem ativos para sempre (`expires_at=None`).

Às 20:07 o mesmo padrão apareceu SEM raise (caminho brando, `_alert_hold_gap`) para
BRIOCHE-CHOCOLAT/BRIOCHE-BURGER/BICHON/BATARD — confirmar qual fluxo foi esse.

## 1. Causas candidatas (WP-A investiga e CONFIRMA antes de corrigir)

1. **Identidade da sessão através do login.** Os holds do carrinho são tagueados com
   `metadata.reference = cart_session_key`. O exchange do access link
   (`storefront/api/auth.py`) pode trocar/flushar a sessão Django; a re-adoção da
   sacola via metadata do token (`cart_session_key` só entra "se a sessão atual
   estiver vazia") tem janelas de perda. Se o pedido commita com outra session_key,
   `_load_session_holds` volta vazio → adoção zero.
2. **Holds planejados órfãos são eternos.** `expires_at=None` sem dono vivo nunca
   expira: seguram o plano do dia e fazem o próprio cliente (e os demais) competirem
   com um fantasma. Não há varredura para órfãos planejados (`cleanup_stale_sessions`
   cobre?). Verificar e criar backstop.
3. **Data futura desliga a adoção por design.** `stock.hold`: `adopt_session_holds =
   target_date in (None, hoje)`. Com data futura, exige `create_hold` contra o
   `target_date` — se não há planejamento PARA AQUELA DATA, o commit recusa. Para a
   casa, isso é exatamente a ENCOMENDA que deveria ser aceita (registrar demanda e
   alimentar a sugestão de produção), não recusada.

## 2. Decisões de produto já tomadas (Pablo, 2026-07-14)

- **Encomenda antecipada = cidadã de 1ª classe.** Convive com pedido normal em todas
  as superfícies (sacola, checkout, gestor, KDS/produção, fechamento).
- **Vocabulário**: linha sem pronta-entrega = **"Lista de espera"** (não "Aguardando
  confirmação"). A sacola orienta: enviar o pedido garante prioridade (fila por ordem
  de chegada). O "avisamos quando ficar pronto" vive na REVISÃO do pedido, não na
  sacola. Título da revisão: **"Revise seu pedido"**. (Entregue em PR separado.)
- **A data já existe no checkout** (`delivery_date` → `get_commitment_date` →
  target de estoque). NADA de inventar novo seletor; o estudo é sobre fazer o motor
  honrar a data de ponta a ponta.

## 3. Work packages

### WP-A — Causa raiz do commit falho (investigação, SEM mudança de produto)
- Reproduzir em teste: add → login (troca de sessão) → checkout hoje → commit.
  Confirmar qual das causas do §1 dispara (instrumentar `_load_session_holds`).
- Mapear o ciclo de vida da `cart_session_key` através de TODOS os logins
  (access link, WhatsApp start no site, in-app browser) e do merge de sacola.
- Entregável: relatório curto + testes de regressão vermelhos (a base do WP-B).

### WP-A — Achados (2026-07-14, investigação concluída) ✅

**Veredito: a causa que disparou é a §1.3 (data futura), não a §1.1 (login).**
Evidência lida direto do DB do staging (probe read-only via `doctl apps console`):

- A sessão do commit falho é `SESS-S37K9EYXUGUH`, `state=open`, e
  **`delivery_date=2026-07-15` — AMANHÃ**. O §0 supunha "checkout com data de
  hoje"; o banco corrige: o pedido era para o dia seguinte (entrega, com
  `__DELIVERY_FEE__` na sessão). `IdempotencyKey commit:web:SESS-S37K9EYXUGUH
  = failed` confirma que foi ESTE commit que caiu.
- Os holds 262/263/264 têm `metadata.reference = SESS-S37K9EYXUGUH` — a MESMA
  chave que commitou. **A `cart_session_key` sobreviveu ao login**; adoção não
  falhou por identidade. (262 foi `released` às 19:55:28 pelo reconcile do
  stepper; 263+264 seguem `pending`, qty 1+1, target 2026-07-14,
  `expires_at=None`.)
- Cadeia exata do raise: `delivery_date=amanhã` → `get_commitment_date` →
  `adopt_session_holds=False` (`services/stock.py:79` — adoção só para
  hoje/None) → fallback `create_hold(target_date=2026-07-15)` → não há quant
  planejado para 15/07 e a política é `planned_ok` → `INSUFFICIENT_AVAILABLE`
  → `ValidationError(insufficient_stock)` → rollback + beco sem saída.
- O padrão das 20:07 "sem raise" era o **PDV** (`PDV-260714-J91`,
  `payment.timing=external` → caminho brando `_alert_hold_gap`). Pergunta do
  §0 respondida: fluxo diferente, mesmo sintoma de reserva impossível.

**Causa §1.2 confirmada como bomba ativa (agravante).** Holds 260/261 de um
round QA ANTERIOR (`SESS-P8V2TWA4RAHW`, 17:29 UTC) seguem `pending` e eternos
(`expires_at=None`) segurando 2 unidades da fornada de hoje. Fábricas de
órfãos planejados encontradas, nenhuma com varredura:
  1. Sacola abandonada (browser fechado): nada libera holds indefinidos.
  2. `assign_phone_handle(abandon_existing=True)` no checkout abandona as
     sessões abertas antigas do MESMO telefone sem liberar os holds delas
     (`shop/services/sessions.py:126-132`).
  3. `cleanup_stale_sessions` DELETA a Session sem liberar os holds (a
     referência morre, o hold fica).
  4. `release_expired` ignora `expires_at=None` por definição.

**Causa §1.1: janelas reais, mas nenhuma disparou.** Mapa do ciclo de vida da
`cart_session_key` (que é a chave da *Session do Orderman* guardada DENTRO da
sessão Django — a rotação de cookie não a destrói por si):
  - add → `request.session["cart_session_key"]` (`storefront/cart.py:63`).
  - access link, mesmo browser → preservada explicitamente
    (`doorman/services/access_link.py:239-258` + `PRESERVE_SESSION_KEYS`).
  - access link, browser novo (in-app WhatsApp) → adotada da metadata do token
    SE o token carrega `cart_session_key` E a sessão atual está vazia
    (`storefront/api/auth.py:168-170`). Janela: token mintado sem contexto do
    site → a sacola não segue; a antiga vira fábrica-de-órfão nº 1.
  - OTP verify-code → preservada (`doorman/services/verification.py:308-321`).
  - trusted-device (`shop/services/auth.py:181`) → `login()` SEM preserve
    explícito; sobrevive via `cycle_key` (anônimo→login), mas o flush (troca
    de usuário na mesma sessão) PERDE a chave. Janela menor.
  - logout → preservada (`preserved_session_values`); checkout OK → `pop`.

**Entregável de testes**
(`shopman/storefront/tests/api/test_checkout_hold_adoption_login.py`):
  - 3 VERDES (guardrail): commit adota os holds planejados da sacola através
    de access link (mesmo browser), access link (browser novo via metadata) e
    OTP — fixa a continuidade que hoje funciona.
  - 2 VERMELHOS (comportamento esperado, base do WP-B/WP-C):
    - `test_second_round_same_phone_not_blocked_by_abandoned_session_ghost_holds`
      — round 2 do mesmo telefone leva 409 no add: o cliente compete com o
      próprio fantasma (§1.2).
    - `test_checkout_tomorrow_with_todays_planned_batch_is_accepted_as_preorder`
      — reprodução EXATA do QA (mesma assinatura de log); fixa a decisão de
      produto do §2: encomenda para amanhã é aceita, não recusada.

### WP-B — Higiene de reserva: órfãos planejados + janelas de login ✅ (2026-07-14)
*(Escopo recalibrado pelos achados do WP-A: a adoção através do login FUNCIONA
— o re-tag por troca de identidade não é necessário, a referência é a chave do
Orderman e viaja dentro da sessão Django. O problema real são os órfãos.)*
- **Liberar holds ao abandonar sessão** (as 3 fábricas do WP-A): função única
  `release_session_holds(session_key)` no shop, chamada por (a)
  `abandon_session`/`clear_session`, (b) `assign_phone_handle`
  (`abandon_existing`), (c) `cleanup_stale_sessions` antes do delete.
- **Varredura backstop** (maintenance_worker): hold planejado ativo cuja
  `reference` não tem Session `open` nem Order viva → release + OperatorAlert
  (o operador precisa saber que o plano do dia foi devolvido).
- **Fechar a janela do trusted-device**: preservar `cart_session_key` em volta
  do `login()` em `trusted_device_login`, mesmo padrão do Doorman.
- Deixa VERDE: `test_second_round_same_phone_not_blocked_by_abandoned_session_ghost_holds`.

**Implementado (2026-07-14):** `release_session_holds` em
`shop/services/availability.py`, chamado por `abandon_session` (cobre
`clear_session`), `assign_phone_handle(abandon_existing)` e
`cleanup_stale_sessions` (antes do delete). Varredura backstop =
`sweep_orphan_holds` (novo comando, no ciclo do `maintenance_worker`): libera
holds indefinidos com referência de sessão morta OU `target_date` passada,
com `OperatorAlert`; nunca toca `purpose=workorder` nem `order:<ref>`.
Trusted-device preserva a sacola no flush. Testes:
`shop/tests/test_orphan_hold_hygiene.py` (6) +
`test_checkout_hold_adoption_login.py` (fantasma e trusted-device verdes).

**Caso deliberadamente FORA do WP-B:** sacola anônima VIVA (aberta, sem
telefone) segurando a fornada contra outros clientes não é órfã — é
concorrência real de lista de espera. O tratamento certo é o WP-C (demanda
além do plano vira encomenda/registro de demanda, não 409 no add).

### WP-C — Desenho proposto (2026-07-14, APROVADO e IMPLEMENTADO)

**Implementado (2026-07-14):**
- Stockman: `StockHolds.hold(allow_demand=True)` — canal autoriza registrar
  demanda quando a política do produto não é `demand_ok`; pausado continua
  recusando. `retag_reference` aceita metadata extra (ex.: `priority`).
- Materialização (`StockPlanning.realize`): o pool inclui holds FLUTUANTES de
  demanda (quant=None) do sku/data e ordena por `metadata.priority` asc
  (ausente = por último), FIFO dentro da classe — pedido enviado (priority=0)
  materializa antes da sacola quando a fornada é curta.
- Gate de commit (`shop/services/stock.py`): data futura + canal com
  `stock.preorder` → holds de hoje da sessão são liberados (leftover) e a
  reserva nasce na data-alvo; sem plano → demanda registrada
  (`reference=order:<ref>`, `priority=0`, `expires_at=None`).
- `ChannelConfig.stock.preorder: bool = True` (PDV/marketplace declaram False).
- Lifecycle: `_on_confirmed`/`_on_paid` ADIAM KDS + baixa quando a data é
  futura e agendam a directive `preorder.activate` (despertador, dedupe por
  pedido, `available_at` = madrugada da data). Handler → `activate_preorder`:
  dispara KDS, baixa o que materializou (`fulfill(pending_materialization_ok)`)
  e marca PREPARING. O receiver de `holds_materialized` estende o backstop de
  48h dos holds de pedido (o TTL de vitrine de 30min não evapora encomenda) e
  completa a baixa adiada quando a fornada da data materializa.
- Produção: `suggest` JÁ enxergava a demanda registrada — o
  `OrderingDemandBackend.committed()` conta holds de demanda por data (Core
  já resolvia; nenhuma mudança).
- Invariante antiga "dia sem produção → recusa" (test_preorder_closed_store_
  commit) atualizada para a decisão nova: registra demanda; canal com
  `preorder=False` mantém a recusa.
- Testes: e2e da encomenda (o vermelho do QA agora VERDE, com demanda/
  despertador/sem-KDS-hoje), `test_preorder_activation.py` (3),
  `stockman/tests/test_preorder_demand.py` (4).

Desenho aprovado (referência):

O contrato observável já está fixado pelo teste vermelho
`test_checkout_tomorrow_with_todays_planned_batch_is_accepted_as_preorder`.
Mecânica proposta, em 4 movimentos:

1. **Gate de commit aceita encomenda** (`shop/services/stock.py`): com
   `target_date` futuro e canal que permite encomenda, o fluxo vira:
   (a) holds da sessão (target hoje) são LIBERADOS — o desejo é para outra
   data, mantê-los roubaria a fornada de hoje; (b) `create_hold` na data-alvo:
   com plano para a data → hold planejado normal (já funciona); sem plano →
   **hold de demanda** (`quant=None`, `expires_at=None`, `reference=order:<ref>`).
   O Stockman JÁ tem o modo demanda (`StockHolds.hold`, política `demand_ok`);
   a única mudança no Core é um kwarg explícito `allow_demand=True` para o
   chamador autorizar o fallback quando a política do PRODUTO não é
   `demand_ok` — extensão mínima do mecanismo existente, sem migração.
2. **Política por canal** (`ChannelConfig.stock`): novo campo no aspecto
   Stock (ex.: `preorder: bool = True` no web/WhatsApp, False no PDV/iFood).
   Horizonte continua sendo o `max_preorder_days` que já governa o checkout;
   corte por dia continua no business_calendar (fechado/after_close). Nada de
   seletor novo.
3. **Produção enxerga a demanda**: `craftsman.suggest` ganha um piso de
   demanda REGISTRADA — holds de demanda com `target_date=D` entram na
   sugestão do dia D (além do histórico). Encomendas aparecem no plano do dia
   (Fournil) na data certa; verificar que KDS/expedição não disparam o pedido
   de amanhã hoje (gate por `delivery_date` na fila).
4. **Prioridade na materialização** (`planning.realize` → transferência de
   holds): pedidos ENVIADOS (`reference=order:*`) materializam antes de
   holds de sacola, FIFO dentro de cada classe (decisão do §2). Na
   materialização o hold de demanda ancora no quant físico e o fulfill segue
   o ciclo normal.

Contrato de erro (WP-E antecipado no que toca o commit): recusa por estoque
só quando NÃO há caminho de encomenda no canal; a mensagem oferece a data
("encomende para amanhã") em vez do beco "ficou indisponível".

### WP-C — Encomenda com data futura (o coração do mandato)
- Commit com `target_date` futuro SEM plano para a data: aceitar como demanda
  registrada (hold de demanda `quant=None` contra a data), nunca recusar por
  `INSUFFICIENT_AVAILABLE` quando o canal permite encomenda.
- Política por canal (`ChannelConfig.stock`): o que é encomendável, horizonte
  (`max_preorder_days` já existe no checkout), corte por dia.
- Produção enxerga a demanda: `suggest_production` considera holds de demanda por
  data; encomendas aparecem no plano do dia (Fournil) e no KDS na data certa —
  hoje o pedido de amanhã não pode disparar pra cozinha hoje.
- Prioridade da fila: pedido ENVIADO ganha prioridade sobre lista de espera de
  sacola (decisão Pablo). Materialização (`planning.realize`) atende primeiro
  holds de pedidos commitados, depois holds de sacola, FIFO.

### WP-D — Superfícies contam a mesma história
- Sacola: linha "Lista de espera" com a orientação de prioridade (feito no PR de
  labels); mostrar a DATA prevista quando houver plano ("fornada de amanhã").
- Revisão/tracking: "avisamos quando ficar pronto" + estado claro de encomenda
  ("pedido para sábado, 08:00"). Gestor/KDS/fechamento: encomenda visível e
  filtrável por data, sem poluir o dia corrente.
- Notificação ativa na materialização (§8.3 do AVAILABILITY-PLAN) CONFERIDA de
  ponta a ponta (WhatsApp/SMS reais, não toast).

### WP-E — Guardrails
- E2e: os 4 fluxos canônicos (pronta-entrega hoje · lista de espera hoje ·
  encomenda com plano futuro · encomenda sem plano) × (anônimo · logando no meio).
- Contrato de erro: recusa por estoque só quando NÃO há caminho de encomenda; a
  mensagem oferece o caminho ("encomende para amanhã") em vez de beco sem saída.

## 4. Fora de escopo deste plano
- Redesenho do seletor de data do checkout (já existe e fica).
- Substitutos inline na sacola (STOCK-UX-PLAN cobre).
- Antesala do PDV (plano próprio).

## 5. Referências
- `shopman/shop/services/stock.py` (hold/adoção/gate), `shopman/shop/lifecycle.py`
  (`secure_stock`), `shopman/shop/services/availability.py` (reserve/reconcile/classify),
  `shopman/storefront/api/auth.py` (exchange/adoção de sacola),
  `packages/stockman` (holds/planning/realize), AVAILABILITY-PLAN §5/§8 (concluído),
  ADR-007 (auto-commit pós-materialização).
- Memórias: `feedback_availability_is_about_when`, `project_storefront_preorder_when_flow`.
