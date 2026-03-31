# Django Shopman — Makefile
#
# Uso rápido:
#   make test        → roda todos os testes
#   make test-utils  → roda testes do utils
#   make install     → instala deps + apps em modo editável

.PHONY: help install test test-utils test-offering test-stocking test-crafting test-ordering test-payments test-customers test-auth test-shopman-app lint clean migrate run dev seed coverage css css-watch fonts

help: ## Mostra este help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ── Setup ─────────────────────────────────────────────────────────────

install: ## Instala deps + apps da suite em modo editável
	pip install --upgrade pip
	pip install Django "djangorestframework>=3.15" "django-filter" \
		phonenumbers pytest pytest-django
	# Instala cada app em modo editável
	pip install -e shopman-core/utils
	pip install -e shopman-core/offering
	pip install -e shopman-core/stocking
	pip install -e shopman-core/crafting
	pip install -e shopman-core/customers
	pip install -e shopman-core/auth
	pip install -e shopman-core/ordering
	pip install -e shopman-core/payments
	pip install -e shopman-app
	@echo "✓ Dependências instaladas"

# ── Testes ────────────────────────────────────────────────────────────

test: test-utils test-offering test-stocking test-crafting test-ordering test-payments test-customers test-auth test-shopman-app ## Roda todos os testes
	@echo "✓ Todos os testes passaram"

test-utils: ## Testes do shopman.utils
	@echo "── Utils ──"
	cd shopman-core/utils && python -m pytest -x -q

test-offering: ## Testes do shopman.offering
	@echo "── Offering ──"
	cd shopman-core/offering && python -m pytest -x -q

test-stocking: ## Testes do shopman.stocking
	@echo "── Stocking ──"
	cd shopman-core/stocking && python -m pytest -x -q

test-crafting: ## Testes do shopman.crafting
	@echo "── Crafting ──"
	cd shopman-core/crafting && python -m pytest -x -q

test-ordering: ## Testes do shopman.ordering
	@echo "── Ordering ──"
	cd shopman-core/ordering && python -m pytest -x -q

test-payments: ## Testes do shopman.payments
	@echo "── Payments ──"
	cd shopman-core/payments && python -m pytest -x -q

test-customers: ## Testes do shopman.customers
	@echo "── Customers ──"
	cd shopman-core/customers && python -m pytest -x -q

test-auth: ## Testes do shopman.auth
	@echo "── Auth ──"
	cd shopman-core/auth && python -m pytest -x -q

test-shopman-app: ## Testes do shopman-app (orquestração)
	@echo "── Shopman App ──"
	cd shopman-app && python -m pytest -x -q

# ── CSS & Frontend ───────────────────────────────────────────────────
# npm é invisível — tudo via make. node_modules instala sob demanda.

shopman-app/node_modules/.package-lock.json: shopman-app/package.json
	@echo "── Instalando dependências frontend ──"
	cd shopman-app && npm install --silent
	@echo "✓ node_modules pronto"

css: shopman-app/node_modules/.package-lock.json ## Build CSS (Tailwind local, minificado)
	cd shopman-app && npx tailwindcss -i ./static/src/input.css -o ./channels/web/static/storefront/css/output.css --minify
	@echo "✓ CSS compilado (~$$(du -h shopman-app/channels/web/static/storefront/css/output.css | cut -f1))"

css-watch: shopman-app/node_modules/.package-lock.json ## CSS watch mode (dev)
	cd shopman-app && npx tailwindcss -i ./static/src/input.css -o ./channels/web/static/storefront/css/output.css --watch

fonts: ## Baixa fontes WOFF2 para self-hosting (Inter + Playfair Display)
	@echo "── Baixando fontes ──"
	@mkdir -p shopman-app/channels/web/static/storefront/fonts
	@cd shopman-app/channels/web/static/storefront/fonts && \
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
	@ls -la shopman-app/channels/web/static/storefront/fonts/*.woff2 2>/dev/null | wc -l | xargs -I{} echo "  {} arquivos woff2"

# ── Server ────────────────────────────────────────────────────────────

migrate: ## Cria/atualiza banco de dados
	cd shopman-app && python manage.py migrate
	@echo "✓ Migrações aplicadas"

run: css ## Sobe o servidor de desenvolvimento (build CSS primeiro)
	cd shopman-app && python manage.py runserver

dev: shopman-app/node_modules/.package-lock.json ## Dev: CSS watch + server em paralelo
	@echo "── Dev mode: CSS watch + Django server ──"
	@echo "  CSS watch em background, servidor em foreground."
	@echo "  Ctrl+C para parar tudo."
	cd shopman-app && npx tailwindcss -i ./static/src/input.css -o ./channels/web/static/storefront/css/output.css --watch &
	cd shopman-app && python manage.py runserver

seed: ## Popula banco com dados demo da Nelson Boulangerie
	cd shopman-app && python manage.py seed
	@echo "✓ Seed completo"

# ── Qualidade ─────────────────────────────────────────────────────────

coverage: ## Roda testes do shopman-app com cobertura
	@echo "── Coverage ──"
	cd shopman-app && python -m pytest --cov --cov-report=term-missing --cov-report=html:htmlcov -q
	@echo "✓ Relatório HTML em shopman-app/htmlcov/index.html"

lint: ## Ruff check
	ruff check shopman-core/ shopman-app/

clean: ## Remove caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Caches limpos"
