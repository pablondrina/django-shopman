"""Admin smoke tests (WP-C4).

Safety net for the whole Django Admin/Unfold surface: every registered
``ModelAdmin`` must render its changelist and add form without a server error,
and every read-only ``admin_console`` console page must return 200. This catches
broken ``list_display``/``fieldsets``, orphan actions, widget/form errors and bad
imports — the kind of breakage that unit tests of individual admins miss because
they never exercise the real request path.

It was this test that surfaced the offerman Product 500 (nutrition virtual fields
injected in ``__init__`` were invisible to ``modelform_factory``).
"""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.urls import NoReverseMatch, reverse
from shopman.orderman.models import Order, OrderItem

from shopman.shop.models import Shop

# Built at import time — pytest-django has already run ``django.setup()`` (which
# triggers admin autodiscover) before this module is collected.
_REGISTERED_MODELS = sorted(
    admin.site._registry.keys(),
    key=lambda m: (m._meta.app_label, m._meta.model_name),
)


# Core packages (packages/*). Every model whose admin lives in one of these is a
# Core model and MUST be registered with an Unfold ``ModelAdmin`` at deployment
# runtime — never a silent vanilla fallback (which happens if a contrib/admin_unfold
# app drops out of INSTALLED_APPS). See test_core_models_use_unfold_admin.
_CORE_MODULE_PREFIXES = (
    "shopman.refs.",
    "shopman.offerman.",
    "shopman.stockman.",
    "shopman.craftsman.",
    "shopman.orderman.",
    "shopman.guestman.",
    "shopman.doorman.",
    "shopman.payman.",
    "shopman.utils.",
)

_CORE_MODELS = [
    model for model in _REGISTERED_MODELS
    if model.__module__.startswith(_CORE_MODULE_PREFIXES)
]


def _model_id(model) -> str:
    return f"{model._meta.app_label}.{model._meta.model_name}"


def _admin_url(model, view: str, *args) -> str:
    return reverse(
        f"admin:{model._meta.app_label}_{model._meta.model_name}_{view}", args=args
    )


@pytest.fixture
def admin_client(client, db):
    Shop.objects.create(name="Loja")
    user = User.objects.create_superuser("smoke-admin", "smoke@test.com", "pw")
    client.force_login(user)
    return client


@pytest.mark.django_db
@pytest.mark.parametrize("model", _REGISTERED_MODELS, ids=_model_id)
def test_changelist_renders(admin_client, model):
    """Every registered model's changelist must not 500."""
    response = admin_client.get(_admin_url(model, "changelist"), follow=True)
    assert response.status_code < 500, (
        f"{_model_id(model)} changelist returned {response.status_code}"
    )


@pytest.mark.django_db
@pytest.mark.parametrize("model", _REGISTERED_MODELS, ids=_model_id)
def test_add_form_renders(admin_client, model):
    """Every registered model's add form must not 500 (403 = add disabled, OK)."""
    try:
        url = _admin_url(model, "add")
    except NoReverseMatch:
        pytest.skip("model has no add view")
    response = admin_client.get(url, follow=True)
    assert response.status_code < 500, (
        f"{_model_id(model)} add form returned {response.status_code}"
    )


@pytest.mark.django_db
def test_change_form_renders_for_seeded_order(admin_client):
    """The Order change form (rich display methods incl. cross-package payment
    info) must render against a real object."""
    order = Order.objects.create(
        ref="SMOKE-ORDER",
        channel_ref="web",
        session_key="smoke-session",
        status=Order.Status.CONFIRMED,
        total_q=3000,
        currency="BRL",
        data={"payment": {"method": "cash"}},
    )
    OrderItem.objects.create(
        order=order,
        line_id="1",
        sku="SMOKE-SKU",
        name="Smoke item",
        qty=2,
        unit_price_q=1500,
        line_total_q=3000,
    )
    response = admin_client.get(_admin_url(order.__class__, "change", order.pk))
    assert response.status_code == 200
    assert "Pagamentos" in response.content.decode("utf-8")


@pytest.mark.parametrize("model", _CORE_MODELS, ids=_model_id)
def test_core_models_use_unfold_admin(model):
    """Contract (WP-C3): every Core model is registered with an Unfold ModelAdmin.

    Each Core package ships a plain ``admin.py`` and (usually) a
    ``contrib/admin_unfold`` app that unregisters the plain admin and re-registers
    an Unfold one. If the contrib app silently drops out of INSTALLED_APPS, the
    admin degrades to vanilla Django with no warning. This guard fails loudly so
    that can never reach production unnoticed — no allowlist, no exceptions.
    """
    from unfold.admin import ModelAdmin as UnfoldModelAdmin

    registered = admin.site._registry[model]
    assert isinstance(registered, UnfoldModelAdmin), (
        f"{_model_id(model)} caiu em admin vanilla "
        f"({type(registered).__module__}.{type(registered).__name__}); "
        "registre-o com unfold.admin.ModelAdmin (ou via contrib/admin_unfold)."
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name",
    [
        "admin_console_production",
        "admin_console_production_planning",
        "admin_console_production_dashboard",
        "admin_console_production_reports",
        "admin_console_day_closing",
    ],
)
def test_admin_console_pages_render(admin_client, url_name):
    """Custom admin_console operational pages must render (200)."""
    response = admin_client.get(reverse(url_name), follow=True)
    assert response.status_code == 200, (
        f"{url_name} returned {response.status_code}"
    )
