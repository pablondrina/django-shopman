"""
Commit-stage validator — blocks commit when stock check is required but missing or stale.

Registered in inventory/apps.py (InventoryConfig.ready).
"""

from __future__ import annotations

import logging

from shopman.ordering.exceptions import ValidationError

logger = logging.getLogger(__name__)


class StockCheckValidator:
    """
    Validates that the session has a fresh ``stock`` check with holds
    before allowing commit.

    Only active when the channel requires the ``"stock"`` check
    (``channel.config["required_checks_on_commit"]`` includes ``"stock"``).
    """

    code = "stock_check"
    stage = "commit"

    def validate(self, *, channel, session, ctx):
        required_checks = channel.config.get("required_checks_on_commit", [])
        if "stock" not in required_checks:
            return  # Channel doesn't require stock check — skip

        checks = (session.data or {}).get("checks", {})
        stock_check = checks.get("stock")

        if not stock_check:
            raise ValidationError(
                code="missing_stock_check",
                message="Stock check obrigatório não encontrado na sessão",
                context={"session_key": session.session_key},
            )

        # Verify the check was done at the current revision
        if stock_check.get("rev") != session.rev:
            raise ValidationError(
                code="stale_stock_check",
                message="Stock check desatualizado — sessão foi modificada após o check",
                context={
                    "check_rev": stock_check.get("rev"),
                    "session_rev": session.rev,
                },
            )

        # Verify holds exist in the result
        result = stock_check.get("result") or {}
        holds = result.get("holds", [])

        if not holds and session.items:
            raise ValidationError(
                code="no_stock_holds",
                message="Nenhum hold de estoque encontrado para os itens da sessão",
                context={"session_key": session.session_key},
            )
