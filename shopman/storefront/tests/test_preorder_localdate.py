"""
Regressão de fuso: validação de encomenda usa o dia LOCAL, não o dia UTC.

Cenário congelado: 01:00 UTC de 12/07 = 22:00 BRT de 11/07. Com o bug
(``timezone.now().date()``), "hoje" já era 12/07 e a encomenda para HOJE
(11/07) era rejeitada como "data passada" — à noite, justamente quando o
cliente monta o pedido do dia seguinte.
"""

from datetime import UTC, datetime
from unittest.mock import patch

from shopman.storefront.intents.checkout import _validate_preorder

# 01:00 UTC de 12/07 = 22:00 BRT de 11/07 — o dia local ainda é 11/07.
FROZEN_UTC = datetime(2026, 7, 12, 1, 0, tzinfo=UTC)


def _frozen_clock():
    return patch("django.utils.timezone.now", return_value=FROZEN_UTC)


def _stub_preorder_config():
    return patch(
        "shopman.shop.projections.checkout_context.preorder_config",
        return_value=(30, []),
    )


def test_preorder_for_local_today_not_rejected_as_past():
    """Encomenda para 11/07 às 22h BRT de 11/07 não é "data passada"."""
    with _frozen_clock(), _stub_preorder_config():
        errors = _validate_preorder("2026-07-11")

    assert "delivery_date" not in errors


def test_preorder_for_local_yesterday_still_rejected():
    """Data realmente passada (10/07) segue rejeitada no mesmo instante."""
    with _frozen_clock(), _stub_preorder_config():
        errors = _validate_preorder("2026-07-10")

    assert errors["delivery_date"] == "Não é possível encomendar para uma data passada."


def test_preorder_max_window_counts_from_local_today():
    """A janela máxima conta a partir do dia local (11/07 + 30d = 10/08)."""
    with _frozen_clock(), _stub_preorder_config():
        ok = _validate_preorder("2026-08-10")
        too_far = _validate_preorder("2026-08-11")

    assert "delivery_date" not in ok
    assert "delivery_date" in too_far
