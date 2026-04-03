# WP-R9: Polish + Documentação — Prompt de Sessão

Estou executando o WP-R9 do plano RESTRUCTURE-APP-PLAN.md (na raiz do repo). Leia o plano INTEIRO antes de começar — ele contém contexto arquitetural essencial (princípios, consistência semântica, hierarquia de flows, apps.py wiring).

Objetivo: Ajustes finais pós-reestruturação — audit, documentação, seed, limpeza.

Contexto: R0–R8 estão concluídos. O `shopman/` é agora o único app de orquestração. `channels/` e `shop/` foram removidos. Todos os 1.901 testes passam (370 app + 1.531 core). Única falha pré-existente: `auth/test_senders.py::TestWhatsAppCloudAPISender` (falta `httpx` — sinalizado em memória para resolução).

## Estado Atual (R8 concluído)

### Estrutura shopman/ pós-reestruturação:

```
shopman/
├── models/             Shop, Promotion, Coupon, RuleConfig, OperatorAlert, KDS*, DayClosing
├── services/           11 services (stock, payment, customer, notification, fulfillment, etc.)
├── adapters/           8 adapters (payment_efi, payment_stripe, payment_mock, notification_*, stock_internal, otp_manychat)
├── rules/              engine.py, pricing.py, validation.py
├── flows.py            BaseFlow → Local/Remote/Marketplace + dispatch()
├── handlers/           16 directive handlers (copiados de channels/)
├── backends/           16 backends (copiados de channels/)
├── setup.py            register_all() — registro centralizado de handlers
├── config.py           ChannelConfig dataclass (copiado de channels/)
├── protocols.py        Contratos (StockBackend, NotificationBackend, etc.)
├── topics.py           Constantes de tópicos de directives
├── notifications.py    Registry + dispatch de notificações
├── confirmation.py     Helpers de confirmação
├── modifiers.py        D1, Discount, Employee, HappyHour modifiers
├── webhooks/           efi.py, stripe.py
├── admin/              shop, orders, alerts, kds, closing, rules, dashboard, widgets
├── web/
│   ├── views/          19 módulos (catalog, cart, checkout, tracking, auth, account, kds, pedidos, pos, etc.)
│   ├── cart.py         CartService
│   ├── constants.py    CHANNEL_REF, HAS_AUTH, HAS_STOCKING
│   ├── urls.py         Todas as URLs do storefront
│   ├── templates/      78 templates (storefront, kds, pedidos, pos, components)
│   └── static/         Icons, JS, images
├── api/                views, serializers, catalog, account, tracking, urls
├── templatetags/       storefront_tags.py
├── context_processors.py  shop() + cart_count()
├── management/commands/   seed, cleanup_d1, cleanup_stale_sessions, suggest_production
├── kds_utils.py        dispatch_to_kds()
├── middleware.py        ChannelParamMiddleware, OnboardingMiddleware
├── apps.py             ShopmanConfig (signal wiring + handler registration + rules boot)
└── tests/              7 test modules + web/ + integration/ + e2e/
```

### O que NÃO existe mais:
- `channels/` — removido (84 .py, ~14.619 LOC)
- `shop/` — removido (39 .py, ~5.275 LOC)
- `shopman_commons/` — removido (era shim, imports corrigidos no Core)

### Pendências conhecidas (NÃO resolver neste WP, apenas documentar):
- BusinessHoursRule: não bloqueia mais checkout (seta flag `outside_business_hours`). Fluxo completo de encomendas/horário pendente de revisão dedicada.
- WhatsApp Cloud API sender: test falha por `httpx` não declarado. Avaliar se é dead code (WhatsApp é via ManyChat).
- Gestor de Pedidos: bloated, avaliar migrar para Admin/Unfold ou redesenhar UX.
- Pipeline audit: guards, transições, edge cases após iterações.

## Entregáveis

### 1. Core Service Usage Audit

Verificar que TODOS os services em `shopman/services/` usam Core services corretamente:

```bash
# Para cada service, verificar:
# - stock.py → usa StockService (holds), CatalogService (expand)
# - payment.py → usa PaymentService
# - customer.py → usa CustomerService
# - pricing.py → usa CatalogService.price()
# - checkout.py → usa CommitService, ModifyService
# - etc.
```

Se algum service contornar o Core (acesso direto a models em vez de usar services), corrigir.

### 2. Atualizar CLAUDE.md

O CLAUDE.md reflete a estrutura antiga (`channels/`, `shop/`). Atualizar:

