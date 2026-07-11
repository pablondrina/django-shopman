"""
Regressão de fuso: ``is_preorder`` compara a data de entrega com o dia LOCAL.

Cenário congelado: 01:00 UTC de 12/07 = 22:00 BRT de 11/07. Com o bug
(``timezone.now().date()``), "hoje" já era 12/07 três horas antes da virada:
uma encomenda para amanhã (12/07) deixava de ser preorder e caía no fluxo de
mesmo dia, exatamente na janela noturna em que os clientes encomendam.
"""

from __future__ import annotations

import types
from datetime import UTC, datetime
from unittest.mock import patch

from django.test import TestCase
from shopman.orderman.ids import generate_idempotency_key
from shopman.orderman.models import Order, Session
from shopman.orderman.services import CommitService

# 01:00 UTC de 12/07 = 22:00 BRT de 11/07 — o dia local ainda é 11/07.
FROZEN_UTC = datetime(2026, 7, 12, 1, 0, tzinfo=UTC)


class PreorderLocaldateBoundaryTests(TestCase):
    """Commit às 22h BRT: o dia de referência é o local, não o UTC."""

    def setUp(self) -> None:
        super().setUp()
        self.channel = types.SimpleNamespace(ref="pdv", name="PDV", is_active=True)

    def _create_session(self, *, delivery_date: str) -> Session:
        return Session.objects.create(
            session_key=f"S-{generate_idempotency_key()[:8]}",
            channel_ref=self.channel.ref,
            state="open",
            pricing_policy="internal",
            edit_policy="open",
            rev=0,
            items=[
                {"line_id": "L1", "sku": "pao-queijo", "name": "Pao de Queijo", "qty": 50, "unit_price_q": 150, "meta": {}},
            ],
            data={"checks": {}, "issues": [], "delivery_date": delivery_date},
        )

    def _commit(self, session: Session) -> Order:
        result = CommitService.commit(
            session_key=session.session_key,
            channel_ref=self.channel.ref,
            idempotency_key=generate_idempotency_key(),
        )
        return Order.objects.get(ref=result.order_ref)

    def test_delivery_local_tomorrow_is_preorder_at_night(self) -> None:
        """Entrega em 12/07 às 22h BRT de 11/07 É preorder (amanhã local)."""
        session = self._create_session(delivery_date="2026-07-12")

        with patch("django.utils.timezone.now", return_value=FROZEN_UTC):
            order = self._commit(session)

        self.assertTrue(order.data.get("is_preorder"))

    def test_delivery_local_today_is_not_preorder_at_night(self) -> None:
        """Entrega em 11/07 às 22h BRT de 11/07 NÃO é preorder (hoje local)."""
        session = self._create_session(delivery_date="2026-07-11")

        with patch("django.utils.timezone.now", return_value=FROZEN_UTC):
            order = self._commit(session)

        self.assertFalse(order.data.get("is_preorder"))
