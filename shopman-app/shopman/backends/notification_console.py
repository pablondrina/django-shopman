"""
Console notification backend — log no console (dev/debug).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from shopman.protocols import NotificationResult

logger = logging.getLogger(__name__)


class ConsoleBackend:
    """Backend que loga notificações no console."""

    def send(
        self,
        *,
        event: str,
        recipient: str,
        context: dict[str, Any],
    ) -> NotificationResult:
        logger.info(
            f"\n{'='*50}\n"
            f"NOTIFICATION: {event}\n"
            f"To: {recipient}\n"
            f"Context: {json.dumps(context, indent=2, default=str)}\n"
            f"{'='*50}"
        )
        return NotificationResult(success=True, message_id=f"console_{id(self)}")
