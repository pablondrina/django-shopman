#!/usr/bin/env python
"""Operational diagnostics for Shopman support runbooks."""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from io import StringIO
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

Level = Literal["OK", "WARN", "FAIL", "INFO"]


@dataclass(frozen=True)
class CheckLine:
    level: Level
    name: str
    detail: str = ""


@dataclass(frozen=True)
class Diagnosis:
    title: str
    lines: tuple[CheckLine, ...]

    @property
    def exit_code(self) -> int:
        return 1 if any(line.level == "FAIL" for line in self.lines) else 0


def setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    previous_disable_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        django.setup()
    finally:
        logging.disable(previous_disable_level)


def diagnose_runtime(*, limit: int = 10, scan_limit: int = 5000) -> Diagnosis:
    _ = (limit, scan_limit)
    return Diagnosis("diagnose-runtime", tuple(_runtime_lines()))


def diagnose_health(*, limit: int = 10, scan_limit: int = 5000) -> Diagnosis:
    _ = (limit, scan_limit)

    from django.conf import settings
    from django.contrib.staticfiles import finders
    from django.core.management import call_command

    lines = list(_runtime_lines())

    lines.append(_call_command_line("django check", call_command, "check", verbosity=0))
    lines.append(
        _call_command_line(
            "django check --deploy",
            call_command,
            "check",
            deploy=True,
            verbosity=0,
        )
    )
    lines.append(
        _call_command_line(
            "migration plan",
            call_command,
            "makemigrations",
            check=True,
            dry_run=True,
            verbosity=0,
        )
    )

    static_probe = finders.find("admin/css/base.css")
    if static_probe:
        lines.append(CheckLine("OK", "staticfiles", "Django admin static asset found"))
    else:
        level: Level = "WARN" if settings.DEBUG else "FAIL"
        lines.append(CheckLine(level, "staticfiles", "Django admin static asset not found by staticfiles finders"))

    lines.extend(_adapter_configuration_lines())
    return Diagnosis("diagnose-health", tuple(lines))


def diagnose_worker(*, limit: int = 10, scan_limit: int = 5000) -> Diagnosis:
    _ = scan_limit

    from django.db.models import Count
    from django.utils import timezone
    from shopman.orderman import registry
    from shopman.orderman.management.commands.process_directives import (
        MAX_ATTEMPTS,
        REAP_STUCK_TIMEOUT_MINUTES,
    )
    from shopman.orderman.models import Directive

    now = timezone.now()
    lines: list[CheckLine] = []

    handlers = registry.get_directive_handlers()
    handler_detail = f"{len(handlers)} registered"
    if handlers:
        handler_detail += f" ({', '.join(sorted(handlers)[:limit])})"
    lines.append(CheckLine("OK" if handlers else "WARN", "directive handlers", handler_detail))

    status_counts = {
        row["status"]: row["total"]
        for row in Directive.objects.values("status").annotate(total=Count("id")).order_by("status")
    }
    lines.append(CheckLine("INFO", "directive status", _format_counts(status_counts)))

    ready_count = Directive.objects.filter(status=Directive.Status.QUEUED, available_at__lte=now).count()
    future_count = Directive.objects.filter(status=Directive.Status.QUEUED, available_at__gt=now).count()
    lines.append(CheckLine("WARN" if ready_count else "OK", "ready backlog", f"{ready_count} ready, {future_count} delayed"))

    stuck_cutoff = now - timedelta(minutes=REAP_STUCK_TIMEOUT_MINUTES)
    stuck = list(
        Directive.objects.filter(
            status=Directive.Status.RUNNING,
            started_at__lte=stuck_cutoff,
        ).order_by("started_at", "id")[:limit]
    )
    lines.append(
        CheckLine(
            "FAIL" if stuck else "OK",
            "stuck running",
            f"{len(stuck)} older than {REAP_STUCK_TIMEOUT_MINUTES}m",
        )
    )
    for directive in stuck:
        lines.append(
            CheckLine(
                "FAIL",
                "stuck directive",
                _directive_detail(directive, now=now, max_attempts=MAX_ATTEMPTS),
            )
        )

    failed = list(Directive.objects.filter(status=Directive.Status.FAILED).order_by("-updated_at", "-id")[:limit])
    lines.append(CheckLine("FAIL" if failed else "OK", "failed directives", f"{len(failed)} shown, newest first"))
    for directive in failed:
        lines.append(
            CheckLine(
                "FAIL",
                "failed directive",
                _directive_detail(directive, now=now, max_attempts=MAX_ATTEMPTS),
            )
        )

    oldest_ready = (
        Directive.objects.filter(status=Directive.Status.QUEUED, available_at__lte=now)
        .order_by("available_at", "id")
        .first()
    )
    if oldest_ready:
        lines.append(
            CheckLine(
                "WARN",
                "oldest ready",
                _directive_detail(oldest_ready, now=now, max_attempts=MAX_ATTEMPTS),
            )
        )

    return Diagnosis("diagnose-worker", tuple(lines))