- Seção "Estrutura do Projeto": substituir `channels/` e `shop/` pela nova estrutura do `shopman/`
- Seção "Convenções Ativas": verificar que todas ainda se aplicam
- Seção "Core é Sagrado": manter (continua válido)
- Seção "Como Rodar": verificar comandos
- Seção "Referências": atualizar links se docs mudaram
- Remover qualquer menção a `channels/`, `shop/`, `handlers/backends/` como conceitos primários
- Adicionar menção a flows.py, services/, adapters/, rules/ como conceitos primários

### 3. Atualizar docs/reference/data-schemas.md

Verificar que todas as chaves de `Session.data`, `Order.data`, `Directive.payload` estão documentadas, incluindo:
- `outside_business_hours` (novo, adicionado em R8)
- Qualquer chave nova adicionada durante R0-R8

### 4. Criar docs/guides/flows.md (substituindo channels.md)

O `docs/guides/channels.md` descreve a arquitetura antiga (handlers, backends, pipeline, ChannelConfig). Criar `docs/guides/flows.md` documentando:

- Hierarquia: BaseFlow → Local/Remote/Marketplace
- 10 fases do lifecycle (on_commit → on_returned)
- Como dispatch() funciona (signal → registry → flow method)
- Relação flow ↔ services (flow coordena, service executa)
- Relação services ↔ adapters (service chama adapter swappable)
- Rules engine (RuleConfig no DB, engine avalia, pricing/validation)
- Exemplo concreto: pedido web (cart → checkout → payment → tracking)

Depois: remover ou renomear `docs/guides/channels.md` (pode mover para `docs/plans/completed/` como referência histórica).

### 5. Seed command

O `shopman/management/commands/seed.py` já existe e não importa de `channels/` nem `shop/`. Verificar que:
- `make seed` funciona
- Dados criados são consistentes com a nova estrutura
- RuleConfigs padrão são criados no seed

### 6. Mover planos concluídos

- `RESTRUCTURE-APP-PLAN.md` → `docs/plans/completed/`
- `WP-R8-PROMPT.md` → `docs/plans/completed/`
- `WP-R9-PROMPT.md` → `docs/plans/completed/` (este arquivo, ao final)
- `AUDIT-PROMPT.md`, `AUDIT-REPORT.md` → `docs/plans/completed/` (se existem na raiz)
- Qualquer outro plano solto na raiz (`WP-POLISH.md`, etc.)

### 7. Limpeza final

- Verificar que `tests/` (fora do shopman) não tem mais testes relevantes — só devem existir em `shopman/tests/`
- Se `tests/` tiver arquivos residuais, avaliar: migrar ou remover
- Remover `__pycache__` dirs soltos
- Verificar `project/settings.py`: zero referências a `channels` ou `shop` (como app standalone)

### 8. WhatsApp Cloud API sender — resolver

Em `shopman-core/auth/shopman/auth/tests/test_senders.py`, o teste `TestWhatsAppCloudAPISender::test_send_code_success` falha por `ModuleNotFoundError: No module named 'httpx'`.

Opções (escolher a mais pragmática):
- **A)** Adicionar `httpx` como dependência opcional do auth (`[whatsapp]` extras) e no Makefile
- **B)** Se WhatsAppCloudAPISender é dead code (WhatsApp é via ManyChat, não Meta Cloud API direta), marcar os testes com `pytest.importorskip("httpx")` e documentar que o sender está deprecated
- Consultar memória: `feedback_whatsapp_via_manychat.md` — WhatsApp é via ManyChat

## O que NÃO fazer

- NÃO implementar o fluxo de BusinessHours/encomendas — está pendente de revisão dedicada
- NÃO alterar lógica de negócio — apenas documentar, auditar, limpar
- NÃO refatorar handlers/backends copiados do channels — eles funcionam, podar é futuro
- NÃO criar features novas

## Critério de Sucesso

1. `make test` verde (1.901+ testes, zero regressão)
2. `make lint` limpo (ou apenas warnings pré-existentes)
3. `make seed` + `make run` funcionais
4. `CLAUDE.md` reflete a estrutura real do projeto
5. `docs/guides/flows.md` existe e documenta a nova arquitetura
6. `docs/guides/channels.md` movido para completed/
7. Zero planos soltos na raiz do repo (tudo em `docs/plans/completed/`)
8. `docs/reference/data-schemas.md` atualizado com chaves novas
9. WhatsApp sender test resolvido (skip ou dep instalada)

## Ordem sugerida

1. Audit de services (rápido, leitura)
2. Documentação (CLAUDE.md, flows.md, data-schemas.md)
3. Seed + run validation
4. WhatsApp sender fix
5. Mover planos concluídos
6. Limpeza final
7. Rodar testes + lint

Já fica previamente aprovado para fazer todas as alterações pertinentes à tarefa. Vou me ausentar e quando retornar quero o trabalho concluido!
