# Django Shopman — Makefile
#
# Uso rápido:
#   make test        → roda todos os testes
#   make test-utils  → roda testes do utils
#   make admin       → valida tudo de Admin/Unfold
#   make install     → instala deps + apps em modo editável

# Python: usa venv se existir, senão o do PATH
PYTHON := $(shell [ -f .venv/bin/python ] && echo $(CURDIR)/.venv/bin/python || echo python)
ADMIN_URL := $(strip $(or $(url),$(URL)))
ADMIN_SCOPE_ARGS := $(if $(ADMIN_URL),--url $(ADMIN_URL),)

.PHONY: help install test test-refs test-utils test-offerman test-stockman test-craftsman test-orderman test-payman test-guestman test-doorman test-framework test-runtime-preflight test-runtime load-test test-coverage lint omotenashi-lint omotenashi-audit admin admin-update admin-ui admin-ui-ci admin-ui-maturity admin-ui-strict admin-ui-surfaces admin-ui-test admin-ui-update unfold unfold-ci unfold-maturity unfold-strict unfold-surfaces unfold-update lint-unfold lint-unfold-maturity clean migrate run dev seed coverage css css-watch fonts up down logs db-shell

help: ## Mostra este help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Setup ─────────────────────────────────────────────────────────────

install: ## Instala deps + apps da suite em modo editável
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install "Django>=5.2,<6.0" "djangorestframework>=3.15" "django-filter" \
		"drf-spectacular>=0.28,<1.0" \
		"django-csp>=4.0,<5.0" \
		"django-ratelimit>=4.1,<5.0" \
		"django-eventstream>=5.3,<6.0" \
		"django-unfold>=0.91,<0.92" \
		"daphne>=4.1,<5.0" \
		"redis>=5.0,<8.0" \
		"psycopg[binary]>=3.2,<4.0" \
		"python-dotenv>=1.0,<2.0" \
		"qrcode[pil]>=7.4,<8.0" \
		"locust>=2.24,<3.0" \
		"ruff>=0.15,<1.0" \
		phonenumbers pytest pytest-django pytest-cov
	# Instala cada app em modo editável
	$(PYTHON) -m pip install -e packages/refs
	$(PYTHON) -m pip install -e packages/utils
	$(PYTHON) -m pip install -e packages/offerman
	$(PYTHON) -m pip install -e packages/stockman
	$(PYTHON) -m pip install -e packages/craftsman
	$(PYTHON) -m pip install -e packages/guestman
	$(PYTHON) -m pip install -e packages/doorman
	$(PYTHON) -m pip install -e packages/orderman
	$(PYTHON) -m pip install -e packages/payman
	$(PYTHON) -m pip install -e .
	@echo "✓ Dependências instaladas"

# ── Testes ────────────────────────────────────────────────────────────

test: test-refs test-utils test-offerman test-stockman test-craftsman test-orderman test-payman test-guestman test-doorman test-framework ## Roda todos os testes
	@echo "✓ Todos os testes passaram"

test-refs: ## Testes do shopman.refs
	@echo "── Refs ──"
	cd packages/refs && $(PYTHON) -m pytest -x -q

test-utils: ## Testes do shopman.utils
	@echo "── Utils ──"
	cd packages/utils && $(PYTHON) -m pytest -x -q

test-offerman: ## Testes do shopman.offering
	@echo "── Offerman ──"
	cd packages/offerman && $(PYTHON) -m pytest -x -q

test-stockman: ## Testes do shopman.stocking
	@echo "── Stockman ──"
	cd packages/stockman && $(PYTHON) -m pytest -x -q

test-craftsman: ## Testes do shopman.crafting
	@echo "── Craftsman ──"
	cd packages/craftsman && $(PYTHON) -m pytest -x -q

test-orderman: ## Testes do shopman.orderman
	@echo "── Orderman ──"
	cd packages/orderman && $(PYTHON) -m pytest -x -q

test-payman: ## Testes do shopman.payments
	@echo "── Payman ──"
	cd packages/payman && $(PYTHON) -m pytest -x -q

test-guestman: ## Testes do shopman.customers
	@echo "── Guestman ──"
	cd packages/guestman && $(PYTHON) -m pytest -x -q

test-doorman: ## Testes do shopman.auth
	@echo "── Doorman ──"
	cd packages/doorman && $(PYTHON) -m pytest -x -q

test-framework: ## Testes do framework (orquestração)
	@echo "── Framework ──"
	$(PYTHON) -m pytest shopman/shop/tests shopman/storefront/tests shopman/backstage/tests -x -q

test-runtime-preflight: ## Falha se PostgreSQL/Redis reais não estiverem configurados
	@echo "── Runtime preflight: PostgreSQL + Redis ──"
	$(PYTHON) scripts/check_runtime_gate.py

test-runtime: test-runtime-preflight ## Stress de segurança/confiabilidade em PostgreSQL + Redis, sem skips
	@echo "── Runtime security/reliability tests ──"
	$(PYTHON) scripts/run_runtime_tests.py
	@echo "✓ Runtime security/reliability gate passou"

