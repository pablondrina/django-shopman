# ROADMAP — Django Shopman

> Atualizado em 2026-05-05. Este documento é o mapa executivo vivo. Estado
> factual fica em [`status.md`](status.md); planos detalhados ficam em
> [`plans/README.md`](plans/README.md).

## Estado Atual

O Shopman está em Django 6 e tem baseline operacional sólido:

- contrato canônico: Python `>=3.12`, Django `>=6.0,<6.1`;
- Redis nativo via `django.core.cache.backends.redis.RedisCache`, sem
  `django-redis`;
- CI `Runtime Gate` no PR #3 validando lint, migrations, `check --deploy`,
  suite completa, build Docker e `make test-runtime` com PostgreSQL + Redis;
- deploy local/staging encapsulado por `make deploy-*`, sem exigir comandos
  Docker manuais do operador;
- POS tab/workbench, KDS Station Runtime e Customer Ready Board implementados;
- observabilidade inicial para webhooks, reconciliação e alertas operacionais.

## Próximos Passos

| Prioridade | Frente | Entrega esperada | Plano |
|------------|--------|------------------|-------|
| P1 | Governança documental | Manter roadmap, status, planos ativos e evidências sempre alinhados ao código. | [`plans/README.md`](plans/README.md) |
| P1 | Gateways sandbox | Validar EFI, Stripe e iFood com eventos duplicados, atrasados e fora de ordem. | ad hoc + docs de predeploy |
| P1 | Reconciliação financeira | Provar rotina diária cruzando pedido, intent, transação, gateway, refund e fechamento. | [`plans/OMOTENASHI-FIRST-FULLNESS-PLAN.md`](plans/OMOTENASHI-FIRST-FULLNESS-PLAN.md) |
| P1 | QA manual Omotenashi E2E | Rodada mobile cliente, tablet KDS e desktop gerente, com estados vazio/erro/timeout/parcial. | [`plans/OMOTENASHI-FIRST-FULLNESS-PLAN.md`](plans/OMOTENASHI-FIRST-FULLNESS-PLAN.md) |
| P2 | Backstage maturity | Higiene de exceções, a11y dinâmica, E2E cross-area e polish final. | [`plans/BACKSTAGE-MATURITY-PLAN.md`](plans/BACKSTAGE-MATURITY-PLAN.md) |
| P2 | Storefront projections | Checkout, pagamento, tracking, conta e histórico consumindo projections consistentes. | [`plans/PROJECTION-UI-PLAN.md`](plans/PROJECTION-UI-PLAN.md) |
| P2 | Disponibilidade e substitutos | PDP/carrinho com feedback acionável, substitutos, holds e timeouts transparentes. | [`plans/AVAILABILITY-PLAN.md`](plans/AVAILABILITY-PLAN.md) |
| P2 | Endereço canônico | Fluxo mobile de endereço com busca, geolocalização opt-in, ajuste no mapa e fallback manual. | [`plans/ADDRESS-UX-PLAN.md`](plans/ADDRESS-UX-PLAN.md) |
| P3 | Pre-prod real | Executar playbook quando houver provedor, domínio, secrets e dados de staging definidos. | [`plans/WP-GAP-07-pre-prod-migration-playbook.md`](plans/WP-GAP-07-pre-prod-migration-playbook.md) |

## Dívida Técnica Viva

| Dívida | Impacto | Próxima ação |
|--------|---------|--------------|
| Gateway sandbox ainda não provado ponta a ponta | Risco de divergência entre mocks e provedores reais. | Criar smoke sandbox para EFI/Stripe/iFood, incluindo replay e eventos fora de ordem. |
| Reconciliação financeira diária incompleta | Payman é forte, mas produção real exige fechamento financeiro auditável. | Implementar/validar relatório diário pedido ↔ gateway ↔ fechamento. |
| QA visual/manual ainda não é gate | Testes automatizados não pegam todo problema de toque, foco, layout e latência percebida. | Rodar e registrar checklist mobile/tablet/desktop. |
| ManyChat webhook ainda pulado | Fluxo completo ManyChat → session → confirmação não está reimplementado. | Retomar junto com canais externos. |
| Shelf life perecível parcialmente ligado | Padaria real precisa de validade por produto/receita sem ambiguidade. | Registrar `OffermanSkuValidator` ou alias canônico de `shelf_life_days`. |
| Playwright E2E opcional | A suite existe, mas só roda quando Playwright está instalado. | Decidir se vira gate antes de piloto público. |
| Migração futura para CSP nativo do Django 6 | `django-csp` funciona, mas Django 6 tem CSP nativo a avaliar. | Avaliar isoladamente, sem misturar com features. |

## Não Dívida Agora

| Item | Estado |
|------|--------|
| Django 6 | Concluído. Plano arquivado em [`plans/completed/DJANGO-6-UPGRADE-PLAN.md`](plans/completed/DJANGO-6-UPGRADE-PLAN.md). |
| `django-redis` | Removido do contrato. Redis usa backend nativo do Django. |
| Docker manual para o operador | Encapsulado por Makefile e GitHub Actions. |
| Runtime PostgreSQL/Redis no CI | Concluído no `Runtime Gate` do PR #3. |
| POS/KDS runtime | Concluído no escopo atual. Plano arquivado em [`plans/completed/POS-KDS-RUNTIME-SURFACE-PLAN.md`](plans/completed/POS-KDS-RUNTIME-SURFACE-PLAN.md). |

## Critério Para Produção Real

Antes de abrir tráfego real, o mínimo honesto é:

1. `Runtime Gate` verde no commit de release.
2. `check --deploy` verde com secrets e hosts reais do ambiente.
3. Gateway sandbox validado para pagamento, refund, webhook duplicado e evento
   fora de ordem.
4. Reconciliação diária provada com dados de staging.
5. QA manual Omotenashi registrado para cliente, operador, cozinha e gerente.
6. Runbook de incidente para gateway fora, webhook atrasado, estoque divergente,
   pedido pago sem confirmação e rollback.
