"""
Tests for services.py validator and modifier integration.

Covers edge cases and branches in ModifyService and CommitService.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from shopman.omniman import registry
from shopman.omniman.exceptions import ValidationError
from shopman.omniman.models import Channel, Session
from shopman.omniman.services import ModifyService


class MockDraftValidator:
    """Validator that runs at draft stage."""
    code = "mock-draft"
    stage = "draft"
    should_fail = False

    def validate(self, *, channel, session, ctx):
        if self.should_fail:
            raise ValidationError(
                code="mock_validation_failed",
                message="Mock validator failed",
            )


class MockCommitValidator:
    """Validator that runs at commit stage."""
    code = "mock-commit"
    stage = "commit"
    should_fail = False

    def validate(self, *, channel, session, ctx):
        if self.should_fail:
            raise ValidationError(
                code="mock_commit_failed",
                message="Mock commit validator failed",
            )


class MockModifier:
    """Modifier that adds metadata to session."""
    code = "mock-modifier"
    order = 10

    def apply(self, *, channel, session, ctx):
        session.data.setdefault("meta", {})
        session.data["meta"]["modified_by"] = "mock-modifier"


class ValidatorIntegrationTests(TestCase):
    """Tests for validator integration in ModifyService."""

    def setUp(self) -> None:
        registry.clear()
        self.channel = Channel.objects.create(
            ref="validator-test",
            name="Validator Test Channel",
            config={},
        )
        self.session = Session.objects.create(
            session_key="VAL-SESS-001",
            channel=self.channel,
            state="open",
            rev=1,
            items=[],
        )

    def tearDown(self) -> None:
        registry.clear()

    def test_modify_runs_draft_validators(self) -> None:
        """Should run draft validators after applying operations."""
        validator = MockDraftValidator()
        validator.should_fail = False
        registry.register_validator(validator)

        # Should not raise
        ModifyService.modify_session(
            session_key=self.session.session_key,
            channel_ref=self.channel.ref,
            ops=[{"op": "add_line", "sku": "TEST-SKU", "qty": 1, "unit_price_q": 1000}],
        )

        self.session.refresh_from_db()
        self.assertEqual(len(self.session.items), 1)

    def test_modify_raises_when_validator_fails(self) -> None:
        """Should raise ValidationError when draft validator fails."""
        validator = MockDraftValidator()
        validator.should_fail = True
        registry.register_validator(validator)

        with self.assertRaises(ValidationError) as ctx:
            ModifyService.modify_session(
                session_key=self.session.session_key,
                channel_ref=self.channel.ref,
                ops=[{"op": "add_line", "sku": "TEST-SKU", "qty": 1, "unit_price_q": 1000}],
            )

        self.assertEqual(ctx.exception.code, "mock_validation_failed")

    def test_modify_does_not_run_commit_validators(self) -> None:
        """Should not run commit-stage validators during modify."""
        commit_validator = MockCommitValidator()
        commit_validator.should_fail = True  # Would fail if run
        registry.register_validator(commit_validator)

        # Should not raise because commit validators aren't run during modify
        ModifyService.modify_session(
            session_key=self.session.session_key,
            channel_ref=self.channel.ref,
            ops=[{"op": "add_line", "sku": "TEST-SKU", "qty": 1, "unit_price_q": 1000}],
        )


class ModifierIntegrationTests(TestCase):
    """Tests for modifier integration in ModifyService."""

    def setUp(self) -> None:
        registry.clear()
        self.channel = Channel.objects.create(
            ref="modifier-test",
            name="Modifier Test Channel",
            config={},
        )
        self.session = Session.objects.create(
            session_key="MOD-SESS-001",
            channel=self.channel,
            state="open",
            rev=1,
            items=[],
        )

    def tearDown(self) -> None:
        registry.clear()

    def test_modify_runs_modifiers(self) -> None:
        """Should run modifiers after applying operations."""
        modifier = MockModifier()
        registry.register_modifier(modifier)

        ModifyService.modify_session(
            session_key=self.session.session_key,
            channel_ref=self.channel.ref,
            ops=[{"op": "add_line", "sku": "TEST-SKU", "qty": 1, "unit_price_q": 1000}],
        )

        self.session.refresh_from_db()
        self.assertEqual(self.session.data.get("meta", {}).get("modified_by"), "mock-modifier")

    def test_modifiers_run_in_order(self) -> None:
        """Should run modifiers in order by their `order` attribute."""
        execution_order = []

        class Modifier1:
            code = "mod1"
            order = 20

            def apply(self, *, channel, session, ctx):
                execution_order.append("mod1")

        class Modifier2:
            code = "mod2"
            order = 10

            def apply(self, *, channel, session, ctx):
                execution_order.append("mod2")

        class Modifier3:
            code = "mod3"
            order = 30

            def apply(self, *, channel, session, ctx):
                execution_order.append("mod3")

        registry.register_modifier(Modifier1())
        registry.register_modifier(Modifier2())
        registry.register_modifier(Modifier3())

        ModifyService.modify_session(
            session_key=self.session.session_key,
            channel_ref=self.channel.ref,
            ops=[{"op": "add_line", "sku": "TEST-SKU", "qty": 1, "unit_price_q": 1000}],
        )

        # Should run in order: mod2 (10), mod1 (20), mod3 (30)
        self.assertEqual(execution_order, ["mod2", "mod1", "mod3"])
