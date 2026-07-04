"""sweep_stuck_orders resgata pedidos órfãos em NEW (crash pós-commit).

on_commit não é durável (roda no on_commit do signal, síncrono); um crash entre o
COMMIT e o callback deixa o pedido em NEW sem hold/confirmação. Um on_commit
completo grava order.data["lifecycle"]["on_commit"]="done"; o sweeper re-despacha,
idempotente, os NEW antigos SEM esse marcador.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone
from shopman.orderman.models import Order

pytestmark = pytest.mark.django_db


def _order(ref, *, status=Order.Status.NEW, data=None, age_minutes=30):
    o = Order.objects.create(
        ref=ref, channel_ref="web", status=status, total_q=1000, data=data or {}
    )
    if age_minutes:
        old = timezone.now() - timedelta(minutes=age_minutes)
        Order.objects.filter(pk=o.pk).update(created_at=old)  # bypassa auto_now_add
    return o


def test_redispatches_orphan_new_without_marker():
    _order("ORD-ORPHAN", data={})
    with patch("shopman.shop.lifecycle.dispatch") as dispatch:
        call_command("sweep_stuck_orders")
    dispatch.assert_called_once()
    assert dispatch.call_args.args[1] == "on_commit"


def test_skips_new_with_completed_marker():
    _order("ORD-DONE", data={"lifecycle": {"on_commit": "done"}})
    with patch("shopman.shop.lifecycle.dispatch") as dispatch:
        call_command("sweep_stuck_orders")
    dispatch.assert_not_called()


def test_skips_young_order():
    _order("ORD-YOUNG", data={}, age_minutes=0)  # criado agora
    with patch("shopman.shop.lifecycle.dispatch") as dispatch:
        call_command("sweep_stuck_orders")
    dispatch.assert_not_called()


def test_skips_non_new_order():
    _order("ORD-CONF", status=Order.Status.CONFIRMED, data={})
    with patch("shopman.shop.lifecycle.dispatch") as dispatch:
        call_command("sweep_stuck_orders")
    dispatch.assert_not_called()


def test_dry_run_does_not_dispatch():
    _order("ORD-DRY", data={})
    with patch("shopman.shop.lifecycle.dispatch") as dispatch:
        call_command("sweep_stuck_orders", "--dry-run")
    dispatch.assert_not_called()
