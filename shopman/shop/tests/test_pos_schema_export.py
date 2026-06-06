"""Drift guard for the generated POS sale-intent contract mirror.

The Nuxt PDV imports version + enums from a generated TypeScript module whose
single source of truth is ``shopman.shop.services.pos_intent``. If the contract
changes without regenerating, this test fails with the fix command — so the
hand-sync the schema was meant to kill cannot creep back via staleness.
"""

from __future__ import annotations

from shopman.shop.management.commands.export_pos_schema import (
    output_path,
    render_pos_contract_ts,
)


def test_generated_pos_contract_is_not_stale() -> None:
    path = output_path()
    assert path.exists(), (
        f"{path} missing — run: python manage.py export_pos_schema"
    )
    assert path.read_text(encoding="utf-8") == render_pos_contract_ts(), (
        "POS contract mirror is stale — run: python manage.py export_pos_schema"
    )


def test_render_is_deterministic() -> None:
    assert render_pos_contract_ts() == render_pos_contract_ts()


def test_render_reflects_contract_source() -> None:
    from shopman.shop.services.pos_intent import (
        POS_SALE_INTENT_PAYMENT_METHODS,
        POS_SALE_INTENT_VERSION,
    )

    rendered = render_pos_contract_ts()
    assert f'"{POS_SALE_INTENT_VERSION}"' in rendered
    for method in POS_SALE_INTENT_PAYMENT_METHODS:
        assert f'"{method}"' in rendered
