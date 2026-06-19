"""WP-D4 — Coupon reset-usage admin action."""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.utils import timezone

from shopman.storefront.models import Coupon, Promotion


@pytest.mark.django_db
def test_reset_usage_zeroes_counter():
    now = timezone.now()
    promo = Promotion.objects.create(
        name="P",
        type=Promotion.PERCENT,
        value=10,
        valid_from=now,
        valid_until=now,
    )
    coupon = Coupon.objects.create(code="X", promotion=promo, max_uses=5, uses_count=3)

    coupon_admin = admin.site._registry[Coupon]
    coupon_admin.reset_usage(_req(), Coupon.objects.filter(pk=coupon.pk))

    coupon.refresh_from_db()
    assert coupon.uses_count == 0


def _req():
    from django.contrib.auth.models import User
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.test import RequestFactory

    request = RequestFactory().post("/")
    request.user = User(is_superuser=True, is_staff=True)
    request.session = {}
    request._messages = FallbackStorage(request)
    return request
