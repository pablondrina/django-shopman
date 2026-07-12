"""Drift guard for the generated order-queue contract mirror.

The gestor (orders-nuxt) imports the projection shapes from a generated
TypeScript module whose single source of truth is
``shopman.backstage.projections.order_queue``. If a dataclass changes without
regenerating, this test fails with the fix command — so the hand-sync the
schema was meant to kill cannot creep back via staleness.
"""

from __future__ import annotations

from shopman.backstage.management.commands.export_orders_schema import (
    output_path,
    render_orders_contract_ts,
)


def test_generated_orders_contract_is_not_stale() -> None:
    path = output_path()
    assert path.exists(), (
        f"{path} missing — run: python manage.py export_orders_schema"
    )
    assert path.read_text(encoding="utf-8") == render_orders_contract_ts(), (
        "Orders contract mirror is stale — run: python manage.py export_orders_schema"
    )


def test_render_is_deterministic() -> None:
    assert render_orders_contract_ts() == render_orders_contract_ts()


def test_render_reflects_contract_source() -> None:
    from dataclasses import fields

    from shopman.backstage.projections.order_queue import TwoZoneQueueProjection

    rendered = render_orders_contract_ts()
    assert "export interface TwoZoneQueueProjection {" in rendered
    for field in fields(TwoZoneQueueProjection):
        assert f"  {field.name}:" in rendered
