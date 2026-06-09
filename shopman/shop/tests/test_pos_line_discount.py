"""Per-line manual discount (POS numpad "Desc"): pricing, intent and gate.

Operator policy (decided 2026-05-30):
- promo vs manual on the same line → "maior desconto ganha" (best wins);
- a manual discount on a D-1 line is only honored with manager approval
  (``approved_by`` stamped), and always requires the manager PIN gate.
"""

from __future__ import annotations

import pytest

from shopman.backstage.projections import pos as pos_projection
from shopman.shop.modifiers import DiscountModifier
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import (
    PosIntentError,
    parse_pos_sale_intent,
)


class TestCalcManual:
    def test_percent_of_unit_price(self) -> None:
        # 10% of R$ 13,00 (1300) = 130
        assert DiscountModifier._calc_manual({"value": 10}, 1300) == 130

    def test_clamped_to_unit_price(self) -> None:
        assert DiscountModifier._calc_manual({"value": 200}, 1300) == 1300

    def test_zero_or_invalid_is_no_discount(self) -> None:
        assert DiscountModifier._calc_manual({"value": 0}, 1300) == 0
        assert DiscountModifier._calc_manual({"value": "abc"}, 1300) == 0
        assert DiscountModifier._calc_manual({}, 1300) == 0


class TestIntentPreservesLineDiscount:
    def test_discount_and_is_d1_survive_parsing(self) -> None:
        intent = parse_pos_sale_intent(
            {
                "items": [
                    {"sku": "BAGUETE", "qty": 2, "unit_price_q": 1300,
                     "is_d1": True, "discount": {"value": 15, "reason": "fidelidade"}},
                ],
            },
            for_commit=True,
        )
        item = intent.payload["items"][0]
        assert item["is_d1"] is True
        assert item["discount"] == {"type": "percent", "value": 15.0, "reason": "fidelidade"}

    def test_percent_clamped_to_100(self) -> None:
        intent = parse_pos_sale_intent(
            {"items": [{"sku": "X", "qty": 1, "unit_price_q": 1000, "discount": {"value": 250}}]},
            for_commit=True,
        )
        assert intent.payload["items"][0]["discount"]["value"] == 100.0

    def test_no_discount_when_absent_or_zero(self) -> None:
        intent = parse_pos_sale_intent(
            {"items": [{"sku": "X", "qty": 1, "unit_price_q": 1000, "discount": {"value": 0}}]},
            for_commit=True,
        )
        assert "discount" not in intent.payload["items"][0]


class TestPayloadDiscountHelpers:
    def test_line_discounts_sum_per_unit_times_qty(self) -> None:
        payload = {"items": [
            {"sku": "A", "qty": 2, "unit_price_q": 1300, "discount": {"value": 10}},  # 130 * 2
            {"sku": "B", "qty": 1, "unit_price_q": 800},                               # no discount
        ]}
        assert pos_service._payload_line_discounts_q(payload) == 260

    def test_d1_line_discount_detected(self) -> None:
        payload = {"items": [
            {"sku": "A", "qty": 1, "unit_price_q": 1300, "is_d1": True, "discount": {"value": 10}},
        ]}
        assert pos_service._payload_has_d1_line_discount(payload) is True

    def test_non_d1_line_discount_not_flagged(self) -> None:
        payload = {"items": [
            {"sku": "A", "qty": 1, "unit_price_q": 1300, "discount": {"value": 10}},
        ]}
        assert pos_service._payload_has_d1_line_discount(payload) is False


@pytest.mark.django_db
class TestBuildSessionOpsStampsDiscount:
    def test_stamps_manual_discount_meta_with_approved_by(self) -> None:
        payload = {
            "items": [{"sku": "BAGUETE", "name": "Baguete", "qty": 1, "unit_price_q": 1300,
                       "discount": {"type": "percent", "value": 10, "reason": "cortesia"}}],
            "manager_approval": {"username": "gerente", "pin": "1234"},
        }
        ops = pos_service.build_session_ops(payload, operator_username="op")
        add_line = next(op for op in ops if op["op"] == "add_line" and op["sku"] == "BAGUETE")
        assert add_line["meta"]["manual_discount"]["value"] == 10
        assert add_line["meta"]["manual_discount"]["reason"] == "cortesia"
        assert add_line["meta"]["manual_discount"]["approved_by"] == "gerente"

    def test_no_meta_discount_without_line_discount(self) -> None:
        payload = {"items": [{"sku": "BAGUETE", "name": "Baguete", "qty": 1, "unit_price_q": 1300}]}
        ops = pos_service.build_session_ops(payload, operator_username="op")
        add_line = next(op for op in ops if op["op"] == "add_line" and op["sku"] == "BAGUETE")
        assert "manual_discount" not in (add_line.get("meta") or {})


