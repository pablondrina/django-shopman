#!/usr/bin/env python
"""Fail-closed PostgreSQL + Redis preflight for release/runtime tests."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _failures() -> list[str]:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()

    from django.conf import settings
    from django.core.cache import cache
    from django.db import connection

    failures: list[str] = []

    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        failures.append("DATABASE_URL is not set; runtime gate requires PostgreSQL.")

    engine = settings.DATABASES.get("default", {}).get("ENGINE", "")
    if "postgresql" not in engine:
        failures.append(f"default database backend is {engine!r}; expected django.db.backends.postgresql.")

    try:
        connection.ensure_connection()
        if connection.vendor != "postgresql":
            failures.append(f"default database vendor is {connection.vendor!r}; expected 'postgresql'.")
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:  # noqa: BLE001 - preflight must report every environment failure
        failures.append(f"PostgreSQL roundtrip failed: {exc.__class__.__name__}: {exc}")

    redis_url = os.environ.get("REDIS_URL", "").strip()
    if not redis_url:
        failures.append("REDIS_URL is not set; runtime gate requires shared Redis.")

    cache_backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    expected_cache = "django.core.cache.backends.redis.RedisCache"
    if cache_backend != expected_cache:
        failures.append(f"default cache backend is {cache_backend!r}; expected {expected_cache!r}.")

    key = f"runtime-gate:{uuid.uuid4().hex}"
    try:
        cache.set(key, "ok", timeout=10)
        value = cache.get(key)
        cache.delete(key)
        if value != "ok":
            failures.append("Redis cache roundtrip returned an unexpected value.")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"Redis cache roundtrip failed: {exc.__class__.__name__}: {exc}")

    if not getattr(settings, "EVENTSTREAM_REDIS", None):
        failures.append("EVENTSTREAM_REDIS is not configured; SSE multi-worker fanout is not on Redis.")

    return failures


def main() -> int:
    try:
        failures = _failures()
    except Exception as exc:  # noqa: BLE001 - settings import failures should be explicit
        print(f"runtime gate preflight failed while loading Django: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1

    if failures:
        print("Runtime gate preflight failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        print(
            "\nSet DATABASE_URL=postgres://... and REDIS_URL=redis://... before running make test-runtime.",
            file=sys.stderr,
        )
        return 1

    print("Runtime gate preflight passed: PostgreSQL + Redis are configured and reachable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
