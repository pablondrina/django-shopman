"""
CommitService — Fecha sessões e cria Orders.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from shopman.ordering import registry
from shopman.ordering.exceptions import CommitError, IdempotencyCacheHit, SessionError, ValidationError
from shopman.ordering.ids import generate_order_ref
from shopman.ordering.models import IdempotencyKey, Order, OrderItem, Session
from shopman.ordering.services.directive import DirectiveService
from shopman.utils.monetary import monetary_mult


logger = logging.getLogger(__name__)


class CommitService:
    """
    Serviço para fechar sessões e criar Orders.

    Pipeline:
    1. Check idempotency (return cached if exists)
    2. Validate session is open
    3. Check required checks are fresh
    4. Check no blocking issues
    5. Run validators (stage="commit")
    6. Create Order + OrderItems
    7. Mark session as committed
    8. Enqueue post-commit directives
    9. Cache response in IdempotencyKey
    """

    @staticmethod
    def commit(
        session_key: str,
        channel_ref: str,
        idempotency_key: str,
        ctx: dict | None = None,
    ) -> dict:
        ctx = ctx or {}
        idem_scope = f"commit:{channel_ref}"

        # 1. Check/create idempotency key
        try:
            idem = CommitService._acquire_idempotency_lock(idem_scope, idempotency_key)
        except IdempotencyCacheHit as cache_hit:
            return cache_hit.cached_response

        try:
            # 2. Execute commit
            response = CommitService._do_commit(
                session_key=session_key,
                channel_ref=channel_ref,
                idempotency_key=idempotency_key,
                ctx=ctx,
            )

            # 3. Mark idempotency key as done
            idem.status = "done"
            idem.response_body = response
            idem.response_code = 201
            idem.save(update_fields=["status", "response_body", "response_code"])

            return response

        except (CommitError, SessionError, ValidationError):
            idem.status = "failed"
            idem.save(update_fields=["status"])
            raise

        except Exception as e:
            idem.status = "failed"
            idem.save(update_fields=["status"])
            logger.exception(f"Unexpected error in commit: {e}")
            raise

    @staticmethod
    def _acquire_idempotency_lock(scope: str, key: str) -> IdempotencyKey:
        with transaction.atomic():
            try:
                idem = IdempotencyKey.objects.select_for_update(nowait=False).get(
                    scope=scope,
                    key=key,
                )
                if idem.status == "done" and idem.response_body:
                    raise IdempotencyCacheHit(idem.response_body)
                elif idem.status == "in_progress":
                    if idem.expires_at and idem.expires_at <= timezone.now():
                        idem.status = "in_progress"
                        idem.expires_at = timezone.now() + timedelta(hours=24)
                        idem.save(update_fields=["status", "expires_at"])
                        return idem
                    raise CommitError(
                        code="in_progress",
                        message="Commit já está em andamento com esta chave",
                    )
                idem.status = "in_progress"
                idem.save(update_fields=["status"])
                return idem

            except IdempotencyKey.DoesNotExist:
                idem, created = IdempotencyKey.objects.get_or_create(
                    scope=scope,
                    key=key,
                    defaults={
                        "status": "in_progress",
                        "expires_at": timezone.now() + timedelta(hours=24),
                    },
                )
                if not created:
                    idem = IdempotencyKey.objects.select_for_update().get(pk=idem.pk)
                    if idem.status == "done" and idem.response_body:
                        raise IdempotencyCacheHit(idem.response_body)
                    elif idem.status == "in_progress":
                        raise CommitError(
                            code="in_progress",
                            message="Commit já está em andamento com esta chave",
                        )
                    idem.status = "in_progress"
                    idem.save(update_fields=["status"])
                return idem

    @staticmethod
    @transaction.atomic
    def _do_commit(
        session_key: str,
        channel_ref: str,
        idempotency_key: str,
        ctx: dict,
    ) -> dict:
        # Lock session
        try:
            session = Session.objects.select_for_update().get(
                session_key=session_key,
                channel__ref=channel_ref,
            )
        except Session.DoesNotExist:
            raise SessionError(
                code="not_found",
                message=f"Sessão não encontrada: {channel_ref}:{session_key}",
            )

        channel = session.channel

        # Validate session is open
        if session.state == "committed":
            order = Order.objects.filter(session_key=session_key, channel=channel).first()
            if order:
                return {"order_ref": order.ref, "status": "already_committed"}
            raise CommitError(code="already_committed", message="Sessão já foi fechada")

        if session.state == "abandoned":
            raise CommitError(code="abandoned", message="Sessão foi abandonada")

        # Check required checks are fresh
        required_checks = channel.config.get("required_checks_on_commit", [])
        checks = session.data.get("checks", {})
        now = timezone.now()

        for check_code in required_checks:
            check = checks.get(check_code)
            if not check:
                raise CommitError(
                    code="missing_check",
                    message=f"Check obrigatório não encontrado: {check_code}",
                    context={"check_code": check_code},
                )
            if check.get("rev") != session.rev:
                raise CommitError(
                    code="stale_check",
                    message=f"Check desatualizado: {check_code}",
                    context={
                        "check_code": check_code,
                        "check_rev": check.get("rev"),
                        "session_rev": session.rev,
                    },
                )
            result = check.get("result") or {}
            deadline = result.get("hold_expires_at")
            if deadline:
                expires_dt = CommitService._parse_iso_datetime(deadline)
                if expires_dt is not None and expires_dt <= now:
                    raise CommitError(
                        code="hold_expired",
                        message="Reserva expirada para este check.",
                        context={"check_code": check_code, "expires_at": deadline},
                    )
            for hold in result.get("holds", []):
                expires_at = hold.get("expires_at")
                if not expires_at:
                    continue
                expires_dt = CommitService._parse_iso_datetime(expires_at)
                if expires_dt is not None and expires_dt <= now:
                    raise CommitError(
                        code="hold_expired",
                        message="Reserva expirada para este check.",
                        context={"check_code": check_code, "hold_id": hold.get("hold_id"), "expires_at": expires_at},
                    )

        # Check no blocking issues
        issues = session.data.get("issues", [])
        blocking = [i for i in issues if i.get("blocking")]
        if blocking:
            raise CommitError(
                code="blocking_issues",
                message="Existem issues bloqueantes",
                context={"issues": blocking},
            )

        # Run validators (stage="commit")
        for validator in registry.get_validators(stage="commit"):
            validator.validate(channel=channel, session=session, ctx=ctx)

        # Validate session has items
        if not session.items:
            raise CommitError(
                code="empty_session",
                message="Sessão sem itens não pode ser confirmada",
                context={"session_key": session_key},
            )

        # Build order.data from session.data
        order_data = {}
        session_data = session.data or {}
        for key in (
            "customer", "fulfillment_type", "delivery_address",
            "delivery_date", "delivery_time_slot", "order_notes",
        ):
            if key in session_data:
                order_data[key] = session_data[key]

        # Compute is_preorder flag
        delivery_date_str = session_data.get("delivery_date")
        if delivery_date_str:
            from datetime import date as date_type
            try:
                delivery_dt = date_type.fromisoformat(delivery_date_str)
                order_data["is_preorder"] = delivery_dt > timezone.now().date()
            except (ValueError, TypeError):
                pass

        # Create Order + OrderItems
        order = Order.objects.create(
            ref=generate_order_ref(),
            channel=channel,
            session_key=session_key,
            handle_type=session.handle_type,
            handle_ref=session.handle_ref,
            status=Order.Status.NEW,
            snapshot={
                "items": session.items,
                "data": session.data,
                "pricing": session.pricing,
                "rev": session.rev,
            },
            data=order_data,
            total_q=CommitService._calculate_total(session.items),
        )

        for item in session.items:
            line_total = item.get("line_total_q")
            if line_total is None:
                line_total = monetary_mult(Decimal(str(item["qty"])), item.get("unit_price_q", 0))

            OrderItem.objects.create(
                order=order,
                line_id=item["line_id"],
                sku=item["sku"],
                name=item.get("name", ""),
                qty=Decimal(str(item["qty"])),
                unit_price_q=item.get("unit_price_q", 0),
                line_total_q=int(line_total),
                meta=item.get("meta", {}),
            )

        # Create event
        order.emit_event(
            event_type="created",
            actor=ctx.get("actor", "system"),
            payload={"from_session": session_key},
        )

        # Emit signal
        from shopman.ordering.signals import order_changed
        order_changed.send(
            sender=Order,
            order=order,
            event_type="created",
            actor=ctx.get("actor", "system"),
        )

        # Mark session as committed
        session.state = "committed"
        session.committed_at = timezone.now()
        session.commit_token = idempotency_key
        session.save()

        # Enqueue post-commit directives
        post_commit_directives = channel.config.get("post_commit_directives", [])
        notification_template = channel.config.get("notification_template")
        stock_holds = None
        stock_check = checks.get("stock")
        if stock_check:
            stock_holds = (stock_check.get("result") or {}).get("holds")
        for topic in post_commit_directives:
            payload = {
                "order_ref": order.ref,
                "channel_ref": channel.ref,
                "session_key": session.session_key,
            }
            if topic == "stock.commit" and stock_holds:
                payload["holds"] = stock_holds
            if topic == "stock.hold":
                payload["rev"] = session.rev
                payload["items"] = [
                    {"sku": item["sku"], "qty": item["qty"]}
                    for item in session.items
                ]
            if topic == "notification.send" and notification_template:
                payload["notification_template"] = notification_template
            DirectiveService.enqueue(topic=topic, payload=payload)

        return {
            "order_ref": order.ref,
            "order_id": order.pk,
            "status": "committed",
            "total_q": order.total_q,
            "items_count": len(session.items),
        }

    @staticmethod
    @transaction.atomic
    def abandon(
        session_key: str,
        channel_ref: str,
        ctx: dict | None = None,
    ) -> dict:
        """
        Abandona uma sessão aberta, liberando handles e resources.

        - Se já abandoned → noop (retorna status "already_abandoned").
        - Se já committed → erro.
        - Marca state="abandoned", registra evento no histórico,
          e enqueue post_abandon_directives do channel config.
        """
        ctx = ctx or {}

        try:
            session = Session.objects.select_for_update().get(
                session_key=session_key,
                channel__ref=channel_ref,
            )
        except Session.DoesNotExist:
            raise SessionError(
                code="not_found",
                message=f"Sessão não encontrada: {channel_ref}:{session_key}",
            )

        channel = session.channel

        if session.state == "abandoned":
            return {"session_key": session_key, "status": "already_abandoned"}

        if session.state == "committed":
            raise CommitError(
                code="already_committed",
                message="Sessão já foi fechada e não pode ser abandonada",
            )

        # Mark as abandoned
        session.state = "abandoned"

        # Emit history event
        history = session.data.get("history", [])
        history.append({
            "event": "abandoned",
            "actor": ctx.get("actor", "system"),
            "at": timezone.now().isoformat(),
        })
        session.data = {**session.data, "history": history}
        session.save()

        # Enqueue post_abandon_directives
        post_abandon_directives = channel.config.get("post_abandon_directives", [])
        for topic in post_abandon_directives:
            payload = {
                "channel_ref": channel.ref,
                "session_key": session.session_key,
            }
            DirectiveService.enqueue(topic=topic, payload=payload)

        return {"session_key": session_key, "status": "abandoned"}

    @staticmethod
    def _calculate_total(items: list[dict]) -> int:
        total = 0
        for item in items:
            line_total = item.get("line_total_q")
            if line_total is not None:
                total += int(line_total)
            else:
                qty = Decimal(str(item.get("qty", 0)))
                price = item.get("unit_price_q", 0)
                total += monetary_mult(qty, price)
        return total

    @staticmethod
    def _parse_iso_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return None
        if timezone.is_naive(dt):
            from datetime import timezone as dt_timezone
            dt = dt.replace(tzinfo=dt_timezone.utc)
        return dt
