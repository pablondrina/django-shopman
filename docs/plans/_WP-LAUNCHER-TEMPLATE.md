# WP Launcher Template

> Prompt genérico para "soltar" qualquer Work Package em agente novo/sessão nova. Troque `<WP-FILE>` pelo nome do WP específico.

---

## Prompt (copy-paste)

```
Você recebeu um Work Package do Django Shopman. Execute-o.

BOOTSTRAP (leia antes de tocar código):
1. CLAUDE.md (raiz do repo) — convenções P1–P12 inegociáveis.
2. docs/plans/<WP-FILE>.md — seu escopo completo.
3. Seções de docs/reference/system-spec.md citadas no WP.
4. ADRs em docs/decisions/ e memórias referenciadas.

EXECUÇÃO:
- Branch: wp-gap-<NN>-<slug-breve> a partir de origin/main atualizado.
- Se o WP tem Fases, respeite ordem; PR-por-fase se prescrito.
- 100% do "Escopo In". 0% do "Out".
- Cada "Invariante a respeitar" é não-negociável: se colidir com viabilidade, PARE e reporte — nunca viole silenciosamente.
- Cada "Critério de aceite" precisa ser verificado por você antes de alegar done.
- make test verde é pré-requisito para commit.
- Commits atômicos, mensagem no estilo conventional commits (siga git log origin/main como referência).
- SEM push. SEM abrir PR. Entregue branch local pronto para review.

SITUAÇÕES ESPECIAIS:
- WP depende de outro não-merged → pare e reporte qual.
- WP marcado Dormant → pare; trigger não foi atingido.
- Fase 1 de investigação obrigatória → entregue só Fase 1 e aguarde aprovação antes de Fase 2.
- Necessidade fora de escopo aparece → NÃO execute; registre como candidato a follow-up WP.
- O WP é o contrato: se a realidade desviar, proponha ADR ou follow-up. Nunca edite o WP para bater com o que foi feito.

REPORT FINAL:
- Branch + commit SHAs em ordem cronológica.
- Arquivos C/M/D com paths.
- Tabela: Critério de Aceite × como foi verificado.
- Screenshots para WPs de UI (light/dark × mobile 375px/desktop).
- Surpresas, decisões de design, follow-ups candidatos.

Comece respondendo em ≤100 palavras qual é seu entendimento do WP. Então proceda.
```

---

## Índice de WPs ativos

| # | Arquivo | Tema |
|---|---------|------|
| 01 | [WP-GAP-01-ifood-webhook.md](WP-GAP-01-ifood-webhook.md) | iFood webhook real |
| 02 | [WP-GAP-02-card-checkout.md](WP-GAP-02-card-checkout.md) | Card checkout (Stripe Checkout redirect) |
| 03 | [WP-GAP-03-omotenashi-copy.md](WP-GAP-03-omotenashi-copy.md) | Omotenashi como engenharia (tag + enforcement) |
| 04 | [WP-GAP-04-postgres-dev.md](WP-GAP-04-postgres-dev.md) | Postgres dev default |
| 05 | [WP-GAP-05-backoffice-ui.md](WP-GAP-05-backoffice-ui.md) | Backoffice UI unification |
| 06 | [WP-GAP-06-ruleconfig-rce-hardening.md](WP-GAP-06-ruleconfig-rce-hardening.md) | RuleConfig RCE hardening |
| 07 | [WP-GAP-07-pre-prod-migration-playbook.md](WP-GAP-07-pre-prod-migration-playbook.md) | Pre-prod migration playbook (DORMANT) |
| 08 | [WP-GAP-08-quant-cache-reconciliation.md](WP-GAP-08-quant-cache-reconciliation.md) | Quant cache reconciliation |
| 09 | [WP-GAP-09-rename-recipe-ref-phone-helper.md](WP-GAP-09-rename-recipe-ref-phone-helper.md) | Rename Recipe.code + phone helper |
| 10 | [WP-GAP-10-discount-rules-externalization.md](WP-GAP-10-discount-rules-externalization.md) | Discount rules externalization (Fase 1 investigação) |
| 11 | [WP-GAP-11-health-check.md](WP-GAP-11-health-check.md) | Health check endpoint |
| 12 | [WP-GAP-12-api-versioning.md](WP-GAP-12-api-versioning.md) | API versioning (/api/v1/) |
| 13 | [WP-GAP-13-rbac-granular.md](WP-GAP-13-rbac-granular.md) | RBAC granular por persona |
| 14 | [WP-GAP-14-availability-substitutes-ux.md](WP-GAP-14-availability-substitutes-ux.md) | Availability + Substitutes UX (kintsugi) |
| 15 | [WP-GAP-15-catalog-projection-ifood.md](WP-GAP-15-catalog-projection-ifood.md) | CatalogProjection adapter iFood |

## Paralelização segura

- **Paralelo sem conflito**: 01, 02, 04, 11, 12 (domínios ortogonais).
- **Serial recomendado**:
  - 03 → 14 (14 usa tag criada em 03).
  - 06 → 13 (ambos em permissions; 06 estabelece padrão).
- **Paralelo em domínios próprios**: 08, 09, 10.
- **Coordena sua própria paralelização**: 05 (BACKOFFICE-UI-PLAN interno).
- **Preferencialmente após 01**: 15 (iFood direção oposta; complementa).
- **Não executar agora**: 07 (dormant; só quando pre-go-live for agendado).
