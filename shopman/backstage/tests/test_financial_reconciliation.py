from __future__ import annotations

from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.utils import timezone
from shopman.orderman.models import Order
from shopman.payman.models import PaymentIntent, PaymentTransaction

from shopman.backstage.models import DayClosing, OperatorAlert
from shopman.backstage.services.financial_reconciliation import (
    build_financial_reconciliation,
    persist_financial_reconciliation,
)


def _user():
    return User.objects.create_user("finance-recon", password="pw", is_staff=True)


def _paid_order(
    *,
    ref="FIN-001",
    status=Order.Status.COMPLETED,
    total_q=1200,
    intent_status=PaymentIntent.Status.CAPTURED,
):
    intent_ref = f"PAY-{ref}"
    order = Order.objects.create(
        ref=ref,
        channel_ref="web",
        status=status,
        total_q=total_q,
        data={"payment": {"method": "pix", "intent_ref": intent_ref}},
    )
    intent = PaymentIntent.objects.create(
        ref=intent_ref,
        order_ref=order.ref,
        method=PaymentIntent.Method.PIX,
        status=intent_status,
        amount_q=total_q,
        gateway="efi",
        gateway_id=f"gw-{ref}",
    )
    PaymentTransaction.objects.create(
        intent=intent,
        type=PaymentTransaction.Type.CAPTURE,
        amount_q=total_q,
        gateway_id=f"gw-{ref}",
    )
    return order, intent


@pytest.mark.django_db
def test_financial_reconciliation_happy_path_persists_to_day_closing():
    today = timezone.localdate()
    _paid_order(ref="FIN-OK")
    closing = DayClosing.objects.create(date=today, closed_by=_user(), data={"items": []})

    report = build_financial_reconciliation(reconciliation_date=today, require_closing=True)
    persisted = persist_financial_reconciliation(report, create_alert=True)

    assert not report.has_errors
    assert persisted.persisted is True
    assert persisted.alert_created is False
    closing.refresh_from_db()
    assert closing.data["financial_reconciliation"]["date"] == today.isoformat()
    assert closing.data["financial_reconciliation"]["net_q"] == 1200
    assert closing.data["financial_reconciliation_errors"] == []
    assert not OperatorAlert.objects.filter(type="payment_reconciliation_failed").exists()


@pytest.mark.django_db
def test_financial_reconciliation_alerts_cancelled_order_with_captured_balance():
    today = timezone.localdate()
    _paid_order(ref="FIN-CANCEL", status=Order.Status.CANCELLED)
    closing = DayClosing.objects.create(date=today, closed_by=_user(), data={"items": []})

    with pytest.raises(CommandError):
        call_command("reconcile_financial_day", date=today.isoformat(), stdout=StringIO())

    closing.refresh_from_db()
    errors = closing.data["financial_reconciliation_errors"]
    assert errors[0]["code"] == "terminal_order_with_captured_balance"
    assert OperatorAlert.objects.filter(
        type="payment_reconciliation_failed",
        severity="critical",
        acknowledged=False,
    ).exists()


@pytest.mark.django_db
def test_financial_reconciliation_flags_open_intent_with_capture():
    today = timezone.localdate()
    _paid_order(ref="FIN-OPEN", intent_status=PaymentIntent.Status.AUTHORIZED)
    DayClosing.objects.create(date=today, closed_by=_user(), data={"items": []})

    report = build_financial_reconciliation(reconciliation_date=today, require_closing=True)

    assert report.has_errors is True
    assert [issue.code for issue in report.issues] == ["open_intent_has_capture"]


@pytest.mark.django_db
def test_financial_reconciliation_dry_run_does_not_persist_or_alert():
    today = timezone.localdate()
    _paid_order(ref="FIN-DRY", status=Order.Status.CANCELLED)
    closing = DayClosing.objects.create(date=today, closed_by=_user(), data={"items": []})

    with pytest.raises(CommandError):
        call_command("reconcile_financial_day", date=today.isoformat(), dry_run=True, stdout=StringIO())

    closing.refresh_from_db()
    assert "financial_reconciliation" not in closing.data
    assert not OperatorAlert.objects.filter(type="payment_reconciliation_failed").exists()


@pytest.mark.django_db
def test_financial_reconciliation_missing_closing_is_warning_unless_required():
    today = timezone.localdate()

    report = build_financial_reconciliation(reconciliation_date=today)
    assert report.has_errors is False
    assert report.issues[0].code == "day_closing_missing"
    assert report.issues[0].severity == "warning"

    with pytest.raises(CommandError):
        call_command(
            "reconcile_financial_day",
            date=today.isoformat(),
            require_closing=True,
            dry_run=True,
            stdout=StringIO(),
        )
