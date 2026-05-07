"""Daily financial reconciliation for operator audits."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Literal

from django.db.models import Q, Sum
from django.utils import timezone
from shopman.orderman.models import Order
from shopman.payman.models import PaymentIntent, PaymentTransaction

from shopman.backstage.models import DayClosing

Severity = Literal["warning", "error", "critical"]


@dataclass(frozen=True)
class FinancialReconciliationIssue:
    code: str
    severity: Severity
    message: str
    order_ref: str = ""
    intent_ref: str = ""
    context: dict[str, int | str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        data = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if self.order_ref:
            data["order_ref"] = self.order_ref
        if self.intent_ref:
            data["intent_ref"] = self.intent_ref
        if self.context:
            data["context"] = self.context
        return data


@dataclass(frozen=True)
class FinancialReconciliationReport:
    date: date
    generated_at: datetime
    order_count: int
    intent_count: int
    transaction_count: int
    order_gross_q: int
    captured_q: int
    refunded_q: int
    chargeback_q: int
    net_q: int
    by_method: dict[str, int]
    by_gateway: dict[str, int]
    issues: tuple[FinancialReconciliationIssue, ...]
    day_closing_id: int | None = None
    persisted: bool = False
    alert_created: bool = False

    @property
    def has_errors(self) -> bool:
        return any(issue.severity in {"error", "critical"} for issue in self.issues)

    @property
    def issue_counts(self) -> dict[str, int]:
        counts = Counter(issue.severity for issue in self.issues)
        return {key: counts.get(key, 0) for key in ("warning", "error", "critical")}

    def as_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "generated_at": self.generated_at.isoformat(),
            "order_count": self.order_count,
            "intent_count": self.intent_count,
            "transaction_count": self.transaction_count,
            "order_gross_q": self.order_gross_q,
            "captured_q": self.captured_q,
            "refunded_q": self.refunded_q,
            "chargeback_q": self.chargeback_q,
            "net_q": self.net_q,
            "by_method": self.by_method,
            "by_gateway": self.by_gateway,
            "issue_counts": self.issue_counts,
            "issues": [issue.as_dict() for issue in self.issues],
            "day_closing_id": self.day_closing_id,
            "persisted": self.persisted,
            "alert_created": self.alert_created,
        }


def build_financial_reconciliation(
    *,
    reconciliation_date: date,
    require_closing: bool = False,
) -> FinancialReconciliationReport:
    """Build a deterministic audit report for one local business date."""
    orders_on_date = list(
        Order.objects.filter(created_at__date=reconciliation_date).only(
            "ref",
            "channel_ref",
            "session_key",
            "snapshot",
            "total_q",
            "currency",
            "status",
            "data",
            "created_at",
        )
    )
    order_refs_on_date = {order.ref for order in orders_on_date}

    tx_intent_ids_on_date = set(
        PaymentTransaction.objects.filter(created_at__date=reconciliation_date).values_list("intent_id", flat=True)
    )
    intents = list(
        PaymentIntent.objects.filter(
            Q(order_ref__in=order_refs_on_date)
            | Q(created_at__date=reconciliation_date)
            | Q(id__in=tx_intent_ids_on_date)
        )
        .distinct()
        .order_by("order_ref", "created_at", "id")
    )
    intent_ids = [intent.id for intent in intents]
    intent_by_ref = {intent.ref: intent for intent in intents}
    intents_by_order: dict[str, list[PaymentIntent]] = defaultdict(list)
    for intent in intents:
        if intent.order_ref:
            intents_by_order[intent.order_ref].append(intent)

    all_order_refs = order_refs_on_date | {intent.order_ref for intent in intents if intent.order_ref}
    orders_by_ref = {
        order.ref: order
        for order in Order.objects.filter(ref__in=all_order_refs).only(
            "ref",
            "channel_ref",
            "session_key",
            "snapshot",
            "total_q",
            "currency",
            "status",
            "data",
            "created_at",
        )
    }

    lifetime_totals = _transaction_totals(
        PaymentTransaction.objects.filter(intent_id__in=intent_ids)
        .values("intent_id", "type")
        .annotate(total=Sum("amount_q"))
    )
    daily_totals = _transaction_totals(
        PaymentTransaction.objects.filter(intent_id__in=intent_ids, created_at__date=reconciliation_date)
        .values("intent_id", "type")
        .annotate(total=Sum("amount_q"))
    )

    issues: list[FinancialReconciliationIssue] = []
    closing = DayClosing.objects.filter(date=reconciliation_date).first()
    if closing is None:
        issues.append(
            FinancialReconciliationIssue(
                code="day_closing_missing",
                severity="error" if require_closing else "warning",
                message="Fechamento do dia ainda não existe para a data reconciliada.",
                context={"date": reconciliation_date.isoformat()},
            )
        )

    for order in orders_on_date:
        _check_order_payment_link(
            order=order,
            intent_by_ref=intent_by_ref,
            intents_by_order=intents_by_order,
            issues=issues,
        )

    for intent in intents:
        _check_intent(
            intent=intent,
            order=orders_by_ref.get(intent.order_ref),
            totals=lifetime_totals[intent.id],
            issues=issues,
        )

    by_method = Counter(intent.method or "-" for intent in intents)
    by_gateway = Counter(intent.gateway or "-" for intent in intents)

    captured_q = sum(row["capture"] for row in daily_totals.values())
    refunded_q = sum(row["refund"] for row in daily_totals.values())
    chargeback_q = sum(row["chargeback"] for row in daily_totals.values())

    return FinancialReconciliationReport(
        date=reconciliation_date,
        generated_at=timezone.now(),
        order_count=len(orders_on_date),
        intent_count=len(intents),
        transaction_count=PaymentTransaction.objects.filter(
            intent_id__in=intent_ids,
            created_at__date=reconciliation_date,
        ).count(),
        order_gross_q=sum(
            int(order.total_q or 0)
            for order in orders_on_date
            if order.status not in (Order.Status.CANCELLED, Order.Status.RETURNED)
        ),
        captured_q=captured_q,
        refunded_q=refunded_q,
        chargeback_q=chargeback_q,
        net_q=captured_q - refunded_q - chargeback_q,
        by_method=dict(sorted(by_method.items())),
        by_gateway=dict(sorted(by_gateway.items())),
        issues=tuple(issues),
        day_closing_id=closing.pk if closing else None,
    )


def persist_financial_reconciliation(
    report: FinancialReconciliationReport,
    *,
    create_alert: bool = True,
) -> FinancialReconciliationReport:
    """Persist report into DayClosing JSON and optionally emit one operator alert."""
    closing = DayClosing.objects.filter(date=report.date).first()
    persisted = False
    if closing is not None:
        data = dict(closing.data or {}) if isinstance(closing.data, dict) else {"items": closing.data or []}
        data["financial_reconciliation"] = _summary_dict(report)
        data["financial_reconciliation_errors"] = [
            issue.as_dict()
            for issue in report.issues
            if issue.severity in {"error", "critical"}
        ]
        closing.data = data
        closing.save(update_fields=["data"])
        persisted = True

    alert_created = False
    if create_alert and report.has_errors:
        from shopman.shop.services import observability

        critical = sum(1 for issue in report.issues if issue.severity == "critical")
        errors = sum(1 for issue in report.issues if issue.severity == "error")
        alert = observability.create_operator_alert(
            type="payment_reconciliation_failed",
            severity="critical" if critical else "error",
            message=(
                f"Reconciliação financeira diária de {report.date.isoformat()} encontrou "
                f"{critical} divergência(s) crítica(s) e {errors} erro(s)."
            ),
            dedupe_key=f"financial-day:{report.date.isoformat()}:{critical}:{errors}",
            debounce_minutes=60,
            issue_counts=report.issue_counts,
        )
        alert_created = alert is not None

    return replace(
        report,
        day_closing_id=closing.pk if closing else report.day_closing_id,
        persisted=persisted,
        alert_created=alert_created,
    )


def _check_order_payment_link(
    *,
    order: Order,
    intent_by_ref: dict[str, PaymentIntent],
    intents_by_order: dict[str, list[PaymentIntent]],
    issues: list[FinancialReconciliationIssue],
) -> None:
    payment = _payment_data(order)
    method = str(payment.get("method") or "").strip()
    intent_ref = str(payment.get("intent_ref") or "").strip()
    order_intents = intents_by_order.get(order.ref, [])

    if method in {"pix", "card"} and order.status not in (Order.Status.CANCELLED, Order.Status.RETURNED):
        if not intent_ref and not order_intents:
            issues.append(
                FinancialReconciliationIssue(
                    code="digital_order_missing_intent",
                    severity="error",
                    message="Pedido digital não tem PaymentIntent vinculado.",
                    order_ref=order.ref,
                    context={"method": method, "status": order.status, "total_q": int(order.total_q or 0)},
                )
            )

    if intent_ref and intent_ref not in intent_by_ref:
        issues.append(
            FinancialReconciliationIssue(
                code="order_data_intent_not_found",
                severity="error",
                message="Order.data.payment.intent_ref aponta para intent inexistente no escopo reconciliado.",
                order_ref=order.ref,
                intent_ref=intent_ref,
            )
        )
    elif not intent_ref and order_intents:
        newest = sorted(order_intents, key=lambda item: item.created_at, reverse=True)[0]
        issues.append(
            FinancialReconciliationIssue(
                code="order_missing_data_intent_ref",
                severity="warning",
                message="Pedido tem PaymentIntent por order_ref, mas Order.data.payment.intent_ref não está preenchido.",
                order_ref=order.ref,
                intent_ref=newest.ref,
            )
        )

    positive_balance = [
        intent for intent in order_intents
        if intent.status in (PaymentIntent.Status.CAPTURED, PaymentIntent.Status.REFUNDED)
    ]
    if len(positive_balance) > 1:
        issues.append(
            FinancialReconciliationIssue(
                code="multiple_captured_intents_for_order",
                severity="critical",
                message="Pedido tem mais de um intent capturado/reembolsado.",
                order_ref=order.ref,
                context={"intent_count": len(positive_balance)},
            )
        )


def _check_intent(
    *,
    intent: PaymentIntent,
    order: Order | None,
    totals: dict[str, int],
    issues: list[FinancialReconciliationIssue],
) -> None:
    captured_q = totals["capture"]
    refunded_q = totals["refund"]
    chargeback_q = totals["chargeback"]
    returned_q = refunded_q + chargeback_q
    net_q = captured_q - returned_q

    if order is None:
        issues.append(
            FinancialReconciliationIssue(
                code="intent_without_order",
                severity="error",
                message="PaymentIntent não tem pedido correspondente.",
                intent_ref=intent.ref,
                context={"order_ref": intent.order_ref, "amount_q": int(intent.amount_q or 0)},
            )
        )
        return

    payment = _payment_data(order)
    data_intent_ref = str(payment.get("intent_ref") or "").strip()
    if data_intent_ref and data_intent_ref != intent.ref and intent.order_ref == order.ref:
        issues.append(
            FinancialReconciliationIssue(
                code="order_intent_ref_mismatch",
                severity="warning",
                message="Pedido referencia outro intent em Order.data.payment.intent_ref.",
                order_ref=order.ref,
                intent_ref=intent.ref,
                context={"data_intent_ref": data_intent_ref},
            )
        )

    if intent.amount_q != order.total_q:
        issues.append(
            FinancialReconciliationIssue(
                code="intent_amount_mismatch",
                severity="error",
                message="Valor do PaymentIntent diverge do total selado do pedido.",
                order_ref=order.ref,
                intent_ref=intent.ref,
                context={"order_total_q": int(order.total_q or 0), "intent_amount_q": int(intent.amount_q or 0)},
            )
        )

    if intent.currency.upper() != order.currency.upper():
        issues.append(
            FinancialReconciliationIssue(
                code="intent_currency_mismatch",
                severity="error",
                message="Moeda do PaymentIntent diverge da moeda do pedido.",
                order_ref=order.ref,
                intent_ref=intent.ref,
                context={"order_currency": order.currency, "intent_currency": intent.currency},
            )
        )

    if intent.status in (PaymentIntent.Status.CAPTURED, PaymentIntent.Status.REFUNDED) and captured_q <= 0:
        issues.append(
            FinancialReconciliationIssue(
                code="captured_intent_without_capture_transaction",
                severity="critical",
                message="Intent capturado/reembolsado não tem transação de captura.",
                order_ref=order.ref,
                intent_ref=intent.ref,
            )
        )

    if intent.status in (PaymentIntent.Status.PENDING, PaymentIntent.Status.AUTHORIZED) and captured_q > 0:
        issues.append(
            FinancialReconciliationIssue(
                code="open_intent_has_capture",
                severity="error",
                message="Intent ainda está aberto/autorizado, mas já possui captura registrada.",
                order_ref=order.ref,
                intent_ref=intent.ref,
                context={"intent_status": intent.status, "captured_q": captured_q},
            )
        )

    if returned_q > captured_q:
        issues.append(
            FinancialReconciliationIssue(
                code="refund_exceeds_capture",
                severity="critical",
                message="Reembolso/chargeback excede o total capturado.",
                order_ref=order.ref,
                intent_ref=intent.ref,
                context={"captured_q": captured_q, "returned_q": returned_q},
            )
        )

    if captured_q > intent.amount_q:
        issues.append(
            FinancialReconciliationIssue(
                code="capture_exceeds_intent_amount",
                severity="critical",
                message="Captura excede o valor autorizado no PaymentIntent.",
                order_ref=order.ref,
                intent_ref=intent.ref,
                context={"captured_q": captured_q, "intent_amount_q": int(intent.amount_q or 0)},
            )
        )

    if order.status == Order.Status.NEW and net_q > 0:
        issues.append(
            FinancialReconciliationIssue(
                code="paid_order_not_confirmed",
                severity="critical",
                message="Pedido ainda está new, mas há saldo capturado.",
                order_ref=order.ref,
                intent_ref=intent.ref,
                context={"net_q": net_q},
            )
        )

    if order.status in (Order.Status.CANCELLED, Order.Status.RETURNED) and net_q > 0:
        issues.append(
            FinancialReconciliationIssue(
                code="terminal_order_with_captured_balance",
                severity="critical",
                message="Pedido cancelado/devolvido ainda tem saldo capturado líquido.",
                order_ref=order.ref,
                intent_ref=intent.ref,
                context={"net_q": net_q, "status": order.status},
            )
        )

    strict_paid_statuses = {
        Order.Status.PREPARING,
        Order.Status.READY,
        Order.Status.DISPATCHED,
        Order.Status.DELIVERED,
        Order.Status.COMPLETED,
    }
    if order.status in strict_paid_statuses and _payment_method(order) in {"pix", "card"} and net_q < order.total_q:
        issues.append(
            FinancialReconciliationIssue(
                code="fulfilled_digital_order_underpaid",
                severity="error",
                message="Pedido digital em fluxo operacional avançado tem saldo capturado abaixo do total.",
                order_ref=order.ref,
                intent_ref=intent.ref,
                context={"net_q": net_q, "order_total_q": int(order.total_q or 0), "status": order.status},
            )
        )

    if intent.status in (PaymentIntent.Status.CANCELLED, PaymentIntent.Status.FAILED) and captured_q > 0:
        issues.append(
            FinancialReconciliationIssue(
                code="terminal_intent_has_capture",
                severity="critical",
                message="Intent terminal falho/cancelado possui captura registrada.",
                order_ref=order.ref,
                intent_ref=intent.ref,
                context={"intent_status": intent.status, "captured_q": captured_q},
            )
        )


def _transaction_totals(rows) -> defaultdict[int, dict[str, int]]:
    totals: defaultdict[int, dict[str, int]] = defaultdict(lambda: {"capture": 0, "refund": 0, "chargeback": 0})
    for row in rows:
        tx_type = row["type"]
        if tx_type in totals[row["intent_id"]]:
            totals[row["intent_id"]][tx_type] += int(row["total"] or 0)
    return totals


def _payment_data(order: Order) -> dict:
    payment = (order.data or {}).get("payment") or {}
    return payment if isinstance(payment, dict) else {}


def _payment_method(order: Order) -> str:
    return str(_payment_data(order).get("method") or "").strip()


def _summary_dict(report: FinancialReconciliationReport) -> dict:
    data = report.as_dict()
    return {key: value for key, value in data.items() if key != "issues"}
