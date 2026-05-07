#!/usr/bin/env python
"""Shopman release/pilot readiness contract.

This script is intentionally stricter than a healthcheck and less expensive
than the full CI suite. It answers one operational question:

    "Can this tree move toward a real pilot, and what is still external?"

Local failures exit non-zero. External blockers (gateway credentials, physical
QA evidence, pre-prod URL) are reported honestly and only fail with
``--strict-external``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Literal

try:
    import fcntl
except ImportError:  # pragma: no cover - POSIX is the supported deploy target
    fcntl = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

Status = Literal["passed", "failed", "blocked_external", "warning"]


@dataclass(frozen=True)
class ReadinessCheck:
    id: str
    title: str
    status: Status
    message: str
    details: dict[str, object] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return self.status == "failed"

    @property
    def external_blocked(self) -> bool:
        return self.status == "blocked_external"

    def as_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "message": self.message,
        }
        if self.details:
            data["details"] = self.details
        return data


@dataclass(frozen=True)
class ReadinessReport:
    checks: tuple[ReadinessCheck, ...]
    strict_external: bool

    @property
    def local_failed(self) -> bool:
        return any(check.failed for check in self.checks)

    @property
    def external_blocked(self) -> bool:
        return any(check.external_blocked for check in self.checks)

    @property
    def blocking(self) -> bool:
        return self.local_failed or (self.strict_external and self.external_blocked)

    @property
    def status(self) -> str:
        if self.local_failed:
            return "failed"
        if self.external_blocked:
            return "blocked_external" if self.strict_external else "passed_with_external_blockers"
        return "passed"

    @property
    def counts(self) -> dict[str, int]:
        statuses = ("passed", "failed", "blocked_external", "warning")
        return {status: sum(1 for check in self.checks if check.status == status) for status in statuses}

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "strict_external": self.strict_external,
            "counts": self.counts,
            "checks": [check.as_dict() for check in self.checks],
        }


def setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    previous_disable_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        django.setup()
    finally:
        logging.disable(previous_disable_level)


@contextmanager
def _process_lock():
    """Serialize readiness runs that mutate local smoke data.

    The gateway smoke fixtures run inside rollback transactions, but two local
    readiness processes sharing SQLite can still collide on write locks. The
    lock is process-scoped and automatically released by the OS on exit.
    """
    if fcntl is None:
        yield
        return

    lock_path = Path(os.environ.get("SHOPMAN_RELEASE_READINESS_LOCK", "/tmp/shopman-release-readiness.lock"))
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def build_report(
    *,
    strict_external: bool = False,
    manual_qa_evidence: str = "",
    preprod_url: str = "",
) -> ReadinessReport:
    setup_django()

    with _suppress_operational_logs():
        checks = [
            _django_system_check(),
            _migration_check(),
            _omotenashi_seed_check(),
            _gateway_smoke_check(),
            _gateway_sandbox_check(),
            _manual_qa_check(manual_qa_evidence),
            _preprod_check(preprod_url),
        ]
    return ReadinessReport(checks=tuple(checks), strict_external=strict_external)


@contextmanager
def _suppress_operational_logs():
    """Keep readiness output operator-readable while preserving check details."""
    previous_disable_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(previous_disable_level)


def _django_system_check() -> ReadinessCheck:
    from django.core.management import call_command

    try:
        output = StringIO()
        call_command("check", stdout=output, stderr=output, verbosity=0)
    except Exception as exc:  # noqa: BLE001 - readiness must report every local blocker
        return ReadinessCheck(
            id="django.check",
            title="Django system checks",
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
        )
    return ReadinessCheck(
        id="django.check",
        title="Django system checks",
        status="passed",
        message="System checks passed.",
    )


def _migration_check() -> ReadinessCheck:
    from django.core.management import call_command

    try:
        output = StringIO()
        call_command("makemigrations", check=True, dry_run=True, stdout=output, stderr=output, verbosity=0)
    except Exception as exc:  # noqa: BLE001 - uncommitted migrations block release
        return ReadinessCheck(
            id="django.migrations",
            title="Migrations committed",
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
        )
    return ReadinessCheck(
        id="django.migrations",
        title="Migrations committed",
        status="passed",
        message="No model changes without migrations.",
    )


def _omotenashi_seed_check() -> ReadinessCheck:
    from shopman.backstage.services.omotenashi_qa import build_omotenashi_qa_report

    try:
        report = build_omotenashi_qa_report()
    except Exception as exc:  # noqa: BLE001
        return ReadinessCheck(
            id="omotenashi.seed",
            title="Omotenashi QA seed matrix",
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
        )

    details = report.as_dict().get("counts", {})
    if report.blocking:
        missing = [check.id for check in report.checks if check.status == "missing"]
        return ReadinessCheck(
            id="omotenashi.seed",
            title="Omotenashi QA seed matrix",
            status="failed",
            message="Seed does not cover every canonical Omotenashi scenario.",
            details={"counts": details, "missing": missing},
        )
    return ReadinessCheck(
        id="omotenashi.seed",
        title="Omotenashi QA seed matrix",
        status="passed",
        message=f"{report.ready_count}/{len(report.checks)} scenarios ready.",
        details={"counts": details},
    )


def _gateway_smoke_check() -> ReadinessCheck:
    from shopman.backstage.services.gateway_smoke import run_gateway_smoke

    try:
        report = run_gateway_smoke(
            include_local=True,
            include_sandbox_readiness=False,
            require_sandbox=False,
            rollback=True,
        )
    except Exception as exc:  # noqa: BLE001
        return ReadinessCheck(
            id="gateways.local",
            title="Local gateway smoke",
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
        )

    failed = [check.as_dict() for check in report.checks if check.is_failure]
    if failed:
        return ReadinessCheck(
            id="gateways.local",
            title="Local gateway smoke",
            status="failed",
            message="At least one local gateway fixture failed.",
            details={"counts": report.counts, "failed": failed},
        )
    return ReadinessCheck(
        id="gateways.local",
        title="Local gateway smoke",
        status="passed",
        message="EFI, Stripe and iFood local contracts passed with rollback.",
        details={"counts": report.counts, "rolled_back": report.rolled_back},
    )


def _gateway_sandbox_check() -> ReadinessCheck:
    from shopman.backstage.services.gateway_smoke import run_gateway_smoke

    try:
        report = run_gateway_smoke(
            include_local=False,
            include_sandbox_readiness=True,
            require_sandbox=False,
            rollback=True,
        )
    except Exception as exc:  # noqa: BLE001
        return ReadinessCheck(
            id="gateways.sandbox",
            title="Gateway sandbox/staging readiness",
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
        )

    blocked = [check.as_dict() for check in report.checks if check.is_blocked]
    failed = [check.as_dict() for check in report.checks if check.is_failure]
    if failed:
        return ReadinessCheck(
            id="gateways.sandbox",
            title="Gateway sandbox/staging readiness",
            status="failed",
            message="Sandbox readiness check failed unexpectedly.",
            details={"counts": report.counts, "failed": failed},
        )
    if blocked:
        return ReadinessCheck(
            id="gateways.sandbox",
            title="Gateway sandbox/staging readiness",
            status="blocked_external",
            message="Requires real sandbox/staging credentials before production traffic.",
            details={"counts": report.counts, "blocked": blocked},
        )
    return ReadinessCheck(
        id="gateways.sandbox",
        title="Gateway sandbox/staging readiness",
        status="passed",
        message="Sandbox/staging gateway configuration is ready to exercise.",
        details={"counts": report.counts},
    )


def _manual_qa_check(evidence_path: str) -> ReadinessCheck:
    evidence = (evidence_path or os.environ.get("SHOPMAN_MANUAL_QA_EVIDENCE", "")).strip()
    if evidence and Path(evidence).expanduser().exists():
        return ReadinessCheck(
            id="omotenashi.manual",
            title="Physical/staging Omotenashi QA evidence",
            status="passed",
            message="Manual QA evidence file exists.",
            details={"evidence": str(Path(evidence).expanduser())},
        )
    return ReadinessCheck(
        id="omotenashi.manual",
        title="Physical/staging Omotenashi QA evidence",
        status="blocked_external",
        message="Needs a human/device or staging evidence file before real release.",
        details={"expected": "Set SHOPMAN_MANUAL_QA_EVIDENCE=/path/to/report.md or pass --manual-qa-evidence."},
    )


def _preprod_check(preprod_url: str) -> ReadinessCheck:
    url = (preprod_url or os.environ.get("SHOPMAN_PREPROD_URL", "")).strip()
    if url:
        return ReadinessCheck(
            id="preprod.environment",
            title="Pre-prod environment",
            status="passed",
            message="Pre-prod URL is declared for release playbook execution.",
            details={"url": url},
        )
    return ReadinessCheck(
        id="preprod.environment",
        title="Pre-prod environment",
        status="blocked_external",
        message="Needs real pre-prod/staging URL, secrets and provider configuration.",
        details={"expected": "Set SHOPMAN_PREPROD_URL=https://staging.example.com for strict release checks."},
    )


def print_human(report: ReadinessReport) -> None:
    print(f"release-readiness: {report.status}")
    print(
        "counts: "
        f"passed={report.counts['passed']} failed={report.counts['failed']} "
        f"blocked_external={report.counts['blocked_external']} warning={report.counts['warning']}"
    )
    for check in report.checks:
        marker = {
            "passed": "OK",
            "failed": "FAIL",
            "blocked_external": "BLOCKED",
            "warning": "WARN",
        }[check.status]
        print(f"- [{marker}] {check.id}: {check.message}")
        if check.details:
            print(f"  details={json.dumps(check.details, ensure_ascii=False, sort_keys=True)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Shopman release/pilot readiness.")
    parser.add_argument("--strict-external", action="store_true", help="Fail when external readiness is blocked.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--manual-qa-evidence", default="", help="Path to a physical/staging QA evidence report.")
    parser.add_argument("--preprod-url", default="", help="Staging/pre-prod URL declared for release playbook.")
    args = parser.parse_args(argv)

    with _process_lock():
        report = build_report(
            strict_external=bool(args.strict_external),
            manual_qa_evidence=args.manual_qa_evidence,
            preprod_url=args.preprod_url,
        )
    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print_human(report)
    return 1 if report.blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
