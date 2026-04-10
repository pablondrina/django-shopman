"""
Stock handlers — issue resolution only.

The legacy StockHoldHandler / StockCommitHandler / StockCheck / StockCheckValidator
flow has been replaced by inline `services.availability.reserve()` (cart-add)
plus `services.stock.hold/fulfill/release` (order lifecycle). This module now
only carries the issue resolver used by the cart UX when stock issues need to
be acted upon (apply suggested ops).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class StockIssueResolver:
    """Resolver para issues de estoque. Source: stock"""

    source = "stock"

    def resolve(self, *, session, issue: dict, action_id: str, ctx: dict):
        from shopman.omniman.exceptions import IssueResolveError
        from shopman.omniman.services import ModifyService

        context = issue.get("context", {})
        actions = context.get("actions", [])

        action = next((a for a in actions if a.get("id") == action_id), None)
        if not action:
            raise IssueResolveError(code="action_not_found", message=f"Action não encontrada: {action_id}")

        action_rev = action.get("rev")
        if action_rev is not None and action_rev != session.rev:
            raise IssueResolveError(code="stale_action", message="Action desatualizada - sessão foi modificada")

        ops = action.get("ops", [])
        if not ops:
            raise IssueResolveError(code="no_ops", message="Action não contém operações")

        return ModifyService.modify_session(
            session_key=session.session_key, channel_ref=session.channel_ref, ops=ops, ctx=ctx,
        )


__all__ = ["StockIssueResolver"]
