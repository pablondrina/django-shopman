#!/usr/bin/env python
"""Shopman migrations gate.

Answers one question, honestly, in the pre-prod phase:

    "Does the migration graph build a clean schema from zero, with nothing
     uncommitted?"

Checks executed today (pre go-live):

1. ``makemigrations --check --dry-run`` — no model change lacks a migration.
2. Fresh ``migrate`` from zero into a throwaway SQLite database — the whole
   graph applies linearly without errors.
3. ``migrate --check`` against that fresh database — the graph is fully applied
   and internally consistent (no missing dependency, no unapplied leftover).

Reserved for go-live (WP-GAP-07): replaying a real production *baseline*
snapshot and validating data survives the upgrade. That step needs a snapshot
to exist, so it stays a documented, skipped slot until then — see
``SHOPMAN_MIGRATIONS_BASELINE`` below.

Local failures exit non-zero. The script never touches the dev database: it
migrates into a temporary SQLite file that is removed on exit.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

Status = Literal["passed", "failed", "skipped"]


@dataclass(frozen=True)
class MigrationCheck:
    id: str
    title: str
    status: Status
    message: str
    details: dict[str, object] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return self.status == "failed"

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
class MigrationReport:
    checks: tuple[MigrationCheck, ...]

    @property
    def blocking(self) -> bool:
        return any(check.failed for check in self.checks)

    @property
    def status(self) -> str:
        return "failed" if self.blocking else "passed"

    @property
    def counts(self) -> dict[str, int]:
        statuses = ("passed", "failed", "skipped")
        return {status: sum(1 for check in self.checks if check.status == status) for status in statuses}

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
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
def _suppress_logs():
    previous_disable_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(previous_disable_level)


def _no_uncommitted_migrations() -> MigrationCheck:
    from django.core.management import call_command

    try:
        output = StringIO()
        call_command("makemigrations", check=True, dry_run=True, stdout=output, stderr=output, verbosity=0)
    except SystemExit as exc:  # makemigrations --check exits non-zero when changes are missing
        if exc.code:
            return MigrationCheck(
                id="migrations.committed",
                title="No model change without a migration",
                status="failed",
                message="Model changes exist without a matching migration. Run makemigrations.",
            )
    except Exception as exc:  # noqa: BLE001 - any failure here blocks release
        return MigrationCheck(
            id="migrations.committed",
            title="No model change without a migration",
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
        )
    return MigrationCheck(
        id="migrations.committed",
        title="No model change without a migration",
        status="passed",
        message="No model changes without migrations.",
    )


@contextmanager
def _fresh_sqlite_database():
    """Point the default connection at a throwaway SQLite file.

    Django fills missing connection defaults when the handler re-reads
    ``settings.DATABASES``, so a minimal ENGINE+NAME dict is enough. The dev
    database is never touched.
    """
    from django.conf import settings
    from django.db import connections

    tmp_dir = tempfile.mkdtemp(prefix="shopman-migrations-")
    db_path = os.path.join(tmp_dir, "fresh.sqlite3")

    original = settings.DATABASES
    settings.DATABASES = {
        **original,
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": db_path,
            "OPTIONS": {"timeout": 10},
        },
    }
    connections.close_all()
    connections.__dict__.pop("databases", None)  # drop cached_property so settings re-read
    try:
        yield db_path
    finally:
        connections.close_all()
        connections.__dict__.pop("databases", None)
        settings.DATABASES = original
        try:
            os.remove(db_path)
        except OSError:
            pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass


def _clean_schema_build() -> tuple[MigrationCheck, MigrationCheck]:
    from django.core.management import call_command

    try:
        with _fresh_sqlite_database():
            output = StringIO()
            call_command("migrate", stdout=output, stderr=output, verbosity=0, no_input=True)
            build = MigrationCheck(
                id="migrations.clean_build",
                title="Clean schema builds from zero",
                status="passed",
                message="Full migration graph applied on an empty database.",
            )

            consistent = StringIO()
            try:
                call_command("migrate", check_unapplied=True, stdout=consistent, stderr=consistent, verbosity=0)
            except SystemExit as exc:
                if exc.code:
                    graph = MigrationCheck(
                        id="migrations.graph_consistent",
                        title="Migration graph fully applied",
                        status="failed",
                        message="migrate --check reported unapplied/inconsistent migrations after a full build.",
                    )
                    return build, graph
            graph = MigrationCheck(
                id="migrations.graph_consistent",
                title="Migration graph fully applied",
                status="passed",
                message="migrate --check is clean after a full build.",
            )
            return build, graph
    except Exception as exc:  # noqa: BLE001 - a broken graph must surface as a failure
        build = MigrationCheck(
            id="migrations.clean_build",
            title="Clean schema builds from zero",
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
        )
        graph = MigrationCheck(
            id="migrations.graph_consistent",
            title="Migration graph fully applied",
            status="failed",
            message="Skipped because the clean build failed.",
        )
        return build, graph


def _baseline_replay() -> MigrationCheck:
    """Reserved go-live step: replay a real baseline snapshot and validate data.

    Activates only once ``SHOPMAN_MIGRATIONS_BASELINE`` points at a snapshot,
    which exists from go-live onward (WP-GAP-07). Until then it is an honest,
    explicitly skipped slot — not a silent pass.
    """
    baseline = (os.environ.get("SHOPMAN_MIGRATIONS_BASELINE", "") or "").strip()
    if not baseline:
        return MigrationCheck(
            id="migrations.baseline_replay",
            title="Baseline snapshot replay (go-live)",
            status="skipped",
            message="No baseline snapshot declared yet (pre go-live).",
            details={"expected": "Set SHOPMAN_MIGRATIONS_BASELINE=/path/to/snapshot once a production baseline exists."},
        )
    if not Path(baseline).expanduser().exists():
        return MigrationCheck(
            id="migrations.baseline_replay",
            title="Baseline snapshot replay (go-live)",
            status="failed",
            message="SHOPMAN_MIGRATIONS_BASELINE is set but the snapshot file does not exist.",
            details={"baseline": baseline},
        )
    # Replay against a real baseline is implemented at go-live (WP-GAP-07), when
    # the snapshot format and validation set are known. Declaring it here keeps
    # the contract visible without pretending it ran.
    return MigrationCheck(
        id="migrations.baseline_replay",
        title="Baseline snapshot replay (go-live)",
        status="skipped",
        message="Baseline declared; replay harness lands at go-live (WP-GAP-07).",
        details={"baseline": baseline},
    )


def build_report() -> MigrationReport:
    setup_django()
    with _suppress_logs():
        committed = _no_uncommitted_migrations()
        build, graph = _clean_schema_build()
        baseline = _baseline_replay()
    return MigrationReport(checks=(committed, build, graph, baseline))


def print_human(report: MigrationReport) -> None:
    print(f"check-migrations: {report.status}")
    print(
        "counts: "
        f"passed={report.counts['passed']} failed={report.counts['failed']} "
        f"skipped={report.counts['skipped']}"
    )
    for check in report.checks:
        marker = {"passed": "OK", "failed": "FAIL", "skipped": "SKIP"}[check.status]
        print(f"- [{marker}] {check.id}: {check.message}")
        if check.details:
            print(f"  details={json.dumps(check.details, ensure_ascii=False, sort_keys=True)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Shopman migration graph health.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    report = build_report()
    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print_human(report)
    return 1 if report.blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
