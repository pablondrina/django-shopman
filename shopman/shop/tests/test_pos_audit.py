"""POS audit trail — the line-diff that feeds SessionEvent (anti-fraud)."""

from __future__ import annotations

from shopman.shop.services import pos as pos_service


class _StubSession:
    """Captures emit_event calls without touching the DB."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit_event(self, event_type: str, actor: str = "system", payload: dict | None = None):
        self.events.append({"type": event_type, "actor": actor, "payload": payload or {}})


class TestAuditQty:
    def test_whole_qty_is_int(self) -> None:
        assert pos_service._audit_qty({"qty": 3}) == 3
        assert isinstance(pos_service._audit_qty({"qty": 3}), int)

    def test_fractional_qty_is_float(self) -> None:
        assert pos_service._audit_qty({"qty": "1.5"}) == 1.5

    def test_invalid_qty_is_zero(self) -> None:
        assert pos_service._audit_qty({"qty": "abc"}) == 0


class TestAuditLineDiff:
    def test_detects_removal(self) -> None:
        s = _StubSession()
        pos_service._audit_line_diff(
            s, before=[{"line_id": "L1", "sku": "PAO", "name": "Pão", "qty": 3}], after=[], actor="op"
        )
        assert [e["type"] for e in s.events] == ["line_removed"]
        assert s.events[0]["payload"]["sku"] == "PAO"
        assert s.events[0]["payload"]["qty"] == 3
        assert s.events[0]["actor"] == "op"

    def test_detects_add(self) -> None:
        s = _StubSession()
        pos_service._audit_line_diff(
            s, before=[], after=[{"line_id": "L1", "sku": "CAFE", "qty": 1}], actor="op"
        )
        assert [e["type"] for e in s.events] == ["line_added"]

    def test_detects_qty_change(self) -> None:
        s = _StubSession()
        pos_service._audit_line_diff(
            s,
            before=[{"line_id": "L1", "sku": "PAO", "qty": 3}],
            after=[{"line_id": "L1", "sku": "PAO", "qty": 1}],
            actor="op",
        )
        assert [e["type"] for e in s.events] == ["qty_changed"]
        assert s.events[0]["payload"]["qty_before"] == 3
        assert s.events[0]["payload"]["qty_after"] == 1

    def test_no_events_when_unchanged(self) -> None:
        s = _StubSession()
        line = [{"line_id": "L1", "sku": "PAO", "qty": 2}]
        pos_service._audit_line_diff(s, before=line, after=line, actor="op")
        assert s.events == []

    def test_ignores_delivery_fee_line(self) -> None:
        s = _StubSession()
        pos_service._audit_line_diff(
            s,
            before=[{"line_id": "D", "sku": "__DELIVERY_FEE__", "qty": 1, "meta": {"type": "delivery_fee"}}],
            after=[],
            actor="op",
        )
        assert s.events == []
