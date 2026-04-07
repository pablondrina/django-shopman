"""
Stock handlers — reserva e commit de estoque + StockCheck.

Inline de shopman.inventory.handlers.
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
from shopman.protocols import StockBackend
from shopman.topics import STOCK_COMMIT, STOCK_HOLD

logger = logging.getLogger(__name__)


class StockHoldHandler:
    """Handler que executa verificação + reserva de estoque. Topic: stock.hold"""

    topic = STOCK_HOLD
    DEFAULT_HOLD_TTL_MINUTES = 15

    def __init__(self, backend: StockBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.ordering.models import Session

        payload = message.payload
        session_key = payload.get("session_key")
        channel_ref = payload.get("channel_ref")

        # Lifecycle pipeline may only pass order_ref — resolve session from order
        if not session_key and payload.get("order_ref"):
            from shopman.ordering.models import Order

            try:
                order = Order.objects.get(ref=payload["order_ref"])
                session_key = order.session_key
                channel_ref = channel_ref or order.channel.ref
            except Order.DoesNotExist:
                pass

        if not session_key or not channel_ref:
            message.status = "done"
            message.last_error = "No session_key available — skipping stock hold."
            message.save(update_fields=["status", "last_error", "updated_at"])
            logger.info("StockHoldHandler: skipping directive %s — no session_key", message.pk)
            return

        expected_rev = payload.get("rev")

        try:
            session = Session.objects.select_related("channel").get(
                session_key=session_key, channel__ref=channel_ref,
            )
        except Session.DoesNotExist:
            message.status = "failed"
            message.last_error = f"Session not found: {channel_ref}:{session_key}"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        if expected_rev is not None and session.rev != expected_rev:
            message.status = "failed"
            message.last_error = f"Stale directive: expected rev {expected_rev}, found {session.rev}"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return
        if expected_rev is None:
            expected_rev = session.rev

        if session.state != "open":
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        # IDEMPOTÊNCIA: Libera holds anteriores desta sessão
        if hasattr(self.backend, "release_holds_for_reference"):
            self.backend.release_holds_for_reference(session_key)

        aggregated_items = self._aggregate_items_by_sku(session.items)
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
                check_kwargs["safety_margin"] = self._get_safety_margin(session.channel)
            allowed_positions = self._get_allowed_positions(session.channel)
            if allowed_positions is not None:
                check_kwargs["allowed_positions"] = allowed_positions
            availability = self.backend.check_availability(**check_kwargs)
            check_result["items"].append({
                "sku": sku, "qty": float(qty),
                "available": availability.available, "available_qty": float(availability.available_qty),
            })

            if not availability.available:
                for line_id in line_ids:
                    issues.append(self._build_issue(
                        sku=sku, line_id=line_id, requested_qty=qty,
                        available_qty=availability.available_qty,
                        message=availability.message, session_rev=session.rev,
                    ))
                continue

            hold_kwargs: dict[str, Any] = dict(
                sku=sku, quantity=qty,
                expires_at=timezone.now() + hold_ttl,
                reference=session_key, target_date=target_date, channel_ref=channel_ref,
            )
            if target_date:
                hold_kwargs["planned_hold_ttl_hours"] = self._get_planned_hold_ttl(session.channel)
            hold_result = self.backend.create_hold(**hold_kwargs)
            if not hold_result.success or not hold_result.hold_id:
                for line_id in line_ids:
                    issues.append(self._build_issue(
                        sku=sku, line_id=line_id, requested_qty=qty,
                        available_qty=Decimal("0"),
                        message=hold_result.message or "Não foi possível reservar estoque.",
                        session_rev=session.rev,
                    ))
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

        if any(h.get("is_planned") for h in check_result.get("holds", [])):
            check_result["has_planned_holds"] = True

        applied = SessionWriteService.apply_check_result(
            session_key=session_key, channel_ref=channel_ref,
            expected_rev=expected_rev, check_code="stock",
            check_payload=check_result, issues=issues,
        )

        message.status = "done" if applied else "failed"
        message.last_error = "" if applied else "stale_rev"
        message.payload["holds"] = check_result.get("holds", [])
        message.save(update_fields=["status", "last_error", "payload", "updated_at"])

    def _get_allowed_positions(self, channel) -> list[str] | None:
        config = channel.config or {}
        return config.get("stock", {}).get("allowed_positions")

    def _get_safety_margin(self, channel) -> int:
        from shopman.confirmation import get_safety_margin

        return get_safety_margin(channel)

    def _get_planned_hold_ttl(self, channel) -> int:
        config = channel.config or {}
        return config.get("stock", {}).get("planned_hold_ttl_hours", 48)

    def _get_hold_ttl(self, channel) -> timedelta:
        try:
            config = channel.config or {}
            stock_config = config.get("stock", {})
            minutes = stock_config.get("checkout_hold_expiration_minutes")
            if minutes:
                return timedelta(minutes=minutes)
        except Exception:
            pass
        return timedelta(minutes=self.DEFAULT_HOLD_TTL_MINUTES)

    def _get_target_date(self, session) -> date | None:
        delivery_date_str = (session.data or {}).get("delivery_date")
        if not delivery_date_str:
            return None
        try:
            target = date.fromisoformat(delivery_date_str)
            if target > date.today():
                return target
        except (ValueError, TypeError):
            pass
        return None

    def _aggregate_items_by_sku(self, items: list[dict]) -> dict[str, dict]:
        aggregated: dict[str, dict] = {}
        for item in items:
            sku = item["sku"]
            qty = Decimal(str(item["qty"]))
            line_id = item["line_id"]

            # Bundle expansion: reserve components, not the bundle itself
            expanded = self._expand_bundle(sku, qty)
            if expanded:
                for comp in expanded:
                    comp_sku = comp["sku"]
                    if comp_sku not in aggregated:
                        aggregated[comp_sku] = {"qty": Decimal("0"), "line_ids": []}
                    aggregated[comp_sku]["qty"] += comp["qty"]
                    aggregated[comp_sku]["line_ids"].append(line_id)
            else:
                if sku not in aggregated:
                    aggregated[sku] = {"qty": Decimal("0"), "line_ids": []}
                aggregated[sku]["qty"] += qty
                aggregated[sku]["line_ids"].append(line_id)
        return aggregated

    def _expand_bundle(self, sku: str, qty: Decimal) -> list[dict] | None:
        """Expand bundle into components. Returns None if not a bundle."""
        try:
            from shopman.offering.service import CatalogService

            return CatalogService.expand(sku, qty)
        except Exception:
            return None

    def _build_issue(self, *, sku, line_id, requested_qty, available_qty, message, session_rev) -> dict:
        alternatives_data: list[dict] = []
        try:
            from shopman.services.alternatives import find as _find_alternatives

            alts = _find_alternatives(sku, qty=requested_qty, limit=4)
            alternatives_data = [
                {"sku": a["sku"], "name": a["name"], "available_qty": float(a["available_qty"])}
                for a in alts
            ]
        except Exception:
            pass

        context: dict[str, Any] = {
            "line_id": line_id, "sku": sku,
            "requested_qty": float(requested_qty), "available_qty": float(available_qty),
            "actions": self._build_actions(
                line_id=line_id, requested_qty=requested_qty,
                available_qty=available_qty, session_rev=session_rev,
            ),
        }
        if alternatives_data:
            context["alternatives"] = alternatives_data

        return {
            "id": generate_issue_id(), "source": "stock",
            "code": "stock.insufficient", "blocking": True,
            "message": message or f"Estoque insuficiente para {sku}",
            "context": context,
        }

    def _build_actions(self, *, line_id, requested_qty, available_qty, session_rev) -> list[dict]:
        actions: list[dict] = []
        if available_qty > 0:
            actions.append({
                "id": generate_action_id(),
                "label": f"Ajustar para {available_qty} unidade(s)",
                "rev": session_rev,
                "ops": [{"op": "set_qty", "line_id": line_id, "qty": float(available_qty)}],
            })
        actions.append({
            "id": generate_action_id(),
            "label": "Remover item", "rev": session_rev,
            "ops": [{"op": "remove_line", "line_id": line_id}],
        })
        return actions


class StockCommitHandler:
    """Handler para confirmação de reservas de estoque. Topic: stock.commit"""

    topic = STOCK_COMMIT

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
                    session.data.get("checks", {}).get("stock", {}).get("result", {}).get("holds", [])
                )
            except Session.DoesNotExist:
                holds = []

        if not holds:
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        errors: list[str] = []

        for hold in holds:
            hold_id = hold.get("hold_id")
            if not hold_id:
                continue

            if hold.get("is_planned"):
                continue

            try:
                self.backend.fulfill_hold(hold_id, reference=order_ref)
            except Exception as exc:
                errors.append(f"{hold_id}: {exc}")

        if errors:
            message.status = "failed"
            message.last_error = f"Fulfill errors: {'; '.join(errors[:5])}"[:500]
        else:
            message.status = "done"
        message.save(update_fields=["status", "last_error", "updated_at"])

        # Check stock alerts for fulfilled SKUs
        fulfilled_skus = {
            h["sku"] for h in holds
            if h.get("hold_id") and not h.get("is_planned") and h.get("sku")
        }
        if fulfilled_skus:
            self._check_stock_alerts(fulfilled_skus)

    def _check_stock_alerts(self, skus: set[str]) -> None:
        """Check stock alerts for recently fulfilled SKUs."""
        try:
            from shopman.handlers.stock_alerts import check_and_alert

            for sku in skus:
                check_and_alert(sku=sku)
        except Exception:
            logger.debug("StockCommitHandler: stock alert check failed", exc_info=True)


class StockCheck:
    """Check de estoque: reserva durante modify, valida no commit."""

    code = "stock"
    topic = STOCK_HOLD

    def validate(self, *, channel, session, ctx):
        from shopman.ordering.exceptions import ValidationError

        checks = (session.data or {}).get("checks", {})
        stock_check = checks.get("stock")
        if not stock_check:
            raise ValidationError(code="missing_check", message="Stock check obrigatório")
        if stock_check.get("rev") != session.rev:
            raise ValidationError(code="stale_check", message="Stock check desatualizado")


class StockCheckValidator:
    """Validates that sessions have fresh stock checks before commit."""

    code = "stock_check"
    stage = "commit"

    def validate(self, *, channel, session, ctx):
        required_checks = channel.config.get("required_checks_on_commit", [])
        if "stock" not in required_checks:
            return
        if not session.items:
            return

        checks = (session.data or {}).get("checks", {})
        stock_check = checks.get("stock")
        if not stock_check:
            from shopman.ordering.exceptions import ValidationError

            raise ValidationError(code="missing_stock_check", message="Stock check obrigatório para este canal")
        if stock_check.get("rev") != session.rev:
            from shopman.ordering.exceptions import ValidationError

            raise ValidationError(code="stale_stock_check", message="Stock check desatualizado")
        result = stock_check.get("result", {})
        holds = result.get("holds", [])
        if not holds:
            from shopman.ordering.exceptions import ValidationError

            raise ValidationError(code="no_stock_holds", message="Nenhuma reserva de estoque encontrada")


class StockIssueResolver:
    """Resolver para issues de estoque. Source: stock"""

    source = "stock"

    def resolve(self, *, session, issue: dict, action_id: str, ctx: dict):
        from shopman.ordering.exceptions import IssueResolveError
        from shopman.ordering.services import ModifyService

        context = issue.get("context", {})
        actions = context.get("actions", [])

        action = next((a for a in actions if a.get("id") == action_id), None)
        if not action:
            raise IssueResolveError(code="action_not_found", message=f"Action não encontrada: {action_id}")

        action_rev = action.get("rev")
        if action_rev is not None and action_rev != session.rev:
            raise IssueResolveError(code="stale_action", message="Action desatualizada - sessão foi modificada")

        ops = action.get("ops", [])
        if not ops:
            raise IssueResolveError(code="no_ops", message="Action não contém operações")

        return ModifyService.modify_session(
            session_key=session.session_key, channel_ref=session.channel.ref, ops=ops, ctx=ctx,
        )


__all__ = ["StockHoldHandler", "StockCommitHandler", "StockCheck", "StockCheckValidator", "StockIssueResolver"]
