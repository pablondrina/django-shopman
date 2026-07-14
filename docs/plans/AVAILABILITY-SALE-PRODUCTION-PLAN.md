# AVAILABILITY-SALE-PRODUCTION-PLAN — disponibilidade × venda × produção

> Mandato (Pablo, 2026-07-14): "encomendas antecipadas devem conviver com pedidos
> normais e serem tratadas como cidadãs de primeiríssima classe". Este plano nasce
> de falhas reais de QA no staging e de uma decisão de produto explícita. Mudanças
> aqui são ESTRUTURAIS: cada WP volta ao Pablo antes de virar código.

## 0. Evidência (QA staging, 2026-07-14)

Fluxo: cliente adiciona 2 BAGUETE (sem estoque pronto, fornada planejada pra HOJE)
→ sacola aceita, linha em lista de espera (holds planejados `262/263/264`, target
`2026-07-14`, `expires_at=None`) → cliente FAZ LOGIN via access link (19:56) →
checkout com `delivery_date=2026-07-14` (HOJE) → envio do pedido (19:58:42) falha:

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

### WP-B — Continuidade da reserva através do login
- O pedido tem que adotar os holds do carrinho MESMO com troca de identidade:
  re-taguear holds no momento do merge/adoção da sacola (uma fonte: quem muda a
  session_key re-tagueia `metadata.reference` dos holds ativos), ou adoção por
  linhagem (old_key registrado na sessão nova).
- Backstop para órfãos planejados: varredura (comando de manutenção) que libera
  holds planejados sem sessão/pedido vivo; alerta de operador quando liberar.

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
