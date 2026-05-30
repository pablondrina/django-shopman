"""Shared pytest fixtures for the shopman surfaces (shop, storefront, backstage)."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_rules_state():
    """Keep the rules engine deterministic across tests, regardless of order.

    Two process-level stores leak between tests because a transaction rollback
    removes RuleConfig rows without firing the signals/teardown that would clean
    up derived state:

    * ``django.core.cache`` caches the active RuleConfig list under one key.
    * ``shopman.orderman`` registers validator *instances* (e.g. a delivery
      ``minimum_order`` with custom params) in an in-process registry; a test
      that registers one leaves it grabbed for every later test.

    Clear the cache and snapshot/restore the validator registry around each
    test so a RuleConfig created in one test cannot bleed into another.
    """
    from django.core.cache import cache
    from shopman.orderman import registry as orderman_registry

    from shopman.shop.rules.engine import CACHE_KEY

    reg = orderman_registry._registry
    with reg._lock:
        validators_snapshot = list(reg._validators)
    cache.delete(CACHE_KEY)

    yield

    cache.delete(CACHE_KEY)
    with reg._lock:
        reg._validators[:] = validators_snapshot
