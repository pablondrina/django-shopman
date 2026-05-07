from __future__ import annotations

import logging
from collections import defaultdict
from contextlib import contextmanager
from time import perf_counter
from typing import Any

from django.conf import settings
from django.db import connection

logger = logging.getLogger(__name__)


class CartMutationPerf:
    """Lightweight phase/query timing for the cart mutation hot path."""

    def __init__(self) -> None:
        self.threshold_ms = float(
            getattr(settings, "SHOPMAN_CART_MUTATION_PERF_LOG_MS", 0) or 0,
        )
        self.enabled = self.threshold_ms > 0
        self.phase = "total"
        self.phase_ms: dict[str, float] = defaultdict(float)
        self.sql_count: dict[str, int] = defaultdict(int)
        self.sql_ms: dict[str, float] = defaultdict(float)
        self.started_at = perf_counter()

    @contextmanager
    def capture(self):
        if not self.enabled:
            yield
            return
        with connection.execute_wrapper(self._execute):
            yield

    @contextmanager
    def step(self, name: str):
        if not self.enabled:
            yield
            return
        previous = self.phase
        self.phase = name
        started_at = perf_counter()
        try:
            yield
        finally:
            self.phase_ms[name] += (perf_counter() - started_at) * 1000
            self.phase = previous

    def _execute(self, execute, sql, params, many, context):  # noqa: ANN001
        started_at = perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            elapsed_ms = (perf_counter() - started_at) * 1000
            self.sql_count[self.phase] += 1
            self.sql_ms[self.phase] += elapsed_ms

    def maybe_log(self, **extra: Any) -> None:
        if not self.enabled:
            return
        total_ms = (perf_counter() - self.started_at) * 1000
        if total_ms < self.threshold_ms:
            return
        logger.info(
            "storefront.cart.set_qty.perf",
            extra={
                "total_ms": round(total_ms, 1),
                "phase_ms": _round_map(self.phase_ms),
                "sql_count": dict(self.sql_count),
                "sql_ms": _round_map(self.sql_ms),
                **extra,
            },
        )


def _round_map(values: dict[str, float]) -> dict[str, float]:
    return {key: round(value, 1) for key, value in values.items()}
