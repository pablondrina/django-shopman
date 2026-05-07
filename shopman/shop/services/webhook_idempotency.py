"""Durable replay guard for inbound webhooks.

Uses Orderman's existing IdempotencyKey table so webhook dedupe has the same
database-backed durability as checkout commits.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone
from shopman.orderman.models import IdempotencyKey

DEFAULT_WEBHOOK_TTL = timedelta(days=30)
DEFAULT_IN_PROGRESS_TTL = timedelta(minutes=15)


@dataclass(frozen=True)
class WebhookClaim:
    record: IdempotencyKey
    done_expires_at: datetime | None = None
    replayed: bool = False
    in_progress: bool = False
    response_code: int = 200
    response_body: dict[str, Any] | None = None

    @property
    def can_process(self) -> bool:
        return not self.replayed and not self.in_progress


def stable_webhook_key(*parts: Any) -> str:
    """Return a stable, fixed-length key for provider ids or raw payloads."""
    digest = hashlib.sha256()
    for part in parts:
        if isinstance(part, bytes):
            chunk = part
        else:
            chunk = str(part or "").encode("utf-8")
        digest.update(chunk)
        digest.update(b"\x1f")
    return digest.hexdigest()


def claim(
    scope: str,
    key: str,
    *,
    ttl: timedelta = DEFAULT_WEBHOOK_TTL,
    in_progress_ttl: timedelta = DEFAULT_IN_PROGRESS_TTL,
) -> WebhookClaim:
    """Claim a webhook event for processing, or return its cached result."""
    normalized_scope = str(scope or "").strip()
    normalized_key = _normalize_key(key)
    if not normalized_scope:
        raise ValueError("webhook idempotency scope is required")
    if len(normalized_scope) > 64:
        raise ValueError("webhook idempotency scope must fit IdempotencyKey.scope")

    now = timezone.now()
    done_expires_at = now + ttl
    in_progress_expires_at = now + in_progress_ttl
    with transaction.atomic():
        try:
            record = IdempotencyKey.objects.select_for_update().get(
                scope=normalized_scope,
                key=normalized_key,
            )
            return _claim_existing(
                record,
                done_expires_at=done_expires_at,
                in_progress_expires_at=in_progress_expires_at,
            )
        except IdempotencyKey.DoesNotExist:
            try:
                record = IdempotencyKey.objects.create(
                    scope=normalized_scope,
                    key=normalized_key,
                    status="in_progress",
                    expires_at=in_progress_expires_at,
                )
            except IntegrityError:
                record = IdempotencyKey.objects.select_for_update().get(
                    scope=normalized_scope,
                    key=normalized_key,
                )
                return _claim_existing(
                    record,
                    done_expires_at=done_expires_at,
                    in_progress_expires_at=in_progress_expires_at,
                )
            return WebhookClaim(record=record, done_expires_at=done_expires_at)


def mark_done(
    claim_result: WebhookClaim,
    *,
    response_body: dict[str, Any] | None = None,
    response_code: int = 200,
) -> None:
    """Persist the response for future replays."""
    if not claim_result.can_process:
        return
    record = claim_result.record
    record.status = "done"
    record.response_code = response_code
    record.response_body = response_body or {"status": "ok"}
    if claim_result.done_expires_at is not None:
        record.expires_at = claim_result.done_expires_at
        record.save(update_fields=["status", "response_code", "response_body", "expires_at"])
        return
    record.save(update_fields=["status", "response_code", "response_body"])


def mark_failed(claim_result: WebhookClaim) -> None:
    """Allow a provider retry to process this webhook again later."""
    if not claim_result.can_process:
        return
    record = claim_result.record
    record.status = "failed"
    record.save(update_fields=["status"])


def _claim_existing(
    record: IdempotencyKey,
    *,
    done_expires_at,
    in_progress_expires_at,
) -> WebhookClaim:
    now = timezone.now()
    expired = record.expires_at is not None and record.expires_at <= now

    if record.status == "done" and record.response_body is not None and not expired:
        return WebhookClaim(
            record=record,
            replayed=True,
            response_code=record.response_code or 200,
            response_body=record.response_body,
        )

    if record.status == "in_progress" and not expired:
        return WebhookClaim(
            record=record,
            in_progress=True,
            response_code=409,
            response_body={
                "status": "in_progress",
                "detail": "Webhook event is already being processed.",
            },
        )

    record.status = "in_progress"
    record.response_code = None
    record.response_body = None
    record.expires_at = in_progress_expires_at
    record.save(update_fields=["status", "response_code", "response_body", "expires_at"])
    return WebhookClaim(record=record, done_expires_at=done_expires_at)


def _normalize_key(key: str) -> str:
    normalized = str(key or "").strip()
    if not normalized:
        raise ValueError("webhook idempotency key is required")
    if len(normalized) <= 128:
        return normalized
    return stable_webhook_key(normalized)


__all__ = [
    "WebhookClaim",
    "claim",
    "mark_done",
    "mark_failed",
    "stable_webhook_key",
]
