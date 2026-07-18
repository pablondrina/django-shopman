"""Per-platform social publish rules.

Config lives in ``Shop.defaults['social_publish']`` as
``{platform: {publish_on_create, require_stock, require_image}}``. Defaults keep
the current behavior (auto-publish on create; no stock/image gate) so the rules
are opt-in per platform and never break existing channels (e.g. iFood).

Applied as GUARDS in the projection auto-trigger — not new business logic:
- ``publish_on_create`` — a brand-new product enters the platform automatically.
- ``require_stock`` — only publish while there is promisable stock (else pending).
- ``require_image`` — do not push an imageless item (Google/Meta reject it).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_DEFAULTS = {
    "publish_on_create": True,
    "require_stock": False,
    "require_image": False,
}


def rules_for(platform: str) -> dict:
    """Merged rules for a platform (defaults + configured overrides)."""
    cfg: dict = {}
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        if shop:
            cfg = ((shop.defaults or {}).get("social_publish") or {}).get(platform) or {}
    except Exception:
        logger.debug("social_publish_rules.rules_for degraded", exc_info=True)
    return {**_DEFAULTS, **{k: bool(v) for k, v in cfg.items() if k in _DEFAULTS}}


def should_auto_publish_new(platform: str) -> bool:
    """Whether a newly-created product should auto-enter this platform."""
    return rules_for(platform)["publish_on_create"]


def projection_gate(item, platform: str) -> tuple[str, str] | None:
    """Return ``(sync_status, reason)`` to SKIP the push, or ``None`` to proceed.

    Applies to any publish trigger (auto or manual) — a platform that rejects
    imageless/out-of-stock items should not receive a doomed payload.
    """
    rules = rules_for(platform)
    if rules["require_image"] and not getattr(item, "image_url", None):
        return ("skipped", "regra: exige imagem")
    if rules["require_stock"] and not _has_promisable_stock(item.sku, platform):
        return ("pending", "regra: exige estoque")
    return None


def _has_promisable_stock(sku: str, platform: str) -> bool:
    """Lenient stock check — only blocks when stock is KNOWN to be zero."""
    try:
        from shopman.shop.projections import catalog_context

        raw = catalog_context.availability_for_sku(sku, channel_ref=platform)
    except Exception:
        logger.debug("social_publish_rules._has_promisable_stock degraded", exc_info=True)
        return True
    if raw is None:
        return True  # unknown → don't block
    if raw.get("availability_policy") == "demand_ok" or raw.get("is_planned"):
        return True
    total = raw.get("total_promisable") or 0
    try:
        return float(total) > 0
    except (TypeError, ValueError):
        return True
