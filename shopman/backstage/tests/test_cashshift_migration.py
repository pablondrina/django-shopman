from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_cashshift_terminal_migration_preserves_concurrent_legacy_open_shifts():
    executor = MigrationExecutor(connection)
    migrate_from = [("backstage", "0007_operationchecklisttemplate_operationtasktemplate_and_more")]
    migrate_to = [("backstage", "0008_cashshift_posterminal")]
    # Estado final do schema para RESTAURAR no finally: sem isso, o banco de
    # teste ficava preso em 0008 para toda a sessão do pytest e qualquer teste
    # posterior que tocasse colunas de 0009+ (ex.: kdsticket.session_key, 0011)
    # morria com OperationalError — a "poluição backstage→shop".
    latest = [target for target in executor.loader.graph.leaf_nodes() if target[0] == "backstage"]

    try:
        executor.migrate(migrate_from)
        old_apps = executor.loader.project_state(migrate_from).apps
        User = old_apps.get_model("auth", "User")
        CashRegisterSession = old_apps.get_model("backstage", "CashRegisterSession")

        now = timezone.now()
        first_operator = User.objects.create(username="legacy-cash-1", is_staff=True)
        second_operator = User.objects.create(username="legacy-cash-2", is_staff=True)

        older_duplicate = CashRegisterSession.objects.create(
            operator=first_operator,
            opened_at=now - timedelta(hours=3),
            status="open",
        )
        CashRegisterSession.objects.create(
            operator=first_operator,
            opened_at=now - timedelta(hours=1),
            status="open",
        )
        second_operator_shift = CashRegisterSession.objects.create(
            operator=second_operator,
            opened_at=now - timedelta(hours=2),
            status="open",
        )

        executor = MigrationExecutor(connection)
        executor.migrate(migrate_to)
        new_apps = executor.loader.project_state(migrate_to).apps
        CashShift = new_apps.get_model("backstage", "CashShift")
        POSTerminal = new_apps.get_model("backstage", "POSTerminal")

        open_shifts = list(CashShift.objects.filter(status="open").order_by("id"))
        void_shift = CashShift.objects.get(pk=older_duplicate.pk)

        assert len(open_shifts) == 2
        assert len({shift.operator_id for shift in open_shifts}) == 2
        assert len({shift.terminal_id for shift in open_shifts}) == 2
        assert void_shift.status == "void"
        assert void_shift.closed_at is not None
        assert POSTerminal.objects.filter(ref=f"pdv-legacy-{second_operator_shift.pk}").exists()
    finally:
        MigrationExecutor(connection).migrate(latest)

