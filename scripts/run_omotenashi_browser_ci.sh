#!/usr/bin/env bash
# Omotenashi browser-QA gate against the surface that ACTUALLY exists:
# the Nuxt customer store (headless) + the Django operator surfaces.
#
# The headless cutover retired the Django customer PAGES, so the old gate (which
# navigated them) was dropped from CI. This orchestration brings it back, rebuilt
# for the real topology:
#   · Django serves the API + admin/operator pages (relative matrix URLs).
#   · The Nuxt store serves the customer pages (absolute matrix URLs, via
#     SHOPMAN_STOREFRONT_BASE_URL → storefront_links → omotenashi_qa matrix).
#
# It is the single source for the gate, runnable identically locally and in CI:
# seed Django, build + serve the Nuxt store pointing at the Django API, start
# Django pointing customer links at the store, then drive the Omotenashi matrix
# in headless Chrome (--strict) and tear both servers down.
set -euo pipefail

PYTHON_BIN="${PYTHON:-.venv/bin/python}"
NUXT_DIR="${SHOPMAN_QA_NUXT_DIR:-surfaces/storefront-nuxt}"

DJANGO_PORT="${SHOPMAN_QA_PORT:-${PORT:-8001}}"
NUXT_PORT="${SHOPMAN_QA_NUXT_PORT:-3100}"
DJANGO_BASE_URL="http://127.0.0.1:${DJANGO_PORT}"
STOREFRONT_BASE_URL="http://127.0.0.1:${NUXT_PORT}"

DJANGO_LOG="${SHOPMAN_QA_SERVER_LOG:-/tmp/shopman-omotenashi-browser-ci-django.log}"
NUXT_LOG="${SHOPMAN_QA_NUXT_LOG:-/tmp/shopman-omotenashi-browser-ci-nuxt.log}"

# Customer links the matrix builds (PDP, checkout, tracking, payment) must resolve
# to the Nuxt store; operator links stay relative to Django. This single knob makes
# storefront_links.storefront_url() absolute → the matrix points at the store.
export SHOPMAN_STOREFRONT_BASE_URL="${STOREFRONT_BASE_URL}"

DJANGO_PID=""
NUXT_PID=""
cleanup() {
  for pid in "${NUXT_PID}" "${DJANGO_PID}"; do
    if [[ -n "${pid}" ]]; then
      kill "${pid}" >/dev/null 2>&1 || true
      wait "${pid}" >/dev/null 2>&1 || true
    fi
  done
}
trap cleanup EXIT INT TERM

wait_for() {
  local url="$1" pid="$2" label="$3" log="$4"
  for _ in $(seq 1 90); do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      return 0
    fi
    if ! kill -0 "${pid}" >/dev/null 2>&1; then
      echo "${label} encerrou antes de ficar pronto. Log:" >&2
      tail -120 "${log}" >&2 || true
      return 1
    fi
    sleep 1
  done
  echo "${label} nao ficou pronto em ${url}. Log:" >&2
  tail -120 "${log}" >&2 || true
  return 1
}

# ── Django: migrate + canonical seed (deterministic Omotenashi scenarios) ──
"${PYTHON_BIN}" manage.py migrate --noinput
"${PYTHON_BIN}" manage.py seed --flush

# ── Nuxt store: install (if needed) + production build ──
if [[ ! -d "${NUXT_DIR}/node_modules" ]]; then
  echo "── Instalando dependências Nuxt ──"
  (cd "${NUXT_DIR}" && npm ci)
fi
echo "── Build da loja Nuxt ──"
(cd "${NUXT_DIR}" && npm run build)

# ── Start Django (API + operator pages) ──
"${PYTHON_BIN}" manage.py runserver --noreload "127.0.0.1:${DJANGO_PORT}" >"${DJANGO_LOG}" 2>&1 &
DJANGO_PID=$!

# ── Start the built Nuxt store, BFF pointing at the Django API ──
HOST=127.0.0.1 PORT="${NUXT_PORT}" NUXT_DJANGO_BASE_URL="${DJANGO_BASE_URL}" \
  node "${NUXT_DIR}/.output/server/index.mjs" >"${NUXT_LOG}" 2>&1 &
NUXT_PID=$!

wait_for "${DJANGO_BASE_URL}/ready/" "${DJANGO_PID}" "Servidor Django" "${DJANGO_LOG}"
wait_for "${STOREFRONT_BASE_URL}/" "${NUXT_PID}" "Loja Nuxt" "${NUXT_LOG}"

# Navigate the matrix: --base-url is Django (operator relative URLs + /health/),
# while the storefront checks are already absolute Nuxt URLs from the matrix.
PYTHON="${PYTHON_BIN}" node scripts/run_omotenashi_browser_qa.mjs --strict --base-url="${DJANGO_BASE_URL}"
