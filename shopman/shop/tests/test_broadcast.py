"""BroadcastService — filtros, conteúdo, aprovação, despacho e notificação.

O contrato central: um evento operacional vira post revisável, a revisão vira
Directives por plataforma, e nada disso pode derrubar a operação que disparou.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.orderman.models import Directive

from shopman.shop.directives import BROADCAST_NOTIFY, BROADCAST_POST
from shopman.shop.models import (
    BroadcastPost,
    BroadcastRule,
    PostStatus,
    PostTemplate,
    UserNotification,
)
from shopman.shop.services import broadcast

pytestmark = pytest.mark.django_db

SKU = "croissant-trad"
User = get_user_model()


@pytest.fixture
def product():
    return Product.objects.create(
        sku=SKU, name="Croissant Tradicional", base_price_q=850, is_sellable=True
    )


@pytest.fixture
def template():
    return PostTemplate.objects.create(
        name="Fornada pronta",
        body="{{produto}} acabou de sair do forno! {{hashtags}} Garanta o seu: {{link}}",
    )


@pytest.fixture
def rule(template):
    return BroadcastRule.objects.create(
        name="Fornada → redes",
        trigger="production_finished",
        template=template,
        platforms=["instagram", "google_business"],
    )


def _context(**overrides) -> dict:
    return {"sku": SKU, "quality": "bom", "quantity": "40", **overrides}


# ── evaluate ─────────────────────────────────────────────────────────


class TestEvaluate:
    def test_matching_rule_creates_a_pending_post(self, product, rule):
        posts = broadcast.evaluate("production_finished", _context())
        assert len(posts) == 1
        assert posts[0].status == PostStatus.PENDING_REVIEW

    def test_inactive_rule_is_ignored(self, product, rule):
        rule.is_active = False
        rule.save()
        assert broadcast.evaluate("production_finished", _context()) == []

    def test_other_trigger_is_ignored(self, product, rule):
        assert broadcast.evaluate("low_stock", _context()) == []

    def test_no_rules_is_a_normal_answer(self, product):
        assert broadcast.evaluate("production_finished", _context()) == []

    def test_auto_post_rule_skips_review(self, product, rule):
        rule.requires_approval = False
        rule.save()
        post = broadcast.evaluate("production_finished", _context())[0]
        assert post.status == PostStatus.PUBLISHING
        assert Directive.objects.filter(topic=BROADCAST_POST).count() == 2

    def test_a_broken_rule_does_not_silence_the_others(self, product, template, rule):
        BroadcastRule.objects.create(
            name="Segunda regra", trigger="production_finished",
            template=template, platforms=["instagram"],
        )
        with patch.object(
            broadcast, "resolve_content", side_effect=[RuntimeError("boom"), {"body": "ok"}]
        ):
            posts = broadcast.evaluate("production_finished", _context())
        assert len(posts) == 1

    def test_trigger_context_is_snapshotted(self, product, rule):
        post = broadcast.evaluate("production_finished", _context(work_order_ref="WO-1"))[0]
        assert post.trigger_context["work_order_ref"] == "WO-1"


# ── trigger_filter ───────────────────────────────────────────────────


class TestTriggerFilter:
    def test_quality_below_minimum_blocks_the_post(self, product, rule):
        rule.trigger_filter = {"quality_min": "excelente"}
        rule.save()
        assert broadcast.evaluate("production_finished", _context(quality="bom")) == []

    def test_quality_at_minimum_passes(self, product, rule):
        rule.trigger_filter = {"quality_min": "bom"}
        rule.save()
        assert len(broadcast.evaluate("production_finished", _context(quality="bom"))) == 1

    def test_quality_above_minimum_passes(self, product, rule):
        rule.trigger_filter = {"quality_min": "bom"}
        rule.save()
        assert len(broadcast.evaluate("production_finished", _context(quality="excelente"))) == 1

    def test_missing_quality_is_treated_as_bom(self, product, rule):
        """O operador pode finalizar sem escolher; o default não pode travar tudo."""
        rule.trigger_filter = {"quality_min": "bom"}
        rule.save()
        context = _context()
        context.pop("quality")
        assert len(broadcast.evaluate("production_finished", context)) == 1

    def test_collection_filter_matches(self, product, rule):
        rule.trigger_filter = {"collections": ["paes"]}
        rule.save()
        assert len(broadcast.evaluate("production_finished", _context(collections=["paes"]))) == 1

    def test_collection_filter_excludes(self, product, rule):
        rule.trigger_filter = {"collections": ["paes"]}
        rule.save()
        assert broadcast.evaluate("production_finished", _context(collections=["doces"])) == []

    def test_max_remaining_gate(self, product, template):
        BroadcastRule.objects.create(
            name="Últimas unidades", trigger="low_stock", template=template,
            platforms=["whatsapp"], trigger_filter={"max_remaining": 3},
        )
        assert broadcast.evaluate("low_stock", _context(available_qty=5)) == []
        assert len(broadcast.evaluate("low_stock", _context(available_qty=2))) == 1

    def test_empty_filter_always_matches(self, product, rule):
        assert len(broadcast.evaluate("production_finished", _context())) == 1


# ── Conteúdo ─────────────────────────────────────────────────────────


class TestContent:
    def test_variables_are_substituted(self, product, rule):
        post = broadcast.evaluate("production_finished", _context())[0]
        assert post.body.startswith("Croissant Tradicional acabou de sair do forno!")

    def test_unknown_variable_becomes_empty(self):
        assert broadcast.render("Olá {{inexistente}}!", {}) == "Olá !"

    def test_render_never_leaks_raw_placeholders(self, product, rule):
        post = broadcast.evaluate("production_finished", _context())[0]
        assert "{{" not in post.body

    def test_price_is_formatted_in_reais(self, product):
        variables = broadcast.resolve_variables({"sku": SKU})
        assert variables["preco"] == "R$ 8,50"

    def test_hashtags_get_the_hash_prefix(self, product):
        product.metadata = {"social": {"hashtags": ["croissant", "fresquinho"]}}
        product.save()
        variables = broadcast.resolve_variables({"sku": SKU})
        assert variables["hashtags"] == "#croissant #fresquinho"

    def test_missing_product_degrades_to_the_sku(self):
        variables = broadcast.resolve_variables({"sku": "fantasma"})
        assert variables["produto"] == "fantasma"

    def test_quality_reaches_the_template(self, product, template, rule):
        template.body = "Fornada {{qualidade}} de {{produto}}"
        template.save()
        post = broadcast.evaluate("production_finished", _context(quality="excelente"))[0]
        assert post.body == "Fornada excelente de Croissant Tradicional"


# ── Aprovação ────────────────────────────────────────────────────────


class TestApprove:
    @pytest.fixture
    def gestor(self):
        return User.objects.create_user(username="gestor", password="x", is_staff=True)

    def test_approval_stamps_who_and_when(self, product, rule, gestor):
        post = broadcast.evaluate("production_finished", _context())[0]
        approved = broadcast.approve(post.pk, gestor)
        assert approved.approved_by == gestor
        assert approved.approved_at is not None

    def test_approval_dispatches_one_directive_per_platform(self, product, rule, gestor):
        post = broadcast.evaluate("production_finished", _context())[0]
        broadcast.approve(post.pk, gestor)
        assert Directive.objects.filter(topic=BROADCAST_POST).count() == 2

    def test_double_click_does_not_double_post(self, product, rule, gestor):
        post = broadcast.evaluate("production_finished", _context())[0]
        broadcast.approve(post.pk, gestor)
        broadcast.approve(post.pk, gestor)
        assert Directive.objects.filter(topic=BROADCAST_POST).count() == 2

    def test_unknown_post_raises(self, gestor):
        with pytest.raises(broadcast.BroadcastError):
            broadcast.approve(9999, gestor)

    def test_expired_post_cannot_be_approved(self, product, rule, gestor):
        """Frescor vencido não vira propaganda: o momento passou."""
        post = broadcast.evaluate("production_finished", _context())[0]
        post.expires_at = timezone.now() - timedelta(minutes=1)
        post.save()
        with pytest.raises(broadcast.BroadcastError):
            broadcast.approve(post.pk, gestor)

    def test_discard_closes_the_post_without_publishing(self, product, rule):
        post = broadcast.evaluate("production_finished", _context())[0]
        assert broadcast.discard(post.pk).status == PostStatus.EXPIRED
        assert Directive.objects.filter(topic=BROADCAST_POST).count() == 0


# ── Expiração ────────────────────────────────────────────────────────


class TestExpiry:
    def test_rule_sets_the_deadline(self, product, rule):
        rule.expires_after_minutes = 30
        rule.save()
        post = broadcast.evaluate("production_finished", _context())[0]
        assert post.expires_at is not None

    def test_zero_means_no_deadline(self, product, rule):
        assert broadcast.evaluate("production_finished", _context())[0].expires_at is None

    def test_sweep_expires_overdue_pending_posts(self, product, rule):
        rule.expires_after_minutes = 30
        rule.save()
        post = broadcast.evaluate("production_finished", _context())[0]
        BroadcastPost.objects.filter(pk=post.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        assert broadcast.expire_stale_posts() == 1
        post.refresh_from_db()
        assert post.status == PostStatus.EXPIRED

    def test_sweep_leaves_fresh_posts_alone(self, product, rule):
        rule.expires_after_minutes = 30
        rule.save()
        broadcast.evaluate("production_finished", _context())
        assert broadcast.expire_stale_posts() == 0


# ── Despacho ─────────────────────────────────────────────────────────


class TestDispatch:
    def test_whatsapp_becomes_a_notify_directive(self, product, template):
        rule = BroadcastRule.objects.create(
            name="Audiência", trigger="production_finished", template=template,
            platforms=["whatsapp"], requires_approval=False,
        )
        broadcast.evaluate("production_finished", _context())
        assert Directive.objects.filter(topic=BROADCAST_NOTIFY).count() == 1
        assert rule.pk  # regra usada

    def test_vip_first_splits_into_two_waves(self, product, template):
        BroadcastRule.objects.create(
            name="VIP primeiro", trigger="production_finished", template=template,
            platforms=["whatsapp"], requires_approval=False,
            audience_rules={"favorites": True, "vip_first_minutes": 15},
        )
        broadcast.evaluate("production_finished", _context())
        waves = sorted(
            d.payload["wave"] for d in Directive.objects.filter(topic=BROADCAST_NOTIFY)
        )
        assert waves == ["general", "vip"]

    def test_the_general_wave_is_delayed(self, product, template):
        BroadcastRule.objects.create(
            name="VIP primeiro", trigger="production_finished", template=template,
            platforms=["whatsapp"], requires_approval=False,
            audience_rules={"vip_first_minutes": 15},
        )
        broadcast.evaluate("production_finished", _context())
        general = Directive.objects.get(topic=BROADCAST_NOTIFY, payload__wave="general")
        vip = Directive.objects.get(topic=BROADCAST_NOTIFY, payload__wave="vip")
        assert general.available_at > vip.available_at

    def test_dedupe_key_is_per_platform(self, product, rule):
        post = broadcast.evaluate("production_finished", _context())[0]
        broadcast.dispatch(post)
        keys = set(Directive.objects.values_list("dedupe_key", flat=True))
        assert keys == {f"broadcast:{post.pk}:instagram", f"broadcast:{post.pk}:google_business"}

    def test_unknown_platform_is_logged_not_dispatched(self, product, template):
        BroadcastRule.objects.create(
            name="Plataforma torta", trigger="production_finished", template=template,
            platforms=["orkut"], requires_approval=False,
        )
        broadcast.evaluate("production_finished", _context())
        assert Directive.objects.count() == 0


# ── Notificação do gestor ────────────────────────────────────────────


class TestNotifyReviewers:
    def test_user_with_permission_is_notified(self, product, rule):
        from django.contrib.auth.models import Permission

        gestor = User.objects.create_user(username="gestor", password="x")
        gestor.user_permissions.add(
            Permission.objects.get(codename="manage_broadcast")
        )
        post = broadcast.evaluate("production_finished", _context())[0]

        notification = UserNotification.objects.get(user=gestor)
        assert notification.is_actionable
        assert notification.action_data["broadcast_post_id"] == post.pk

    def test_user_without_permission_is_not_notified(self, product, rule):
        User.objects.create_user(username="cozinha", password="x")
        broadcast.evaluate("production_finished", _context())
        assert UserNotification.objects.count() == 0

    def test_explicit_notify_users_wins(self, product, rule):
        chosen = User.objects.create_user(username="escolhido", password="x")
        User.objects.create_superuser(username="root", password="x")
        rule.notify_users = [chosen.pk]
        rule.save()

        broadcast.evaluate("production_finished", _context())
        assert list(UserNotification.objects.values_list("user", flat=True)) == [chosen.pk]

    def test_auto_post_rule_notifies_nobody(self, product, rule):
        User.objects.create_superuser(username="root", password="x")
        rule.requires_approval = False
        rule.save()
        broadcast.evaluate("production_finished", _context())
        assert UserNotification.objects.count() == 0

    def test_audience_size_reaches_the_message(self, product, rule):
        User.objects.create_superuser(username="root", password="x")
        with patch.object(
            broadcast.audience_service, "resolve"
        ) as resolve:
            resolve.return_value.summary.return_value = {"total": 43}
            broadcast.evaluate("production_finished", _context())
        assert "43 cliente(s)" in UserNotification.objects.get().message


# ── Agendamento e edição ─────────────────────────────────────────────


class TestScheduledApproval:
    """Aprovar com hora marcada: o gestor decide agora, o post sai depois."""

    def test_future_publish_at_holds_the_dispatch(self, product, rule):
        post = broadcast.evaluate("production_finished", _context())[0]
        approved = broadcast.approve(
            post.pk, _user(), publish_at=timezone.now() + timedelta(hours=2)
        )
        assert approved.status == PostStatus.APPROVED
        assert approved.publish_at is not None
        assert Directive.objects.filter(topic=BROADCAST_POST).count() == 0

    def test_past_publish_at_goes_out_now(self, product, rule):
        post = broadcast.evaluate("production_finished", _context())[0]
        approved = broadcast.approve(
            post.pk, _user(), publish_at=timezone.now() - timedelta(minutes=1)
        )
        assert approved.publish_at is None
        assert Directive.objects.filter(topic=BROADCAST_POST).count() == 2

    def test_sweep_dispatches_when_the_hour_arrives(self, product, rule):
        post = broadcast.evaluate("production_finished", _context())[0]
        broadcast.approve(post.pk, _user(), publish_at=timezone.now() + timedelta(hours=2))

        assert broadcast.dispatch_due() == 0  # ainda não é hora
        BroadcastPost.objects.filter(pk=post.pk).update(
            publish_at=timezone.now() - timedelta(minutes=1)
        )
        assert broadcast.dispatch_due() == 1

        post.refresh_from_db()
        assert post.publish_at is None  # não despacha duas vezes
        assert broadcast.dispatch_due() == 0
        assert Directive.objects.filter(topic=BROADCAST_POST).count() == 2

    def test_rescheduling_a_post_that_has_not_gone_out_is_allowed(self, product, rule):
        post = broadcast.evaluate("production_finished", _context())[0]
        broadcast.approve(post.pk, _user(), publish_at=timezone.now() + timedelta(hours=2))
        later = timezone.now() + timedelta(hours=5)
        assert broadcast.approve(post.pk, _user(), publish_at=later).publish_at == later

    def test_already_dispatched_post_is_not_redispatched(self, product, rule):
        post = broadcast.evaluate("production_finished", _context())[0]
        broadcast.approve(post.pk, _user())
        before = Directive.objects.filter(topic=BROADCAST_POST).count()
        broadcast.approve(post.pk, _user())
        assert Directive.objects.filter(topic=BROADCAST_POST).count() == before


class TestContentEditing:
    def test_editing_the_body_reprojects_the_platform_variants(self, product, template, rule):
        template.platform_variants = {"instagram": {"body": "{{produto}} no forno!"}}
        template.save()
        post = broadcast.evaluate("production_finished", _context())[0]

        edited = broadcast.update_content(post.pk, body="Texto do gestor")
        assert edited.content["body"] == "Texto do gestor"
        # A variação por plataforma acompanha a edição — senão o Instagram
        # publicaria o texto antigo.
        assert edited.platform_content

    def test_hashtags_are_trimmed_and_emptied_out(self, product, rule):
        post = broadcast.evaluate("production_finished", _context())[0]
        edited = broadcast.update_content(post.pk, hashtags=[" pao ", "", "fornada"])
        assert edited.content["hashtags"] == ["pao", "fornada"]

    def test_omitted_keys_are_left_alone(self, product, rule):
        post = broadcast.evaluate("production_finished", _context())[0]
        original = post.content["body"]
        assert broadcast.update_content(post.pk, platforms=["tv"]).content["body"] == original

    def test_published_post_cannot_be_rewritten(self, product, rule):
        post = broadcast.evaluate("production_finished", _context())[0]
        broadcast.approve(post.pk, _user())
        with pytest.raises(broadcast.BroadcastError):
            broadcast.update_content(post.pk, body="tarde demais")


def _user():
    return User.objects.create_user(f"gestor-{User.objects.count()}", is_staff=True)