def diagnose_payments(*, limit: int = 10, scan_limit: int = 5000) -> Diagnosis:
    from django.db.models import Count, Sum
    from shopman.orderman.models import Order
    from shopman.payman.models import PaymentIntent, PaymentTransaction

    lines: list[CheckLine] = []

    intent_counts = {
        row["status"]: row["total"]
        for row in PaymentIntent.objects.values("status").annotate(total=Count("id")).order_by("status")
    }
    lines.append(CheckLine("INFO", "payment intents", _format_counts(intent_counts)))

    method_counts = {
        row["method"]: row["total"]
        for row in PaymentIntent.objects.values("method").annotate(total=Count("id")).order_by("method")
    }
    lines.append(CheckLine("INFO", "payment methods", _format_counts(method_counts)))

    gateway_counts = {
        row["gateway"] or "-": row["total"]
        for row in PaymentIntent.objects.values("gateway").annotate(total=Count("id")).order_by("gateway")
    }
    lines.append(CheckLine("INFO", "gateways", _format_counts(gateway_counts)))

    orders = list(
        Order.objects.only(
            "ref",
            "channel_ref",
            "session_key",
            "snapshot",
            "total_q",
            "currency",
            "status",
            "data",
            "created_at",
        )
        .order_by("-created_at", "-id")[:scan_limit]
    )
    order_by_ref = {order.ref: order for order in orders}
    order_intent_refs = {
        order.ref: intent_ref
        for order in orders
        if (intent_ref := _order_intent_ref(order))
    }

    intents = list(
        PaymentIntent.objects.only("id", "ref", "order_ref", "status", "method", "amount_q", "gateway", "created_at")
        .order_by("-created_at", "-id")[:scan_limit]
    )
    intent_by_ref = {intent.ref: intent for intent in intents}
    order_refs_from_intents = {intent.order_ref for intent in intents if intent.order_ref}
    known_order_refs = set(Order.objects.filter(ref__in=order_refs_from_intents).values_list("ref", flat=True))

    missing_intents = [
        (order_ref, intent_ref)
        for order_ref, intent_ref in order_intent_refs.items()
        if intent_ref not in intent_by_ref
    ][:limit]
    lines.append(
        CheckLine(
            "FAIL" if missing_intents else "OK",
            "orders with missing intent",
            f"{len(missing_intents)} shown from {len(order_intent_refs)} orders with payment intent_ref",
        )
    )
    for order_ref, intent_ref in missing_intents:
        lines.append(CheckLine("FAIL", "missing intent", f"order={order_ref} intent={intent_ref}"))

    orphan_intents = [intent for intent in intents if intent.order_ref and intent.order_ref not in known_order_refs][:limit]
    lines.append(
        CheckLine(
            "FAIL" if orphan_intents else "OK",
            "intents without order",
            f"{len(orphan_intents)} shown from {len(intents)} scanned intents",
        )
    )
    for intent in orphan_intents:
        lines.append(
            CheckLine(
                "FAIL",
                "orphan intent",
                f"intent={intent.ref} status={intent.status} order={intent.order_ref} amount={intent.amount_q}q",
            )
        )

    orders_missing_data_link = [
        intent
        for intent in intents
        if intent.order_ref in order_by_ref and order_intent_refs.get(intent.order_ref) != intent.ref
    ][:limit]
    lines.append(
        CheckLine(
            "WARN" if orders_missing_data_link else "OK",
            "orders missing data intent link",
            f"{len(orders_missing_data_link)} shown",
        )
    )
    for intent in orders_missing_data_link:
        lines.append(
            CheckLine(
                "WARN",
                "missing data intent link",
                f"order={intent.order_ref} intent={intent.ref} status={intent.status}",
            )
        )

    tx_totals = _payment_transaction_totals(
        PaymentTransaction.objects.filter(intent_id__in=[intent.id for intent in intents])
        .values("intent_id", "type")
        .annotate(total=Sum("amount_q"))
    )

    order_intent_pairs = {
        (order_ref, intent_ref)
        for order_ref, intent_ref in order_intent_refs.items()
        if order_ref in order_by_ref
    }
    order_intent_pairs.update(
        (intent.order_ref, intent.ref)
        for intent in intents
        if intent.order_ref in order_by_ref
    )

    issues: list[str] = []
    for order_ref, intent_ref in sorted(order_intent_pairs):
        intent = intent_by_ref.get(intent_ref)
        order = order_by_ref[order_ref]
        if intent is None:
            continue
        totals = tx_totals[intent.id]
        captured_q = totals["capture"]
        refunded_q = totals["refund"] + totals["chargeback"]
        net_q = captured_q - refunded_q

        if intent.order_ref != order.ref:
            issues.append(
                f"order={order.ref} intent={intent.ref} intent_order={intent.order_ref} issue=order_ref_mismatch"
            )
        if intent.amount_q != order.total_q:
            issues.append(
                f"order={order.ref} intent={intent.ref} order_total={order.total_q}q intent_amount={intent.amount_q}q"
            )
        if order.status == Order.Status.NEW and intent.status in (PaymentIntent.Status.CAPTURED, PaymentIntent.Status.REFUNDED):
            issues.append(f"order={order.ref} status={order.status} intent={intent.ref} issue=paid_not_confirmed")
        if order.status in _ACTIVE_PAID_ORDER_STATUSES(Order) and intent.status in (
            PaymentIntent.Status.CAPTURED,
            PaymentIntent.Status.REFUNDED,
        ) and net_q < order.total_q:
            issues.append(
                f"order={order.ref} status={order.status} intent={intent.ref} net={net_q}q total={order.total_q}q"
            )
        if order.status in (Order.Status.CANCELLED, Order.Status.RETURNED) and net_q > 0:
            issues.append(
                f"order={order.ref} status={order.status} intent={intent.ref} net_captured={net_q}q"
            )
        if intent.status in (PaymentIntent.Status.CAPTURED, PaymentIntent.Status.REFUNDED) and captured_q <= 0:
            issues.append(f"order={order.ref} intent={intent.ref} status={intent.status} issue=missing_capture_tx")
        if refunded_q > captured_q:
            issues.append(
                f"order={order.ref} intent={intent.ref} captured={captured_q}q refunded_or_chargeback={refunded_q}q"
            )

        if len(issues) >= limit:
            break

    lines.append(CheckLine("FAIL" if issues else "OK", "payment divergences", f"{len(issues)} shown"))
    for issue in issues:
        lines.append(CheckLine("FAIL", "payment divergence", issue))

    return Diagnosis("diagnose-payments", tuple(lines))


