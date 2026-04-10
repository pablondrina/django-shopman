"""
Tests for ModifyService operations.

Covers:
- replace_sku operation
- set_data operation
- merge_lines operation
- Error cases (session not found, locked, abandoned, etc.)
"""

from __future__ import annotations
import types

from decimal import Decimal

from django.test import TestCase

from shopman.omniman.exceptions import SessionError, ValidationError
from shopman.omniman.models import Session
from shopman.omniman.services import ModifyService


class ModifyServiceBaseTests(TestCase):
    """Base test setup for ModifyService tests."""

    def setUp(self) -> None:
        self.channel = types.SimpleNamespace(
            ref="test",
            name="Test Channel",
        )


class ModifyServiceSessionNotFoundTests(ModifyServiceBaseTests):
    """Tests for session not found error."""

    def test_modify_session_not_found_raises_error(self) -> None:
        """Should raise SessionError when session doesn't exist."""
        with self.assertRaises(SessionError) as ctx:
            ModifyService.modify_session(
                session_key="NONEXISTENT",
                channel_ref=self.channel.ref,
                ops=[{"op": "add_line", "sku": "X", "qty": 1, "unit_price_q": 100}],
            )

        self.assertEqual(ctx.exception.code, "not_found")


class ModifyServiceLockedSessionTests(ModifyServiceBaseTests):
    """Tests for locked session error."""

    def test_modify_locked_session_raises_error(self) -> None:
        """Should raise SessionError when session is locked."""
        session = Session.objects.create(
            session_key="LOCKED-SESSION",
            channel_ref=self.channel.ref,
            state="open",
            edit_policy="locked",  # Locked!
        )

        with self.assertRaises(SessionError) as ctx:
            ModifyService.modify_session(
                session_key=session.session_key,
                channel_ref=self.channel.ref,
                ops=[{"op": "add_line", "sku": "X", "qty": 1, "unit_price_q": 100}],
            )

        self.assertEqual(ctx.exception.code, "locked")


class ModifyServiceAbandonedSessionTests(ModifyServiceBaseTests):
    """Tests for abandoned session error."""

    def test_modify_abandoned_session_raises_error(self) -> None:
        """Should raise SessionError when session is abandoned."""
        session = Session.objects.create(
            session_key="ABANDONED-SESSION",
            channel_ref=self.channel.ref,
            state="abandoned",
        )

        with self.assertRaises(SessionError) as ctx:
            ModifyService.modify_session(
                session_key=session.session_key,
                channel_ref=self.channel.ref,
                ops=[{"op": "add_line", "sku": "X", "qty": 1, "unit_price_q": 100}],
            )

        self.assertEqual(ctx.exception.code, "already_abandoned")


class ModifyServiceReplaceSKUTests(ModifyServiceBaseTests):
    """Tests for replace_sku operation."""

    def setUp(self) -> None:
        super().setUp()
        self.session = Session.objects.create(
            session_key="REPLACE-SKU-SESSION",
            channel_ref=self.channel.ref,
            state="open",
            pricing_policy="external",  # Explicitly set
            items=[
                {"line_id": "L1", "sku": "OLD-SKU", "qty": 2, "unit_price_q": 1000, "meta": {}},
            ],
        )

    def test_replace_sku_updates_sku(self) -> None:
        """Should replace SKU on existing line."""
        ModifyService.modify_session(
            session_key=self.session.session_key,
            channel_ref=self.channel.ref,
            ops=[{
                "op": "replace_sku",
                "line_id": "L1",
                "sku": "NEW-SKU",
                "unit_price_q": 1500,
            }],
        )

        self.session.refresh_from_db()
        self.assertEqual(self.session.items[0]["sku"], "NEW-SKU")
        self.assertEqual(self.session.items[0]["unit_price_q"], 1500)

    def test_replace_sku_updates_meta(self) -> None:
        """Should update meta when provided."""
        ModifyService.modify_session(
            session_key=self.session.session_key,
            channel_ref=self.channel.ref,
            ops=[{
                "op": "replace_sku",
                "line_id": "L1",
                "sku": "NEW-SKU",
                "unit_price_q": 1500,
                "meta": {"color": "red"},
            }],
        )

        self.session.refresh_from_db()
        self.assertEqual(self.session.items[0]["meta"], {"color": "red"})

    def test_replace_sku_missing_sku_raises_error(self) -> None:
        """Should raise error when SKU is missing."""
        with self.assertRaises(ValidationError) as ctx:
            ModifyService.modify_session(
                session_key=self.session.session_key,
                channel_ref=self.channel.ref,
                ops=[{
                    "op": "replace_sku",
                    "line_id": "L1",
                    "unit_price_q": 1500,
                }],
            )

        self.assertEqual(ctx.exception.code, "missing_sku")

    def test_replace_sku_missing_price_external_policy_raises_error(self) -> None:
        """Should raise error when price missing with external pricing."""
        with self.assertRaises(ValidationError) as ctx:
            ModifyService.modify_session(
                session_key=self.session.session_key,
                channel_ref=self.channel.ref,
                ops=[{
                    "op": "replace_sku",
                    "line_id": "L1",
                    "sku": "NEW-SKU",
                    # Missing unit_price_q
                }],
            )

        self.assertEqual(ctx.exception.code, "missing_unit_price_q")

    def test_replace_sku_unknown_line_id_raises_error(self) -> None:
        """Should raise error when line_id not found."""
        with self.assertRaises(ValidationError) as ctx:
            ModifyService.modify_session(
                session_key=self.session.session_key,
                channel_ref=self.channel.ref,
                ops=[{
                    "op": "replace_sku",
                    "line_id": "UNKNOWN",
                    "sku": "NEW-SKU",
                    "unit_price_q": 1500,
                }],
            )

        self.assertEqual(ctx.exception.code, "unknown_line_id")


