"""Resolver plugável que decide SE a NFC-e é emitida (fiscal.should_emit)."""

from __future__ import annotations

from types import SimpleNamespace

from django.test import override_settings

from shopman.shop.services.fiscal import should_emit


def _order(fiscal=None, total_q=0):
    return SimpleNamespace(data={"fiscal": fiscal or {}}, total_q=total_q)


# Resolvers de teste (referenciados por caminho pontilhado).
def resolver_always_true(order):
    return True


def resolver_only_big(order):
    return order.total_q >= 5000


def resolver_boom(order):
    raise RuntimeError("resolver quebrado")


_HERE = "shopman.shop.tests.test_fiscal_should_emit"


def test_fallback_without_resolver_uses_issue_document():
    assert should_emit(_order(fiscal={"issue_document": True})) is True
    assert should_emit(_order(fiscal={"issue_document": False})) is False
    assert should_emit(_order(fiscal={})) is False


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=f"{_HERE}.resolver_always_true")
def test_resolver_true_overrides_optin():
    # Mesmo sem issue_document, o resolver manda emitir.
    assert should_emit(_order(fiscal={})) is True


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=f"{_HERE}.resolver_only_big")
def test_resolver_by_business_rule():
    assert should_emit(_order(total_q=6000)) is True
    assert should_emit(_order(total_q=1000)) is False


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=f"{_HERE}.resolver_boom")
def test_broken_resolver_falls_back():
    # Resolver quebrado não trava o pedido — cai no fallback (issue_document).
    assert should_emit(_order(fiscal={"issue_document": True})) is True
    assert should_emit(_order(fiscal={"issue_document": False})) is False


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=f"{_HERE}.does_not_exist")
def test_missing_resolver_path_falls_back():
    assert should_emit(_order(fiscal={"issue_document": True})) is True
