# Planos Ativos

> Atualizado em 2026-06-28 (auditoria profunda de status — 28 planos arquivados em `completed/`).

Este diretório deve conter apenas plano vivo, spec ativa ou backlog explícito.
Planos concluídos ficam em [`completed/`](completed/). Material histórico incerto
fica em [`_quarantine/`](_quarantine/).

## Ativos / em andamento (⏳)

| Plano | Estado |
|-------|--------|
| [`GO-LIVE-READINESS-PLAN.md`](GO-LIVE-READINESS-PLAN.md) | Gate de go-live. Lotes A/B/C de engenharia em sua maioria feitos; corte v1 + QA + data bloqueados no Pablo. |
| [`PRODUCTION-EXCELLENCE-PLAN.md`](PRODUCTION-EXCELLENCE-PLAN.md) | Cadeia de planejamento/produção no nível das demais superfícies (auditoria e2e 2026-07-02). WP-PE0..6 não iniciados. |
| [`PRODUCT-V1-SCOPE-BACKLOG.md`](PRODUCT-V1-SCOPE-BACKLOG.md) | Índice-mestre de escopo do v1; gate de produto do go-live. |
| [`BUYMAN-PROCUREMENT-PLAN.md`](BUYMAN-PROCUREMENT-PLAN.md) | Fase 1 (Material/Supplier/custo/shelf-life/admin) concluída e deployada; Fases 2–4 (PurchaseOrder, Recebimento, Reposição) pós-go-live. |
| [`VALIDITY-SHELFLIFE-REVIEW.md`](VALIDITY-SHELFLIFE-REVIEW.md) | Referência viva do hardening de validade; P0 ligado (WP-B5), P1/P2 = WP-B6 pendente. |
| [`OPERATION-DOMAIN-PLAN.md`](OPERATION-DOMAIN-PLAN.md) | Baseline de modelos/Admin implementado; próxima camada (superfície de execução, BI) aberta. |
| [`OPERATION-RUNBOOKS-PLAN.md`](OPERATION-RUNBOOKS-PLAN.md) | Baseline de runbooks/diagnose concluído; snapshot/smoke real de gateway bloqueado por credenciais. |
| [`OMOTENASHI-FIRST-FULLNESS-PLAN.md`](OMOTENASHI-FIRST-FULLNESS-PLAN.md) | Algumas rodadas entregues; maioria dos WP-OF-* não executados. |
| [`POS-FIRST-CLASS-PLAN.md`](POS-FIRST-CLASS-PLAN.md) | WP-0..8 entregues; WP-9+ (offline-first, analytics) roadmap; campos fiscais por produto pendentes. |
| [`POS-FASE-C-REVISION.md`](POS-FASE-C-REVISION.md) | Auditoria do POS; 1 fix aplicado; achados abertos cruzam gate fiscal/go-live. |
| [`POS-REDESIGN-PLAN.md`](POS-REDESIGN-PLAN.md) | Padronização A/B entregue; seção C (captura de crachá no POS) parcial. |
| [`STOREFRONT-GAPS-ACTION-PLAN.md`](STOREFRONT-GAPS-ACTION-PLAN.md) | WP1–10 feitos; resta WP-11 slice 3 (teleporte, bloqueado no Pablo) + Fase C. |
| [`PROJECTION-UI-PLAN.md`](PROJECTION-UI-PLAN.md) | Camada de projections largamente realizada; mantido como spec de contratos/evolução de UI. |
| [`SEO-PLAN.md`](SEO-PLAN.md) | SEO técnico do storefront entregue; mantido como capítulo permanente (conteúdo/keywords futuros). |

## Backlog / futuro (📋)

