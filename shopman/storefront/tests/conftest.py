import pytest


@pytest.fixture(autouse=True)
def clear_omotenashi_cache():
    from shopman.storefront.omotenashi.copy import invalidate_cache

    invalidate_cache()
    yield
    invalidate_cache()