def diagnose_webhooks(*, limit: int = 10, scan_limit: int = 5000) -> Diagnosis:
    _ = scan_limit

    from django.db.models import Count
    from django.utils import timezone
    from shopman.orderman.models import IdempotencyKey

    from shopman.backstage.models import OperatorAlert

    now = timezone.now()
    lines: list[CheckLine] = []

    webhook_keys = IdempotencyKey.objects.filter(scope__startswith="webhook:")
    counts = list(
        webhook_keys.values("scope", "status")
        .annotate(total=Count("id"))
        .order_by("scope", "status")
    )
    if counts:
        for row in counts[:limit]:
            lines.append(
                CheckLine(
                    "INFO",
                    "webhook idempotency",
                    f"scope={row['scope']} status={row['status']} total={row['total']}",
                )
            )
    else:
        lines.append(CheckLine("WARN", "webhook idempotency", "no webhook idempotency rows found"))

    stale_cutoff = now - timedelta(minutes=5)
    stale = list(webhook_keys.filter(status="in_progress", created_at__lte=stale_cutoff).order_by("created_at")[:limit])
    lines.append(CheckLine("FAIL" if stale else "OK", "stale webhook keys", f"{len(stale)} older than 5m"))
    for key in stale:
        lines.append(CheckLine("FAIL", "stale webhook key", _idempotency_detail(key, now=now)))

    failed = list(webhook_keys.filter(status="failed").order_by("-created_at", "-id")[:limit])
    lines.append(CheckLine("FAIL" if failed else "OK", "failed webhook keys", f"{len(failed)} shown"))
    for key in failed:
        lines.append(CheckLine("FAIL", "failed webhook key", _idempotency_detail(key, now=now)))

    alert_types = ("webhook_failed", "payment_reconciliation_failed")
    alert_counts = {
        row["type"]: row["total"]
        for row in OperatorAlert.objects.filter(type__in=alert_types, acknowledged=False)
        .values("type")
        .annotate(total=Count("id"))
        .order_by("type")
    }
    lines.append(CheckLine("FAIL" if alert_counts else "OK", "active webhook/payment alerts", _format_counts(alert_counts)))

    alerts = list(
        OperatorAlert.objects.filter(type__in=alert_types, acknowledged=False)
        .order_by("-created_at", "-id")[:limit]
    )
    for alert in alerts:
        lines.append(
            CheckLine(
                "FAIL",
                "active alert",
                (
                    f"type={alert.type} severity={alert.severity} order={alert.order_ref or '-'} "
                    f"age={_age(alert.created_at, now=now)} message={_compact_text(alert.message, 140)}"
                ),
            )
        )

    return Diagnosis("diagnose-webhooks", tuple(lines))


