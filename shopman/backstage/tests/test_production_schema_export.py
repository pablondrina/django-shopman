"""Drift guard for the generated production contract mirror.

The fournil surface (production-nuxt) imports the projection shapes from a
generated TypeScript module whose single source of truth is
``shopman.backstage.projections.production``. If a dataclass changes without
regenerating, this test fails with the fix command — so the hand-sync the
schema was meant to kill cannot creep back via staleness.
"""

from __future__ import annotations

from shopman.backstage.management.commands.export_production_schema import (
    output_path,
    render_production_contract_ts,
)


def test_generated_production_contract_is_not_stale() -> None:
    path = output_path()
    assert path.exists(), (
        f"{path} missing — run: python manage.py export_production_schema"
    )
    assert path.read_text(encoding="utf-8") == render_production_contract_ts(), (
        "Production contract mirror is stale — run: python manage.py export_production_schema"
    )


def test_render_is_deterministic() -> None:
    assert render_production_contract_ts() == render_production_contract_ts()


def test_render_reflects_contract_source() -> None:
    from dataclasses import fields

    from shopman.backstage.projections.production import ProductionBoardProjection

    rendered = render_production_contract_ts()
    assert "export interface ProductionBoardProjection {" in rendered
    for field in fields(ProductionBoardProjection):
        assert f"  {field.name}:" in rendered
