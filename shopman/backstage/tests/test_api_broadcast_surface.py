"""Contrato da superfície Broadcast (surfaces/broadcast-nuxt).

O que este arquivo protege, em ordem de importância:

1. **O gate.** ``shop.manage_broadcast`` é o portão. Staff comum não publica —
   quem cuida da fila de pedidos não decide o que a padaria diz ao mundo.
2. **Post que já saiu não se reescreve.** Editar o corpo depois de publicado
   seria mentira retroativa sobre o que o cliente leu.
3. **As chaves que o Nuxt lê.** Se a projection mudar de forma, o app quebra em
   silêncio; aqui quebra em vermelho.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.utils import timezone

from shopman.shop.models import BroadcastPost, BroadcastRule, PostStatus, PostTemplate

pytestmark = pytest.mark.django_db

User = get_user_model()

BOARD_URL = "/api/v1/backstage/broadcast/"
RULES_URL = "/api/v1/backstage/broadcast/rules/"
TEMPLATES_URL = "/api/v1/backstage/broadcast/templates/"
OPTIONS_URL = "/api/v1/backstage/broadcast/options/"
HISTORY_URL = "/api/v1/backstage/broadcast/history/"


@pytest.fixture
def gestor():
    user = User.objects.create_user(username="marketing", password="x", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_broadcast"))
    return user


@pytest.fixture
def template():
    return PostTemplate.objects.create(name="Fornada", body="{{produto}} saiu do forno!")


@pytest.fixture
def rule(template):
    return BroadcastRule.objects.create(
        name="Fornada de pães",
        trigger="production_finished",
        template=template,
        platforms=["instagram", "google_business"],
        audience_rules={"favorites": True},
    )


def _post(rule, template, *, status=PostStatus.PENDING_REVIEW, **kwargs) -> BroadcastPost:
    defaults = {
        "content": {"body": "Croissant saiu do forno", "hashtags": ["padaria"], "link": "/p/cro"},
        "platforms": ["instagram", "google_business"],
        "audience": {"favorites": 12, "alerts": 3, "total": 15},
        "trigger_context": {"sku": "CRO-001"},
    }
    return BroadcastPost.objects.create(
        rule=rule, template=template, status=status, **{**defaults, **kwargs}
    )


# ── Gate ─────────────────────────────────────────────────────────────


class TestGate:
    def test_anonymous_is_rejected(self, client):
        assert client.get(BOARD_URL).status_code in (401, 403)

    def test_staff_without_permission_is_rejected(self, client):
        User.objects.create_user(username="caixa", password="x", is_staff=True)
        client.login(username="caixa", password="x")
        assert client.get(BOARD_URL).status_code == 403

    def test_manager_with_permission_gets_the_board(self, client, gestor):
        client.force_login(gestor)
        assert client.get(BOARD_URL).status_code == 200

    def test_staff_without_permission_cannot_approve(self, client, rule, template):
        post = _post(rule, template)
        User.objects.create_user(username="caixa", password="x", is_staff=True)
        client.login(username="caixa", password="x")
        response = client.post(f"/api/v1/backstage/broadcast/posts/{post.pk}/approve/")
        assert response.status_code == 403
        post.refresh_from_db()
        assert post.status == PostStatus.PENDING_REVIEW


# ── Painel ───────────────────────────────────────────────────────────


class TestBoard:
    def test_pending_post_carries_the_keys_the_surface_reads(self, client, gestor, rule, template):
        _post(rule, template)
        client.force_login(gestor)

        board = client.get(BOARD_URL).json()["board"]

        assert board["stats"]["pending_count"] == 1
        card = board["pending"][0]
        assert card["body"] == "Croissant saiu do forno"
        assert card["audience_total"] == 15
        assert card["rule_name"] == "Fornada de pães"
        assert card["sku"] == "CRO-001"
        assert [r["platform"] for r in card["platform_results"]] == [
            "instagram",
            "google_business",
        ]

    def test_expired_pending_post_leaves_the_board(self, client, gestor, rule, template):
        """Post vencido não pede decisão: propaganda velha destrói confiança."""
        _post(rule, template, expires_at=timezone.now() - timezone.timedelta(minutes=1))
        client.force_login(gestor)

        board = client.get(BOARD_URL).json()["board"]
        assert board["pending"] == []
        assert board["stats"]["pending_count"] == 0

    def test_history_lists_what_went_out(self, client, gestor, rule, template):
        _post(rule, template, status=PostStatus.PUBLISHED, published_at=timezone.now())
        _post(rule, template)  # pendente não é histórico
        client.force_login(gestor)

        posts = client.get(HISTORY_URL).json()["posts"]
        assert len(posts) == 1
        assert posts[0]["status"] == PostStatus.PUBLISHED


# ── Decisão sobre o post ─────────────────────────────────────────────


class TestPostDecision:
    def test_approve_dispatches_the_post(self, client, gestor, rule, template):
        post = _post(rule, template)
        client.force_login(gestor)

        response = client.post(f"/api/v1/backstage/broadcast/posts/{post.pk}/approve/")

        assert response.status_code == 200
        post.refresh_from_db()
        assert post.status in (PostStatus.APPROVED, PostStatus.PUBLISHING, PostStatus.PUBLISHED)
        assert post.approved_by_id == gestor.pk

    def test_discard_keeps_it_off_the_air(self, client, gestor, rule, template):
        post = _post(rule, template)
        client.force_login(gestor)

        assert client.post(f"/api/v1/backstage/broadcast/posts/{post.pk}/discard/").status_code == 200
        post.refresh_from_db()
        assert post.status == PostStatus.EXPIRED

    def test_edit_before_approving(self, client, gestor, rule, template):
        post = _post(rule, template)
        client.force_login(gestor)

        response = client.patch(
            f"/api/v1/backstage/broadcast/posts/{post.pk}/",
            data={"body": "Fornada quentinha agora", "hashtags": ["#paes", "artesanal"]},
            content_type="application/json",
        )

        assert response.status_code == 200
        post.refresh_from_db()
        assert post.content["body"] == "Fornada quentinha agora"
        # O "#" é do texto, não do dado: guardar a tag limpa evita "##paes".
        assert post.content["hashtags"] == ["paes", "artesanal"]

    def test_published_post_cannot_be_rewritten(self, client, gestor, rule, template):
        post = _post(rule, template, status=PostStatus.PUBLISHED)
        client.force_login(gestor)

        response = client.patch(
            f"/api/v1/backstage/broadcast/posts/{post.pk}/",
            data={"body": "outra coisa"},
            content_type="application/json",
        )

        assert response.status_code == 400
        post.refresh_from_db()
        assert post.content["body"] == "Croissant saiu do forno"

    def test_empty_body_is_refused(self, client, gestor, rule, template):
        post = _post(rule, template)
        client.force_login(gestor)

        response = client.patch(
            f"/api/v1/backstage/broadcast/posts/{post.pk}/",
            data={"body": "   "},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json()["field"] == "body"


# ── Regras ───────────────────────────────────────────────────────────


class TestRules:
    def test_create_rule(self, client, gestor, template):
        client.force_login(gestor)

        response = client.post(
            RULES_URL,
            data={
                "name": "Estoque baixo → Google",
                "trigger": "low_stock",
                "template_id": template.pk,
                "platforms": ["google_business"],
                "expires_after_minutes": 240,
            },
            content_type="application/json",
        )

        assert response.status_code == 201
        rule = BroadcastRule.objects.get(name="Estoque baixo → Google")
        assert rule.trigger == "low_stock"
        assert rule.expires_after_minutes == 240

    def test_unknown_trigger_is_refused(self, client, gestor, template):
        client.force_login(gestor)

        response = client.post(
            RULES_URL,
            data={
                "name": "X", "trigger": "fornada_magica",
                "template_id": template.pk, "platforms": ["instagram"],
            },
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json()["field"] == "trigger"

    def test_unknown_platform_is_refused(self, client, gestor, template):
        client.force_login(gestor)

        response = client.post(
            RULES_URL,
            data={
                "name": "X", "trigger": "low_stock",
                "template_id": template.pk, "platforms": ["tiktok"],
            },
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json()["field"] == "platforms"

    def test_rule_without_platform_is_refused(self, client, gestor, template):
        """Regra sem destino dispara no vazio — melhor recusar na criação."""
        client.force_login(gestor)

        response = client.post(
            RULES_URL,
            data={"name": "X", "trigger": "low_stock", "template_id": template.pk, "platforms": []},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json()["field"] == "platforms"

    def test_toggle_rule_off(self, client, gestor, rule):
        client.force_login(gestor)

        response = client.patch(
            f"{RULES_URL}{rule.pk}/",
            data={"is_active": False},
            content_type="application/json",
        )

        assert response.status_code == 200
        rule.refresh_from_db()
        assert rule.is_active is False


# ── Modelos de post ──────────────────────────────────────────────────


class TestTemplates:
    def test_create_template(self, client, gestor):
        client.force_login(gestor)

        response = client.post(
            TEMPLATES_URL,
            data={"name": "Simples", "body": "{{produto}} por {{preco}}"},
            content_type="application/json",
        )

        assert response.status_code == 201
        assert PostTemplate.objects.filter(name="Simples").exists()

    def test_template_in_use_cannot_be_deleted(self, client, gestor, rule, template):
        """PROTECT no model: apagar deixaria a regra disparando no vazio."""
        client.force_login(gestor)

        response = client.delete(f"{TEMPLATES_URL}{template.pk}/")

        assert response.status_code == 400
        assert PostTemplate.objects.filter(pk=template.pk).exists()

    def test_unused_template_can_be_deleted(self, client, gestor):
        template = PostTemplate.objects.create(name="Órfão", body="x")
        client.force_login(gestor)

        assert client.delete(f"{TEMPLATES_URL}{template.pk}/").status_code == 200
        assert not PostTemplate.objects.filter(pk=template.pk).exists()


# ── Opções do formulário ─────────────────────────────────────────────


class TestOptions:
    def test_options_feed_the_rule_form(self, client, gestor, template):
        client.force_login(gestor)

        options = client.get(OPTIONS_URL).json()["options"]

        assert {t["value"] for t in options["triggers"]} >= {"production_finished", "low_stock"}
        assert {p["value"] for p in options["platforms"]} >= {"instagram", "google_business"}
        assert template.pk in {t["pk"] for t in options["templates"]}
        assert "produto" in options["variables"]


class TestScheduledPublishing:
    """"Agendar" no card: a decisão é agora, a publicação é na hora marcada."""

    def test_future_publish_at_schedules_instead_of_dispatching(
        self, client, gestor, rule, template
    ):
        post = _post(rule, template)
        client.force_login(gestor)
        when = timezone.now() + timedelta(hours=3)

        response = client.post(
            f"/api/v1/backstage/broadcast/posts/{post.pk}/approve/",
            data={"publish_at": when.isoformat()},
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.json()["scheduled"] is True
        post.refresh_from_db()
        assert post.status == PostStatus.APPROVED
        assert post.publish_at is not None

    def test_approve_applies_the_card_edits_in_the_same_request(
        self, client, gestor, rule, template
    ):
        post = _post(rule, template)
        client.force_login(gestor)

        response = client.post(
            f"/api/v1/backstage/broadcast/posts/{post.pk}/approve/",
            data={"body": "Texto revisado pelo gestor", "platforms": ["instagram"]},
            content_type="application/json",
        )

        assert response.status_code == 200
        post.refresh_from_db()
        assert post.content["body"] == "Texto revisado pelo gestor"
        assert post.platforms == ["instagram"]

    def test_garbage_date_is_refused_before_anything_is_published(
        self, client, gestor, rule, template
    ):
        post = _post(rule, template)
        client.force_login(gestor)

        response = client.post(
            f"/api/v1/backstage/broadcast/posts/{post.pk}/approve/",
            data={"publish_at": "amanhã cedo"},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json()["field"] == "publish_at"
        post.refresh_from_db()
        assert post.status == PostStatus.PENDING_REVIEW

    def test_empty_body_is_refused(self, client, gestor, rule, template):
        post = _post(rule, template)
        client.force_login(gestor)

        response = client.post(
            f"/api/v1/backstage/broadcast/posts/{post.pk}/approve/",
            data={"body": "   "},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json()["field"] == "body"


class TestPlatformResultDetail:
    """O painel precisa do PORQUÊ, e o handler não grava numa chave só."""

    def _results(self, client, gestor, rule, template, results):
        post = _post(rule, template, status=PostStatus.PUBLISHED, platform_results=results)
        client.force_login(gestor)
        response = client.get(HISTORY_URL)
        assert response.status_code == 200
        found = next(p for p in response.json()["posts"] if p["pk"] == post.pk)
        return {r["platform"]: r for r in found["platform_results"]}

    def test_failure_reason_reaches_the_screen(self, client, gestor, rule, template):
        # O handler grava ``error`` na falha — ler só ``detail`` deixaria um
        # "falhou" mudo no histórico.
        results = self._results(
            client, gestor, rule, template,
            {"instagram": {"status": "failed", "error": "token expirado"}},
        )
        assert results["instagram"]["detail"] == "token expirado"

    def test_manual_pending_explains_itself(self, client, gestor, rule, template):
        results = self._results(
            client, gestor, rule, template,
            {"instagram": {"status": "pending_manual", "reason": "sem adapter configurado"}},
        )
        assert results["instagram"]["status"] == "pending_manual"
        assert results["instagram"]["detail"] == "sem adapter configurado"

    def test_whatsapp_reports_how_many_actually_went_out(self, client, gestor, rule, template):
        post = _post(
            rule, template, status=PostStatus.PUBLISHED, platforms=["whatsapp"],
            platform_results={"whatsapp": {"status": "sent", "sent": 38, "failed": 2}},
        )
        client.force_login(gestor)
        found = next(
            p for p in client.get(HISTORY_URL).json()["posts"] if p["pk"] == post.pk
        )
        assert found["platform_results"][0]["detail"] == "38 enviados, 2 falharam"

    def test_a_clean_whatsapp_wave_does_not_invent_a_failure_count(
        self, client, gestor, rule, template
    ):
        post = _post(
            rule, template, status=PostStatus.PUBLISHED, platforms=["whatsapp"],
            platform_results={"whatsapp": {"status": "sent", "sent": 40, "failed": 0}},
        )
        client.force_login(gestor)
        found = next(
            p for p in client.get(HISTORY_URL).json()["posts"] if p["pk"] == post.pk
        )
        assert found["platform_results"][0]["detail"] == "40 enviados"

    def test_targeted_platform_with_no_answer_yet_stays_visible(
        self, client, gestor, rule, template
    ):
        # Silêncio no painel esconderia justamente o caso que precisa de ação.
        results = self._results(client, gestor, rule, template, {})
        assert results["instagram"]["status"] == "queued"
