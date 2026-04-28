"""Backstage context processors."""

from __future__ import annotations

from shopman.backstage.operator.context import build_operator_context


def operator(request):
    return {"operator": build_operator_context(request)}
