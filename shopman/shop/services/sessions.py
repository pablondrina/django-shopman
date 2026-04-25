"""Order session orchestration facade.

Surfaces should use this module instead of calling Orderman write services
directly. Read projections may still query kernel models when that is the
clearest representation boundary.
"""

from __future__ import annotations

from shopman.orderman.ids import generate_idempotency_key, generate_session_key
from shopman.orderman.models import Session
from shopman.orderman.services.commit import CommitResult, CommitService
from shopman.orderman.services.modify import ModifyService

from shopman.shop.config import ChannelConfig
from shopman.shop.models import Channel


def new_session_key() -> str:
    """Return a canonical Orderman session key."""
    return generate_session_key()


def new_idempotency_key() -> str:
    """Return a canonical Orderman idempotency key."""
    return generate_idempotency_key()


def create_session(
    channel_ref: str,
    *,
    handle_type: str | None = None,
    handle_ref: str | None = None,
    data: dict | None = None,
    state: str = "open",
) -> Session:
    """Create an open Orderman session with resolved channel policies."""
    channel = Channel.objects.get(ref=channel_ref)
    config = ChannelConfig.for_channel(channel)
    return Session.objects.create(
        session_key=new_session_key(),
        channel_ref=channel.ref,
        state=state,
        pricing_policy=config.pricing.policy,
        edit_policy=config.editing.policy,
        handle_type=handle_type,
        handle_ref=handle_ref,
        data=data or {},
    )


def modify_session(
    *,
    session_key: str,
    channel_ref: str,
    ops: list[dict],
    ctx: dict | None = None,
    channel_config: dict | None = None,
) -> Session:
    """Apply canonical session operations through Orderman."""
    return ModifyService.modify_session(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=ops,
        ctx=ctx,
        channel_config=channel_config,
    )


def commit_session(
    *,
    session_key: str,
    channel_ref: str,
    idempotency_key: str,
    ctx: dict | None = None,
    channel_config: dict | None = None,
) -> CommitResult:
    """Commit a session through the canonical Orderman service."""
    return CommitService.commit(
        session_key=session_key,
        channel_ref=channel_ref,
        idempotency_key=idempotency_key,
        ctx=ctx,
        channel_config=channel_config,
    )


def assign_phone_handle(
    *,
    session_key: str,
    channel_ref: str,
    phone: str,
    abandon_existing: bool = True,
) -> None:
    """Attach an open session to a phone handle.

    When ``abandon_existing`` is true, older open sessions for the same phone
    and channel are abandoned so the phone has a single active cart/session.
    """
    if not phone:
        return
    try:
        session = Session.objects.get(session_key=session_key, channel_ref=channel_ref, state="open")
    except Session.DoesNotExist:
        return
    if abandon_existing:
        Session.objects.filter(
            channel_ref=session.channel_ref,
            handle_type="phone",
            handle_ref=phone,
            state="open",
        ).exclude(pk=session.pk).update(state="abandoned")
    session.handle_type = "phone"
    session.handle_ref = phone
    session.save(update_fields=["handle_type", "handle_ref"])


def assign_handle(
    *,
    session_key: str,
    channel_ref: str,
    handle_type: str,
    handle_ref: str,
) -> None:
    """Attach a generic handle to an open session."""
    Session.objects.filter(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
    ).update(handle_type=handle_type, handle_ref=handle_ref)


def abandon_session(*, session_key: str, channel_ref: str) -> bool:
    """Mark an open session as abandoned."""
    updated = Session.objects.filter(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
    ).update(state="abandoned")
    return bool(updated)