load-test: ## Locust headless contra servidor rodando (HOST=http://localhost:8000 USERS=100 RATE=10 TIME=60s)
	$(PYTHON) -m locust -f shopman/shop/tests/load/locustfile.py --host=$(or $(HOST),http://localhost:8000) --headless -u $(or $(USERS),100) -r $(or $(RATE),10) --run-time $(or $(TIME),60s)

test-coverage: ## Cobertura do Backstage com gate de 75%
	@echo "── Backstage coverage ──"
	$(PYTHON) -m coverage run --source=shopman/backstage -m pytest shopman/backstage/tests -q
	$(PYTHON) -m coverage report --include="shopman/backstage/*" --fail-under=75

# ── CSS & Frontend ───────────────────────────────────────────────────
# npm é invisível — tudo via make. node_modules instala sob demanda.

node_modules/.package-lock.json: package.json
	@echo "── Instalando dependências frontend ──"
	npm install --silent
	@echo "✓ node_modules pronto"

css: node_modules/.package-lock.json ## Build CSS (Tailwind v4 storefront + v4 gestor)
	npm run css:build
	npm run gestor:build
	@echo "✓ CSS compilado (output.css + output-gestor.css)"

css-watch: node_modules/.package-lock.json ## CSS watch mode v4 (storefront)
	npm run css:watch

fonts: ## Baixa fontes WOFF2 para self-hosting (Inter + Playfair Display)
	@echo "── Baixando fontes ──"
	@mkdir -p shopman/shop/static/storefront/fonts
	@cd shopman/shop/static/storefront/fonts && \
		curl -sLO "https://fonts.gstatic.com/s/inter/v18/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuLyfMZhrib2Bg-4.woff2" && mv UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuLyfMZhrib2Bg-4.woff2 inter-latin-400.woff2 && \
		curl -sLO "https://fonts.gstatic.com/s/inter/v18/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuI6fMZhrib2Bg-4.woff2" && mv UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuI6fMZhrib2Bg-4.woff2 inter-latin-500.woff2 && \
		curl -sLO "https://fonts.gstatic.com/s/inter/v18/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuGKYMZhrib2Bg-4.woff2" && mv UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuGKYMZhrib2Bg-4.woff2 inter-latin-600.woff2 && \
		curl -sLO "https://fonts.gstatic.com/s/inter/v18/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuFuYMZhrib2Bg-4.woff2" && mv UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuFuYMZhrib2Bg-4.woff2 inter-latin-700.woff2 && \
		curl -sLO "https://fonts.gstatic.com/s/playfairdisplay/v37/nuFvD-vYSZviVYUb_rj3ij__anPXJzDwcbmjWBN2PKdFvUDQZNLo_U2r.woff2" && mv nuFvD-vYSZviVYUb_rj3ij__anPXJzDwcbmjWBN2PKdFvUDQZNLo_U2r.woff2 playfair-display-latin-400.woff2 && \
		curl -sLO "https://fonts.gstatic.com/s/playfairdisplay/v37/nuFvD-vYSZviVYUb_rj3ij__anPXJzDwcbmjWBN2PKdFvXzWZNLo_U2r.woff2" && mv nuFvD-vYSZviVYUb_rj3ij__anPXJzDwcbmjWBN2PKdFvXzWZNLo_U2r.woff2 playfair-display-latin-600.woff2 && \
		curl -sLO "https://fonts.gstatic.com/s/playfairdisplay/v37/nuFvD-vYSZviVYUb_rj3ij__anPXJzDwcbmjWBN2PKdFvUXWZNLo_U2r.woff2" && mv nuFvD-vYSZviVYUb_rj3ij__anPXJzDwcbmjWBN2PKdFvUXWZNLo_U2r.woff2 playfair-display-latin-700.woff2 && \
		curl -sLO "https://fonts.gstatic.com/s/playfairdisplay/v37/nuFRD-vYSZviVYUb_rj3ij__anPXDTnCjmHKM4nYO7KN_qiTbtbK-F2rA0s.woff2" && mv nuFRD-vYSZviVYUb_rj3ij__anPXDTnCjmHKM4nYO7KN_qiTbtbK-F2rA0s.woff2 playfair-display-latin-400-italic.woff2 && \
		curl -sLO "https://fonts.gstatic.com/s/playfairdisplay/v37/nuFRD-vYSZviVYUb_rj3ij__anPXDTnCjmHKM4nYO7KN_giUbtbK-F2rA0s.woff2" && mv nuFRD-vYSZviVYUb_rj3ij__anPXDTnCjmHKM4nYO7KN_giUbtbK-F2rA0s.woff2 playfair-display-latin-600-italic.woff2
	@echo "✓ Fontes baixadas"
	@ls -la shopman/shop/static/storefront/fonts/*.woff2 2>/dev/null | wc -l | xargs -I{} echo "  {} arquivos woff2"

# ── Infra (Docker: Postgres + Redis) ──────────────────────────────────

up: ## Sobe Postgres + Redis via docker compose (aguarda healthcheck)
	docker compose up -d
	@echo "Aguardando Postgres..."
	@until docker compose exec -T postgres pg_isready -U shopman >/dev/null 2>&1; do sleep 1; done
	@echo "✓ Postgres + Redis prontos"

down: ## Para Postgres + Redis
	docker compose down

logs: ## Stream dos logs dos services
	docker compose logs -f

db-shell: ## psql no Postgres do docker
	docker compose exec postgres psql -U shopman -d shopman

# ── Server ────────────────────────────────────────────────────────────

migrate: ## Cria/atualiza banco de dados
	$(PYTHON) manage.py migrate
	@echo "✓ Migrações aplicadas"

run: css ## Sobe servidor + tunnel + directive worker (0.0.0.0:8000)
	-$(PYTHON) manage.py refresh_oven
	lsof -ti:8000 | xargs kill -9 2>/dev/null || true
	killall cloudflared 2>/dev/null || true
	killall ngrok 2>/dev/null || true
	$(PYTHON) manage.py process_directives --watch &
	cloudflared tunnel --url http://localhost:8000 2>&1 | tee .tunnel.log &
	@sleep 3
	@grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' .tunnel.log | head -1 || echo "⚠ Tunnel URL not yet available — check .tunnel.log"
	$(PYTHON) manage.py runserver 0.0.0.0:8000

dev: node_modules/.package-lock.json ## Dev: CSS watch + ngrok + directive worker + server (0.0.0.0:8000)
	@echo "── Dev mode: CSS watch + ngrok + directive worker + Django server ──"
	@echo "  Ctrl+C para parar tudo."
	npm run css:watch &
	$(PYTHON) manage.py process_directives --watch &
	ngrok http 8000 --domain=lathlike-thelma-undiaphanously.ngrok-free.dev > /dev/null &
	$(PYTHON) manage.py runserver 0.0.0.0:8000

seed: ## Popula banco com dados demo da instancia ativa (flush + recria)
	$(PYTHON) manage.py seed --flush
	@echo "✓ Seed completo"

# ── Qualidade ─────────────────────────────────────────────────────────

coverage: ## Roda testes do framework com cobertura
	@echo "── Coverage ──"
	$(PYTHON) -m pytest --cov --cov-report=term-missing --cov-report=html:htmlcov -q
	@echo "✓ Relatório HTML em htmlcov/index.html"

lint: admin ## Ruff + Admin/Unfold
	ruff check packages/ shopman/shop/ config/

omotenashi-lint: ## Gate CI: copy crítica do storefront precisa vir de Omotenashi
	$(PYTHON) scripts/lint_omotenashi_copy.py --critical --error

omotenashi-audit: ## Auditoria ampla: lista copy visível ainda não migrada
	$(PYTHON) scripts/lint_omotenashi_copy.py

admin: ## Admin: valida tudo de Admin/Unfold
	$(PYTHON) scripts/check_unfold_canonical.py --maturity $(ADMIN_SCOPE_ARGS)
ifneq ($(ADMIN_URL),)
	@echo "✓ Admin canônico ($(ADMIN_URL))"
else
	$(PYTHON) -m pytest shopman/backstage/tests/test_unfold_canonical_templates.py shopman/backstage/tests/test_admin_operational_integration.py -q
	@echo "✓ Admin canônico"
endif

admin-update:
	$(PYTHON) scripts/snapshot_unfold_reference.py
	$(PYTHON) scripts/check_unfold_canonical.py

admin-ui: admin

admin-ui-surfaces:
	$(PYTHON) scripts/check_unfold_canonical.py --surfaces

admin-ui-maturity:
	$(PYTHON) scripts/check_unfold_canonical.py --maturity

admin-ui-strict: admin-ui-maturity

admin-ui-test: admin

admin-ui-ci: admin

admin-ui-update: admin-update

unfold: admin

unfold-ci: admin

unfold-maturity: admin-ui-maturity

unfold-strict: admin-ui-strict

unfold-surfaces: admin-ui-surfaces

unfold-update: admin-update

lint-unfold: admin

lint-unfold-maturity: admin-ui-maturity

clean: ## Remove caches
	find . \( -path ./.git -o -path ./.venv -o -path ./node_modules \) -prune -o -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . \( -path ./.git -o -path ./.venv -o -path ./node_modules \) -prune -o -type f -name "*.pyc" -delete 2>/dev/null || true
	find . \( -path ./.git -o -path ./.venv -o -path ./node_modules \) -prune -o -type d \( -name ".pytest_cache" -o -name ".ruff_cache" -o -name "*.egg-info" \) -exec rm -rf {} + 2>/dev/null || true
	find . \( -path ./.git -o -path ./.venv -o -path ./node_modules \) -prune -o -type f -name ".DS_Store" -delete 2>/dev/null || true
	@echo "✓ Caches limpos"
