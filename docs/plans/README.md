# Planos Ativos

> Atualizado em 2026-07-11 (reorganização pós hardening pré-alpha, PRs #53–#69).

Este diretório deve conter apenas plano vivo, spec ativa ou backlog explícito.
Planos concluídos ficam em [`completed/`](completed/). Material histórico incerto
fica em [`_quarantine/`](_quarantine/).

> `copy-wiring-backlog.txt` é **artefato de gate** (lido por
> `shopman/shop/tests/test_omotenashi_copy_keys.py::test_copy_wiring_backlog`):
> lista as chaves de copy ainda não religadas. Não mover nem renomear.

## Gate de go-live (⏳ bloqueados no dono / externo)

| Plano | Estado |
|-------|--------|
| [`GO-LIVE-READINESS-PLAN.md`](GO-LIVE-READINESS-PLAN.md) | Gate de go-live. Lotes A/B feitos; Lote C (2FA/IP) + corte v1 + QA + data bloqueados no Pablo. |
| [`GO-LIVE-CREDENTIALS-MATRIX.md`](GO-LIVE-CREDENTIALS-MATRIX.md) | Matriz de credenciais por fase (WhatsApp Meta, Focus NFe, iFood, Machine). Comtele ✅. |
| [`GO-LIVE-SMS-WHATSAPP-STATUS.md`](GO-LIVE-SMS-WHATSAPP-STATUS.md) | Retomada das credenciais WhatsApp/SMS-OTP: passos exatos para concluir. |
| [`ACCESS-LINK-UNIFICATION-PLAN.md`](ACCESS-LINK-UNIFICATION-PLAN.md) | F1/F2/F4 mergeadas (PR #45); resta F3 (fluxo ManyChat, lado do Pablo) + URLs de staging. |
| [`PRODUCT-V1-SCOPE-BACKLOG.md`](PRODUCT-V1-SCOPE-BACKLOG.md) | Índice-mestre de escopo do v1; gate de produto do go-live. |
| [`WP-GAP-07-pre-prod-migration-playbook.md`](WP-GAP-07-pre-prod-migration-playbook.md) | Dormant; dispara às vésperas do primeiro deploy real. |

## Ativos / em andamento (⏳)

| Plano | Estado |
|-------|--------|
| [`FISCALMAN-PLAN.md`](FISCALMAN-PLAN.md) | S0–S4 concluídos e verdes; resta S5 (NF-e mod. 55/resale) + contador valida NCM/CSC/IBPT. |
| [`BUYMAN-PROCUREMENT-PLAN.md`](BUYMAN-PROCUREMENT-PLAN.md) | Fase 1 concluída e deployada (INVENTORY_BACKEND ligado, WP-B5b); Fases 2–4 pós-go-live. |
| [`IFOOD-DIRECT-INTEGRATION-PLAN.md`](IFOOD-DIRECT-INTEGRATION-PLAN.md) | Integração direta (polling) em staging; homologação de produção pendente. |
| [`DELIVERY-EXTERNAL-LOGISTICS-PLAN.md`](DELIVERY-EXTERNAL-LOGISTICS-PLAN.md) | Machine (courier) construída (PR #43); faltam credenciais centrais + homologação de webhook. |
| [`DELIVERY-GEOCODING-AND-FEEDBACK-PLAN.md`](DELIVERY-GEOCODING-AND-FEEDBACK-PLAN.md) | Cascata de geocoding entregue; pendente robustez multi-provedor + feedback omotenashi. |
| [`VALIDITY-SHELFLIFE-REVIEW.md`](VALIDITY-SHELFLIFE-REVIEW.md) | Referência viva; P0 ligado (WP-B5, validator composto); P1/P2 = WP-B6 pendente. |
| [`OPERATION-DOMAIN-PLAN.md`](OPERATION-DOMAIN-PLAN.md) | Baseline de modelos/Admin implementado; próxima camada (superfície de execução, BI) aberta. |
| [`OPERATION-RUNBOOKS-PLAN.md`](OPERATION-RUNBOOKS-PLAN.md) | Baseline de runbooks/diagnose concluído; snapshot/smoke real de gateway bloqueado por credenciais. |
| [`OMOTENASHI-FIRST-FULLNESS-PLAN.md`](OMOTENASHI-FIRST-FULLNESS-PLAN.md) | Algumas rodadas entregues; maioria dos WP-OF-* não executados. |
| [`EXCELLENCE-AUDIT-2026-07.md`](EXCELLENCE-AUDIT-2026-07.md) | Auditoria-mãe (16 lentes); Onda 0 executada; Ondas 1–3 abertas. |
| [`POS-FIRST-CLASS-PLAN.md`](POS-FIRST-CLASS-PLAN.md) | WP-0..8 entregues; WP-9+ (offline-first, analytics) roadmap; campos fiscais por produto pendentes. |
| [`POS-FASE-C-REVISION.md`](POS-FASE-C-REVISION.md) | Auditoria do POS; achados abertos cruzam gate fiscal/go-live (DANFE NFC-e no PDV). |
| [`POS-REDESIGN-PLAN.md`](POS-REDESIGN-PLAN.md) | Padronização A/B entregue; seção C (captura de crachá no POS) parcial. |
| [`GESTOR-CATALOG-STOCK-AWARE.md`](GESTOR-CATALOG-STOCK-AWARE.md) | Matriz produto×canal com estado de estoque (Esgotado); aprovado, execução aberta. |
| [`GESTOR-UX-STANDARDIZATION.md`](GESTOR-UX-STANDARDIZATION.md) | Padrão único de UI/UX para os boards do Gestor (Pedidos + Cardápio); handoff aberto. |
| [`STOREFRONT-GAPS-ACTION-PLAN.md`](STOREFRONT-GAPS-ACTION-PLAN.md) | WP1–10 feitos; resta WP-11 slice 3 (auto-fill do teleporte) + Fase C. |
| [`PROJECTION-UI-PLAN.md`](PROJECTION-UI-PLAN.md) | Camada de projections largamente realizada; mantido como spec de contratos/evolução de UI. |
| [`SEO-PLAN.md`](SEO-PLAN.md) | SEO técnico entregue; capítulo permanente (conteúdo/keywords futuros). |

## Backlog / futuro (📋)

| Plano | Estado |
|-------|--------|
| [`CROSS-CHANNEL-CATALOG-HUB-PLAN.md`](CROSS-CHANNEL-CATALOG-HUB-PLAN.md) | Visão: Gestor como hub cross-channel (superfície fed-by-coleção, menuboard SSE). |
| [`CATALOG-FEEDS-GOOGLE-META.md`](CATALOG-FEEDS-GOOGLE-META.md) | Superfícies FEED do hub cross-channel (RSS/XML para Google/Meta). |
| [`CATALOG-SYNC-EXTERNO-PLAN.md`](CATALOG-SYNC-EXTERNO-PLAN.md) | Adapters Google/Meta/WhatsApp Catalog; bloqueado em credenciais externas. |
| [`MANYCHAT-CONVERSACIONAL-PLAN.md`](MANYCHAT-CONVERSACIONAL-PLAN.md) | Pedido conversacional inbound via ManyChat; proposto, bloqueado no Pablo. |
| [`WHATSAPP-TRANSACTIONAL-CHANNEL-PLAN.md`](WHATSAPP-TRANSACTIONAL-CHANNEL-PLAN.md) | Spike do canal WhatsApp transacional (notificação + OTP) Meta-direto. |
| [`PRODUCTION-FORECAST-BOARD-PLAN.md`](PRODUCTION-FORECAST-BOARD-PLAN.md) | Painel estilo aeroporto para vendas/encomendas (o que dá para prometer por data). |
| [`AVAILABILITY-ADMIN-PLAN.md`](AVAILABILITY-ADMIN-PLAN.md) | UI de calendário de funcionamento no Admin (WP-AV-1/2/3) — não iniciado. |
| [`STOCK-UX-PLAN.md`](STOCK-UX-PLAN.md) | Spec "NUNCA PERDER" de alerta de estoque acionável; 1-toque entregue ([`completed/STOCK-SUBSTITUTE-1CLICK-PLAN.md`](completed/STOCK-SUBSTITUTE-1CLICK-PLAN.md)). |
| [`ADDRESS-UX-PLAN.md`](ADDRESS-UX-PLAN.md) | Spec canônica de endereço iFood-style (ler antes de tocar qualquer tela de endereço). |
| [`CHANGE-PHONE-NUMBER-PLAN.md`](CHANGE-PHONE-NUMBER-PLAN.md) | Mudar número (telefone=identidade); só executar se valer a pena (Pablo). |
| [`SECURITY-ACCOUNT-NOTIFICATIONS.md`](SECURITY-ACCOUNT-NOTIFICATIONS.md) | Notificações de segurança de conta; não implementado. |
| [`STATUS-BAR-CTA-CONFIG-PLAN.md`](STATUS-BAR-CTA-CONFIG-PLAN.md) | CTA da status-bar (Ligar/Mensagem) configurável; base entregue no PR #21, resto aberto. |

## Concluídos Recentemente (2026-07-11)

Arquivados em [`completed/`](completed/) nesta reorganização:

| Plano | Evidência |
|-------|-----------|
| `completed/BACKSTAGE-EXCELLENCE-HARDENING-PLAN.md` | 5 superfícies de operador + OperatorRail + Central; deployado em staging (PR #36). |
| `completed/STOREFRONT-EXCELLENCE-HARDENING-PLAN.md` | WP-S0..S6 concluídos; lint 0, suíte verde. |
| `completed/PRODUCTION-EXCELLENCE-PLAN.md` | WP-PE0..6 entregues + staging; **resta só QA físico** (som/térmica), vivo no ROADMAP. |
| `completed/GO-LIVE-ALPHA-AUDIT.md` | Lotes 1–6 corrigidos com teste por bug (status ✅ no próprio doc, 2026-07-02). |
| `completed/OPERATOR-PIN-SELFSERVICE-PLAN.md` | PIN autoatendimento + reset por gerente (PR #32). |
| `completed/COPY-CONSOLIDATION-PLAN.md` + `completed/COPY-BACKLOG-UNBUILT.md` | Burndown omotenashi fechado, backlog de copy zerado (PRs #49–#53). |
| `completed/STOCK-SUBSTITUTE-1CLICK-PLAN.md` | Substituto acionável em 1 toque entregue; duplicata em `plans/` removida. |

Histórico anterior (auditoria 2026-06-28, 28 planos) e demais planos concluídos: ver [`completed/`](completed/).