| Plano | Estado |
|-------|--------|
| [`AVAILABILITY-ADMIN-PLAN.md`](AVAILABILITY-ADMIN-PLAN.md) | UI de calendário de funcionamento no Admin (WP-AV-1/2/3) — não iniciado. |
| [`CATALOG-SYNC-EXTERNO-PLAN.md`](CATALOG-SYNC-EXTERNO-PLAN.md) | Adapters Google/Meta/WhatsApp; bloqueado em credenciais externas. |
| [`MANYCHAT-CONVERSACIONAL-PLAN.md`](MANYCHAT-CONVERSACIONAL-PLAN.md) | Pedido conversacional inbound via ManyChat; proposto, bloqueado no Pablo. |
| [`STOCK-UX-PLAN.md`](STOCK-UX-PLAN.md) | Spec "NUNCA PERDER" de alerta de estoque acionável; corpo HTMX anotado como aposentado (realidade Nuxt). |
| [`STOCK-SUBSTITUTE-1CLICK-PLAN.md`](STOCK-SUBSTITUTE-1CLICK-PLAN.md) | Arco pronto p/ sessão nova: tornar substituto do carrinho acionável em 1 toque (backend já pronto; fecha o princípio do STOCK-UX). |
| [`ADDRESS-UX-PLAN.md`](ADDRESS-UX-PLAN.md) | Spec canônica de endereço iFood-style (ler antes de tocar qualquer tela de endereço). |
| [`CHANGE-PHONE-NUMBER-PLAN.md`](CHANGE-PHONE-NUMBER-PLAN.md) | Mudar número (telefone=identidade); só executar se valer a pena (Pablo). |
| [`SECURITY-ACCOUNT-NOTIFICATIONS.md`](SECURITY-ACCOUNT-NOTIFICATIONS.md) | Notificações de segurança de conta; não implementado. |
| [`WP-GAP-07-pre-prod-migration-playbook.md`](WP-GAP-07-pre-prod-migration-playbook.md) | Gate dormant; dispara só às vésperas do primeiro deploy real. |

## Concluídos Recentemente

Auditoria de 2026-06-28 arquivou 28 planos em [`completed/`](completed/) com evidência (commit/arquivo). Destaques:

| Plano | Evidência |
|-------|-----------|
| `completed/GESTOR-PEDIDOS-PLAN.md` | Gestor de pedidos v1 (Arcs 1–5) mergeado + deployado (`2a7c96da`, `58ba30cc`). |
| `completed/OPERATOR-APPS-PLAN.md` | Apps Nuxt do operador (loja/pos/kds/gestor/fournil) no ar; Fases 0–4. |
| `completed/OPERATOR-AUTH-PLAN.md` | Login cross-subdomínio + trava por operador; engenharia entregue (falta flag/QA do Pablo). |
| `completed/POS-UITHING-REDESIGN-PLAN.md` + `completed/WP7-*` | POS Nuxt — 5 arcos do WP7 fechados (layout, multi-select, fire, print). |
| `completed/ADMIN-CONFIG-OMOTENASHI-PLAN.md` | WP-1..8 em `main` (mergeado, ao contrário do marcador antigo). |
| `completed/THEMING-PLAN.md`, `completed/HOME-HERO-NAVBAR-PLAN.md`, `completed/ARC8-*`, `completed/ARC9-*`, `completed/STOREFRONT-ARC6/7-*`, `completed/STOREFRONT-AUDIT-FIXES-PLAN.md` | Storefront Nuxt: theming, home/hero/navbar, tracking/pagamento, conta, auth, audit fixes. |
| `completed/REMOTE-MULTISURFACE-PLAN.md` | 6/6 WPs concluídos (matriz E2E, contrato, runbook). |
| `completed/DELIVERY-FEE-TOTAL-PLAN.md`, `completed/PDP-DATA-FIELDS-PLAN.md`, `completed/URL-STANDARDIZATION-PLAN.md`, `completed/OMOTENASHI-PLAN.md`, `completed/DJANGO-HEADLESS-PLAN.md` | Frentes de storefront/checkout/headless entregues. |
| `completed/MATERIAL-MASTER-PLAN.md`, `completed/BACKOFFICE-UI-PLAN.md`, `completed/STOREFRONT-NUXT-PARITY-ACTION-PLAN-2026-05-14.md` | Absorvidos/superados (Buyman; Admin-Unfold + apps Nuxt; storefront-uithing). |