class ModifyServiceSetDataTests(ModifyServiceBaseTests):
    """Tests for set_data operation."""

    def setUp(self) -> None:
        super().setUp()
        self.session = Session.objects.create(
            session_key="SET-DATA-SESSION",
            channel_ref=self.channel.ref,
            state="open",
            data={},
        )

    def test_set_data_simple_path(self) -> None:
        """Should set data at simple path."""
        ModifyService.modify_session(
            session_key=self.session.session_key,
            channel_ref=self.channel.ref,
            ops=[{
                "op": "set_data",
                "path": "customer_name",
                "value": "John Doe",
            }],
        )

        self.session.refresh_from_db()
        self.assertEqual(self.session.data["customer_name"], "John Doe")

    def test_set_data_nested_path(self) -> None:
        """Should set data at nested path."""
        ModifyService.modify_session(
            session_key=self.session.session_key,
            channel_ref=self.channel.ref,
            ops=[{
                "op": "set_data",
                "path": "customer.name",
                "value": "Jane Doe",
            }],
        )

        self.session.refresh_from_db()
        self.assertEqual(self.session.data["customer"]["name"], "Jane Doe")

    def test_set_data_deeply_nested_path(self) -> None:
        """Should set data at deeply nested path."""
        ModifyService.modify_session(
            session_key=self.session.session_key,
            channel_ref=self.channel.ref,
            ops=[{
                "op": "set_data",
                "path": "customer.address.city",
                "value": "São Paulo",
            }],
        )

        self.session.refresh_from_db()
        self.assertEqual(self.session.data["customer"]["address"]["city"], "São Paulo")


class ModifyServiceMergeLinesTests(ModifyServiceBaseTests):
    """Tests for merge_lines operation."""

    def setUp(self) -> None:
        super().setUp()
        self.session = Session.objects.create(
            session_key="MERGE-LINES-SESSION",
            channel_ref=self.channel.ref,
            state="open",
            items=[
                {"line_id": "L1", "sku": "COFFEE", "qty": 2, "unit_price_q": 500, "meta": {}},
                {"line_id": "L2", "sku": "COFFEE", "qty": 3, "unit_price_q": 500, "meta": {}},
            ],
        )

    def test_merge_lines_combines_quantities(self) -> None:
        """Should merge quantities from one line into another."""
        ModifyService.modify_session(
            session_key=self.session.session_key,
            channel_ref=self.channel.ref,
            ops=[{
                "op": "merge_lines",
                "from_line_id": "L1",
                "into_line_id": "L2",
            }],
        )

        self.session.refresh_from_db()
        self.assertEqual(len(self.session.items), 1)
        self.assertEqual(self.session.items[0]["line_id"], "L2")
        self.assertEqual(self.session.items[0]["qty"], Decimal("5"))  # 2 + 3

    def test_merge_lines_same_ids_raises_error(self) -> None:
        """Should raise error when merging line into itself."""
        with self.assertRaises(ValidationError) as ctx:
            ModifyService.modify_session(
                session_key=self.session.session_key,
                channel_ref=self.channel.ref,
                ops=[{
                    "op": "merge_lines",
                    "from_line_id": "L1",
                    "into_line_id": "L1",
                }],
            )

        self.assertEqual(ctx.exception.code, "invalid_merge")

    def test_merge_lines_unknown_from_raises_error(self) -> None:
        """Should raise error when from_line_id not found."""
        with self.assertRaises(ValidationError) as ctx:
            ModifyService.modify_session(
                session_key=self.session.session_key,
                channel_ref=self.channel.ref,
                ops=[{
                    "op": "merge_lines",
                    "from_line_id": "UNKNOWN",
                    "into_line_id": "L2",
                }],
            )

        self.assertEqual(ctx.exception.code, "unknown_line_id")

    def test_merge_lines_unknown_into_raises_error(self) -> None:
        """Should raise error when into_line_id not found."""
        with self.assertRaises(ValidationError) as ctx:
            ModifyService.modify_session(
                session_key=self.session.session_key,
                channel_ref=self.channel.ref,
                ops=[{
                    "op": "merge_lines",
                    "from_line_id": "L1",
                    "into_line_id": "UNKNOWN",
                }],
            )

        self.assertEqual(ctx.exception.code, "unknown_line_id")


