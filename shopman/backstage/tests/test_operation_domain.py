from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from shopman.backstage.models import (
    OperationArea,
    OperationChecklistRun,
    OperationChecklistTemplate,
    OperationChecklistTemplateTask,
    OperationEvidence,
    OperationMoment,
    OperationRunStatus,
    OperationTaskStatus,
    OperationTaskTemplate,
)
from shopman.backstage.services.operations import (
    OperationChecklistError,
    complete_checklist_run,
    complete_task_run,
    start_checklist_run,
    supervise_task_run,
)


@pytest.fixture
def operator(db):
    return User.objects.create_user(username="operador", password="x")


def _template() -> OperationChecklistTemplate:
    checklist = OperationChecklistTemplate.objects.create(
        ref="opening-test",
        title="Abertura teste",
        moment=OperationMoment.OPENING,
    )
    cash = OperationTaskTemplate.objects.create(
        ref="opening-cash-test",
        title="Caixa conferido",
        moment=OperationMoment.OPENING,
        area=OperationArea.CASH,
        evidence_required=OperationEvidence.NUMBER,
        sort_order=10,
    )
    equipment = OperationTaskTemplate.objects.create(
        ref="opening-equipment-test",
        title="Equipamentos seguros",
        moment=OperationMoment.OPENING,
        area=OperationArea.PRODUCTION,
        evidence_required=OperationEvidence.DOUBLE_CHECK,
        sort_order=20,
    )
    OperationChecklistTemplateTask.objects.create(checklist_template=checklist, task_template=cash, sort_order=10)
    OperationChecklistTemplateTask.objects.create(
        checklist_template=checklist,
        task_template=equipment,
        sort_order=20,
    )
    return checklist


@pytest.mark.django_db
def test_start_checklist_run_materializes_ordered_task_runs(operator):
    checklist = _template()

    run = start_checklist_run(
        template=checklist,
        business_date=timezone.localdate(),
        shift_ref="manha",
        user=operator,
        context={"source": "test"},
    )

    assert run.status == OperationRunStatus.OPEN
    assert run.context == {"source": "test"}
    assert run.task_runs.count() == 2
    assert list(run.task_runs.order_by("template__sort_order").values_list("template__ref", flat=True)) == [
        "opening-cash-test",
        "opening-equipment-test",
    ]

    same = start_checklist_run(
        template=checklist,
        business_date=timezone.localdate(),
        shift_ref="manha",
        user=operator,
    )

    assert same.pk == run.pk
    assert OperationChecklistRun.objects.count() == 1
    assert same.task_runs.count() == 2


@pytest.mark.django_db
def test_required_evidence_and_double_check_gate_completion(operator):
    checklist = _template()
    run = start_checklist_run(template=checklist, business_date=timezone.localdate(), user=operator)
    cash = run.task_runs.get(template__ref="opening-cash-test")
    equipment = run.task_runs.get(template__ref="opening-equipment-test")

    with pytest.raises(OperationChecklistError, match="evidência numérica"):
        complete_task_run(cash, user=operator)

    complete_task_run(cash, user=operator, evidence_number=Decimal("200.00"))
    complete_task_run(equipment, user=operator)

    cash.refresh_from_db()
    equipment.refresh_from_db()
    assert cash.status == OperationTaskStatus.DONE
    assert cash.evidence_number == Decimal("200.000")
    assert equipment.requires_supervision

    with pytest.raises(OperationChecklistError, match="dupla conferência"):
        complete_checklist_run(run, user=operator)

    supervise_task_run(equipment, user=operator, notes="Conferido com gerente.")
    complete_checklist_run(run, user=operator)

    run.refresh_from_db()
    assert run.status == OperationRunStatus.COMPLETED
    assert run.completed_by == operator
