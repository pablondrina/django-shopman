"""
SessionWriteService — Write-back de resultados de checks.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone
from shopman.orderman.models import Session

logger = logging.getLogger(__name__)


class SessionWriteService:
    """
    Serviço para write-back de resultados de checks.

    Garante que apenas checks com rev compatível são aplicados (stale-safe).
    """

    @staticmethod
    @transaction.atomic
    def apply_check_result(
        session_key: str,
        channel_ref: str,
        expected_rev: int,
        check_code: str,
        check_payload: dict,
        issues: list[dict],
    ) -> bool:
        log_context = {
            "check_code": check_code,
            "session_key": session_key,
            "channel_ref": channel_ref,
            "expected_rev": expected_rev,
            "has_issues": len(issues) > 0,
        }

        logger.info("Applying check result", extra=log_context)

        try:
            session = Session.objects.select_for_update().get(
                session_key=session_key,
                channel_ref=channel_ref,
            )
        except Session.DoesNotExist:
            logger.warning("Session not found for check result", extra=log_context)
            return False

        if session.rev != expected_rev:
            logger.warning(
                "Stale rev for check result",
                extra={**log_context, "session_rev": session.rev},
            )
            return False

        if session.state != "open":
            logger.warning(
                "Session not open for check result",
                extra={**log_context, "session_state": session.state},
            )
            return False

        if "checks" not in session.data:
            session.data["checks"] = {}

        session.data["checks"][check_code] = {
            "rev": session.rev,
            "at": timezone.now().isoformat(),
            "result": check_payload,
        }

        if "issues" not in session.data:
            session.data["issues"] = []

        session.data["issues"] = [
            i for i in session.data["issues"] if i.get("source") != check_code
        ]

        session.data["issues"].extend(issues)

        session.save()
        logger.info(
            "Check result applied successfully",
            extra={**log_context, "session_rev": session.rev},
        )
        return True
