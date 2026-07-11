"""Dedupe de directives como garantia no orquestrador.

``create_deduped`` é o único caminho de criação com dedupe_key: o UNIQUE
parcial do Core (``orderman_directive_live_dedupe_unique``) fecha a corrida do
check-then-create e a violação vira dedupe-hit (``None``), nunca exceção.
O teste de corrida real (threads) requer PostgreSQL, como os demais testes de
concorrência da suíte.
"""

from __future__ import annotations

import threading
from unittest.mock import patch

import pytest
from django.conf import settings
from django.db import connection, transaction
from django.test import TransactionTestCase
from shopman.orderman.models import Directive, Order

from shopman.shop.directives import NOTIFICATION_SEND, create_deduped
from shopman.shop.services import notification as notification_svc

pytestmark = pytest.mark.django_db

requires_postgres = pytest.mark.skipif(
    "sqlite" in settings.DATABASES["default"]["ENGINE"],
    reason="Requires PostgreSQL for real concurrency testing",
)

KEY = "notification.send:ORD-DD-1:order_confirmed"


def test_create_deduped_creates_when_no_live_duplicate():
    created = create_deduped(NOTIFICATION_SEND, payload={"order_ref": "ORD-DD-1"}, dedupe_key=KEY)
    assert created is not None
    assert Directive.objects.filter(topic=NOTIFICATION_SEND, dedupe_key=KEY).count() == 1


def test_create_deduped_returns_none_on_live_duplicate():
    create_deduped(NOTIFICATION_SEND, payload={}, dedupe_key=KEY)
    duplicate = create_deduped(NOTIFICATION_SEND, payload={}, dedupe_key=KEY)
    assert duplicate is None
    assert Directive.objects.filter(dedupe_key=KEY).count() == 1


def test_create_deduped_does_not_poison_outer_transaction():
    create_deduped(NOTIFICATION_SEND, payload={}, dedupe_key=KEY)
    with transaction.atomic():
        assert create_deduped(NOTIFICATION_SEND, payload={}, dedupe_key=KEY) is None
        # A transação externa continua utilizável após o IntegrityError interno.
        Order.objects.create(ref="ORD-DD-TX", channel_ref="web", total_q=100)
    assert Order.objects.filter(ref="ORD-DD-TX").exists()


def test_notification_send_treats_race_as_dedupe_hit():
    """Simula a corrida: o pré-check não vê a duplicata, o INSERT vê."""
    order = Order.objects.create(ref="ORD-DD-RACE", channel_ref="web", total_q=100, data={})
    dedupe_key = f"notification.send:{order.ref}:order_confirmed"
    Directive.objects.create(
        topic=NOTIFICATION_SEND, payload={}, dedupe_key=dedupe_key, status="queued"
    )

    fake_qs = Directive.objects.none()
    with patch.object(Directive.objects, "filter", return_value=fake_qs):
        notification_svc.send(order, "order_confirmed")  # não pode levantar

    assert Directive.objects.filter(dedupe_key=dedupe_key).count() == 1


@requires_postgres
class TestConcurrentNotificationSend(TransactionTestCase):
    """Duas threads enfileiram a mesma notificação: exatamente UMA directive."""

    def test_concurrent_send_creates_single_directive(self):
        order = Order.objects.create(
            ref="ORD-DD-CONC", channel_ref="web", total_q=100, data={}
        )
        barrier = threading.Barrier(2)
        errors = []

        def worker():
            try:
                barrier.wait(timeout=5)
                # O dispatch pós-commit não interessa aqui — só a criação.
                with patch("shopman.orderman.dispatch._on_commit_callback"):
                    notification_svc.send(order, "order_confirmed")
            except Exception as exc:  # noqa: BLE001 — colecionar para assert
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == []
        dedupe_key = f"notification.send:{order.ref}:order_confirmed"
        assert Directive.objects.filter(dedupe_key=dedupe_key).count() == 1
