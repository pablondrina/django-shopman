"""
Stock Resolvers — Resolvers para issues de estoque.
"""

from __future__ import annotations

from typing import Any

from shopman.omniman.exceptions import IssueResolveError
from shopman.omniman.services import ModifyService


class StockIssueResolver:
    """
    Resolver para issues de estoque.

    Source: stock

    Processa actions definidas pelo StockHoldHandler,
    aplicando as ops à sessão via ModifyService.
    """

    source = "stock"

    def resolve(
        self,
        *,
        session: Any,
        issue: dict,
        action_id: str,
        ctx: dict,
        channel_config: dict | None = None,
    ) -> Any:
        """
        Resolve issue de estoque aplicando action selecionada.

        Args:
            session: Session com a issue
            issue: Issue a resolver
            action_id: ID da action escolhida
            ctx: Contexto adicional

        Returns:
            Session atualizada

        Raises:
            IssueResolveError: Se resolução falhar
        """
        context = issue.get("context", {})
        actions = context.get("actions", [])

        # Busca action
        action = None
        for a in actions:
            if a.get("id") == action_id:
                action = a
                break

        if not action:
            raise IssueResolveError(
                code="action_not_found",
                message=f"Action não encontrada: {action_id}",
                context={"issue_id": issue.get("id"), "action_id": action_id},
            )

        # Valida rev (stale check)
        action_rev = action.get("rev")
        if action_rev is not None and action_rev != session.rev:
            raise IssueResolveError(
                code="stale_action",
                message="Action desatualizada - sessão foi modificada",
                context={
                    "action_rev": action_rev,
                    "session_rev": session.rev,
                },
            )

        # Aplica ops
        ops = action.get("ops", [])
        if not ops:
            raise IssueResolveError(
                code="no_ops",
                message="Action não contém operações",
            )

        return ModifyService.modify_session(
            session_key=session.session_key,
            channel_ref=session.channel_ref,
            ops=ops,
            ctx=ctx,
            channel_config=channel_config,
        )
