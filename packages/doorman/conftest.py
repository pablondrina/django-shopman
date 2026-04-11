"""Root conftest for Auth tests."""

import pytest

from shopman.doorman.conf import reset_adapter, reset_customer_resolver

_GUESTMAN_RESOLVER = "shopman.guestman.adapters.auth.CustomerResolver"


def _enrich_doorman(*, setting, value, enter, **kwargs):
    """Inject resolver class when a test overrides DOORMAN without one.

    @override_settings(DOORMAN={...}) replaces the entire DOORMAN dict.
    If the resolver class is omitted, fall back to the Guestman resolver
    (which is always available in the test environment) and reset the
    singleton so the new settings take effect.
    """
    if setting != "DOORMAN" or not isinstance(value, dict):
        return
    if "CUSTOMER_RESOLVER_CLASS" not in value:
        value["CUSTOMER_RESOLVER_CLASS"] = _GUESTMAN_RESOLVER
    reset_customer_resolver()
    reset_adapter()


@pytest.fixture(autouse=True)
def _reset_resolver():
    """Reset the cached customer resolver and adapter between tests."""
    from django.test.signals import setting_changed

    setting_changed.connect(_enrich_doorman)
    reset_customer_resolver()
    reset_adapter()
    yield
    reset_customer_resolver()
    reset_adapter()
    setting_changed.disconnect(_enrich_doorman)
