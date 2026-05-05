# Planos Ativos

> Atualizado em 2026-05-05.

Este diretório deve conter apenas plano vivo, spec ativa ou backlog explícito.
Planos concluídos ficam em [`completed/`](completed/). Material histórico incerto
fica em [`_quarantine/`](_quarantine/).

## Próxima Ordem Recomendada

| Ordem | Plano | Por quê |
|-------|-------|---------|
| 1 | [`OMOTENASHI-FIRST-FULLNESS-PLAN.md`](OMOTENASHI-FIRST-FULLNESS-PLAN.md) | Torna promessa operacional consistente entre cliente, pagamento, tracking, KDS e backstage. |
| 2 | [`PROJECTION-UI-PLAN.md`](PROJECTION-UI-PLAN.md) | Continua a migração de telas para projections, começando por checkout, pagamento e tracking. |
| 3 | [`AVAILABILITY-PLAN.md`](AVAILABILITY-PLAN.md) | Unifica disponibilidade, substitutos, holds, timeouts e feedback de estoque. |
| 4 | [`ADDRESS-UX-PLAN.md`](ADDRESS-UX-PLAN.md) | Fecha endereço canônico para checkout real, baixa atenção e mobile. |
| 5 | [`OPERATION-RUNBOOKS-PLAN.md`](OPERATION-RUNBOOKS-PLAN.md) | Baseline de runbooks/diagnose/reconciliação/smoke local e QA manual executável concluído; continuar sandbox real. |
| 6 | [`WP-GAP-07-pre-prod-migration-playbook.md`](WP-GAP-07-pre-prod-migration-playbook.md) | Só dispara quando houver ambiente de pré-produção real agendado. |

## Backlog Planejado

| Plano | Status |
|-------|--------|
| [`BACKOFFICE-UI-PLAN.md`](BACKOFFICE-UI-PLAN.md) | Spec histórica útil; execução atual foi parcialmente absorvida por Admin/Unfold e runtime POS/KDS. |
| [`OMOTENASHI-PLAN.md`](OMOTENASHI-PLAN.md) | Fundacional; manter como referência da camada de copy/contexto. |
| [`OPERATION-DOMAIN-PLAN.md`](OPERATION-DOMAIN-PLAN.md) | Backlog de domínio operacional. |
| [`PDP-DATA-FIELDS-PLAN.md`](PDP-DATA-FIELDS-PLAN.md) | Backlog de PDP: ingredientes, nutrição e dados derivados de receita. |
| [`SEO-PLAN.md`](SEO-PLAN.md) | Backlog de storefront público. |
| [`SECURITY-ACCOUNT-NOTIFICATIONS.md`](SECURITY-ACCOUNT-NOTIFICATIONS.md) | Backlog de notificações de segurança de conta. |
| [`STOCK-UX-PLAN.md`](STOCK-UX-PLAN.md) | Spec de UX de estoque; sucessor operativo é [`AVAILABILITY-PLAN.md`](AVAILABILITY-PLAN.md). |

## Concluídos Recentemente

| Plano | Evidência |
|-------|-----------|
| [`completed/BACKSTAGE-MATURITY-PLAN.md`](completed/BACKSTAGE-MATURITY-PLAN.md) | Higiene de exceções, a11y, E2E cross-area e polish final estavam concluídos no histórico do próprio plano; removido da fila ativa. |
| [`completed/DJANGO-6-UPGRADE-PLAN.md`](completed/DJANGO-6-UPGRADE-PLAN.md) | Django 6 é o contrato canônico e o `Runtime Gate` passou no PR #3. |
| [`completed/POS-KDS-RUNTIME-SURFACE-PLAN.md`](completed/POS-KDS-RUNTIME-SURFACE-PLAN.md) | POS tab/workbench, KDS Station Runtime e Customer Ready Board foram implementados. |
