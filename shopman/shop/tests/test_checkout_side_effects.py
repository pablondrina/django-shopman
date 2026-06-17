"""WP-1 — post-commit side effects wired into checkout.process().

The headless API checkout (`storefront/api/views.py`) calls `checkout.process()`,
which must run the customer-facing side effects the deleted Django page used to do:
upsert customer, persist a new delivery address, save checkout defaults. Saving is
the omotenashi default; the surface opts out via `save_as_default=false`. All are
best-effort — never break the (already committed) order.
"""
from __future__ import annotations

from unittest.mock import patch

from shopman.shop.services import checkout


def _data(**over) -> dict:
    data = {
        "customer": {"name": "Ana", "phone": "+5543999990001"},
        "fulfillment_type": "delivery",
        "delivery_address": "Rua das Flores, 1",
        "save_as_default": True,
    }
    data.update(over)
    return data


def test_runs_all_three_side_effects():
    with (
        patch.object(checkout, "ensure_customer") as ec,
        patch.object(checkout, "persist_new_address") as pa,
        patch.object(checkout, "save_defaults") as sd,
    ):
        checkout._apply_post_commit_side_effects(_data(), "web", order_ref="ORD-1")

    ec.assert_called_once()
    pa.assert_called_once()
    sd.assert_called_once()
    assert sd.call_args.kwargs["enabled"] is True


def test_save_as_default_false_disables_defaults_only():
    with (
        patch.object(checkout, "ensure_customer") as ec,
        patch.object(checkout, "persist_new_address") as pa,
        patch.object(checkout, "save_defaults") as sd,
    ):
        checkout._apply_post_commit_side_effects(_data(save_as_default=False), "web", order_ref="ORD-2")

    # Endereço novo e cliente são salvos SEMPRE; só os defaults respeitam o toggle.
    ec.assert_called_once()
    pa.assert_called_once()
    assert sd.call_args.kwargs["enabled"] is False


def test_default_is_save_when_flag_absent():
    data = _data()
    data.pop("save_as_default")
    with (
        patch.object(checkout, "ensure_customer"),
        patch.object(checkout, "persist_new_address"),
        patch.object(checkout, "save_defaults") as sd,
    ):
        checkout._apply_post_commit_side_effects(data, "web", order_ref="ORD-3")

    assert sd.call_args.kwargs["enabled"] is True


def test_no_phone_skips_everything():
    data = {"customer": {"name": "Ana"}, "fulfillment_type": "pickup"}
    with (
        patch.object(checkout, "ensure_customer") as ec,
        patch.object(checkout, "persist_new_address") as pa,
        patch.object(checkout, "save_defaults") as sd,
    ):
        checkout._apply_post_commit_side_effects(data, "web", order_ref="ORD-4")

    ec.assert_not_called()
    pa.assert_not_called()
    sd.assert_not_called()


def test_best_effort_swallows_exceptions():
    with (
        patch.object(checkout, "ensure_customer", side_effect=Exception("boom")),
        patch.object(checkout, "persist_new_address") as pa,
        patch.object(checkout, "save_defaults") as sd,
    ):
        # Não levanta — o pedido já foi commitado; persistência é best-effort.
        checkout._apply_post_commit_side_effects(_data(), "web", order_ref="ORD-5")

    # Falha no primeiro não impede os demais.
    pa.assert_called_once()
    sd.assert_called_once()
