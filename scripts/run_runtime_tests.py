#!/usr/bin/env python
"""Run the runtime security/reliability subset and fail on any skipped test."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_RUNTIME_TEST_PATHS = (
    "packages/stockman/shopman/stockman/tests/test_concurrency.py",
    "packages/stockman/shopman/stockman/tests/test_quantity_invariant.py",
    "packages/payman/shopman/payman/tests/test_concurrency.py",
    "packages/craftsman/shopman/craftsman/tests/test_concurrency.py",
    "shopman/storefront/tests/test_concurrent_checkout.py",
    "shopman/storefront/tests/test_rate_limiting.py",
    "shopman/storefront/tests/web/test_order_access_security.py",
    "shopman/shop/tests/test_eventstream_permissions.py",
    "shopman/shop/tests/test_payment_webhooks.py",
    "shopman/shop/tests/test_ifood_webhook.py",
    "shopman/shop/tests/test_deploy_checks.py",
    "shopman/shop/tests/test_health.py",
)


@dataclass(eq=False)
class SkipCollector:
    skipped: list[tuple[str, str]] = field(default_factory=list)

    def pytest_runtest_logreport(self, report) -> None:
        if not report.skipped:
            return
        if report.when not in {"setup", "call"}:
            return
        reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else str(report.longrepr)
        self.skipped.append((report.nodeid, reason))


def _runtime_paths() -> list[str]:
    configured = os.environ.get("SHOPMAN_RUNTIME_TEST_PATHS", "").strip()
    if configured:
        return configured.split()
    return list(DEFAULT_RUNTIME_TEST_PATHS)


def main(argv: list[str] | None = None) -> int:
    try:
        import pytest
    except ImportError:
        print("pytest is required to run runtime tests.", file=sys.stderr)
        return 1

    collector = SkipCollector()
    extra_args = list(argv if argv is not None else sys.argv[1:])
    pytest_args = [*_runtime_paths(), "-q", "--maxfail=1", "-r", "s", *extra_args]
    result = pytest.main(pytest_args, plugins=[collector])

    if result == 0 and collector.skipped:
        print("\nRuntime gate failed because tests were skipped:", file=sys.stderr)
        for nodeid, reason in collector.skipped:
            print(f"- {nodeid}: {reason}", file=sys.stderr)
        return 1

    return int(result)


if __name__ == "__main__":
    raise SystemExit(main())
