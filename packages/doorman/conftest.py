"""Root conftest for Auth tests."""

import pytest

from shopman.auth.conf import reset_adapter, reset_customer_resolver


@pytest.fixture(autouse=True)
def _reset_resolver():
    """Reset the cached customer resolver and adapter between tests."""
    reset_customer_resolver()
    reset_adapter()
    yield
    reset_customer_resolver()
    reset_adapter()
