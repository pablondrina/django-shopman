"""Handlers de broadcast — receivers de evento e handlers de directive.

Dois contratos: (1) marketing nunca derruba a operação que o disparou; (2) a
audiência é resolvida no despacho, não na criação do post.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from shopman.offerman.models import Product

from shopman.shop.handlers import broadcast as handlers
from shopman.shop.models import BroadcastPost, BroadcastRule, PostStatus, PostTemplate

pytestmark = pytest.mark.django_db

SKU = "croissant-trad"


@pytest.fixture
def product():
    return Product.objects.create(sku=SKU, name="Croissant", base_price_q=850, is_sellable=True)


@pytest.fixture
def rule():
    template = PostTemplate.objects.create(name="T", body="{{produto}} saiu do forno")
    return BroadcastRule.objects.create(
        name="Fornada", trigger="production_finished",
        template=template, platforms=["instagram"],
    )


def _work_order(**overrides):
    fields = {
        "ref": "WO-2026-00001",
        "meta": {"quality": "excelente"},
        "finished": 40,
        "finished_at": None,
        "output_sku": SKU,
    }
    return SimpleNamespace(**{**fields, **overrides})


# ── Receiver de produção ─────────────────────────────────────────────


class TestProductionReceiver:
    def _fire(self, *, action="finished", work_order=None):
        with patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()):
            handlers.on_production_changed(
                sender=None, product_ref=SKU, date=None, action=action,
                work_order=work_order or _work_order(),
            )

    def test_finished_bake_creates_a_post(self, product, rule):
        self._fire()
        assert BroadcastPost.objects.count() == 1

    def test_other_actions_are_ignored(self, product, rule):
        for action in ("planned", "started", "adjusted", "voided"):
            self._fire(action=action)
        assert BroadcastPost.objects.count() == 0

    def test_quality_flows_from_work_order_meta(self, product, rule):
        self._fire()
        assert BroadcastPost.objects.get().trigger_context["quality"] == "excelente"

    def test_missing_quality_defaults_to_bom(self, product, rule):
        self._fire(work_order=_work_order(meta={}))
        assert BroadcastPost.objects.get().trigger_context["quality"] == "bom"

    def test_evaluation_failure_never_breaks_the_bake(self, product, rule):
        """Marketing quebrado não pode impedir o operador de fechar a fornada."""
        with patch(
            "shopman.shop.services.broadcast.evaluate", side_effect=RuntimeError("boom")
        ):
            self._fire()  # não levanta

    def test_evaluation_waits_for_commit(self, product, rule):
        """Avaliar dentro da transação leria estoque que ainda não existe."""
        with patch("django.db.transaction.on_commit") as on_commit:
            handlers.on_production_changed(
                sender=None, product_ref=SKU, date=None,
                action="finished", work_order=_work_order(),
            )
        on_commit.assert_called_once()
        assert BroadcastPost.objects.count() == 0


# ── Receiver de disponibilidade ──────────────────────────────────────


class TestAvailabilityReceiver:
    def _fire(self, *, available, was_out=False):
        with (
            patch.object(handlers, "_available_qty", return_value=available),
            patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
        ):
            handlers.on_availability_changed(sender=None, sku=SKU, was_out_of_stock=was_out)

    def _rule(self, trigger: str):
        template = PostTemplate.objects.create(name=trigger, body="{{produto}}")
        return BroadcastRule.objects.create(
            name=trigger, trigger=trigger, template=template, platforms=["instagram"]
        )

    def test_scarce_stock_triggers_low_stock(self, product):
        self._rule("low_stock")
        self._fire(available=2)
        assert BroadcastPost.objects.count() == 1

    def test_healthy_stock_triggers_nothing(self, product):
        self._rule("low_stock")
        self._fire(available=50)
        assert BroadcastPost.objects.count() == 0

    def test_sold_out_announces_nothing(self, product):
        """Sem estoque não há o que anunciar."""
        self._rule("low_stock")
        self._fire(available=0)
        assert BroadcastPost.objects.count() == 0

    def test_coming_back_triggers_stock_back(self, product):
        self._rule("stock_back")
        self._fire(available=20, was_out=True)
        assert BroadcastPost.objects.count() == 1

    def test_missing_sku_is_ignored(self, product):
        self._rule("low_stock")
        handlers.on_availability_changed(sender=None, sku="")
        assert BroadcastPost.objects.count() == 0


# ── Directive: broadcast.post ────────────────────────────────────────


class TestPostHandler:
    def _post(self, rule) -> BroadcastPost:
        return BroadcastPost.objects.create(
            rule=rule, template=rule.template, status=PostStatus.PUBLISHING,
            content={"body": "Croissant saiu do forno"}, platforms=["instagram"],
        )

    def _handle(self, post, platform="instagram"):
        message = SimpleNamespace(pk=1, payload={"post_id": post.pk, "platform": platform})
        handlers.BroadcastPostHandler().handle(message=message, ctx={})

    def test_without_an_adapter_the_post_waits_for_manual_publishing(self, rule):
        """Sem credencial (F5/F6), o conteúdo fica pronto e o gestor copia."""
        post = self._post(rule)
        self._handle(post)
        post.refresh_from_db()
        assert post.platform_results["instagram"]["status"] == "pending_manual"

    def test_manual_publishing_still_closes_the_post(self, rule):
        post = self._post(rule)
        self._handle(post)
        post.refresh_from_db()
        assert post.status == PostStatus.PUBLISHED
        assert post.published_at is not None

    def test_a_working_adapter_publishes(self, rule):
        post = self._post(rule)
        adapter = MagicMock()
        adapter.publish.return_value = {"post_id": "ig_123", "url": "https://ig/p/123"}
        with patch.object(handlers, "_posting_adapter", return_value=adapter):
            self._handle(post)
        post.refresh_from_db()
        assert post.platform_results["instagram"]["post_id"] == "ig_123"
        assert post.status == PostStatus.PUBLISHED

    def test_adapter_failure_marks_the_post_and_reraises_for_retry(self, rule):
        post = self._post(rule)
        adapter = MagicMock()
        adapter.publish.side_effect = RuntimeError("meta fora do ar")
        with (
            patch.object(handlers, "_posting_adapter", return_value=adapter),
            pytest.raises(RuntimeError),
        ):
            self._handle(post)
        post.refresh_from_db()
        assert post.status == PostStatus.FAILED

    def test_a_post_is_only_settled_once_every_platform_answered(self, rule):
        post = self._post(rule)
        post.platforms = ["instagram", "google_business"]
        post.save()
        self._handle(post)
        post.refresh_from_db()
        assert post.status == PostStatus.PUBLISHING

        self._handle(post, platform="google_business")
        post.refresh_from_db()
        assert post.status == PostStatus.PUBLISHED

    def test_missing_post_is_a_no_op(self):
        message = SimpleNamespace(pk=1, payload={"post_id": 9999, "platform": "instagram"})
        handlers.BroadcastPostHandler().handle(message=message, ctx={})


# ── Directive: broadcast.notify ──────────────────────────────────────


class TestNotifyHandler:
    def _post(self) -> BroadcastPost:
        template = PostTemplate.objects.create(name="T", body="{{produto}}")
        rule = BroadcastRule.objects.create(
            name="Audiência", trigger="production_finished", template=template,
            platforms=["whatsapp"], audience_rules={"favorites": True},
        )
        return BroadcastPost.objects.create(
            rule=rule, template=template, status=PostStatus.PUBLISHING,
            content={"body": "Saiu do forno", "link": "https://loja/p/x"},
            platforms=["whatsapp"], trigger_context={"sku": SKU},
        )

    def _handle(self, post, wave="all"):
        message = SimpleNamespace(pk=1, payload={"post_id": post.pk, "wave": wave})
        handlers.BroadcastNotifyHandler().handle(message=message, ctx={})

    def test_audience_is_resolved_at_dispatch_not_at_creation(self):
        """Entre a fornada e a aprovação, favoritos e alertas mudam."""
        post = self._post()
        with patch("shopman.shop.services.audience.resolve") as resolve:
            resolve.return_value.all_recipients.return_value = ()
            self._handle(post)
        resolve.assert_called_once()
        assert resolve.call_args.args[0] == SKU

    def test_each_recipient_gets_the_message(self):
        post = self._post()
        recipients = (
            SimpleNamespace(phone="+5543999990001"),
            SimpleNamespace(phone="+5543999990002"),
        )
        with (
            patch("shopman.shop.services.audience.resolve") as resolve,
            patch("shopman.shop.notifications.notify") as notify,
        ):
            resolve.return_value.all_recipients.return_value = recipients
            notify.return_value = SimpleNamespace(success=True)
            self._handle(post)
        assert notify.call_count == 2
        post.refresh_from_db()
        assert post.platform_results["whatsapp"]["sent"] == 2

    def test_a_failed_send_is_counted_not_swallowed(self):
        post = self._post()
        with (
            patch("shopman.shop.services.audience.resolve") as resolve,
            patch("shopman.shop.notifications.notify", side_effect=RuntimeError("wa off")),
        ):
            resolve.return_value.all_recipients.return_value = (
                SimpleNamespace(phone="+5543999990001"),
            )
            self._handle(post)
        post.refresh_from_db()
        assert post.platform_results["whatsapp"]["failed"] == 1

    def test_the_vip_wave_only_reaches_vips(self):
        post = self._post()
        with (
            patch("shopman.shop.services.audience.resolve") as resolve,
            patch("shopman.shop.notifications.notify") as notify,
        ):
            resolve.return_value.vip = (SimpleNamespace(phone="+5543999990010"),)
            resolve.return_value.general = (
                SimpleNamespace(phone="+5543999990011"),
                SimpleNamespace(phone="+5543999990012"),
            )
            notify.return_value = SimpleNamespace(success=True)
            self._handle(post, wave="vip")
        assert notify.call_count == 1

    def test_empty_audience_still_closes_the_post(self):
        post = self._post()
        with patch("shopman.shop.services.audience.resolve") as resolve:
            resolve.return_value.all_recipients.return_value = ()
            self._handle(post)
        post.refresh_from_db()
        assert post.status == PostStatus.PUBLISHED
