"""Backstage constants — operator-surface configuration."""

from __future__ import annotations

from django.conf import settings

# Override via SHOPMAN_POS_CHANNEL_REF in your Django settings.
POS_CHANNEL_REF: str = getattr(settings, "SHOPMAN_POS_CHANNEL_REF", "pdv")
