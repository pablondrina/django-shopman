#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON:-.venv/bin/python}"
QA_PORT="${SHOPMAN_QA_PORT:-${PORT:-8000}}"
BASE_URL="http://127.0.0.1:${QA_PORT}"
SERVER_LOG="${SHOPMAN_QA_SERVER_LOG:-/tmp/shopman-omotenashi-browser-ci-server.log}"

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]]; then
    kill "${SERVER_PID}" >/dev/null 2>&1 || true
    wait "${SERVER_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

"${PYTHON_BIN}" manage.py migrate --noinput
"${PYTHON_BIN}" manage.py seed --flush

"${PYTHON_BIN}" manage.py runserver --noreload "127.0.0.1:${QA_PORT}" >"${SERVER_LOG}" 2>&1 &
SERVER_PID=$!

ready=0
for _ in $(seq 1 60); do
  if curl -fsS "${BASE_URL}/ready/" >/dev/null 2>&1; then
    ready=1
    break
  fi
  if ! kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
    echo "Servidor Django encerrou antes de ficar pronto. Log:" >&2
    tail -120 "${SERVER_LOG}" >&2 || true
    exit 1
  fi
  sleep 1
done

if [[ "${ready}" != "1" ]]; then
  echo "Servidor Django nao ficou pronto em ${BASE_URL}. Log:" >&2
  tail -120 "${SERVER_LOG}" >&2 || true
  exit 1
fi

PYTHON="${PYTHON_BIN}" node scripts/run_omotenashi_browser_qa.mjs --strict --base-url="${BASE_URL}"
