# Operações

Guia curto para operadores / ops de produção. Cresce conforme amadurecemos
deploy, observabilidade e incident response.

## Health checks

Dois endpoints, sem auth, sem CSRF, sem rate limit, JSON puro.

### `GET /health/` — liveness

Responde se o processo Django está vivo e consegue falar com o banco e o cache.
Usado por **load balancers** e **k8s livenessProbe** para decidir se o container
precisa ser reiniciado.

- **200 ok**: banco acessível, cache operacional (ou `skipped` se `LocMemCache`).
- **503 error**: banco inacessível **ou** cache quebrado.
- Migrations pendentes **não** causam 503 aqui — liveness não deve reiniciar
  container por schema drift (isso é readiness).

Exemplo:

```json
{
  "status": "ok",
  "checks": {
    "database": "ok",
    "cache": "skipped",
    "migrations": "ok"
  }
}
```

### `GET /ready/` — readiness

Tudo do `/health/` + verifica que **não há migrations pendentes**. Usado por
**k8s readinessProbe** e **deploy validation** para segurar tráfego até que o
schema esteja alinhado com o código em produção.

- **200 ok**: pronto para receber tráfego.
- **503 error**: qualquer check falhou (inclui migrations).

### Snippet k8s

```yaml
livenessProbe:
  httpGet:
    path: /health/
    port: 8000
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /ready/
    port: 8000
  periodSeconds: 5
  failureThreshold: 2
```

### Snippet uptime monitor

```bash
curl -fsS https://seu-host/health/ || alerta
```

### Cache em dev e produção

`LocMemCache` não é production-grade (per-process, some a cada restart), então
o check de cache retorna `skipped` em fallback local — não é um sinal negativo
nesse modo. Em staging/producao, `REDIS_URL` é obrigatório: o check faz
roundtrip `set`/`get` e falha se o Redis estiver inacessível.

Redis é usado para cache compartilhado, `django-ratelimit`, caches operacionais
curtos e fanout SSE multi-worker. Ver o contrato em
[`docs/reference/runtime-dependencies.md`](../reference/runtime-dependencies.md).

### Observabilidade

Sucessos **não** geram log (evita poluição em ambientes com probes de alta
frequência). Falhas emitem `WARNING` em `shopman.shop.views.health` com a lista
de checks críticos que falharam.

### Segurança

- Endpoints não expõem stacktrace, config, nem dados de negócio — apenas o
  nome da classe da exceção (`OperationalError`, `ConnectionRefusedError`).
- Não retornam sessão, token, ou cookie.
- Públicos por design (probes não autenticam).
