"""API de notificações pessoais — isolamento por usuário e ação acionável.

O teste que importa mais aqui é o de isolamento: a caixa é da pessoa, e nem
staff nem superusuário leem (ou agem sobre) a notificação alheia.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from shopman.shop.models import (
    BroadcastPost,
    BroadcastRule,
    PostStatus,
    PostTemplate,
    UserNotification,
)

pytestmark = pytest.mark.django_db

User = get_user_model()

LIST_URL = "/api/v1/backstage/notifications/"


@pytest.fixture
def gestor():
    user = User.objects.create_user(username="gestor", password="x", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_broadcast"))
    return user


@pytest.fixture
def colega():
    return User.objects.create_user(username="colega", password="x", is_staff=True)


def _post() -> BroadcastPost:
    template = PostTemplate.objects.create(name="T", body="{{produto}}")
    rule = BroadcastRule.objects.create(
        name="Fornada", trigger="production_finished",
        template=template, platforms=["instagram"],
    )
    return BroadcastPost.objects.create(
        rule=rule, template=template, status=PostStatus.PENDING_REVIEW,
        content={"body": "Saiu do forno"}, platforms=["instagram"],
    )


def _notification(user, *, post=None, actionable=True) -> UserNotification:
    return UserNotification.objects.create(
        user=user,
        category="broadcast",
        title="Post pronto para revisão",
        message="Croissant saiu do forno",
        action_data={"broadcast_post_id": post.pk} if post else {},
        is_actionable=actionable,
    )


# ── Listagem ─────────────────────────────────────────────────────────


class TestList:
    def test_anonymous_is_rejected(self, client):
        assert client.get(LIST_URL).status_code in (401, 403)

    def test_own_unread_notifications_are_listed(self, client, gestor):
        _notification(gestor)
        client.force_login(gestor)

        body = client.get(LIST_URL).json()
        assert len(body["notifications"]) == 1
        assert body["unread_count"] == 1
        assert body["actionable_count"] == 1

    def test_another_users_box_is_invisible(self, client, gestor, colega):
        """A caixa é da pessoa: nem staff lê a alheia."""
        _notification(colega)
        client.force_login(gestor)

        body = client.get(LIST_URL).json()
        assert body["notifications"] == []
        assert body["unread_count"] == 0

    def test_read_ones_are_hidden_by_default(self, client, gestor):
        notification = _notification(gestor)
        notification.mark_read()
        client.force_login(gestor)

        assert client.get(LIST_URL).json()["notifications"] == []

    def test_all_flag_includes_the_read_ones(self, client, gestor):
        _notification(gestor).mark_read()
        client.force_login(gestor)

        assert len(client.get(f"{LIST_URL}?all=1").json()["notifications"]) == 1

    def test_limit_is_capped(self, client, gestor):
        for _ in range(5):
            _notification(gestor)
        client.force_login(gestor)

        assert len(client.get(f"{LIST_URL}?limit=2").json()["notifications"]) == 2


# ── Marcar como lida ─────────────────────────────────────────────────


class TestRead:
    def test_marking_read_drops_the_unread_count(self, client, gestor):
        notification = _notification(gestor)
        client.force_login(gestor)

        body = client.post(f"{LIST_URL}{notification.pk}/read/").json()
        assert body["unread_count"] == 0

    def test_rereading_keeps_the_first_timestamp(self, client, gestor):
        notification = _notification(gestor)
        client.force_login(gestor)

        client.post(f"{LIST_URL}{notification.pk}/read/")
        notification.refresh_from_db()
        first = notification.read_at

        client.post(f"{LIST_URL}{notification.pk}/read/")
        notification.refresh_from_db()
        assert notification.read_at == first

    def test_cannot_read_someone_elses(self, client, gestor, colega):
        notification = _notification(colega)
        client.force_login(gestor)

        assert client.post(f"{LIST_URL}{notification.pk}/read/").status_code == 404


# ── Ação ─────────────────────────────────────────────────────────────


class TestAction:
    def test_approving_publishes_the_post(self, client, gestor):
        post = _post()
        notification = _notification(gestor, post=post)
        client.force_login(gestor)

        response = client.post(
            f"{LIST_URL}{notification.pk}/action/", {"action": "approve"}
        )
        assert response.status_code == 200
        post.refresh_from_db()
        assert post.approved_by == gestor

    def test_approve_is_the_default_action(self, client, gestor):
        post = _post()
        notification = _notification(gestor, post=post)
        client.force_login(gestor)

        client.post(f"{LIST_URL}{notification.pk}/action/")
        post.refresh_from_db()
        assert post.approved_at is not None

    def test_acting_marks_the_notification_read(self, client, gestor):
        notification = _notification(gestor, post=_post())
        client.force_login(gestor)

        client.post(f"{LIST_URL}{notification.pk}/action/")
        notification.refresh_from_db()
        assert notification.is_read

    def test_discard_closes_without_publishing(self, client, gestor):
        post = _post()
        notification = _notification(gestor, post=post)
        client.force_login(gestor)

        client.post(f"{LIST_URL}{notification.pk}/action/", {"action": "discard"})
        post.refresh_from_db()
        assert post.status == PostStatus.EXPIRED

    def test_operator_without_the_permission_cannot_publish(self, client, colega):
        """Staff não basta: publicar exige shop.manage_broadcast."""
        notification = _notification(colega, post=_post())
        client.force_login(colega)

        assert client.post(f"{LIST_URL}{notification.pk}/action/").status_code == 403

    def test_unknown_action_is_rejected(self, client, gestor):
        notification = _notification(gestor, post=_post())
        client.force_login(gestor)

        response = client.post(
            f"{LIST_URL}{notification.pk}/action/", {"action": "incendiar"}
        )
        assert response.status_code == 400
        assert response.json()["field"] == "action"

    def test_a_non_actionable_notification_has_no_action(self, client, gestor):
        notification = _notification(gestor, actionable=False)
        client.force_login(gestor)

        assert client.post(f"{LIST_URL}{notification.pk}/action/").status_code == 400

    def test_cannot_act_on_someone_elses(self, client, gestor, colega):
        notification = _notification(colega, post=_post())
        client.force_login(gestor)

        assert client.post(f"{LIST_URL}{notification.pk}/action/").status_code == 404

    def test_expired_post_answers_clearly_and_clears_the_card(self, client, gestor):
        from django.utils import timezone

        post = _post()
        post.expires_at = timezone.now() - timezone.timedelta(minutes=1)
        post.save()
        notification = _notification(gestor, post=post)
        client.force_login(gestor)

        assert client.post(f"{LIST_URL}{notification.pk}/action/").status_code == 400
        notification.refresh_from_db()
        assert notification.is_read


# ── Stream pessoal ───────────────────────────────────────────────────


class TestUserStream:
    def test_anonymous_gets_404_not_a_reconnect_loop(self, client):
        assert client.get("/gestor/events/me/").status_code == 404

    def test_channel_manager_only_lets_the_owner_read(self, gestor, colega):
        from shopman.shop.eventstream import ShopmanChannelManager

        manager = ShopmanChannelManager()
        assert manager.can_read_channel(gestor, f"user-{gestor.pk}")
        assert not manager.can_read_channel(colega, f"user-{gestor.pk}")

    def test_superuser_does_not_get_a_master_key(self, gestor):
        from shopman.shop.eventstream import ShopmanChannelManager

        root = User.objects.create_superuser(username="root", password="x")
        assert not ShopmanChannelManager().can_read_channel(root, f"user-{gestor.pk}")
