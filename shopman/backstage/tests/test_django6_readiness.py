from __future__ import annotations

import warnings


def test_admin_url_fields_assume_https_without_django6_warning() -> None:
    from shopman.offerman.contrib.admin_unfold.nutrition_form import ProductAdminForm
    from shopman.orderman.admin import FulfillmentAdminForm

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        ProductAdminForm()
        FulfillmentAdminForm()

    RemovedInDjango60Warning = _removed_in_django60_warning()
    if RemovedInDjango60Warning is None:
        return

    messages = [str(item.message) for item in captured if issubclass(item.category, RemovedInDjango60Warning)]
    assert not any("assume_scheme" in message for message in messages)


def _removed_in_django60_warning():
    try:
        from django.utils.deprecation import RemovedInDjango60Warning
    except ImportError:
        return None
    return RemovedInDjango60Warning
