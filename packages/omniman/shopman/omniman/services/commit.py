"""
CommitService — Fecha sessões e cria Orders.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from shopman.omniman import registry
from shopman.omniman.exceptions import CommitError, IdempotencyCacheHit, SessionError, ValidationError
from shopman.omniman.ids import generate_order_ref
from shopman.omniman.models import Directive, IdempotencyKey, Order, OrderItem, Session
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
        channel_config: dict | None = None,
    ) -> dict:
        """
        Fecha uma sessão e cria um Order.

        Args:
            session_key: Chave da sessão
            channel_ref: Código do canal
            idempotency_key: Chave de idempotência
            ctx: Contexto adicional
            channel_config: Config resolvido com cascade (canal←loja←defaults).
                Obrigatório em produção — fornecido pelo framework via ChannelConfig.for_channel().
                Testes podem omitir para usar comportamento padrão.

        Returns:
            dict com order_ref e dados do pedido

        Raises:
            CommitError: Se commit falhar
            SessionError: Se sessão não encontrada
        """
        ctx = ctx or {}
        idem_scope = f"commit:{channel_ref}"

        # 1. Check/create idempotency key (outside main transaction)
        try:
            idem = CommitService._acquire_idempotency_lock(idem_scope, idempotency_key)
        except IdempotencyCacheHit as cache_hit:
            # Cached response from previous successful commit
            return cache_hit.cached_response

        try:
            # 2. Execute commit in atomic transaction
            response = CommitService._do_commit(
                session_key=session_key,
                channel_ref=channel_ref,
                idempotency_key=idempotency_key,
                ctx=ctx,
                channel_config=channel_config,
            )

            # 3. Mark idempotency key as done (outside transaction)
            idem.status = "done"
            idem.response_body = response
            idem.response_code = 201
            idem.save(update_fields=["status", "response_body", "response_code"])

            return response

        except (CommitError, SessionError, ValidationError):
            # Mark idempotency key as failed (persists even if transaction rolled back)
            idem.status = "failed"
            idem.save(update_fields=["status"])
            raise

        except Exception as e:
            # Unexpected error - mark as failed and re-raise
            idem.status = "failed"
            idem.save(update_fields=["status"])
            logger.exception(f"Unexpected error in commit: {e}")
            raise

    @staticmethod
    def _acquire_idempotency_lock(scope: str, key: str) -> IdempotencyKey:
        """
        Acquire idempotency lock for a commit operation.

        Returns:
            IdempotencyKey with status="in_progress"

        Raises:
            IdempotencyCacheHit: If key exists and has cached response (not an error)
            CommitError: If key is already in progress
        """
        with transaction.atomic():
            try:
                idem = IdempotencyKey.objects.select_for_update(nowait=False).get(
                    scope=scope,
                    key=key,
                )
                # Key exists - check status
                if idem.status == "done" and idem.response_body:
                    raise IdempotencyCacheHit(idem.response_body)
                elif idem.status == "in_progress":
                    if idem.expires_at and idem.expires_at <= timezone.now():
                        # Orphaned key — allow retry
                        idem.status = "in_progress"
                        idem.expires_at = timezone.now() + timedelta(hours=24)
                        idem.save(update_fields=["status", "expires_at"])
                        return idem
                    raise CommitError(
                        code="in_progress",
                        message="Commit já está em andamento com esta chave",
                    )
                # Status is "failed" - allow retry
                idem.status = "in_progress"
                idem.save(update_fields=["status"])
                return idem

            except IdempotencyKey.DoesNotExist:
                # Create new key
                idem, created = IdempotencyKey.objects.get_or_create(
                    scope=scope,
                    key=key,
                    defaults={
                        "status": "in_progress",
                        "expires_at": timezone.now() + timedelta(hours=24),
                    },
                )
                if not created:
                    # Race condition: another request created it - re-check with lock
                    idem = IdempotencyKey.objects.select_for_update().get(pk=idem.pk)
                    if idem.status == "done" and idem.response_body:
                        raise IdempotencyCacheHit(idem.response_body)
                    elif idem.status == "in_progress":
                        raise CommitError(
                            code="in_progress",
                            message="Commit já está em andamento com esta chave",
                        )
                    # Status is "failed" - allow retry
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
        channel_config: dict | None = None,
    ) -> dict:
        """
        Execute the actual commit logic in an atomic transaction.
        """
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
            # Return existing order (idempotency)
            order = Order.objects.filter(session_key=session_key, channel=channel).first()
            if order:
                return {"order_ref": order.ref, "status": "already_committed"}
            raise CommitError(code="already_committed", message="Sessão já foi fechada")

        if session.state == "abandoned":
            raise CommitError(code="abandoned", message="Sessão foi abandonada")

        # Check required checks are fresh
        # channel_config must always be supplied by the framework caller (cascade resolvido).
        # Kernel não lê channel.config — o framework passa o config resolvido como parâmetro.
        effective_config = channel_config or {}
        required_checks = effective_config.get("rules", {}).get("checks", [])
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

        # H08: Validate session has items before commit
        if not session.items:
            raise CommitError(
                code="empty_session",
                message="Sessão sem itens não pode ser confirmada",
                context={"session_key": session_key},
            )

        # Build order.data from session.data (key fields for handlers)
        order_data = {}
        session_data = session.data or {}
        for key in (
            "customer", "fulfillment_type", "delivery_address",
            "delivery_address_structured", "delivery_date",
            "delivery_time_slot", "order_notes",
            "origin_channel", "payment",
            "delivery_fee_q",
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
                "lifecycle": effective_config.get("lifecycle", {}),
            },
            data=order_data,
            total_q=CommitService._calculate_total(session.items),
        )

        for item in session.items:
            # Usa line_total_q existente ou calcula se não existir
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

        # Create event (via emit_event para seq automático)
        order.emit_event(
            event_type="created",
            actor=ctx.get("actor", "system"),
            payload={"from_session": session_key},
        )

        # Emit signal
        from shopman.omniman.signals import order_changed
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

        # Preorder reminder: D-1 notification if delivery_date is future
        if order_data.get("is_preorder") and order_data.get("delivery_date"):
            from datetime import date as date_type, datetime as datetime_type, time as time_type

            try:
                delivery_dt = date_type.fromisoformat(order_data["delivery_date"])
                reminder_date = delivery_dt - timedelta(days=1)
                # Schedule reminder for 09:00 on D-1
                reminder_at = datetime_type.combine(reminder_date, time_type(9, 0))
                if timezone.is_naive(reminder_at):
                    from datetime import timezone as dt_timezone
                    # Use server timezone (BRT = UTC-3)
                    reminder_at = timezone.make_aware(reminder_at)

                customer_name = order_data.get("customer", {}).get("name", "")
                time_slot = order_data.get("delivery_time_slot", "")
                items_summary = ", ".join(
                    f"{item.get('qty', '')}x {item.get('name', item.get('sku', ''))}"
                    for item in session.items[:5]
                )

                Directive.objects.create(
                    topic="notification.send",
                    available_at=reminder_at,
                    payload={
                        "order_ref": order.ref,
                        "template": "preorder_reminder",
                        "context": {
                            "customer_name": customer_name,
                            "delivery_date": order_data["delivery_date"],
                            "delivery_time_slot": time_slot,
                            "items_summary": items_summary,
                            "fulfillment_type": order_data.get("fulfillment_type", "pickup"),
                        },
                    },
                )
            except (ValueError, TypeError):
                pass

        return {
            "order_ref": order.ref,
            "status": "committed",
            "total_q": order.total_q,
            "items_count": len(session.items),
        }

    @staticmethod
    def _calculate_total(items: list[dict]) -> int:
        """
        Calcula total do pedido.

        Usa line_total_q se existir (pode ter sido calculado com lógica
        customizada como descontos). Se não existir, calcula qty * unit_price_q.
        """
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
        """
        Parse ISO datetime string to timezone-aware datetime.

        If the input has no timezone info, it's assumed to be in UTC
        (not the server's local timezone) to ensure consistent behavior
        regardless of server configuration.
        """
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return None
        if timezone.is_naive(dt):
            # Assume UTC for naive datetimes (safer than assuming local TZ)
            # Using datetime.timezone.utc (stdlib, no pytz needed)
            from datetime import timezone as dt_timezone
            dt = dt.replace(tzinfo=dt_timezone.utc)
        return dt
