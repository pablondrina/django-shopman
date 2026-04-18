# WP-GAP-11 — Health check endpoint

> Endpoint `/health/` trivial para load balancer / probe / uptime monitoring. Prompt auto-contido.

**Status**: Ready to start
**Dependencies**: nenhuma
**Severidade**: 🔴 Alta (ops). Projeto não tem endpoint de saúde — qualquer load balancer, k8s liveness/readiness probe, ou uptime monitor falha em integrar.

---

## Contexto

Projeto se pretende solução standalone para comércio — mesmo em fase inicial, operador de produção precisa de health check para:
- Load balancer não rotear para instância unhealthy.
- K8s liveness probe reiniciar container travado.
- K8s readiness probe remover do pool até schema migrations completarem.
- Uptime monitor (UptimeRobot, Healthchecks.io) detectar queda.
- CI/CD deploy validation antes de virar tráfego.

Trivial de implementar; operacionalmente crítico; escopo excluído do projeto só porque "deploy está fora do escopo" — mas health é **boundary de aplicação**, não de deploy.

---

## Escopo

### In

- Endpoint `GET /health/` retornando JSON:
  ```json
  {
    "status": "ok",
    "checks": {
      "database": "ok",
      "cache": "ok" | "skipped",
      "migrations": "ok"
    }
  }
  ```
  - HTTP 200 se tudo OK.
  - HTTP 503 se alguma check crítica falhar (com detalhes do check falhado).
- Checks:
  - **Database**: `connection.ensure_connection()` + `SELECT 1`.
  - **Cache**: `cache.set + get` roundtrip (skip se `LocMemCache` em dev — não é production-grade).
  - **Migrations**: `executor.migration_plan()` vazio (sem migrations pendentes).
- Opcional: endpoint separado `/ready/` com checks mais completos (banco + migrations + app-specific) vs `/health/` (só process alive).
- CSRF exempt (probes não enviam token).
- Sem auth (health é público por design; não expõe dados sensíveis).
- Sem rate limit (probes são high-frequency).
- Log apenas em falha (evitar poluir log com cada check).

### Out

- Dashboard de saúde visual — outro eixo.
- Métricas Prometheus — outro WP (depois).
- Alerting externo (PagerDuty integration) — responsabilidade do monitoring externo.
- Tracing distributed — não cabe aqui.
- Self-remediation (restart automático) — responsabilidade do orchestrator.

---

## Entregáveis

### Novos arquivos

- `shopman/shop/views/health.py` com `HealthCheckView` + `ReadyCheckView`.
- `shopman/shop/tests/test_health.py`:
  - 200 quando tudo OK.
  - 503 quando DB offline (simular via connection close + patch).
  - 503 quando migration pendente (patch executor).
  - Rate limit não dispara em request rápido.

### Edições

- [config/urls.py](../../config/urls.py): adicionar `path("health/", HealthCheckView.as_view())` no topo, antes de `api/`.
- Opcional: `path("ready/", ReadyCheckView.as_view())`.

### Doc

- Seção curta em `docs/guides/operations.md` (criar se não existir; ou adicionar a guia equivalente — **verificar** antes de criar).

---

## Invariantes a respeitar

- **Zero dependência de auth/session**: endpoint não chama middleware de auth customizada.
- **Fast response**: total checks < 500ms p95 — probes são frequentes.
- **Idempotente e sem side effects**: não persiste nada, não emite eventos.
- **Error envelope**: JSON com `{"status": "error", "checks": {<name>: "fail — <reason>"}}`.
- **Não vazar detalhes sensíveis**: stacktrace não vai pro response body.
- **CSP compatível**: endpoint não precisa scripts; JSON puro.

---

## Critérios de aceite

1. `curl http://localhost:8000/health/` em dev retorna 200 + JSON com 3 checks OK.
2. Stop do Postgres (docker compose stop postgres) → `/health/` retorna 503.
3. Aplicar migration fake pendente → `/health/` ainda 200 em `/health/` mas 503 em `/ready/` (se implementado).
4. `make test` passa com suite nova.
5. k8s liveness probe sample funciona:
   ```yaml
   livenessProbe:
     httpGet:
       path: /health/
       port: 8000
     periodSeconds: 10
   ```
6. Tempo de resposta p95 < 500ms.

---

## Referências

- [config/urls.py](../../config/urls.py).
- Django health check patterns: `django-health-check` library (consultar para inspiração mas **não** adicionar como dep — implementação manual é simples e evita surface de risco).
- [docs/reference/system-spec.md §2.13 API](../reference/system-spec.md) — padrão de endpoints.
