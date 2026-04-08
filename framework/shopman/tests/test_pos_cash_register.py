"""Tests for WP-R16 — POS Gestão de Caixa."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase


def _make_shop():
    from shopman.models import Shop
    return Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})[0]


def _make_channel():
    from shopman.omniman.models import Channel
    return Channel.objects.get_or_create(
        ref="balcao",
        defaults={"name": "Balcão", "pricing_policy": "fixed", "edit_policy": "open", "config": {}, "is_active": True},
    )[0]


class CashRegisterSessionModelTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        User = get_user_model()
        self.operator = User.objects.create_user(username="cashier", password="x", is_staff=True)

    def test_open_session_created(self) -> None:
        from shopman.models import CashRegisterSession
        session = CashRegisterSession.objects.create(operator=self.operator, opening_amount_q=5000)
        self.assertEqual(session.status, "open")
        self.assertEqual(session.opening_amount_q, 5000)

    def test_get_open_for_operator(self) -> None:
        from shopman.models import CashRegisterSession
        CashRegisterSession.objects.create(operator=self.operator, opening_amount_q=0)
        found = CashRegisterSession.get_open_for_operator(self.operator)
        self.assertIsNotNone(found)

    def test_no_open_session_returns_none(self) -> None:
        from shopman.models import CashRegisterSession
        found = CashRegisterSession.get_open_for_operator(self.operator)
        self.assertIsNone(found)

    def test_close_session(self) -> None:
        from shopman.models import CashRegisterSession
        session = CashRegisterSession.objects.create(operator=self.operator, opening_amount_q=10000)
        session.close(closing_amount_q=10000)
        self.assertEqual(session.status, "closed")
        self.assertIsNotNone(session.closed_at)
        self.assertIsNotNone(session.expected_amount_q)
        self.assertEqual(session.difference_q, 0)

    def test_close_with_difference(self) -> None:
        from shopman.models import CashRegisterSession
        session = CashRegisterSession.objects.create(operator=self.operator, opening_amount_q=10000)
        # Close with 200 less than expected (only opening, no sales)
        session.close(closing_amount_q=9800)
        self.assertEqual(session.difference_q, -200)

    def test_sangria_movement_created(self) -> None:
        from shopman.models import CashMovement, CashRegisterSession
        session = CashRegisterSession.objects.create(operator=self.operator, opening_amount_q=5000)
        CashMovement.objects.create(
            session=session, movement_type="sangria", amount_q=2000, reason="retirada"
        )
        self.assertEqual(session.movements.count(), 1)


class CashRegisterViewTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        _make_shop()
        _make_channel()
        User = get_user_model()
        self.staff = User.objects.create_user(username="cash_view_staff", password="x", is_staff=True)
        self.client.force_login(self.staff)

    def test_pos_without_open_register_shows_cash_open_page(self) -> None:
        """POS redirects to 'Abrir Caixa' if no open session."""
        resp = self.client.get("/gestao/pos/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Abrir Caixa")
        self.assertTemplateUsed(resp, "pos/cash_open.html")

    def test_open_cash_register(self) -> None:
        """POST /caixa/abrir/ creates a session and redirects to POS."""
        resp = self.client.post("/gestao/pos/caixa/abrir/", {"opening_amount": "50.00"})
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, "/gestao/pos/")

        from shopman.models import CashRegisterSession
        session = CashRegisterSession.get_open_for_operator(self.staff)
        self.assertIsNotNone(session)
        self.assertEqual(session.opening_amount_q, 5000)

    def test_pos_with_open_register_shows_grid(self) -> None:
        """POS shows product grid when a register is open."""
        from shopman.models import CashRegisterSession
        CashRegisterSession.objects.create(operator=self.staff, opening_amount_q=0)
        resp = self.client.get("/gestao/pos/")
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "pos/index.html")

    def test_open_second_register_redirects(self) -> None:
        """Opening a register when one is already open redirects to POS."""
        from shopman.models import CashRegisterSession
        CashRegisterSession.objects.create(operator=self.staff, opening_amount_q=0)
        resp = self.client.post("/gestao/pos/caixa/abrir/", {"opening_amount": "0"})
        self.assertRedirects(resp, "/gestao/pos/")

    def test_sangria_without_open_register(self) -> None:
        """Sangria with no open register returns 422."""
        resp = self.client.post("/gestao/pos/caixa/sangria/", {"movement_type": "sangria", "amount": "50"})
        self.assertEqual(resp.status_code, 422)

    def test_sangria_with_open_register(self) -> None:
        """Sangria creates a CashMovement."""
        from shopman.models import CashMovement, CashRegisterSession
        session = CashRegisterSession.objects.create(operator=self.staff, opening_amount_q=10000)
        resp = self.client.post("/gestao/pos/caixa/sangria/", {
            "movement_type": "sangria", "amount": "20.00", "reason": "retirada",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(CashMovement.objects.filter(session=session).count(), 1)

    def test_close_register(self) -> None:
        """Closing register renders report template."""
        from shopman.models import CashRegisterSession
        CashRegisterSession.objects.create(operator=self.staff, opening_amount_q=5000)
        resp = self.client.post("/gestao/pos/caixa/fechar/", {
            "closing_amount": "50.00", "notes": "turno tranquilo",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "pos/cash_close_report.html")
        self.assertContains(resp, "Caixa Fechado")
