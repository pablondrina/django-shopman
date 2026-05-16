"""Services for operational checklists."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from shopman.backstage.models import (
    OperationChecklistRun,
    OperationChecklistTemplate,
    OperationEvidence,
    OperationRunStatus,
    OperationTaskRun,
    OperationTaskStatus,
)


class OperationChecklistError(ValueError):
    """Raised when an operational checklist transition is invalid."""


def start_checklist_run(
    *,
    template: OperationChecklistTemplate,
    business_date,
    user,
    shift_ref: str = "",
    context: dict | None = None,
) -> OperationChecklistRun:
    """Open a checklist run and materialize task runs idempotently."""
    if not template.is_active:
        raise OperationChecklistError("Checklist inativo não pode ser iniciado.")

    with transaction.atomic():
        run, created = OperationChecklistRun.objects.select_for_update().get_or_create(
            template=template,
            business_date=business_date,
            shift_ref=shift_ref,
            defaults={
                "started_by": user,
                "context": context or {},
            },
        )
        if created:
            run.status = OperationRunStatus.OPEN
        elif context:
            run.context = {**(run.context or {}), **context}
            run.save(update_fields=["context"])
        _sync_task_runs(run)
    return run


def _sync_task_runs(run: OperationChecklistRun) -> None:
    links = (
        run.template.task_links.select_related("task_template")
        .filter(task_template__is_active=True)
        .order_by("sort_order", "task_template__sort_order", "task_template__title")
    )
    for link in links:
        task = link.task_template
        OperationTaskRun.objects.get_or_create(
            checklist_run=run,
            template=task,
            defaults={
                "is_required": link.effective_required,
                "evidence_required": task.evidence_required,
            },
        )


def complete_task_run(
    task_run: OperationTaskRun,
    *,
    user,
    evidence_text: str = "",
    evidence_number: Decimal | int | str | None = None,
    evidence_data: dict | None = None,
    notes: str = "",
) -> OperationTaskRun:
    """Mark a task as done after validating the required evidence contract."""
    evidence_data = evidence_data or {}
    evidence_text = evidence_text.strip()
    _validate_evidence(
        required=task_run.evidence_required,
        evidence_text=evidence_text,
        evidence_number=evidence_number,
        evidence_data=evidence_data,
    )

    task_run.status = OperationTaskStatus.DONE
    task_run.executed_by = user
    task_run.executed_at = timezone.now()
    task_run.evidence_text = evidence_text
    if evidence_number is not None:
        task_run.evidence_number = Decimal(str(evidence_number))
    task_run.evidence_data = evidence_data
    if notes:
        task_run.notes = notes
    task_run.save(
        update_fields=[
            "status",
            "executed_by",
            "executed_at",
            "evidence_text",
            "evidence_number",
            "evidence_data",
            "notes",
            "updated_at",
        ]
    )
    return task_run


def supervise_task_run(task_run: OperationTaskRun, *, user, notes: str = "") -> OperationTaskRun:
    """Attach supervisory evidence without overwriting execution authorship."""
    if task_run.status != OperationTaskStatus.DONE:
        raise OperationChecklistError("Apenas tarefas concluídas podem ser supervisionadas.")
    task_run.supervised_by = user
    task_run.supervised_at = timezone.now()
    if notes:
        task_run.notes = f"{task_run.notes}\n{notes}".strip() if task_run.notes else notes
    task_run.save(update_fields=["supervised_by", "supervised_at", "notes", "updated_at"])
    return task_run


def complete_checklist_run(run: OperationChecklistRun, *, user) -> OperationChecklistRun:
    """Close a checklist only when required tasks are done and supervised."""
    task_runs = list(run.task_runs.select_related("template"))
    pending_required = [
        task.template.title
        for task in task_runs
        if task.is_required and task.status != OperationTaskStatus.DONE
    ]
    if pending_required:
        raise OperationChecklistError("Tarefas obrigatórias pendentes: " + ", ".join(pending_required))

    unsupervised = [
        task.template.title
        for task in task_runs
        if task.is_required and task.requires_supervision and not task.is_supervised
    ]
    if unsupervised:
        raise OperationChecklistError("Tarefas exigem dupla conferência: " + ", ".join(unsupervised))

    run.status = OperationRunStatus.COMPLETED
    run.completed_by = user
    run.completed_at = timezone.now()
    run.save(update_fields=["status", "completed_by", "completed_at"])
    return run


def _validate_evidence(
    *,
    required: str,
    evidence_text: str,
    evidence_number: Decimal | int | str | None,
    evidence_data: dict,
) -> None:
    if required == OperationEvidence.TEXT and not evidence_text:
        raise OperationChecklistError("Esta tarefa exige evidência textual.")
    if required == OperationEvidence.NUMBER and evidence_number is None:
        raise OperationChecklistError("Esta tarefa exige evidência numérica.")
    if required == OperationEvidence.PHOTO and not evidence_data:
        raise OperationChecklistError("Esta tarefa exige evidência de foto em evidence_data.")
