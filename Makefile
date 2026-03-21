# Django Shopman — Makefile
#
# Uso rápido:
#   make test        → roda todos os testes
#   make test-utils  → roda testes do utils
#   make install     → instala deps + apps em modo editável

.PHONY: help install test test-utils lint clean

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
	# pip install -e shopman-core/offering   # WP-1
	# pip install -e shopman-core/stocking   # WP-2
	# pip install -e shopman-core/crafting   # WP-3
	# pip install -e shopman-core/attending  # WP-4
	# pip install -e shopman-core/gating     # WP-4
	# pip install -e shopman-core/ordering   # WP-5
	# pip install -e shopman-app             # WP-6
	@echo "✓ Dependências instaladas"

# ── Testes ────────────────────────────────────────────────────────────

test: test-utils ## Roda todos os testes
	@echo "✓ Todos os testes passaram"

test-utils: ## Testes do shopman.utils
	@echo "── Utils ──"
	cd shopman-core/utils && python -m pytest -x -q

# ── Qualidade ─────────────────────────────────────────────────────────

lint: ## Ruff check
	ruff check shopman-core/ shopman-app/

clean: ## Remove caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Caches limpos"
