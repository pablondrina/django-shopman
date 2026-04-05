"""ManyChat OTP sender — delivers verification codes via WhatsApp (ManyChat).

TODO WP-R2: implement full adapter from channels/backends/otp_manychat.py
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ManychatOTPSender:
    """Send OTP codes via ManyChat WhatsApp flow."""

    def send_code(self, target: str, code: str, method: str) -> bool:
        """Send OTP code to phone via ManyChat.

        Returns True if sent successfully.
        """
        logger.warning("ManychatOTPSender.send_code() — stub, not implemented yet (WP-R2)")
        return False
