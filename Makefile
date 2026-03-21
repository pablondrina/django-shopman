# Django Shopman — Makefile
#
# Uso rápido:
#   make test        → roda todos os testes
#   make test-utils  → roda testes do utils
#   make install     → instala deps + apps em modo editável

.PHONY: help install test test-utils test-offering test-stocking test-crafting test-ordering lint clean

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
	# pip install -e shopman-core/attending  # WP-R2
	# pip install -e shopman-core/gating     # WP-R2
	pip install -e shopman-core/ordering
	# pip install -e shopman-app             # WP-R3+
	@echo "✓ Dependências instaladas"

# ── Testes ────────────────────────────────────────────────────────────

test: test-utils test-offering test-stocking test-crafting test-ordering ## Roda todos os testes
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

# ── Qualidade ─────────────────────────────────────────────────────────

lint: ## Ruff check
	ruff check shopman-core/ shopman-app/

clean: ## Remove caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Caches limpos"