def _runtime_lines() -> list[CheckLine]:
    from django.conf import settings
    from django.db import connection

    from shopman.shop.views.health import _LOCMEM_BACKEND, _check_cache, _check_database, _check_migrations

    lines: list[CheckLine] = [
        CheckLine("INFO", "debug", f"DEBUG={settings.DEBUG}"),
    ]

    db_status, db_detail = _check_database()
    db_engine = settings.DATABASES.get("default", {}).get("ENGINE", "")
    db_vendor = getattr(connection, "vendor", "unknown")
    if db_status == "ok":
        lines.append(CheckLine("OK", "database roundtrip", f"vendor={db_vendor} engine={db_engine}"))
    else:
        lines.append(CheckLine("FAIL", "database roundtrip", db_detail or "failed"))

    db_required_level = _required_level(settings.DEBUG)
    database_url_set = bool(os.environ.get("DATABASE_URL", "").strip())
    if "postgresql" in db_engine and database_url_set:
        lines.append(CheckLine("OK", "postgresql runtime", "DATABASE_URL set and PostgreSQL engine active"))
    else:
        lines.append(
            CheckLine(
                db_required_level,
                "postgresql runtime",
                f"DATABASE_URL={'set' if database_url_set else 'missing'} engine={db_engine or '-'}",
            )
        )

    cache_status, cache_detail = _check_cache()
    cache_backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    if cache_status == "ok":
        lines.append(CheckLine("OK", "cache roundtrip", cache_backend))
    elif cache_status == "skipped":
        level = "WARN" if cache_backend == _LOCMEM_BACKEND and settings.DEBUG else "FAIL"
        lines.append(CheckLine(level, "cache roundtrip", f"skipped backend={cache_backend}"))
    else:
        lines.append(CheckLine("FAIL", "cache roundtrip", cache_detail or cache_backend or "failed"))

    redis_url_set = bool(os.environ.get("REDIS_URL", "").strip())
    if redis_url_set and cache_backend == "django.core.cache.backends.redis.RedisCache":
        lines.append(CheckLine("OK", "redis runtime", "REDIS_URL set and native Django Redis cache active"))
    else:
        lines.append(
            CheckLine(
                _required_level(settings.DEBUG),
                "redis runtime",
                f"REDIS_URL={'set' if redis_url_set else 'missing'} cache_backend={cache_backend or '-'}",
            )
        )

    if getattr(settings, "EVENTSTREAM_REDIS", None):
        lines.append(CheckLine("OK", "eventstream fanout", "EVENTSTREAM_REDIS configured"))
    else:
        lines.append(CheckLine(_required_level(settings.DEBUG), "eventstream fanout", "EVENTSTREAM_REDIS missing"))

    migrations_status, migrations_detail = _check_migrations()
    if migrations_status == "ok":
        lines.append(CheckLine("OK", "migrations", "applied"))
    else:
        lines.append(CheckLine("FAIL", "migrations", migrations_detail or "pending"))

    return lines


