# GO-LIVE-READINESS-PLAN — Sair do staging e publicar de verdade

> Plano executivo, honesto e priorizado para virar a chave de produção da Nelson.
> Consolida o "Critério Para Produção Real" do [ROADMAP](../ROADMAP.md) com o
> [WP-GAP-07 pre-prod migration playbook](WP-GAP-07-pre-prod-migration-playbook.md).
> Separa **o que um agente executa sozinho** de **o que depende do Pablo**
> (credenciais, domínio, decisões, QA físico, data de go-live).

**Status**: 🟢 Plano aprovado para gravação — execução dos lotes ainda **não iniciada**
(decisão Pablo 2026-06-26: "montar o plano em docs" primeiro).
**Última auditoria de estado**: 2026-06-26 (via `make release-readiness` + leitura de código).

---

## 1. Estado real hoje (não a memória)

`make release-readiness` em 2026-06-26: **`passed_with_external_blockers`** —
`5 passed / 0 failed / 3 blocked_external`.

```
[OK]      django.check          System checks passed.
[OK]      django.migrations     No model changes without migrations.
[OK]      storefront.contact    WhatsApp configurado (wa.me/554333231997).
[OK]      omotenashi.seed       11/11 cenários canônicos com seed.
[OK]      gateways.local        EFI, Stripe e iFood — 5 fixtures com rollback.
[BLOCKED] gateways.sandbox      Falta focus_nfe (NFC-e), iFood, ManyChat. EFI+Stripe = "ready" local.
[BLOCKED] omotenashi.manual     Falta arquivo de evidência física/staging marcado `manual_qa_status: passed`.
[BLOCKED] preprod.environment   Falta URL/secrets de pré-prod declarados (SHOPMAN_PREPROD_URL).
```

**Correções ao que a memória dizia (estavam pessimistas):**

- **2FA já existe em código.** `django_otp` + `otp_totp` instalados; `AdminTwoFactorMiddleware`
  ([`shopman/backstage/middleware_2fa.py`](../../shopman/backstage/middleware_2fa.py)) faz o gate,
  no-op até `SHOPMAN_ADMIN_REQUIRE_2FA` ([`config/settings.py:867`](../../config/settings.py)).
  Falta só **enrollment dos operadores reais + virar a flag** — decisão/operação do Pablo,
  não código novo.
- **Gap cross-subdomínio de auth já está RESOLVIDO no staging.** Opção C no ar e verificada
  ao vivo em `*.boulangerie.com.br` (login único + autorização por operador ativo + tela de
  trava nas 4 surfaces) — ver [OPERATOR-AUTH-PLAN](OPERATOR-AUTH-PLAN.md). Não é mais bloqueio
  de QA autenticado. O que resta é **produção**: domínio próprio, `SESSION_COOKIE_DOMAIN` de
  prod, e substituir os superusers triviais de staging (`admin/admin`) pelo `bootstrap_admin`
  env-driven.
- **IP allowlist NÃO existe** (só um TODO em [`config/settings.py:866`](../../config/settings.py)).
  Decisão correta é **ingress** (DigitalOcean/Cloudflare), não um middleware app-level frágil.
- **Runbooks de incidente já cobrem** gateway/webhook/estoque/pago-sem-confirmação/postgres/
  redis/worker em [`docs/runbooks/`](../runbooks/README.md); rollback citado em
  `docs/guides/deploy.md` e `operations.md` (a auditar — WP-B1).

**Volume de migrations hoje** (justifica o squash final do WP-GAP-07): shop 16, craftsman 16,
backstage 14, orderman 8, payman 8, demais ≤5.

---

## 2. Os 7 critérios de produção → quem executa

| # | Critério (ROADMAP §"Produção Real") | Estado | Dono |
|---|---|---|---|
| 1 | `Runtime Gate` verde no commit de release | Verde no PR #3 | ✅ ~pronto |
| 2 | `release-readiness-strict` verde | Local 5/5; faltam 3 externos | 🟡 misto |
| 3 | `check --deploy` com secrets/hosts reais | Verde local; precisa env de prod | 🔴 Pablo |
| 4 | Gateway sandbox: pagamento, refund, webhook duplicado, evento fora de ordem | **Lógica já provada por fixtures locais**; falta exercer contra sandbox real | 🔴 Pablo (creds) |
| 5 | Reconciliação diária + snapshot de gateway em staging | Reconciliação pronta; snapshot real falta | 🔴 Pablo (creds) |
| 6 | QA manual Omotenashi (cliente/operador/cozinha/gerente) | Gate browser CI verde; falta evidência física | 🔴 Pablo (device/humano) |
| 7 | Runbook de incidente (gateway fora, webhook atrasado, estoque divergente, pago-sem-confirmação) + rollback | ✅ completo (rollback runbook criado 2026-06-26) | ✅ |
| — | WP-GAP-07 migrations-freeze | Greenfield (nada criado) | 🟢 agente (prep) / 🔴 Pablo (data go-live) |

