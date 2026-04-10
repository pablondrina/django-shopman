"""
ResolveService — Resolve issues delegando para resolvers registrados.
"""

from __future__ import annotations

import logging

from django.db import transaction

from shopman.orderman import registry
from shopman.orderman.exceptions import IssueResolveError, SessionError, ValidationError
from shopman.orderman.models import Session


logger = logging.getLogger(__name__)


class ResolveService:
    """Serviço para resolver issues delegando para resolvers registrados."""

    @staticmethod
    @transaction.atomic
    def resolve(
        session_key: str,
        channel_ref: str,
        issue_id: str,
        action_id: str,
        ctx: dict | None = None,
        channel_config: dict | None = None,
    ) -> Session:
        ctx = ctx or {}

        try:
            session = Session.objects.select_for_update().get(
                session_key=session_key,
                channel_ref=channel_ref,
            )
        except Session.DoesNotExist:
            raise IssueResolveError(
                code="session_not_found",
                message=f"Sessão não encontrada: {channel_ref}:{session_key}",
            )

        issues = session.data.get("issues", [])
        issue = None
        for i in issues:
            if i.get("id") == issue_id:
                issue = i
                break

        if not issue:
            raise IssueResolveError(
                code="issue_not_found",
                message=f"Issue não encontrada: {issue_id}",
            )

        source = issue.get("source")
        resolver = registry.get_issue_resolver(source)

        if not resolver:
            raise IssueResolveError(
                code="no_resolver",
                message=f"Nenhum resolver registrado para source: {source}",
            )

        try:
            return resolver.resolve(
                session=session,
                issue=issue,
                action_id=action_id,
                ctx=ctx,
                channel_config=channel_config,
            )
        except IssueResolveError:
            raise
        except SessionError as exc:
            raise IssueResolveError(code=exc.code, message=exc.message, context=exc.context) from exc
        except ValidationError as exc:
            raise IssueResolveError(code=exc.code, message=exc.message, context=exc.context) from exc
        except Exception as exc:
            logger.exception(
                "Resolver %s falhou ao aplicar action %s na issue %s (sessão %s)",
                source,
                action_id,
                issue_id,
                session.session_key,
            )
            raise IssueResolveError(
                code="resolver_error",
                message="Resolver falhou ao aplicar action.",
                context={"source": source, "issue_id": issue_id, "action_id": action_id},
            ) from exc