class ModifyServiceSetQtyUnknownLineTests(ModifyServiceBaseTests):
    """Tests for set_qty with unknown line."""

    def test_set_qty_unknown_line_raises_error(self) -> None:
        """Should raise error when line_id not found for set_qty."""
        session = Session.objects.create(
            session_key="SET-QTY-UNKNOWN",
            channel_ref=self.channel.ref,
            state="open",
            items=[
                {"line_id": "L1", "sku": "X", "qty": 1, "unit_price_q": 100, "meta": {}},
            ],
        )

        with self.assertRaises(ValidationError) as ctx:
            ModifyService.modify_session(
                session_key=session.session_key,
                channel_ref=self.channel.ref,
                ops=[{
                    "op": "set_qty",
                    "line_id": "UNKNOWN",
                    "qty": 5,
                }],
            )

        self.assertEqual(ctx.exception.code, "unknown_line_id")


class SessionWriteServiceTests(TestCase):
    """Tests for SessionWriteService.apply_check_result."""

    def setUp(self) -> None:
        self.channel = types.SimpleNamespace(
            ref="check-test",
            name="Check Test",
        )
        self.session = Session.objects.create(
            session_key="CHECK-RESULT-SESSION",
            channel_ref=self.channel.ref,
            state="open",
            rev=5,
            data={},
        )

    def test_apply_check_result_success(self) -> None:
        """Should apply check result when rev matches."""
        from shopman.omniman.services import SessionWriteService

        result = SessionWriteService.apply_check_result(
            session_key=self.session.session_key,
            channel_ref=self.channel.ref,
            check_code="stock",
            check_payload={"holds": [{"hold_id": "H1"}]},
            expected_rev=5,
            issues=[],
        )

        self.assertTrue(result)
        self.session.refresh_from_db()
        self.assertIn("stock", self.session.data["checks"])
        self.assertEqual(self.session.data["checks"]["stock"]["rev"], 5)

    def test_apply_check_result_stale_rev(self) -> None:
        """Should return False when rev doesn't match."""
        from shopman.omniman.services import SessionWriteService

        result = SessionWriteService.apply_check_result(
            session_key=self.session.session_key,
            channel_ref=self.channel.ref,
            check_code="stock",
            check_payload={},
            expected_rev=3,  # Wrong rev!
            issues=[],
        )

        self.assertFalse(result)

    def test_apply_check_result_session_not_found(self) -> None:
        """Should return False when session not found."""
        from shopman.omniman.services import SessionWriteService

        result = SessionWriteService.apply_check_result(
            session_key="NONEXISTENT",
            channel_ref=self.channel.ref,
            check_code="stock",
            check_payload={},
            expected_rev=5,
            issues=[],
        )

        self.assertFalse(result)

    def test_apply_check_result_session_not_open(self) -> None:
        """Should return False when session is not open."""
        from shopman.omniman.services import SessionWriteService

        self.session.state = "committed"
        self.session.save()

        result = SessionWriteService.apply_check_result(
            session_key=self.session.session_key,
            channel_ref=self.channel.ref,
            check_code="stock",
            check_payload={},
            expected_rev=5,
            issues=[],
        )

        self.assertFalse(result)

    def test_apply_check_result_with_issues(self) -> None:
        """Should add issues to session."""
        from shopman.omniman.services import SessionWriteService

        issues = [
            {
                "id": "ISS-1",
                "source": "stock",
                "code": "insufficient_stock",
                "message": "Not enough stock",
            }
        ]

        result = SessionWriteService.apply_check_result(
            session_key=self.session.session_key,
            channel_ref=self.channel.ref,
            check_code="stock",
            check_payload={},
            expected_rev=5,
            issues=issues,
        )

        self.assertTrue(result)
        self.session.refresh_from_db()
        self.assertEqual(len(self.session.data["issues"]), 1)
        self.assertEqual(self.session.data["issues"][0]["code"], "insufficient_stock")

    def test_apply_check_result_replaces_old_issues(self) -> None:
        """Should replace old issues from same source."""
        from shopman.omniman.services import SessionWriteService

        # First check with issues
        SessionWriteService.apply_check_result(
            session_key=self.session.session_key,
            channel_ref=self.channel.ref,
            check_code="stock",
            check_payload={},
            expected_rev=5,
            issues=[{"id": "OLD", "source": "stock", "code": "old_issue", "message": "Old"}],
        )

        self.session.refresh_from_db()
        self.assertEqual(len(self.session.data["issues"]), 1)

        # Second check replaces issues
        SessionWriteService.apply_check_result(
            session_key=self.session.session_key,
            channel_ref=self.channel.ref,
            check_code="stock",
            check_payload={},
            expected_rev=5,
            issues=[{"id": "NEW", "source": "stock", "code": "new_issue", "message": "New"}],
        )

        self.session.refresh_from_db()
        self.assertEqual(len(self.session.data["issues"]), 1)
        self.assertEqual(self.session.data["issues"][0]["id"], "NEW")
