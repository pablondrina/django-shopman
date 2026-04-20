"""
Tests for HP2-01 fixes:
  1. Session.channel_ref is CharField, not FK — admin was incorrectly using
     session.channel.ref which raises AttributeError. Fixed to session.channel_ref.
  2. OrderViewSet lacked lookup_field = "ref", defaulting to PK.
     GET /api/orders/{ref}/ now resolves by ref as documented.
"""

from __future__ import annotations

from django.db import models as django_models
from django.test import TestCase
from rest_framework.test import APIClient
from shopman.orderman.ids import generate_idempotency_key
from shopman.orderman.models import Order, Session
from shopman.orderman.services import CommitService


def _create_committed_session(channel_ref: str = "pos") -> tuple[Session, Order]:
    """Create an open session with one item and commit it; return (session, order)."""
    from shopman.orderman.ids import generate_session_key

    session_key = generate_session_key()
    session = Session.objects.create(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
        pricing_policy="internal",
        edit_policy="open",
        rev=0,
        items=[{"line_id": "L-1", "sku": "CROISSANT", "qty": 2, "unit_price_q": 750, "meta": {}}],
        data={"checks": {}, "issues": []},
    )
    result = CommitService.commit(
        session_key=session_key,
        channel_ref=channel_ref,
        idempotency_key=generate_idempotency_key(),
        ctx={"actor": "test"},
    )
    order = Order.objects.get(ref=result["order_ref"])
    return session, order


class SessionChannelRefFieldTest(TestCase):
    """Regression: Session.channel_ref is a CharField, not a ForeignKey.

    Before the fix, admin code used session.channel.ref which raises AttributeError
    because Session has no 'channel' FK — only a 'channel_ref' CharField.
    """

    def test_channel_ref_is_charfield_not_fk(self) -> None:
        field = Session._meta.get_field("channel_ref")
        self.assertIsInstance(field, django_models.CharField)
        self.assertNotIsInstance(field, django_models.ForeignKey)

    def test_session_channel_ref_accessible(self) -> None:
        """session.channel_ref returns the string value — no AttributeError."""
        session = Session.objects.create(
            session_key="SESS-HP2-1",
            channel_ref="balcao",
            state="open",
            pricing_policy="internal",
            edit_policy="open",
            rev=0,
            items=[],
            data={"checks": {}, "issues": []},
        )
        self.assertEqual(session.channel_ref, "balcao")

    def test_session_has_no_channel_fk(self) -> None:
        """Accessing session.channel raises AttributeError — proving the FK doesn't exist."""
        session = Session(session_key="X", channel_ref="balcao", state="open")
        with self.assertRaises(AttributeError):
            _ = session.channel.ref  # noqa: B018 — intentionally triggering the old bug


class OrderViewSetRefLookupTest(TestCase):
    """Regression: OrderViewSet.lookup_field = 'ref'.

    Before the fix, GET /api/orders/{ref}/ used PK lookup and returned 404.
    """

    def setUp(self) -> None:
        super().setUp()
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user("api_user", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_get_order_by_ref(self) -> None:
        """GET /api/orders/{ref}/ returns 200 with the correct order."""
        _, order = _create_committed_session(channel_ref="pos")

        resp = self.client.get(f"/api/orders/{order.ref}")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["ref"], order.ref)

    def test_get_order_by_pk_not_ref_returns_404(self) -> None:
        """GET /api/orders/{pk}/ returns 404 (PK is not the lookup field)."""
        _, order = _create_committed_session(channel_ref="pos")

        # PKs are integers; refs look like 'ORD-XXXX'. Using the PK as a ref
        # string should 404 since it won't match any ref.
        resp = self.client.get(f"/api/orders/{order.pk}")
        # Will match if ref happens to equal str(pk), but conventionally it won't.
        if resp.status_code == 200:
            # Confirm it returned the right order by ref, not by PK accidentally
            self.assertEqual(resp.data["ref"], str(order.pk))
        else:
            self.assertEqual(resp.status_code, 404)

    def test_get_nonexistent_ref_returns_404(self) -> None:
        """GET /api/orders/ORD-BOGUS returns 404."""
        resp = self.client.get("/api/orders/ORD-BOGUS")
        self.assertEqual(resp.status_code, 404)

    def test_list_orders(self) -> None:
        """GET /api/orders returns paginated results."""
        _create_committed_session(channel_ref="pos")
        resp = self.client.get("/api/orders")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertIn("results", resp.data)
        self.assertGreaterEqual(len(resp.data["results"]), 1)