---

## 3. Lotes autônomos (agente executa sem depender do Pablo)

Cada WP abaixo é auto-contido, commitável e validável com `make test` / `make admin` / `make lint`.

### Lote A — WP-GAP-07 prep (maior bloco; pré-requisito honesto de tudo)

> **Política de squash (decisão Pablo 2026-06-26): prep agora, reset/squash no go-live.**
> O playbook diz que squashear antes da hora é engenharia prematura (migrations envelhecem).
> Logo: criar tooling + docs + dry-run agora; o **reset final é evento único, só no go-live**.

- **WP-A1 · `make test-migrations`** — harness que roda `migrate` de schema limpo + `check`
  pós-migrate + valida que `makemigrations --check --dry-run` está limpo. Vira gate local
  (e candidato ao `Runtime Gate`). Entregável: target no `Makefile` + script.
- **WP-A2 · `docs/guides/production-upgrades.md`** — playbook zero-downtime:
  expand-contract para renames; renome de chave em `Session.data`/`Order.data` (backfill +
  lookup condicional em serializers, respeitando `CommitService._do_commit`); checklist
  pré-deploy (backup, testar migration em staging, rollback); feature-flag para rollout gradual.
- **WP-A3 · `docs/decisions/adr-015-backward-compat-policy-post-prod.md`** — formaliza a virada:
  pós go-live, aliases temporários permitidos em janela explícita (1 sprint) com
  `# DEPRECATED(remove in v{x})`; migrations append-only (nunca editar migration aplicada em prod).
  *(O WP-GAP-07 chamava de "adr-011", mas 011 já é `formula-and-cashshift`; o número livre é 015.)*
- **WP-A4 · Atualizar `CLAUDE.md`** — substituir parcialmente "zero residuals/zero backward-compat":
  regra nova vale **a partir do go-live**, apontando para o ADR-015. Hoje (pré-prod) as regras
  atuais seguem valendo.
