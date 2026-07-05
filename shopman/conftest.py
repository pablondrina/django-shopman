"""Shared pytest fixtures for the shopman surfaces (shop, storefront, backstage)."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_rules_state():
    """Keep process-level singletons deterministic across tests, regardless of order.

    Several process-level stores leak between tests because a transaction rollback
    removes DB rows without firing the signals/teardown that would clean up the
    derived in-Python state:

    * ``django.core.cache`` caches the active RuleConfig list under ``CACHE_KEY``
      and the singleton ``Shop`` under ``SHOP_CACHE_KEY``. A test that creates a
      ``Shop`` (rolled back afterwards) leaves a stale instance cached for the
      next test's ``Shop.load()``.
    * ``shopman.orderman`` registers validator *instances* (e.g. a
      ``business_hours`` rule with custom params) in an in-process registry; a
      test that registers one leaves it grabbed for every later test.
    * ``shopman.shop.rules.engine._bootstrapped`` is a module-level flag set once
      by ``bootstrap_active_rules()`` and never reset, so a test that triggers a
      bootstrap blocks re-bootstrap for every later test.
    * ``shopman.shop.adapters._external._suppressed_reason`` is a module-level
      flag set by ``suppress()`` — which the ``seed`` command calls at startup and
      never restores. A test that runs ``seed`` (e.g. the Nelson seed coverage in
      backstage) leaves every external adapter inert for the rest of the process,
      so a later test that asserts a real send (``test_sms_opt_in_...``) sees no
      call and fails. It only reproduces under full-suite ordering, never in
      isolation — the classic test-pollution signature.

    Clear the caches, reset the bootstrap flag, drop the suppression flag, and
    snapshot/restore the validator registry around each test so state created in
    one test cannot bleed into another.
    """
    from django.core.cache import cache
    from shopman.orderman import registry as orderman_registry

    from shopman.shop.adapters import _external
    from shopman.shop.models.shop import SHOP_CACHE_KEY
    from shopman.shop.rules import engine as rules_engine

    reg = orderman_registry._registry
    with reg._lock:
        validators_snapshot = list(reg._validators)

    def _reset_process_state() -> None:
        cache.delete(rules_engine.CACHE_KEY)
        cache.delete(SHOP_CACHE_KEY)
        rules_engine._bootstrapped = False
        _external._suppressed_reason = None

    _reset_process_state()

    yield

    _reset_process_state()
    with reg._lock:
        reg._validators[:] = validators_snapshot
