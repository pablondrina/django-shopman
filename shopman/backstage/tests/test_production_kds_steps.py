from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from django.urls import reverse

from shopman.backstage.projections.production import build_production_kds, resolve_production_access
from shopman.backstage.services import production as production_service
from shopman.backstage.services.exceptions import ProductionError
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrder


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser("steps-admin", "steps@test.com", "pw")


def _recipe(ref: str, *, meta=None, steps=None):
    return Recipe.objects.create(
        ref=ref,
        name=ref,
        output_sku=ref.upper(),
        batch_size=Decimal("10"),
        meta=meta or {},
        steps=steps or [],
    )


def _started(recipe, *, minutes_ago: int, meta=None):
    wo = craft.plan(recipe, 10, date=date.today())
    craft.start(wo, quantity=10, expected_rev=0)
    WorkOrder.objects.filter(pk=wo.pk).update(
        started_at=timezone.now() - timedelta(minutes=minutes_ago),
        meta=meta or {},
    )
    return WorkOrder.objects.get(pk=wo.pk)


@pytest.mark.django_db
def test_work_order_without_steps_keeps_fallback(superuser):
    recipe = _recipe("plain")
    _started(recipe, minutes_ago=1)

    card = build_production_kds(access=resolve_production_access(superuser)).cards[0]

    assert card.current_step == "Produção"
    assert card.current_step_index is None
    assert card.total_steps == 0


@pytest.mark.django_db
def test_meta_steps_calculate_current_step_progress(superuser):
    recipe = _recipe("with-steps", meta={"steps": [
        {"name": "Misturar", "target_seconds": 600},
        {"name": "Assar", "target_seconds": 300},
        {"name": "Resfriar", "target_seconds": 180},
    ]})
    _started(recipe, minutes_ago=5)

    card = build_production_kds(access=resolve_production_access(superuser)).cards[0]

    assert card.current_step_index == 1
    assert card.current_step_name == "Misturar"
    assert 45 <= card.step_progress_pct <= 55
    assert card.next_step_name == "Assar"


@pytest.mark.django_db
def test_elapsed_time_advances_to_next_step(superuser):
    recipe = _recipe("advanced", meta={"steps": [
        {"name": "Misturar", "target_seconds": 600},
        {"name": "Assar", "target_seconds": 300},
    ]})
    _started(recipe, minutes_ago=12)

    card = build_production_kds(access=resolve_production_access(superuser)).cards[0]

    assert card.current_step_index == 2
    assert card.current_step_name == "Assar"


@pytest.mark.django_db
def test_steps_progress_manual_override(superuser):
    recipe = _recipe("manual", meta={"steps": [
        {"name": "Misturar", "target_seconds": 600},
        {"name": "Assar", "target_seconds": 300},
    ]})
    _started(recipe, minutes_ago=1, meta={"steps_progress": 2})

    card = build_production_kds(access=resolve_production_access(superuser)).cards[0]

    assert card.current_step_index == 2
    assert card.current_step_name == "Assar"


@pytest.mark.django_db
def test_legacy_recipe_steps_are_supported(superuser):
    recipe = _recipe("legacy", steps=["Modelar", "Forno"], meta={"max_started_minutes": 20})
    _started(recipe, minutes_ago=1)

    card = build_production_kds(access=resolve_production_access(superuser)).cards[0]

    assert card.current_step_name == "Modelar"
    assert card.total_steps == 2


@pytest.mark.django_db
def test_apply_advance_step_increments_pointer(superuser):
    recipe = _recipe("advance", meta={"steps": [
        {"name": "Misturar", "target_seconds": 600},
        {"name": "Assar", "target_seconds": 300},
        {"name": "Resfriar", "target_seconds": 180},
    ]})
    wo = _started(recipe, minutes_ago=1)

    new_index = production_service.apply_advance_step(work_order_id=wo.pk, actor="op:test")
    assert new_index == 1
    wo.refresh_from_db()
    assert wo.meta["steps_progress"] == 1

    production_service.apply_advance_step(work_order_id=wo.pk, actor="op:test")
    wo.refresh_from_db()
    assert wo.meta["steps_progress"] == 2


@pytest.mark.django_db
def test_apply_advance_step_caps_at_total(superuser):
    recipe = _recipe("cap", meta={"steps": [
        {"name": "A", "target_seconds": 60},
        {"name": "B", "target_seconds": 60},
    ]})
    wo = _started(recipe, minutes_ago=1, meta={"steps_progress": 5})

    new_index = production_service.apply_advance_step(work_order_id=wo.pk, actor="op:cap")
    assert new_index == 2


@pytest.mark.django_db
def test_apply_advance_step_rejects_recipe_without_steps(superuser):
    recipe = _recipe("no-steps")
    wo = _started(recipe, minutes_ago=1)

    with pytest.raises(ProductionError):
        production_service.apply_advance_step(work_order_id=wo.pk, actor="op:test")


@pytest.mark.django_db
def test_advance_step_view_requires_post(client, superuser):
    from shopman.shop.models import Shop

    Shop.objects.create(name="Loja")
    recipe = _recipe("view", meta={"steps": [
        {"name": "A", "target_seconds": 60},
        {"name": "B", "target_seconds": 60},
    ]})
    wo = _started(recipe, minutes_ago=1)
    client.force_login(superuser)

    url = reverse("backstage:production_advance_step", args=[wo.pk])
    response = client.post(url, HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    wo.refresh_from_db()
    assert wo.meta["steps_progress"] == 1