def _adapter_configuration_lines() -> list[CheckLine]:
    from django.conf import settings

    lines: list[CheckLine] = []
    payment_adapters = getattr(settings, "SHOPMAN_PAYMENT_ADAPTERS", {})
    for method in ("pix", "card"):
        adapter = payment_adapters.get(method)
        if not adapter:
            lines.append(CheckLine("INFO", f"{method} adapter", "not configured"))
            continue
        if "payment_mock" in adapter:
            level = "WARN" if settings.DEBUG else "FAIL"
            lines.append(CheckLine(level, f"{method} adapter", f"mock adapter active: {adapter}"))
        else:
            lines.append(CheckLine("OK", f"{method} adapter", adapter))

    efi_token = getattr(settings, "SHOPMAN_EFI_WEBHOOK", {}).get("webhook_token", "")
    lines.append(_secret_presence_line("efi webhook token", efi_token, settings.DEBUG))

    ifood_token = getattr(settings, "SHOPMAN_IFOOD", {}).get("webhook_token", "")
    lines.append(_secret_presence_line("ifood webhook token", ifood_token, settings.DEBUG))

    stripe_configured = any("payment_stripe" in str(adapter) for adapter in payment_adapters.values())
    if stripe_configured:
        stripe_secret = getattr(settings, "SHOPMAN_STRIPE", {}).get("webhook_secret", "")
        lines.append(_secret_presence_line("stripe webhook secret", stripe_secret, settings.DEBUG))
    else:
        lines.append(CheckLine("INFO", "stripe webhook secret", "stripe adapter not active"))

    return lines


def _call_command_line(name: str, call_command, *args, **kwargs) -> CheckLine:
    stdout = StringIO()
    stderr = StringIO()
    try:
        call_command(*args, stdout=stdout, stderr=stderr, **kwargs)
    except Exception as exc:  # noqa: BLE001 - diagnostics must surface every operational failure
        return CheckLine("FAIL", name, _exception_summary(exc))
    return CheckLine("OK", name, "passed")


def _secret_presence_line(name: str, value: str, debug: bool) -> CheckLine:
    if value:
        return CheckLine("OK", name, "configured")
    return CheckLine(_required_level(debug), name, "missing")


