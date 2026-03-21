"""
Console Backend — Log no console (desenvolvimento/debug).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from shopman.notifications.protocols import NotificationResult

logger = logging.getLogger(__name__)


class ConsoleBackend:
    """
    Backend que loga notificacoes no console.

    Util para desenvolvimento e testes.
    """

    def send(
        self,
        *,
        event: str,
        recipient: str,
        context: dict[str, Any],
    ) -> NotificationResult:
        """Loga notificacao no console."""
        logger.info(
            f"\n{'='*50}\n"
            f"NOTIFICATION: {event}\n"
            f"To: {recipient}\n"
            f"Context: {json.dumps(context, indent=2, default=str)}\n"
            f"{'='*50}"
        )

        return NotificationResult(
            success=True,
            message_id=f"console_{id(self)}",
        )
