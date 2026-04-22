# Django Shopman — Makefile
#
# Uso rápido:
#   make test        → roda todos os testes
#   make test-utils  → roda testes do utils
#   make install     → instala deps + apps em modo editável

# Python: usa venv se existir, senão o do PATH
PYTHON := $(shell [ -f .venv/bin/python ] && echo $(CURDIR)/.venv/bin/python || echo python)

# Python: usa venv se existir, senao o do PATH
PYTHON := $(shell [ -f .venv/bin/python ] && echo $(CURDIR)/.venv/bin/python || echo python)

.PHONY: help install test test-refs test-utils test-offerman test-stockman test-craftsman test-orderman test-payman test-guestman test-doorman test-framework lint clean migrate run dev seed coverage css css-watch fonts up down logs db-shell

help: ## Mostra este help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ── Setup ─────────────────────────────────────────────────────────────

install: ## Instala deps + apps da suite em modo editável
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install Django "djangorestframework>=3.15" "django-filter" \
		"django-csp>=4.0,<5.0" \
		"django-ratelimit>=4.1,<5.0" \
		"django-redis>=5.4,<6.0" \
		"psycopg[binary]>=3.2,<4.0" \
		phonenumbers pytest pytest-django
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

# ── CSS & Frontend ───────────────────────────────────────────────────
# npm é invisível — tudo via make. node_modules instala sob demanda.

node_modules/.package-lock.json: package.json
	@echo "── Instalando dependências frontend ──"
	npm install --silent
	@echo "✓ node_modules pronto"

css: node_modules/.package-lock.json ## Build CSS (Tailwind v4 storefront + v4 gestao)
	npm run css:build
	npm run gestao:build
	@echo "✓ CSS compilado (output.css + output-gestao.css)"

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

run: css ## Sobe servidor + directive worker (0.0.0.0:8000)
	-$(PYTHON) manage.py refresh_oven
	$(PYTHON) manage.py process_directives --watch &
	$(PYTHON) manage.py runserver 0.0.0.0:8000

dev: node_modules/.package-lock.json ## Dev: CSS watch + directive worker + server (0.0.0.0:8000)
	@echo "── Dev mode: CSS watch + directive worker + Django server ──"
	@echo "  Ctrl+C para parar tudo."
	npm run css:watch &
	$(PYTHON) manage.py process_directives --watch &
	$(PYTHON) manage.py runserver 0.0.0.0:8000

seed: ## Popula banco com dados demo da instancia ativa (flush + recria)
	$(PYTHON) manage.py seed --flush
	@echo "✓ Seed completo"

# ── Qualidade ─────────────────────────────────────────────────────────

coverage: ## Roda testes do framework com cobertura
	@echo "── Coverage ──"
	$(PYTHON) -m pytest --cov --cov-report=term-missing --cov-report=html:htmlcov -q
	@echo "✓ Relatório HTML em htmlcov/index.html"

lint: ## Ruff check
	ruff check packages/ shopman/shop/ config/

clean: ## Remove caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Caches limpos"