@pytest.mark.django_db
class TestManagerApprovalGate:
    def test_d1_line_discount_requires_approval_even_without_threshold(self) -> None:
        payload = {
            "items": [{"sku": "BAGUETE", "qty": 1, "unit_price_q": 1300,
                       "is_d1": True, "discount": {"value": 10}}],
        }
        with pytest.raises(PosIntentError) as exc:
            pos_service.validate_manager_approval(payload, operator_username="op")
        assert exc.value.code == "manager_approval_required"

    def test_plain_line_discount_below_threshold_passes(self) -> None:
        # Default threshold is 0 (no approval); a non-D-1 line discount does not gate.
        payload = {
            "items": [{"sku": "BAGUETE", "qty": 1, "unit_price_q": 1300, "discount": {"value": 10}}],
        }
        # Must not raise.
        pos_service.validate_manager_approval(payload, operator_username="op")


class TestPriceOverrideIntentAndOps:
    """Operator unit-price override (numpad "Preço"): flag survives parsing, is
    stamped into line meta (so the modifier freezes it), and gates manager PIN."""

    def test_flag_survives_parsing(self) -> None:
        intent = parse_pos_sale_intent(
            {"items": [{"sku": "X", "qty": 1, "unit_price_q": 500, "price_overridden": True}]},
            for_commit=True,
        )
        assert intent.payload["items"][0]["price_overridden"] is True

    def test_absent_flag_not_added(self) -> None:
        intent = parse_pos_sale_intent(
            {"items": [{"sku": "X", "qty": 1, "unit_price_q": 1300}]},
            for_commit=True,
        )
        assert "price_overridden" not in intent.payload["items"][0]

    def test_payload_helper_detects_override(self) -> None:
        payload = {"items": [{"sku": "X", "qty": 1, "unit_price_q": 500, "price_overridden": True}]}
        assert pos_service._payload_has_price_override(payload) is True
        plain = {"items": [{"sku": "X", "qty": 1, "unit_price_q": 1300}]}
        assert pos_service._payload_has_price_override(plain) is False

    @pytest.mark.django_db
    def test_build_session_ops_stamps_override_meta(self) -> None:
        payload = {
            "items": [{"sku": "X", "name": "Item", "qty": 1, "unit_price_q": 500,
                       "price_overridden": True}],
            "manager_approval": {"username": "gerente", "pin": "1234"},
        }
        ops = pos_service.build_session_ops(payload, operator_username="op")
        add_line = next(op for op in ops if op["op"] == "add_line" and op["sku"] == "X")
        assert add_line["unit_price_q"] == 500
        assert add_line["meta"]["price_overridden"] is True
        assert add_line["meta"]["price_approved_by"] == "gerente"

    @pytest.mark.django_db
    def test_override_requires_manager_pin(self) -> None:
        payload = {"items": [{"sku": "X", "qty": 1, "unit_price_q": 500, "price_overridden": True}]}
        with pytest.raises(PosIntentError) as exc:
            pos_service.validate_manager_approval(payload, operator_username="op")
        assert exc.value.code == "manager_approval_required"

    @pytest.mark.django_db
    def test_override_passes_with_valid_manager_pin(self, monkeypatch) -> None:
        monkeypatch.setattr(pos_service, "_verify_manager_pin", lambda u, p: object())
        payload = {
            "items": [{"sku": "X", "qty": 1, "unit_price_q": 500, "price_overridden": True}],
            "manager_approval": {"username": "gerente", "pin": "1234"},
        }
        pos_service.validate_manager_approval(payload, operator_username="op")  # must not raise


class TestTabPayloadRestore:
    def test_line_discount_surfaced_for_restore(self) -> None:
        item = {"sku": "X", "meta": {"manual_discount": {"value": 10, "reason": "cortesia"}}}
        assert pos_projection._tab_payload_line_discount(item) == {"value": 10, "reason": "cortesia"}

    def test_no_discount_returns_none(self) -> None:
        assert pos_projection._tab_payload_line_discount({"sku": "X", "meta": {}}) is None

    def test_display_price_uses_pre_discount_when_manual_applied(self) -> None:
        # After the modifier ran, unit_price_q is discounted; display restores base.
        item = {
            "sku": "X",
            "unit_price_q": 1170,  # 1300 - 10%
            "meta": {"manual_discount": {"value": 10, "reason": "cortesia"}},
            "modifiers_applied": [{"type": "manual", "original_price_q": 1300, "discount_q": 130}],
        }
        assert pos_projection._tab_line_display_price_q(item) == 1300

    def test_display_price_falls_back_to_unit_price(self) -> None:
        item = {"sku": "X", "unit_price_q": 1300, "meta": {}}
        assert pos_projection._tab_line_display_price_q(item) == 1300