- **WP-A5 · Decisão de squash documentada** — nota de decisão (squashear vs já-compacto) por
  app. **Não executa o reset** — só deixa pronto para o go-live. Ver [Apêndice A](#apêndice-a--decisão-de-squash-wp-a5).

### Lote B — Critério 7 (runbooks/rollback) ✅ CONCLUÍDO (2026-06-26)

- **WP-B1 ✅ · Runbook de rollback de deploy** criado:
  [`docs/runbooks/rollback-de-deploy.md`](../runbooks/rollback-de-deploy.md) (DO App Platform +
  self-hosted; rollback por tipo de migration, ancorado no ADR-015) + adicionado ao índice
  [`docs/runbooks/README.md`](../runbooks/README.md). Os 5 cenários do critério 7 ficam cobertos:
  gateway/webhook (`webhook-falhando`, `pagamento-divergente`), estoque (`estoque-divergente`),
  pago-sem-confirmação (`pedido-pago-sem-confirmacao`) e rollback (novo).

### Lote C — Hardening de auth do operador ✅ CONCLUÍDO (2026-06-26)

- **WP-C1 ✅ · 2FA provado + documentado** — gate já existe e é testado (`test_admin_2fa.py`,
  8 passed); comando `setup_admin_totp` (QR + otpauth). Procedimento de enrollment + virada da
  flag documentado em
  [`docs/guides/operator-security-hardening.md`](../guides/operator-security-hardening.md).
- **WP-C2 ✅ · IP allowlist desenhada como ingress** — decisão: Cloudflare Access/WAF na frente
  de `admin.`/`pos.`/`kds.`/`gestor.`/`fournil.` (não middleware app-level, por causa do
  `X-Forwarded-For` forjável). Documentado no mesmo guia; fecha o TODO de
  [`config/settings.py`](../../config/settings.py). **Faixas de IP = pendente do Pablo.**

---

## 4. Bloqueios no Pablo (checklist de insumos — agente fecha cada um na hora que chegar)

| Insumo | Destrava | Critério |
|---|---|---|
| Creds **EFI sandbox** + **Stripe test** (exercer de verdade) | `make smoke-gateways-sandbox` real: refund, webhook duplicado, evento fora de ordem | 4, 5 |
| Creds **Focus NFe homologação** (NFC-e) | smoke fiscal real | 4 |
| Creds **iFood sandbox** + **ManyChat** (token + webhook secret) | smoke marketplace/conversacional | 4 |
| **Domínio de produção** + secrets + `SHOPMAN_PREPROD_URL` | `preprod.environment` verde; `check --deploy` real | 2, 3 |
| **`SESSION_COOKIE_DOMAIN` de prod** + `bootstrap_admin` env-driven (matar `admin/admin`) | auth operador segura em prod | 3 |
| **Decisão 2FA**: virar flag + enrollar operadores; faixas de IP do allowlist | hardening de acesso | — |
| **QA físico Omotenashi**: device/humano gera `manual_qa_status: passed` | `omotenashi.manual` verde | 6 |
| **Dados reais da Nelson** | catálogo/estoque/preços de verdade | 6 |
| **Data de go-live** (>30 dias, DB de prod existe) | dispara o **reset final** do WP-GAP-07 | — |

---

## 5. Ordem de execução recomendada

1. **Lote A** (WP-GAP-07 prep) — autônomo, maior, pré-requisito. Termina com `make test` verde
   e o squash pronto-para-disparar.
2. **Lote B + C** — autônomos, menores; fecham critério 7 e o desenho de hardening.
3. **Conforme Pablo traz insumos** (§4) — agente fecha cada bloqueio: roda
   `smoke-gateways-sandbox` real, declara `SHOPMAN_PREPROD_URL`, registra evidência de QA, etc.,
   até `make release-readiness-strict` ficar verde.
4. **No go-live** (data definida pelo Pablo) — executar o **reset/squash final** do WP-GAP-07,
   `git tag go-live-v1`, rollback testado em staging.

---

## 6. Definição de pronto (sair do staging)

`make release-readiness-strict` **verde** (sem `blocked_external`) **E** os 7 critérios do
ROADMAP §"Critério Para Produção Real" satisfeitos com evidência **E** WP-GAP-07 executado
(reset final + tag + rollback testado).

---

## Apêndice A — Decisão de squash (WP-A5)

**Decisão (2026-06-26): squashear no go-live os apps com histórico longo; não
executar agora** (o reset é evento único, no go-live — ADR-015). `squashmigrations`
do Django não tem dry-run real (gera arquivo), então a decisão fica documentada
aqui e a execução no playbook WP-GAP-07.

Contagem de leaf migrations hoje:

| App | Migrations | Squashear no go-live? |
|---|---|---|
| shop | 16 | ✅ sim (→ 1 initial) |
| craftsman | 16 | ✅ sim |
| backstage | 14 | ✅ sim |
| orderman | 8 | ✅ sim |
| payman | 8 | ✅ sim |
| doorman | 5 | ✅ sim |
| offerman | 5 | ✅ sim |
| storefront | 5 | ✅ sim |
| stockman, guestman, refs, consent, identifiers, insights, loyalty, merge, preferences, timeline | ≤2 | ⏭️ já compacto, deixar |

**Procedimento no go-live** (executado no WP-GAP-07, não agora):
1. `make test-migrations` verde + `make test` verde no commit base.
2. Por app marcado ✅: `python manage.py squashmigrations <app> <primeira> <última>`,
   revisar o initial gerado, remover as antigas, rodar `make test-migrations`.
3. Aplicar em staging com snapshot representativo; validar dados.
4. Tag `go-live-v1` após deploy verde.

> Squash ≠ reset destrutivo de dado: Django mantém o estado via
> `replaces`. Ainda assim, só rodar com backup e em staging primeiro.

---

## Referências

- [ROADMAP §"Critério Para Produção Real"](../ROADMAP.md)
- [WP-GAP-07 pre-prod migration playbook](WP-GAP-07-pre-prod-migration-playbook.md)
- [OPERATOR-AUTH-PLAN](OPERATOR-AUTH-PLAN.md) — auth cross-subdomínio (Opção C no ar em staging)
- [OPERATION-RUNBOOKS-PLAN](OPERATION-RUNBOOKS-PLAN.md) — gateways/diagnóstico
- [OMOTENASHI-FIRST-FULLNESS-PLAN](OMOTENASHI-FIRST-FULLNESS-PLAN.md) — QA manual
- [`scripts/check_release_readiness.py`](../../scripts/check_release_readiness.py) — contrato de prontidão
- [`shopman/backstage/services/gateway_smoke.py`](../../shopman/backstage/services/gateway_smoke.py) — smoke local + readiness sandbox
