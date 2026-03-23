"""
Shopman Stock Handlers — Handlers de diretiva para estoque.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.utils import timezone

from shopman.ordering.ids import generate_action_id, generate_issue_id
from shopman.ordering.models import Directive
from shopman.ordering.services import SessionWriteService

from .protocols import StockBackend

logger = logging.getLogger(__name__)


class StockHoldHandler:
    """
    Handler que executa verificação + reserva de estoque.

    Topic: stock.hold

    Comportamento idempotente:
    - Antes de criar novos holds, libera os anteriores da mesma sessão
    - Um hold por SKU por sessão (quantidades são agregadas)
    - Executar N vezes = mesmo resultado
    """

    topic = "stock.hold"
    DEFAULT_HOLD_TTL_MINUTES = 15

    def __init__(self, backend: StockBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.ordering.models import Session

        payload = message.payload
        session_key = payload["session_key"]
        channel_ref = payload["channel_ref"]
        expected_rev = payload["rev"]

        try:
            session = Session.objects.select_related("channel").get(
                session_key=session_key,
                channel__ref=channel_ref,
            )
        except Session.DoesNotExist:
            logger.error(
                "StockHoldHandler: Session not found. "
                f"session_key={session_key}, channel_ref={channel_ref}"
            )
            message.status = "failed"
            message.last_error = f"Session not found: {channel_ref}:{session_key}"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        if session.rev != expected_rev:
            logger.warning(
                "StockHoldHandler: rev mismatch (stale directive). "
                f"session_key={session_key}, expected_rev={expected_rev}, "
                f"session.rev={session.rev}"
            )
            message.status = "failed"
            message.last_error = f"Stale directive: expected rev {expected_rev}, found {session.rev}"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        if session.state != "open":
            logger.info(
                "StockHoldHandler: session not open, skipping. "
                f"session_key={session_key}, state={session.state}"
            )
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        # IDEMPOTÊNCIA: Libera holds anteriores desta sessão antes de criar novos.
        if hasattr(self.backend, "release_holds_for_reference"):
            self.backend.release_holds_for_reference(session_key)

        # Agrega quantidades por SKU (um hold por SKU por sessão)
        aggregated_items = self._aggregate_items_by_sku(session.items)

        # Check for pre-order target_date
        target_date = self._get_target_date(session)

        issues: list[dict] = []
        check_result: dict[str, Any] = {"items": [], "holds": []}
        hold_expirations: list[datetime] = []
        hold_ttl = self._get_hold_ttl(session.channel)

        for sku, item_data in aggregated_items.items():
            qty = item_data["qty"]
            line_ids = item_data["line_ids"]

            check_kwargs: dict[str, Any] = {"sku": sku, "quantity": qty}
            if target_date:
                check_kwargs["target_date"] = target_date
            availability = self.backend.check_availability(**check_kwargs)
            check_result["items"].append(
                {
                    "sku": sku,
                    "qty": float(qty),
                    "available": availability.available,
                    "available_qty": float(availability.available_qty),
                }
            )

            if not availability.available:
                for line_id in line_ids:
                    issues.append(
                        self._build_issue(
                            sku=sku,
                            line_id=line_id,
                            requested_qty=qty,
                            available_qty=availability.available_qty,
                            message=availability.message,
                            session_rev=session.rev,
                        )
                    )
                continue

            hold_result = self.backend.create_hold(
                sku=sku,
                quantity=qty,
                expires_at=timezone.now() + hold_ttl,
                reference=session_key,
                target_date=target_date,
                channel_ref=channel_ref,
            )
            if not hold_result.success or not hold_result.hold_id:
                for line_id in line_ids:
                    issues.append(
                        self._build_issue(
                            sku=sku,
                            line_id=line_id,
                            requested_qty=qty,
                            available_qty=Decimal("0"),
                            message=hold_result.message or "Não foi possível reservar estoque.",
                            session_rev=session.rev,
                        )
                    )
                continue

            hold_payload = {"sku": sku, "hold_id": hold_result.hold_id, "qty": float(qty)}
            if hold_result.is_planned:
                hold_payload["is_planned"] = True
            if hold_result.expires_at:
                hold_payload["expires_at"] = hold_result.expires_at.isoformat()
                hold_expirations.append(hold_result.expires_at)
            check_result["holds"].append(hold_payload)

        if hold_expirations:
            check_result["hold_expires_at"] = min(hold_expirations).isoformat()

        # Flag if any holds are against planned stock (no timeout yet)
        if any(h.get("is_planned") for h in check_result.get("holds", [])):
            check_result["has_planned_holds"] = True

        logger.info(
            f"StockHoldHandler: attempting to apply check result. "
            f"session_key={session_key}, expected_rev={expected_rev}, "
            f"issues_count={len(issues)}, holds_count={len(check_result.get('holds', []))}"
        )

        applied = SessionWriteService.apply_check_result(
            session_key=session_key,
            channel_ref=channel_ref,
            expected_rev=expected_rev,
            check_code="stock",
            check_payload=check_result,
            issues=issues,
        )

        if not applied:
            logger.warning(
                f"StockHoldHandler: check result NOT applied (stale_rev). "
                f"session_key={session_key}, expected_rev={expected_rev}, "
                f"issues_count={len(issues)}, holds_count={len(check_result.get('holds', []))}"
            )
        else:
            logger.info(
                f"StockHoldHandler: check result applied successfully. "
                f"session_key={session_key}, expected_rev={expected_rev}"
            )

        message.status = "done" if applied else "failed"
        message.last_error = "" if applied else "stale_rev"
        message.payload["holds"] = check_result.get("holds", [])
        message.save(update_fields=["status", "last_error", "payload", "updated_at"])

    def _get_hold_ttl(self, channel) -> timedelta:
        """
        Retorna TTL do hold baseado na config do canal.

        Cascata:
        1. Channel.config["stock"]["checkout_hold_expiration_minutes"]
        2. DEFAULT_HOLD_TTL_MINUTES (15)
        """
        try:
            from shopman.confirmation.service import calculate_hold_ttl
            return calculate_hold_ttl(channel)
        except Exception:
            return timedelta(minutes=self.DEFAULT_HOLD_TTL_MINUTES)

    def _get_target_date(self, session) -> date | None:
        """
        Extract target_date from session.data for pre-orders.
        """
        delivery_date_str = (session.data or {}).get("delivery_date")
        if not delivery_date_str:
            return None
        try:
            from datetime import date as date_type

            target = date_type.fromisoformat(delivery_date_str)
            if target > date_type.today():
                return target
        except (ValueError, TypeError):
            pass
        return None

    def _aggregate_items_by_sku(self, items: list[dict]) -> dict[str, dict]:
        """
        Agrega itens por SKU, somando quantidades.
        """
        aggregated: dict[str, dict] = {}
        for item in items:
            sku = item["sku"]
            qty = Decimal(str(item["qty"]))
            line_id = item["line_id"]

            if sku not in aggregated:
                aggregated[sku] = {"qty": Decimal("0"), "line_ids": []}

            aggregated[sku]["qty"] += qty
            aggregated[sku]["line_ids"].append(line_id)

        return aggregated

    def _build_issue(
        self,
        *,
        sku: str,
        line_id: str,
        requested_qty: Decimal,
        available_qty: Decimal,
        message: str | None,
        session_rev: int,
    ) -> dict:
        alternatives_data: list[dict] = []
        try:
            alternatives = self.backend.get_alternatives(sku, requested_qty)
            alternatives_data = [
                {
                    "sku": alt.sku,
                    "name": alt.name,
                    "available_qty": float(alt.available_qty),
                }
                for alt in alternatives
            ]
        except Exception:
            logger.debug("Failed to get alternatives for %s", sku)

        context: dict[str, Any] = {
            "line_id": line_id,
            "sku": sku,
            "requested_qty": float(requested_qty),
            "available_qty": float(available_qty),
            "actions": self._build_actions(
                line_id=line_id,
                requested_qty=requested_qty,
                available_qty=available_qty,
                session_rev=session_rev,
            ),
        }
        if alternatives_data:
            context["alternatives"] = alternatives_data

        return {
            "id": generate_issue_id(),
            "source": "stock",
            "code": "stock.insufficient",
            "blocking": True,
            "message": message or f"Estoque insuficiente para {sku}",
            "context": context,
        }

    def _build_actions(
        self,
        *,
        line_id: str,
        requested_qty: Decimal,
        available_qty: Decimal,
        session_rev: int,
    ) -> list[dict]:
        actions: list[dict] = []
        if available_qty > 0:
            actions.append(
                {
                    "id": generate_action_id(),
                    "label": f"Ajustar para {available_qty} unidade(s)",
                    "rev": session_rev,
                    "ops": [{"op": "set_qty", "line_id": line_id, "qty": float(available_qty)}],
                }
            )
        actions.append(
            {
                "id": generate_action_id(),
                "label": "Remover item",
                "rev": session_rev,
                "ops": [{"op": "remove_line", "line_id": line_id}],
            }
        )
        return actions


class StockCommitHandler:
    """
    Handler para confirmação de reservas de estoque.

    Topic: stock.commit
    """

    topic = "stock.commit"

    def __init__(self, backend: StockBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.ordering.models import Session

        payload = message.payload
        holds = payload.get("holds") or []
        order_ref = payload.get("order_ref")

        if not holds and payload.get("session_key") and payload.get("channel_ref"):
            try:
                session = Session.objects.get(
                    session_key=payload["session_key"],
                    channel__ref=payload["channel_ref"],
                )
                holds = (
                    session.data.get("checks", {})
                    .get("stock", {})
                    .get("result", {})
                    .get("holds", [])
                )
            except Session.DoesNotExist:
                holds = []

        if not holds:
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        errors: list[str] = []
        fulfilled: list[str] = []

        for hold in holds:
            hold_id = hold.get("hold_id")
            if not hold_id:
                continue

            # Skip planned holds
            if hold.get("is_planned"):
                logger.info(
                    "StockCommitHandler: skipping planned hold %s (order %s) — "
                    "will be fulfilled when production completes.",
                    hold_id, order_ref,
                )
                continue

            try:
                self.backend.fulfill_hold(hold_id, reference=order_ref)
                fulfilled.append(hold_id)
            except Exception as exc:
                error_msg = f"{hold_id}: {exc}"
                errors.append(error_msg)
                logger.error(
                    "StockCommitHandler: fulfill failed for hold %s (order %s): %s",
                    hold_id, order_ref, exc,
                )

        if errors:
            message.status = "failed"
            message.last_error = f"Fulfill errors ({len(errors)}/{len(holds)}): {'; '.join(errors[:5])}"[:500]
            message.save(update_fields=["status", "last_error", "updated_at"])
        else:
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
