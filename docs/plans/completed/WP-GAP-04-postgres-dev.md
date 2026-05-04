# WP-GAP-04 — Postgres como default de desenvolvimento

> Entrega para garantir que invariante "zero over-sell" é exercitada no dev loop. Prompt auto-contido.

**Status**: Ready to start
**Dependencies**: nenhuma
**Severidade original**: 🔴 Alta. Default SQLite pula testes de concorrência que provam o contrato principal do Stockman (`select_for_update` + recheck).

---

## Contexto

### O contrato que o sistema promete

Stockman declara "zero over-sell garantido" via `select_for_update()` + recheck após lock. O contrato é provado em `packages/stockman/shopman/stockman/tests/test_concurrency.py`:

- `TestConcurrentHoldSameSku`: dois threads disputam o mesmo quant; apenas um vence.
- `TestConcurrentFulfillSameHold`: fulfill não duplica.
- `TestConcurrentReleaseAndFulfill`: release e fulfill mutuamente exclusivos.

Esses testes usam `select_for_update()` e advisory locks — **pulam com skip silencioso em SQLite** (ORM + backend não suportam o mesmo modelo de lock).

### O que está errado hoje

[config/settings.py:170-176](../../config/settings.py):

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(BASE_DIR, "db.sqlite3"),
    }
}
```

- **Sem fallback** via env var.
- Comentário "⚠️ PRODUÇÃO: Usar PostgreSQL" é só um aviso.
- `pyproject.toml` não lista `psycopg[binary]` como dependência.
- Sem `docker-compose.yml`.
- Novo dev clona, roda `make test` ✅ verde — sem nunca exercitar o contrato principal.

### O que isso afeta

- **Onboarding**: novo contribuidor assume tudo funciona; primeiro deploy em Postgres pode revelar bugs que dev nunca testou.
- **CI local**: testes ficam falsamente verdes.
- **Confiança**: o "zero over-sell" é afirmado mas não exercitado por default.

---

## Escopo

### In

- `DATABASE_URL` env var resolvida em `config/settings.py`, com fallback para SQLite quando não setada.
- `docker-compose.yml` na raiz com services `postgres:16-alpine` + `redis:7-alpine`.
- `pyproject.toml` adiciona `psycopg[binary]>=3.2` (Django 5.x + driver moderno).
- Makefile targets `up` / `down` / `logs`.
- `.env.example` documentando `DATABASE_URL`, `REDIS_URL`.
- Atualizar guia de dev: editar [docs/guides/](../guides/) setup existente ou adicionar seção específica. **Não criar doc novo se já existir algum equivalente** — checar primeiro.
- Validar: `make up && make migrate && make seed && make test` em máquina limpa completa sem skip de concurrency.

### Out

- Deploy / produção (fora do escopo do projeto geral).
- Remoção do SQLite como fallback — mantém para CI leve, scripts rápidos, read-only scenarios.
- Tuning Postgres (connection pool, shared_buffers) — config default de docker serve.
- pgbouncer / replicas.
- Migração de dados existentes (projeto pre-produção, reset de migrations permitido).

---

## Entregáveis

### Novos arquivos

- `docker-compose.yml` raiz:
  ```yaml
  services:
    postgres:
      image: postgres:16-alpine
      environment:
        POSTGRES_DB: shopman
        POSTGRES_USER: shopman
        POSTGRES_PASSWORD: shopman
      ports: ["5432:5432"]
      volumes: ["postgres_data:/var/lib/postgresql/data"]
      healthcheck:
        test: ["CMD-SHELL", "pg_isready -U shopman"]
        interval: 5s
        retries: 5
    redis:
      image: redis:7-alpine
      ports: ["6379:6379"]
      healthcheck:
        test: ["CMD", "redis-cli", "ping"]
        interval: 5s
  volumes:
    postgres_data:
  ```
- `.env.example` na raiz documentando:
  ```
  DATABASE_URL=postgres://shopman:shopman@localhost:5432/shopman
  REDIS_URL=redis://localhost:6379/0
  # (demais secrets já existentes: GOOGLE_MAPS_API_KEY, STRIPE_*, MANYCHAT_*, SHOPMAN_EFI_*, SHOPMAN_IFOOD_*)
  ```

### Edições

- [config/settings.py](../../config/settings.py) `DATABASES`:
  ```python
  import urllib.parse as _urlparse
  _DB_URL = os.environ.get("DATABASE_URL")
  if _DB_URL:
      _parsed = _urlparse.urlparse(_DB_URL)
      DATABASES = {
          "default": {
              "ENGINE": "django.db.backends.postgresql",
              "NAME": _parsed.path.lstrip("/"),
              "USER": _parsed.username,
              "PASSWORD": _parsed.password,
              "HOST": _parsed.hostname,
              "PORT": _parsed.port or 5432,
              "CONN_MAX_AGE": 60,
          }
      }
  else:
      DATABASES = {
          "default": {
              "ENGINE": "django.db.backends.sqlite3",
              "NAME": os.path.join(BASE_DIR, "db.sqlite3"),
          }
      }
  ```
  (Alternativa limpa: `dj-database-url` como dependência — **não** adicionar para evitar dep nova; manual resolution é suficiente.)

- [pyproject.toml](../../pyproject.toml) dependências:
  ```toml
  "psycopg[binary]>=3.2,<4.0",
  ```

- [Makefile](../../Makefile):
  ```makefile
  up:
  	docker compose up -d
  	@echo "Aguardando Postgres..."
  	@until docker compose exec -T postgres pg_isready -U shopman; do sleep 1; done
  	@echo "Pronto."

  down:
  	docker compose down

  logs:
  	docker compose logs -f

  db-shell:
  	docker compose exec postgres psql -U shopman -d shopman
  ```

- Guia de dev (procurar `docs/guides/` existente; editar; se não houver arquivo equivalente, adicionar seção em `docs/guides/dev-setup.md` — **verificar** antes de criar).

---

## Invariantes a respeitar

- **Zero gambiarras**: configuração limpa, não workarounds. Sem `try/except` espalhados só para "funcionar em SQLite".
- **SQLite ainda suportado** para CI leve / contribuidor que não queira Docker — mas o fluxo documentado default é Postgres.
- **Sem segredo hardcoded**: `.env.example` é template; `.env` em `.gitignore` (verificar se já está).
- **`CONN_MAX_AGE`** configurado (60s) para reutilizar conexões — evita "too many connections" em teste + dev.
- **Healthcheck** no docker-compose para `make up` esperar DB pronto antes de retornar.
- **Redis também subido**: aproveita para destravar cache real com o backend nativo `django.core.cache.backends.redis.RedisCache`; `django-ratelimit` requer backend compartilhado.

---

## Critérios de aceite

1. Em máquina limpa: `git clone && cd django-shopman && cp .env.example .env && make up && make install && make migrate && make seed && make run` → Nelson Boulangerie rodando em `localhost:8000` com Postgres + Redis.
2. `make test` roda **todos** os testes de concorrência (sem skip em `test_concurrency.py`).
3. `make test-stockman` não mostra `SKIPPED` em `TestConcurrentHoldSameSku`.
4. `make down` para tudo limpo; `docker compose ps` vazio.
5. Variável `DATABASE_URL` vazia → fallback SQLite ainda funciona para dev leve.
6. `make test` em CI hipotético com `DATABASE_URL` setada → verde.
7. README ou guia de dev atualizado com 2-command setup (`make up && make install`).
8. Nenhum segredo real commitado.

---

## Referências

- [config/settings.py:170-176](../../config/settings.py).
- [packages/stockman/shopman/stockman/tests/test_concurrency.py](../../packages/stockman/shopman/stockman/tests/test_concurrency.py).
- [pyproject.toml](../../pyproject.toml).
- [Makefile](../../Makefile).
- [docs/reference/system-spec.md](../reference/system-spec.md) §3.2 Bootstrap, §5.5 Onboarding.
- Docs Django: `docs.djangoproject.com/en/5.2/ref/databases/#postgresql-notes`.
- Memória [project_stockman_scope_unified.md](.claude/memory) — contrato check↔reserve é o que estamos protegendo.