def _required_level(debug: bool) -> Level:
    return "WARN" if debug else "FAIL"


def _order_intent_ref(order) -> str:
    payment = (order.data or {}).get("payment") or {}
    return str(payment.get("intent_ref") or "").strip()


def _ACTIVE_PAID_ORDER_STATUSES(Order) -> tuple[str, ...]:
    return (
        Order.Status.CONFIRMED,
        Order.Status.PREPARING,
        Order.Status.READY,
        Order.Status.DISPATCHED,
        Order.Status.DELIVERED,
        Order.Status.COMPLETED,
    )


def _payment_transaction_totals(rows) -> defaultdict[int, dict[str, int]]:
    totals: defaultdict[int, dict[str, int]] = defaultdict(lambda: {"capture": 0, "refund": 0, "chargeback": 0})
    for row in rows:
        tx_type = row["type"]
        if tx_type in totals[row["intent_id"]]:
            totals[row["intent_id"]][tx_type] += int(row["total"] or 0)
    return totals


def _directive_detail(directive, *, now, max_attempts: int) -> str:
    started = f" started_age={_age(directive.started_at, now=now)}" if directive.started_at else ""
    available = f" available_age={_age(directive.available_at, now=now)}" if directive.available_at else ""
    error = f" error={_compact_text(directive.last_error, 100)}" if directive.last_error else ""
    return (
        f"id={directive.pk} topic={directive.topic} status={directive.status} "
        f"attempts={directive.attempts}/{max_attempts} error_code={directive.error_code or '-'}"
        f"{started}{available}{error}"
    )


def _idempotency_detail(key, *, now) -> str:
    response = f" response={key.response_code}" if key.response_code else ""
    return (
        f"id={key.pk} scope={key.scope} key={_fingerprint(key.key)} status={key.status} "
        f"age={_age(key.created_at, now=now)}{response}"
    )


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{key or '-'}={value}" for key, value in sorted(counts.items()))


def _age(value, *, now) -> str:
    if not value:
        return "-"
    delta = now - value
    seconds = max(int(delta.total_seconds()), 0)
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h"
    return f"{hours // 24}d"


def _fingerprint(value: str) -> str:
    if not value:
        return "-"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"sha256:{digest}"


def _compact_text(value: str, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[redacted-email]", text)
    text = re.sub(r"\+?\d[\d\s().-]{7,}\d", "[redacted-phone]", text)
    text = re.sub(r"(?i)(bearer|token|secret|password)=\S+", r"\1=[redacted]", text)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _exception_summary(exc: BaseException) -> str:
    detail = _compact_text(str(exc), 180)
    if not detail:
        return exc.__class__.__name__
    return f"{exc.__class__.__name__}: {detail}"


def render(diagnosis: Diagnosis) -> None:
    print(f"== {diagnosis.title} ==")
    for line in diagnosis.lines:
        detail = f": {line.detail}" if line.detail else ""
        print(f"[{line.level}] {line.name}{detail}")
    status = "FAIL" if diagnosis.exit_code else "OK"
    print(f"result={status}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Shopman operational diagnostics")
    parser.add_argument(
        "command",
        choices=("runtime", "worker", "payments", "webhooks", "health"),
        help="Diagnostic command to run",
    )
    parser.add_argument("--limit", type=int, default=10, help="Maximum detail rows per diagnostic section")
    parser.add_argument("--scan-limit", type=int, default=5000, help="Maximum recent rows scanned per model")
    args = parser.parse_args(argv)

    setup_django()

    commands = {
        "runtime": diagnose_runtime,
        "worker": diagnose_worker,
        "payments": diagnose_payments,
        "webhooks": diagnose_webhooks,
        "health": diagnose_health,
    }
    previous_disable_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        diagnosis = commands[args.command](limit=max(args.limit, 1), scan_limit=max(args.scan_limit, 1))
    finally:
        logging.disable(previous_disable_level)
    render(diagnosis)
    return diagnosis.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
