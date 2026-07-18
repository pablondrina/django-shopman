"""django-eventstream channel permissions for Shopman."""

from __future__ import annotations

import logging

from django_eventstream.channelmanager import DefaultChannelManager

logger = logging.getLogger(__name__)


class ShopmanChannelManager(DefaultChannelManager):
    """Restrict sensitive SSE channels while keeping public stock updates."""

    def is_channel_reliable(self, channel):
        channel = str(channel or "")
        if channel.startswith("stock-") or channel.startswith("fomo-"):
            # Efêmeros: sem histórico/resume — a verdade é refeita no fetch canônico.
            return False
        return super().is_channel_reliable(channel)

    def can_read_channel(self, user, channel):
        channel = str(channel or "")
        if channel.startswith("order-"):
            return self._can_read_order_channel(user, channel.removeprefix("order-"))
        if channel.startswith("user-"):
            return self._can_read_user_channel(user, channel.removeprefix("user-"))
        if channel.startswith("backstage-"):
            return bool(
                user
                and getattr(user, "is_authenticated", False)
                and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))
            )
        return super().can_read_channel(user, channel)

    @staticmethod
    def _can_read_user_channel(user, user_id: str) -> bool:
        """Canal pessoal: só o próprio dono. Nem staff lê a caixa alheia."""
        if not user_id.isdigit() or not getattr(user, "is_authenticated", False):
            return False
        return str(getattr(user, "pk", "")) == user_id

    @staticmethod
    def _can_read_order_channel(user, order_ref: str) -> bool:
        if not order_ref:
            return False
        try:
            from shopman.orderman.models import Order

            from shopman.shop.services import customer_orders

            order = Order.objects.filter(ref=order_ref).first()
            if order is None:
                return False
            if order_ref in set(getattr(user, "_shopman_order_sse_refs", ()) or ()):
                return True
            return customer_orders.user_can_access_order(user, order)
        except Exception:
            logger.warning("eventstream_order_permission_failed order=%s", order_ref, exc_info=True)
            return False
