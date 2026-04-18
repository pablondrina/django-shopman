"""Health and readiness endpoints for load balancers, probes and monitors.

`/health/` — liveness: processo responde. Reporta DB, cache e migrations, mas
só DB e cache são críticos (liveness não deve reiniciar container apenas
porque migration está pendente — isso é readiness).

`/ready/` — readiness: DB + cache + migrations, todos críticos. Usado por
k8s readinessProbe / deploy validation para segurar tráfego até schema pronto.

Ambos: públicos, sem auth, sem CSRF, sem rate limit, JSON puro, log só em falha.
"""

from __future__ import annotations

import logging
import uuid

from django.core.cache import cache
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

_LOCMEM_BACKEND = "django.core.cache.backends.locmem.LocMemCache"


def _check_database() -> tuple[str, str | None]:
    try:
        conn = connections[DEFAULT_DB_ALIAS]
        conn.ensure_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:  # noqa: BLE001 — health endpoint must never raise
        return "fail", exc.__class__.__name__
    return "ok", None


def _check_cache() -> tuple[str, str | None]:
    from django.conf import settings

    backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    if backend == _LOCMEM_BACKEND:
        return "skipped", None
    key = f"health:{uuid.uuid4().hex}"
    try:
        cache.set(key, "1", timeout=5)
        value = cache.get(key)
        cache.delete(key)
    except Exception as exc:  # noqa: BLE001
        return "fail", exc.__class__.__name__
    if value != "1":
        return "fail", "roundtrip mismatch"
    return "ok", None


def _check_migrations() -> tuple[str, str | None]:
    try:
        executor = MigrationExecutor(connections[DEFAULT_DB_ALIAS])
        targets = executor.loader.graph.leaf_nodes()
        plan = executor.migration_plan(targets)
    except Exception as exc:  # noqa: BLE001
        return "fail", exc.__class__.__name__
    if plan:
        return "fail", f"{len(plan)} pending"
    return "ok", None


def _build_response(
    checks: dict[str, tuple[str, str | None]],
    critical: set[str],
) -> JsonResponse:
    failed_critical = [
        name for name, (status, _) in checks.items()
        if status == "fail" and name in critical
    ]
    payload = {
        "status": "error" if failed_critical else "ok",
        "checks": {
            name: (status if reason is None else f"fail — {reason}")
            for name, (status, reason) in checks.items()
        },
    }
    http_status = 503 if failed_critical else 200
    if failed_critical:
        logger.warning("Health check failed: %s", ", ".join(failed_critical))
    return JsonResponse(payload, status=http_status)


@method_decorator(csrf_exempt, name="dispatch")
class HealthCheckView(View):
    """Liveness probe: reports DB, cache and migrations.

    Only DB and cache are critical; pending migrations are surfaced for
    visibility but do not cause 503 (that is `/ready/`'s job).
    """

    def get(self, request):
        checks = {
            "database": _check_database(),
            "cache": _check_cache(),
            "migrations": _check_migrations(),
        }
        return _build_response(checks, critical={"database", "cache"})


@method_decorator(csrf_exempt, name="dispatch")
class ReadyCheckView(View):
    """Readiness probe: DB + cache + migrations, all critical."""

    def get(self, request):
        checks = {
            "database": _check_database(),
            "cache": _check_cache(),
            "migrations": _check_migrations(),
        }
        return _build_response(
            checks, critical={"database", "cache", "migrations"}
        )
