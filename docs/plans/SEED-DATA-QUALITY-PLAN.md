# SEED-DATA-QUALITY-PLAN — Auditoria e melhoria dos dados de seed (dev/staging)

> **Origem:** QA exploratório do backstage (2026-07-13,
> [docs/reports/qa_exploratorio_backstage_2026-07-13.md](../reports/qa_exploratorio_backstage_2026-07-13.md)).
> O Pablo levantou que "dados errados no seed podem induzir situações de erro que não são o que os
> contratos de fato produzem" e pediu **dados de seed impecáveis em dev/staging para testar todos os
> cenários**. Este plano é o WP de execução; a **triagem seed-vs-código já foi feita** (abaixo).
>
> **Decisões do Pablo (2026-07-13):** (1) quick-wins de config feitos na sessão do QA; overhaul de
> dados dinâmicos é este WP próprio. (2) Arquitetura de **dois perfis: `demo` (realista/aleatório
> atual) + `qa` (determinístico, cenários nomeados garantidos)**.

## Princípio-guia (LER ANTES DE TOCAR NO SEED)

**O seed não pode mascarar bug de código.** A maior parte dos achados-manchete do QA são bugs de
código/contrato que o seed apenas *expõe* — "corrigir o seed" para o sintoma sumir esconderia o bug
real. Os seguintes são **CÓDIGO, não seed** — não alterar o dado para contorná-los (têm fix próprio
no relatório de QA):

- **Fornada finalizada cai na posição "ontem":** o seed CORRETAMENTE tem `vitrine` e `ontem` ambos
  `is_saleable=True` (D-1 é venda real, staff-only). O bug é `.first()` sem `order_by` em
  `packages/craftsman/shopman/craftsman/contrib/stockman/handlers.py:500`.
- **Promoção "Semana do Pão" exige gerente:** a promoção seedada é legítima e um cenário que
  queremos testar. O bug é `derive_price_overrides` comparar preço promocional com o canônico
  sem-promoção (`shopman/shop/services/pos.py:1355`).
- **Guardrail de insumo dispara em todo finish com MASSA-\*:** massas serem `PROCESS`/não-estocáveis
  é design correto do seed. O bug é a validação/consumo não explodir sub-receita
  (`shopman/backstage/services/production.py:411`).

Regra: onde o dado do seed é fiel a uma operação real e o CÓDIGO trata errado, **mantém o dado e
corrige o código** (fora deste WP).

## Fase 0 — Quick-wins de config JÁ FEITOS (sessão do QA, 2026-07-13)

Aplicados e verificados; este WP só precisa garantir que sobrevivam ao reseed e cobrir com teste:

- ✅ Grupo **Gerente** ganhou `backstage.adjust_cashshift` + `backstage.manage_operators`
  (`shopman/shop/management/commands/setup_groups.py:52-53`). Era a camada (c) do bug-semente: o
  gerente de RBAC não aprovava override nem resetava PIN.
- ✅ iFood `stale_new_alert_minutes` 30 → **20** (< `hold_ttl_minutes` 30) em
  `config/management/commands/seed.py:2660` — o operador é cutucado enquanto a reserva ainda vale.

**Teste a canonizar (Fase 0):** um teste que compara os gates de permissão usados no código
(`_verify_manager_pin`, `PinCredentialAdmin`, etc.) com as permissões de cada grupo do
`setup_groups` — para que um grupo nunca fique sem a permissão que um gate exige.

## Fase 1 — Arquitetura de dois perfis

Introduzir `--profile {demo,qa}` no comando `seed` (default `demo` = comportamento atual).

- **`demo`:** mantém a geração realista/aleatória atual (35 dias de histórico, `random`,
  multiplicador sazonal) — bom para telas "vivas" e apresentação.
- **`qa`:** conjunto **determinístico e curado** (seed fixo do RNG OU dados literais) que **garante a
  existência de cada cenário-chave**, com refs previsíveis (ex.: `QA-PREORDER-01`) para os testes
  ancorarem. Datas sempre **relativas a `timezone.localdate()`** (nunca literais) para não envelhecer.

Os dois perfis compartilham a base estática (catálogo, canais, posições, receitas, operadores,
grupos); divergem só nos **dados dinâmicos** (pedidos, produção, comandas, turnos, alertas).

## Fase 2 — Cenários nomeados garantidos (perfil `qa`)

