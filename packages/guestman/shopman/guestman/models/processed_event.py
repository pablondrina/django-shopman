"""
ProcessedEvent model for replay protection (G5).

Stores processed webhook event nonces to prevent replay attacks
in distributed/multi-server environments.
"""

from datetime import timedelta

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class ProcessedEvent(models.Model):
    """
    Tracks processed webhook events for replay protection (G5).

    This model stores nonces/event IDs to prevent the same event
    from being processed twice in a distributed environment.
    """

    nonce = models.CharField(verbose_name=_("nonce"), max_length=255, unique=True, db_index=True)
    provider = models.CharField(verbose_name=_("provedor"), max_length=50, db_index=True)
    processed_at = models.DateTimeField(verbose_name=_("processado em"), auto_now_add=True)

    class Meta:
        db_table = "customers_processed_event"
        verbose_name = _("evento processado")
        verbose_name_plural = _("eventos processados")
        indexes = [
            models.Index(fields=["provider", "processed_at"]),
        ]

    def __str__(self):
        return f"{self.provider}:{self.nonce[:20]}"

    @classmethod
    def cleanup_old_events(cls, days: int | None = None):
        """Remove events older than N days."""
        if days is None:
            from shopman.guestman.conf import guestman_settings
            days = guestman_settings.EVENT_CLEANUP_DAYS
        cutoff = timezone.now() - timedelta(days=days)
        return cls.objects.filter(processed_at__lt=cutoff).delete()
