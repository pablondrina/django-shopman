"""Root conftest for Auth tests."""

import pytest

from shopman.auth.conf import reset_customer_resolver


@pytest.fixture(autouse=True)
def _reset_resolver():
    """Reset the cached customer resolver between tests."""
    reset_customer_resolver()
    yield
    reset_customer_resolver()
