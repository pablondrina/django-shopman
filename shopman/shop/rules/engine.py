"""
Rules engine — loads, caches, and registers active RuleConfigs.

## Governance model — two layers, intentionally separate

**Handlers** (static, boot-time):
    Registered once in `setup.register_all()` at `AppConfig.ready()`. These are
    the directive processors (NotificationSendHandler, ConfirmationTimeoutHandler,
    etc.) that wire the lifecycle together. They never change at runtime.

**Rules** (dynamic, DB-driven):
    `RuleConfig` rows in the database configure validators and pricing modifiers.
    Operators can toggle rules, set params, and restrict to channels — all without
    a deploy. `register_active_rules()` loads them at boot and the cache is
    invalidated on every `RuleConfig` save/delete.

The split is intentional: handlers express *how the system works*; rules express
*how the business behaves*. Changing a rule is an operational action; changing a
handler is a code change.
"""

from __future__ import annotations

import importlib
import logging
import threading

from django.core.cache import cache
from django.db import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)

CACHE_KEY = "shopman_rules"
CACHE_TIMEOUT = 60 * 60  # 1 hour (invalidated on save)
_boot_lock = threading.Lock()
_bootstrapped = False


def get_active_rules(channel=None, stage=None):
    """Return active RuleConfigs, optionally filtered by channel and stage.

    Uses Django cache, invalidated by post_save signal on RuleConfig.
    """
    from shopman.shop.models import RuleConfig

    cached = cache.get(CACHE_KEY)
    if cached is None:
        cached = list(
            RuleConfig.objects.filter(enabled=True)
            .prefetch_related("channels")
            .order_by("priority")
        )
        cache.set(CACHE_KEY, cached, CACHE_TIMEOUT)

    rules = cached

    if channel is not None:
        rules = [
            r for r in rules
            if not r.channels.exists() or r.channels.filter(pk=channel.pk).exists()
        ]

    if stage is not None:
        filtered = []
        for r in rules:
            rule_cls = _import_rule_class(r.rule_path)
            if rule_cls is not None and getattr(rule_cls, "rule_type", None) == stage:
                filtered.append(r)
        rules = filtered

    return rules


def load_rule(rule_config):
    """Import and instantiate a rule class from rule_config.rule_path.

    Passes rule_config.params as kwargs to the constructor.
    """
    cls = _import_rule_class(rule_config.rule_path)
    if cls is None:
        raise ImportError(f"Cannot import rule: {rule_config.rule_path}")
    return cls(**(rule_config.params or {}))


def register_active_rules():
    """Register active validator rules in the orderman registry.

    Called at boot (apps.py ready), AFTER channels.setup.register_all().

    For R5, only registers VALIDATORS (BusinessHours, MinimumOrder) that are
    not registered anywhere else. Pricing modifiers continue to be registered
    via channels.setup — R8 will migrate everything.
    """
    from shopman.orderman import registry

    from shopman.shop.models import RuleConfig

    active = RuleConfig.objects.filter(enabled=True).order_by("priority")

    registered_validator_codes = {v.code for v in registry.get_validators()}

    for rc in active:
        rule = _safe_load(rc)
        if rule is None:
            continue

        if getattr(rule, "rule_type", None) != "validator":
            continue

        if rule.code in registered_validator_codes:
            continue

        try:
            registry.register_validator(rule)
            registered_validator_codes.add(rule.code)
            logger.info("rules.engine: Registered validator %s", rule.code)
        except TypeError:
            logger.warning("rules.engine: %s does not satisfy Validator protocol", rc.rule_path)


def bootstrap_active_rules() -> None:
    """Register DB-driven validators once, after the DB connection is ready."""
    global _bootstrapped

    if _bootstrapped:
        return

    with _boot_lock:
        if _bootstrapped:
            return
        try:
            register_active_rules()
            _bootstrapped = True
        except (OperationalError, ProgrammingError):
            logger.debug("rules.engine: rules table not ready yet; bootstrap deferred.")
        except Exception:
            logger.debug("rules.engine: deferred bootstrap failed; will retry later.", exc_info=True)


def invalidate_rules_cache(sender, **kwargs):
    """Signal handler — invalidate rules cache on RuleConfig save/delete."""
    cache.delete(CACHE_KEY)


def _import_rule_class(dotted_path):
    """Import a rule class from a dotted path. Returns None on failure."""
    try:
        module_path, class_name = dotted_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    except (ImportError, AttributeError, ValueError):
        logger.warning("rules.engine: Could not import %s", dotted_path)
        return None


def _safe_load(rule_config):
    """Load a rule, returning None on failure."""
    try:
        return load_rule(rule_config)
    except Exception:
        logger.warning("rules.engine: Failed to load rule %s", rule_config.code, exc_info=True)
        return None
