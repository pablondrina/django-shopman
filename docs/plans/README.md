# Planos Ativos

> Atualizado em 2026-05-06.

Este diretório deve conter apenas plano vivo, spec ativa ou backlog explícito.
Planos concluídos ficam em [`completed/`](completed/). Material histórico incerto
fica em [`_quarantine/`](_quarantine/).

## Próxima Ordem Recomendada

| Ordem | Plano | Por quê |
|-------|-------|---------|
| 1 | [`OPERATION-RUNBOOKS-PLAN.md`](OPERATION-RUNBOOKS-PLAN.md) | Baseline local concluído; continuar gateway sandbox/snapshot real quando houver credenciais. |
| 2 | [`OMOTENASHI-FIRST-FULLNESS-PLAN.md`](OMOTENASHI-FIRST-FULLNESS-PLAN.md) | Gate browser CI existe; falta evidência física/staging antes de release real. |
| 3 | [`OPERATION-DOMAIN-PLAN.md`](OPERATION-DOMAIN-PLAN.md) | Baseline de modelos/Admin/seed implementado; continuar superfície de execução e BI operacional. |
| 4 | [`ADDRESS-UX-PLAN.md`](ADDRESS-UX-PLAN.md) | Fecha endereço canônico para checkout real, baixa atenção e mobile. |
| 5 | [`PROJECTION-UI-PLAN.md`](PROJECTION-UI-PLAN.md) | Projections core estão implementadas; manter como spec de evolução e contratos de UI. |
| 6 | [`WP-GAP-07-pre-prod-migration-playbook.md`](WP-GAP-07-pre-prod-migration-playbook.md) | Só dispara quando houver ambiente de pré-produção real agendado. |

## Backlog Planejado

| Plano | Status |
|-------|--------|
| [`BACKOFFICE-UI-PLAN.md`](BACKOFFICE-UI-PLAN.md) | Spec histórica útil; execução atual foi parcialmente absorvida por Admin/Unfold e runtime POS/KDS. |
| [`OMOTENASHI-PLAN.md`](OMOTENASHI-PLAN.md) | Fundacional; manter como referência da camada de copy/contexto. |
| [`PDP-DATA-FIELDS-PLAN.md`](PDP-DATA-FIELDS-PLAN.md) | Backlog de PDP: ingredientes, nutrição e dados derivados de receita. |
| [`SEO-PLAN.md`](SEO-PLAN.md) | Backlog de storefront público. |
| [`SECURITY-ACCOUNT-NOTIFICATIONS.md`](SECURITY-ACCOUNT-NOTIFICATIONS.md) | Backlog de notificações de segurança de conta. |
| [`STOCK-UX-PLAN.md`](STOCK-UX-PLAN.md) | Spec de UX de estoque; sucessor operativo concluído em [`completed/AVAILABILITY-PLAN.md`](completed/AVAILABILITY-PLAN.md). |

## Concluídos Recentemente

| Plano | Evidência |
|-------|-----------|
| [`completed/AVAILABILITY-PLAN.md`](completed/AVAILABILITY-PLAN.md) | WP-AV-01..14 concluídos e cobertos; Runtime Gate passou no PR #3 após o fechamento do plano. |
| [`completed/BACKSTAGE-MATURITY-PLAN.md`](completed/BACKSTAGE-MATURITY-PLAN.md) | Higiene de exceções, a11y, E2E cross-area e polish final estavam concluídos no histórico do próprio plano; removido da fila ativa. |
| [`completed/DJANGO-6-UPGRADE-PLAN.md`](completed/DJANGO-6-UPGRADE-PLAN.md) | Django 6 é o contrato canônico e o `Runtime Gate` passou no PR #3. |
| [`completed/POS-KDS-RUNTIME-SURFACE-PLAN.md`](completed/POS-KDS-RUNTIME-SURFACE-PLAN.md) | POS tab/workbench, KDS Station Runtime e Customer Ready Board foram implementados. |
