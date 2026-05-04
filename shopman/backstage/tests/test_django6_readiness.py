from __future__ import annotations

import warnings

from django.utils.deprecation import RemovedInDjango60Warning


def test_admin_url_fields_assume_https_without_django6_warning() -> None:
    from shopman.offerman.contrib.admin_unfold.nutrition_form import ProductAdminForm
    from shopman.orderman.admin import FulfillmentAdminForm

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        ProductAdminForm()
        FulfillmentAdminForm()

    messages = [str(item.message) for item in captured if issubclass(item.category, RemovedInDjango60Warning)]
    assert not any("assume_scheme" in message for message in messages)
