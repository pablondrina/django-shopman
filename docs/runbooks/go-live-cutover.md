# Go-live — checklist de cutover (staging → produção)

> Procedimento de virada de chave. A **engenharia autônoma está feita** (auth
> cross-subdomínio, surface convergence, Lote A WP-GAP-07 prep, Lote B rollback
> runbook, Buyman Fase 1). O que falta é **decisão/ação do Pablo** (creds, 2FA,
> QA física, escopo, data). Este checklist é a ordem dessas ações.
>
> Âncoras: [GO-LIVE-READINESS-PLAN](../plans/GO-LIVE-READINESS-PLAN.md) ·
> [WP-GAP-07](../plans/WP-GAP-07-pre-prod-migration-playbook.md) ·
> [production-upgrades](../guides/production-upgrades.md) · [ADR-015](../decisions/adr-015-backward-compat-policy-post-prod.md) ·
> rollback: [rollback-de-deploy](rollback-de-deploy.md).

## 0. Estado dos 7 critérios (ROADMAP §"Produção Real")

| # | Critério | Estado | Quem |
|---|---|---|---|
| 1 | Runtime Gate verde no commit de release | ✅ | — |
| 2 | `release-readiness-strict` verde | 🟡 local 5/5; 3 externos faltam | Pablo (creds) |
| 3 | `check --deploy` com secrets/hosts REAIS | 🔴 env de prod | Pablo |
| 4 | Gateway sandbox: pagamento/refund/webhook-dup/fora-de-ordem | 🔴 exercer contra sandbox real | Pablo (creds) |
| 5 | Reconciliação diária + snapshot de gateway | 🔴 snapshot real | Pablo (creds) |
| 6 | QA manual Omotenashi (cliente/operador/cozinha/gerente) | 🔴 evidência física | Pablo (humano) |
| 7 | Runbooks de incidente + rollback | ✅ | — |

## 1. Decisões pré-cutover (Pablo)

- [ ] **Corte de escopo v1** — fechar o que entra (ver [PRODUCT-V1-SCOPE-BACKLOG](../plans/PRODUCT-V1-SCOPE-BACKLOG.md)). Tudo fora do corte = pós-go-live, não bloqueia.
- [ ] **Domínio de produção** definido (loja + zona de operador). Hoje staging usa `nelsonboulangerie.com.br` (cliente) + `boulangerie.com.br` (operador). Decidir os equivalentes de prod (ou promover os atuais).
- [ ] **Data do go-live** marcada — é o gatilho do reset de migrations (WP-GAP-07) e do `git tag go-live-v1`.

## 2. Credenciais e segredos de produção (Pablo)

- [ ] `DJANGO_SECRET_KEY` forte (não o default) · `DJANGO_DEBUG=false` · `DJANGO_ALLOWED_HOSTS` explícito (sem `*`).
- [ ] Banco de produção (Postgres) + Redis/Valkey provisionados; `DATABASE_URL`/cache configurados.
- [ ] **Gateways em modo PRODUÇÃO**: EFI (Pix) cert+creds de prod, Stripe live keys, iFood prod. (Hoje staging = sandbox/test.)
- [ ] `ADMIN_PASSWORD` forte (≥12, não-trivial) p/ o bootstrap do superuser de prod (em prod NÃO usar `admin/admin`).
- [ ] Notificação: ManyChat token de prod, EmailSender de prod.

## 3. Hardening (Lote C — Pablo)

- [ ] **2FA do Admin**: rodar `python manage.py setup_admin_totp` p/ cada superuser (enrolla um TOTP device) e ligar o gate `SHOPMAN_ADMIN_REQUIRE_2FA=true`. (Backend já implementado, gated OFF.)
- [ ] **IP allowlist** no ingress de prod p/ o `admin.` (Django Admin = CRUD/config restrito). A zona de operador (`gestor./kds./pos./fournil.`) fica acessível; só o `admin.` tranca.
- [ ] `check --deploy` verde com o env real (critério 3): `make deploy-check` no ambiente de prod.

## 4. QA antes da virada (Pablo — humano)

- [ ] **Gateway sandbox real** (critérios 4-5): pagamento aprovado, refund, webhook duplicado, evento fora de ordem; depois `make reconcile-financial-day dry_run=1` sem divergência + snapshot do gateway.
- [ ] **QA Omotenashi física** (critério 6): cliente faz pedido na loja; operador no gestor/PDV; cozinha no KDS; gerente no fechamento. Login 1× cobre a zona de operador (já verificado ao vivo).
- [ ] **Reseed/seed de produção**: decidir os dados reais (catálogo, preços, posições, insumos). NÃO usar `seed --flush` de staging em prod (é demo). Popular o catálogo real via Admin/import.

## 5. Reset de migrations (WP-GAP-07 — evento único, só agora)

> Política travada (ADR-015): squash é prematuro antes da hora. Fazer **só no go-live**.

- [ ] `make test-migrations` verde (schema limpo do zero).
- [ ] Squash dos apps com >5 migrations (ver Apêndice A do GO-LIVE-READINESS-PLAN); apps ≤2 já compactos.
- [ ] Após o reset: `makemigrations --check --dry-run` limpo; `make test` verde.

## 6. Cutover (dia D)

- [ ] **Backup** do banco de prod (se já houver dado) ANTES de tudo.
- [ ] `git tag go-live-v1` no commit de release; a partir daqui valem as regras pós-prod do ADR-015 (migrations append-only, aliases só em janela explícita).
- [ ] Deploy de prod (mesmo padrão do staging, app/contexto de PROD): `doctl apps create-deployment <APP_ID_PROD> --wait`. O release job roda `check --deploy` + `migrate`.
   - ⚠️ Lembrar do gotcha: **todo pacote `packages/*` precisa estar no Dockerfile + pyproject** (mordeu com o buyman). Já corrigido; conferir se algum novo entrou.
- [ ] Validar ao vivo: `/ready/` (db/cache/migrations ok), `/health/`, loja, login do operador (cookie na zona certa), um **pedido ponta-a-ponta** com pagamento real de teste.

## 7. Pós-cutover

- [ ] `make diagnose-health` · `make diagnose-worker` (sem backlog) · `make diagnose-payments` (sem divergência).
- [ ] **Reconciliação financeira** do primeiro dia: `make reconcile-financial-day`.
- [ ] Monitorar alertas (CPU/mem/restart já no spec) nas primeiras horas.
- [ ] **Rollback pronto**: se algo quebrar, seguir [rollback-de-deploy](rollback-de-deploy.md) (classificar tipo de migration ANTES de reverter).

## Notas de operação aprendidas (staging)

- **Contexto doctl** de deploy = `shopman-staging-deploy` (único vivo; os outros foram removidos). Prod terá o seu — gerar token e `doctl auth init`.
- **Autodeploy OFF**: push no `main` NÃO deploya; é sempre `create-deployment` manual.
- **Reseed via job**: console/exec dá 403; reseed roda armando `seed --flush` no job `bootstrap-staging` (POST_DEPLOY) e revertendo o spec depois. Em prod, seed é evento único de bootstrap, não rotina.
- **Preservar os secrets `EV[...]`** ao editar o spec (usar `apps spec get` como base, nunca o `.do/app.yaml` cru).
