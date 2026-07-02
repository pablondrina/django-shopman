"""Resolver plugável que decide SE a NFC-e é emitida (fiscal.emission_resolver)."""

from __future__ import annotations

from types import SimpleNamespace

from django.test import override_settings

from shopman.shop import fiscal_resolvers
from shopman.shop.services.fiscal import emission_resolver


def _order(fiscal=None, customer=None, total_q=0, channel_ref="web"):
    return SimpleNamespace(
        data={"fiscal": fiscal or {}, "customer": customer or {}},
        total_q=total_q,
        channel_ref=channel_ref,
    )


# Resolvers de teste (referenciados por caminho pontilhado).
def resolver_always_true(order):
    return True


def resolver_only_big(order):
    return order.total_q >= 5000


def resolver_boom(order):
    raise RuntimeError("resolver quebrado")


_HERE = "shopman.shop.tests.test_fiscal_emission_resolver"


def test_fallback_without_resolver_uses_issue_document():
    assert emission_resolver(_order(fiscal={"issue_document": True})) is True
    assert emission_resolver(_order(fiscal={"issue_document": False})) is False
    assert emission_resolver(_order(fiscal={})) is False


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=f"{_HERE}.resolver_always_true")
def test_resolver_true_overrides_optin():
    assert emission_resolver(_order(fiscal={})) is True


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=f"{_HERE}.resolver_only_big")
def test_resolver_by_business_rule():
    assert emission_resolver(_order(total_q=6000)) is True
    assert emission_resolver(_order(total_q=1000)) is False


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=f"{_HERE}.resolver_boom")
def test_broken_resolver_falls_back():
    assert emission_resolver(_order(fiscal={"issue_document": True})) is True
    assert emission_resolver(_order(fiscal={"issue_document": False})) is False


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=f"{_HERE}.does_not_exist")
def test_missing_resolver_path_falls_back():
    assert emission_resolver(_order(fiscal={"issue_document": True})) is True


# ── exemplos prontos (shopman.shop.fiscal_resolvers) ──────────────────────────


def test_example_always():
    assert fiscal_resolvers.always(_order()) is True


def test_example_on_request_or_tax_id():
    r = fiscal_resolvers.on_request_or_tax_id
    assert r(_order(fiscal={"issue_document": True})) is True
    assert r(_order(customer={"tax_id": "12345678909"})) is True
    assert r(_order(fiscal={}, customer={})) is False


def test_example_channels_factory():
    only_pdv = fiscal_resolvers.channels("pdv")
    assert only_pdv(_order(channel_ref="pdv")) is True
    assert only_pdv(_order(channel_ref="web")) is False


def test_example_above_amount_factory():
    big = fiscal_resolvers.above_amount_q(10000)
    assert big(_order(total_q=10000)) is True
    assert big(_order(total_q=9999)) is False
