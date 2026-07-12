"""Dedupe como garantia: UNIQUE parcial em (topic, dedupe_key) para directives vivas.

O check-then-create dos criadores era só convenção — sob corrida nasciam
duplicatas. A constraint ``orderman_directive_live_dedupe_unique`` garante no
máximo UMA directive viva (queued/running) por (topic, dedupe_key), e mantém
deliberadamente fora da condição:

* ``done``   — re-fire após conclusão continua permitido (ex.: reprojeção);
* ``failed`` — re-enfileirar após falha terminal continua permitido;
* ``dedupe_key=""`` — directives sem dedupe não participam.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction
from shopman.orderman.models import Directive

pytestmark = pytest.mark.django_db

TOPIC = "notification.send"
KEY = "notification.send:ORD-1:order_confirmed"


def _directive(status="queued", topic=TOPIC, dedupe_key=KEY):
    return Directive.objects.create(topic=topic, status=status, payload={}, dedupe_key=dedupe_key)


def test_second_live_directive_with_same_key_violates():
    _directive(status="queued")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _directive(status="queued")


def test_running_also_counts_as_live():
    _directive(status="running")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _directive(status="queued")


def test_done_does_not_block_new_directive():
    _directive(status="done")
    _directive(status="queued")  # re-fire após conclusão é permitido
    assert Directive.objects.filter(dedupe_key=KEY).count() == 2


def test_failed_does_not_block_new_directive():
    _directive(status="failed")
    _directive(status="queued")  # re-enfileirar após falha terminal é permitido
    assert Directive.objects.filter(dedupe_key=KEY).count() == 2


def test_empty_dedupe_key_is_not_constrained():
    _directive(dedupe_key="")
    _directive(dedupe_key="")
    assert Directive.objects.filter(topic=TOPIC, dedupe_key="").count() == 2


def test_same_key_different_topic_is_allowed():
    _directive(topic="notification.send")
    _directive(topic="payment.timeout")
    assert Directive.objects.filter(dedupe_key=KEY).count() == 2


def test_requeue_of_the_same_row_does_not_violate():
    # running → queued (deferral/reaper) é UPDATE da mesma linha: nunca viola.
    d = _directive(status="running")
    d.status = "queued"
    d.save(update_fields=["status", "updated_at"])
    d.refresh_from_db()
    assert d.status == "queued"
