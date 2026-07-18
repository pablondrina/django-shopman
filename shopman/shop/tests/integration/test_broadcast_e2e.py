"""E2E do broadcast: fornada real → post → notificação → aprovação → directive.

Os testes unitários mockam o work order; aqui a fornada é de verdade (Recipe →
WorkOrder → finish do Craftsman), então o caminho signal → handler → service
passa inteiro. É o teste que quebra se alguém desligar o wiring.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.offerman.models import Product
from shopman.orderman.models import Directive

from shopman.backstage.services import production
from shopman.shop.directives import BROADCAST_POST
from shopman.shop.models import (
    BroadcastPost,
    BroadcastRule,
    PostStatus,
    PostTemplate,
    UserNotification,
)
from shopman.shop.services import broadcast

pytestmark = pytest.mark.django_db

SKU = "croissant-e2e"


@pytest.fixture
def product():
    return Product.objects.create(
        sku=SKU, name="Croissant", base_price_q=850, is_sellable=True,
        metadata={"social": {"hashtags": ["croissant", "fresquinho"]}},
    )


@pytest.fixture
def recipe(product):
    return Recipe.objects.create(
        ref="croissant-e2e-v1", name="Croissant", output_sku=SKU, batch_size=Decimal("20")
    )


@pytest.fixture
def rule():
    template = PostTemplate.objects.create(
        name="Fornada pronta",
        body="{{produto}} acabou de sair do forno! {{hashtags}} Peça: {{link}}",
    )
    return BroadcastRule.objects.create(
        name="Fornada excelente → redes",
        trigger="production_finished",
        template=template,
        platforms=["instagram"],
        trigger_filter={"quality_min": "excelente"},
    )


@pytest.fixture
def gestor():
    user = get_user_model().objects.create_user(
        username="gestor-e2e", password="x", is_staff=True
    )
    user.user_permissions.add(Permission.objects.get(codename="manage_broadcast"))
    return user


def _bake(recipe, *, quality: str) -> WorkOrder:
    _, wo_ref, _, _ = production.apply_planned(
        recipe_id=recipe.pk, quantity="20",
        target_date_value=date.today().isoformat(), actor="production:op",
    )
    work_order = WorkOrder.objects.get(ref=wo_ref)
    production.apply_start(work_order_id=work_order.pk, quantity="20", actor="production:op")
    production.apply_finish(
        work_order_id=work_order.pk, quantity="20",
        actor="production:op", quality=quality,
    )
    work_order.refresh_from_db()
    return work_order


def test_excellent_bake_reaches_the_manager_as_an_approvable_post(
    django_capture_on_commit_callbacks, recipe, rule, gestor
):
    with django_capture_on_commit_callbacks(execute=True):
        work_order = _bake(recipe, quality="excelente")

    post = BroadcastPost.objects.get()
    assert post.status == PostStatus.PENDING_REVIEW
    assert post.body == (
        "Croissant acabou de sair do forno! #croissant #fresquinho "
        "Peça: " + post.content["link"]
    )
    assert post.trigger_context["work_order_ref"] == work_order.ref

    notification = UserNotification.objects.get(user=gestor)
    assert notification.is_actionable
    assert notification.action_data["broadcast_post_id"] == post.pk


def test_a_regular_bake_never_becomes_a_post(
    django_capture_on_commit_callbacks, recipe, rule, gestor
):
    """A régua de qualidade é do gestor: fornada comum não vira propaganda."""
    with django_capture_on_commit_callbacks(execute=True):
        _bake(recipe, quality="regular")

    assert BroadcastPost.objects.count() == 0
    assert UserNotification.objects.count() == 0


def test_approval_turns_the_post_into_a_platform_directive(
    django_capture_on_commit_callbacks, recipe, rule, gestor
):
    with django_capture_on_commit_callbacks(execute=True):
        _bake(recipe, quality="excelente")

    post = BroadcastPost.objects.get()
    broadcast.approve(post.pk, gestor)

    directive = Directive.objects.get(topic=BROADCAST_POST)
    assert directive.payload == {"post_id": post.pk, "platform": "instagram"}
    assert directive.dedupe_key == f"broadcast:{post.pk}:instagram"


def test_the_bake_survives_a_broken_broadcast(
    django_capture_on_commit_callbacks, recipe, rule, gestor, monkeypatch
):
    """Marketing quebrado não pode impedir o operador de fechar a fornada."""
    monkeypatch.setattr(
        broadcast, "evaluate", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    with django_capture_on_commit_callbacks(execute=True):
        work_order = _bake(recipe, quality="excelente")

    assert work_order.status == WorkOrder.Status.FINISHED
    assert BroadcastPost.objects.count() == 0


def test_no_active_rule_means_no_post(
    django_capture_on_commit_callbacks, recipe, gestor
):
    with django_capture_on_commit_callbacks(execute=True):
        _bake(recipe, quality="excelente")

    assert BroadcastPost.objects.count() == 0