Cada cenário abaixo saiu de um achado do QA que os agentes tiveram que **criar à mão** por não
existir no seed. No perfil `qa`, cada um deve existir com ref previsível e estado estável:

**Pedidos:**
- `QA-PREORDER-*` — pedido `is_preorder` com `delivery_date` = amanhã e slot definido, em cada
  estado relevante (novo, confirmado). (Hoje não há pedido preorder seedado — só `preorder_products`
  de estoque.)
- `QA-PAID-READY-*` — pedido PAGO (PIX/cartão capturado) em `ready`/`dispatched`, para exercitar
  cancelamento-tardio e o fluxo de **devolução/estorno** (`RETURNED`). (Hoje não há pedido
  `RETURNED`/estorno seedado — só o template de notificação.)
- `QA-PIX-PENDING-*` — pedido confirmado com PIX **pendente** (para distinguir pago × não-pago no
  card, e testar o timeout de pagamento).
- `QA-IFOOD-*` — pedido de canal `ifood` (para o fluxo de código de cancelamento marketplace).
- `QA-NOTES-*` — pedido web com `order_notes` do cliente (para verificar propagação Gestor/KDS).
- `QA-NAMED-ITEMS-*` — pedido web cujos `OrderItem.name` estejam preenchidos (regressão do bug de
  SKU cru — mas ver nota: o fix real é no `cart_mutations`, o seed só garante o caso de teste).

**Produção:**
- Uma WorkOrder em **cada** estado (`planned`, `started`, `finished`) com `target_date` = hoje.
- Uma WO `started` de **ontem** (para o cenário "fornada de dia anterior presa"), claramente
  identificável.
- Estoque planejado (`Quant.target_date`) para hoje..+6 dias — **já existe** (14–19/07 no DB atual);
  garantir que o perfil `qa` o produza deterministicamente.

**Caixa/comandas:**
- Um turno de caixa **aberto** e um **fechado** (com divergência conhecida, para testar conferência).
- Uma comanda POS **aberta** com itens (e uma com item já disparado à cozinha).

## Fase 3 — Correções de dado/config genuínas (balde B do QA)

Além da Fase 0 (feita), avaliar no overhaul:

- ✅ **Threshold de aprovação de desconto** (`SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q`): Pablo
  definiu **R$ 5,00 (500q)** (2026-07-13, Questão 2). Default no `config/settings.py`; a suíte fixa
  `0` como baseline hermético e testa o gate via `override_settings`.
- **Pedidos antigos em estado ATIVO:** o perfil `demo` gera 35 dias de histórico — confirmar que
  pedidos de dias anteriores não ficam em `confirmed`/`preparing` (senão poluem o board como
  "zumbis"). Fechar/entregar os históricos; deixar ativos só os recentes.
- **Higiene de reseed:** documentar que `make seed` (flush) é o estado limpo canônico; a "poluição"
  vista no QA (206 pedidos, tickets-zumbi) foi acúmulo de testes sem reflush, não bug do seed.

## O que já está BOM (não regredir)

- Datas de pedidos/WOs são **relativas** (`now - timedelta(...)`), não literais. ✅
- Posições D-1 (`vitrine` + `ontem` saleable) e `excluded_positions: ["ontem"]` nos canais remotos. ✅
- Quants futuros com `target_date` (o mecanismo do P0 de preorder do storefront). ✅
- `suppress("seed")` impede notificação real de dado sintético em qualquer ambiente. ✅
- Guard destrutivo do `--flush` em produção. ✅

## Critérios de aceite

1. `seed --profile qa` produz, de forma **determinística**, todos os cenários nomeados da Fase 2
   (idempotente: rodar 2× dá o mesmo conjunto de refs).
2. Nenhuma data literal de calendário em dados dinâmicos (tudo relativo a `localdate()`).
3. Teste de paridade grupo-de-permissão × gate (Fase 0).
4. `make test` verde; `seed --profile demo` mantém o comportamento atual (sem regressão de telas).
5. Um doc curto em `docs/reference/` listando os cenários `qa` e suas refs, para o QA ancorar.

## Referências

- Relatório de QA: [docs/reports/qa_exploratorio_backstage_2026-07-13.md](../reports/qa_exploratorio_backstage_2026-07-13.md)
- Seed: `config/management/commands/seed.py` (4.7k linhas; `handle()` orquestra ~30 `_seed_*`)
- Grupos: `shopman/shop/management/commands/setup_groups.py`
- Schemas de JSONField: [docs/reference/data-schemas.md](../reference/data-schemas.md)
