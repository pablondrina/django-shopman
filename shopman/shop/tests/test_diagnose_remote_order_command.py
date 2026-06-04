from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from shopman.orderman.models import Directive, Order

pytestmark = pytest.mark.django_db


def test_diagnose_remote_order_reports_payment_directives_and_recommendations():
    order = Order.objects.create(
        ref="REMOTE-DIAG-1",
        channel_ref="web",
        session_key="REMOTE-DIAG-SESSION",
        status=Order.Status.NEW,
        snapshot={"items": []},
        data={"payment": {"method": "pix", "status": "pending"}},
        total_q=1000,
    )
    Directive.objects.create(
        topic="notification.send",
        status=Directive.Status.FAILED,
        error_code="terminal",
        payload={"order_ref": order.ref},
    )

    out = StringIO()
    call_command("diagnose_remote_order", order.ref, stdout=out)
    output = out.getvalue()

    assert "result=OK order=REMOTE-DIAG-1 status=new channel=web" in output
    assert "result=WARN payment method=pix state=pending" in output
    assert "result=FAIL directives total=1" in output
    assert "conversation source=" in output
    assert "recommendation=python manage.py reconcile_payments --since=4h --dry-run" in output
    assert "recommendation=python manage.py process_directives --limit=50" in output
