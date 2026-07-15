"""Shared fixtures for the storefront persona E2E suite.

These tests drive the JSON API end-to-end through the pytest-django ``client``
fixture (a real ``django.test.Client`` hitting ``/api/v1/...``). Business rules,
stock holds, pricing modifiers, payment intents and the order lifecycle all run
for real — only the outbound adapters (payment, notifications) are the in-repo
mock/console backends configured by ``config.settings_test``.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_caches():
    """Isolate rate-limit counters and omotenashi copy between tests.

    The storefront checkout/cart/tracking endpoints rate-limit by ``user_or_ip``
    through the Django cache; a persona journey fires several mutations, so we
    clear the counter store around every test to keep the suite order-independent.
    """
    from django.core.cache import cache

    from shopman.shop.omotenashi.copy import invalidate_cache

    cache.clear()
    invalidate_cache()
    yield
    cache.clear()
    invalidate_cache()
