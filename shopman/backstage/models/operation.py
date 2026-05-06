"""Operational checklist models."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class OperationMoment(models.TextChoices):
    OPENING = "opening", "Abertura"
    ROUTINE = "routine", "Rotina"
    CLOSING = "closing", "Fechamento"


class OperationArea(models.TextChoices):
    CASH = "cash", "Caixa"
    ROOM = "room", "Salão"
    PRODUCTION = "production", "Produção"
    STOCK = "stock", "Estoque"
    CLEANING = "cleaning", "Limpeza"
    MANAGEMENT = "management", "Gestão"


class OperationEvidence(models.TextChoices):
    NONE = "none", "Nenhuma"
    TEXT = "text", "Texto"
    NUMBER = "number", "Número"
    PHOTO = "photo", "Foto"
    DOUBLE_CHECK = "double_check", "Dupla conferência"


class OperationRunStatus(models.TextChoices):
    OPEN = "open", "Aberto"
    COMPLETED = "completed", "Concluído"
    CANCELLED = "cancelled", "Cancelado"


class OperationTaskStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    DONE = "done", "Concluída"
    SKIPPED = "skipped", "Ignorada"
    BLOCKED = "blocked", "Bloqueada"


class OperationTaskTemplate(models.Model):
    """Configurable operational task used by opening/routine/closing checklists."""

    ref = models.SlugField("ref", max_length=80, unique=True)
    title = models.CharField("título", max_length=160)
    description = models.TextField("descrição curta", blank=True)
    moment = models.CharField("momento", max_length=20, choices=OperationMoment.choices)
    area = models.CharField("área", max_length=20, choices=OperationArea.choices)
    evidence_required = models.CharField(
        "evidência exigida",
        max_length=20,
        choices=OperationEvidence.choices,
        default=OperationEvidence.NONE,
    )
    expected_role = models.CharField("responsável esperado", max_length=80, blank=True)
    is_required = models.BooleanField("obrigatória", default=True)
    is_active = models.BooleanField("ativa", default=True)
    is_system = models.BooleanField("tarefa do sistema", default=False)
    sort_order = models.PositiveIntegerField("ordem", default=0)
    config = models.JSONField("configuração", default=dict, blank=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizada em", auto_now=True)

    class Meta:
        verbose_name = "template de tarefa operacional"
        verbose_name_plural = "templates de tarefas operacionais"
        ordering = ["moment", "sort_order", "title"]
        permissions = [
            ("manage_operation_checklists", "Pode configurar checklists operacionais"),
            ("perform_operation_task", "Pode executar tarefas operacionais"),
            ("supervise_operation_task", "Pode supervisionar tarefas operacionais"),
            ("view_operation_reports", "Pode ver relatórios operacionais"),
        ]

    def __str__(self) -> str:
        return self.title


class OperationChecklistTemplate(models.Model):
    """Configurable group of operational tasks for a moment of the day."""

    ref = models.SlugField("ref", max_length=80, unique=True)
    title = models.CharField("título", max_length=160)
    description = models.TextField("descrição curta", blank=True)
    moment = models.CharField("momento", max_length=20, choices=OperationMoment.choices)
    is_active = models.BooleanField("ativo", default=True)
    sort_order = models.PositiveIntegerField("ordem", default=0)
    tasks = models.ManyToManyField(
        OperationTaskTemplate,
        through="OperationChecklistTemplateTask",
        related_name="checklist_templates",
        verbose_name="tarefas",
    )
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "template de checklist operacional"
        verbose_name_plural = "templates de checklists operacionais"
        ordering = ["moment", "sort_order", "title"]

    def __str__(self) -> str:
        return self.title


class OperationChecklistTemplateTask(models.Model):
    """Ordered task membership inside a checklist template."""

    checklist_template = models.ForeignKey(
        OperationChecklistTemplate,
        on_delete=models.CASCADE,
        related_name="task_links",
        verbose_name="checklist",
    )
    task_template = models.ForeignKey(
        OperationTaskTemplate,
        on_delete=models.PROTECT,
        related_name="checklist_links",
        verbose_name="tarefa",
    )
    sort_order = models.PositiveIntegerField("ordem", default=0)
    is_required_override = models.BooleanField("obrigatória neste checklist", null=True, blank=True)

    class Meta:
        verbose_name = "tarefa do template de checklist"
        verbose_name_plural = "tarefas do template de checklist"
        ordering = ["sort_order", "task_template__title"]
        constraints = [
            models.UniqueConstraint(
                fields=["checklist_template", "task_template"],
                name="backstage_operation_template_task_unique",
            ),
        ]

    @property
    def effective_required(self) -> bool:
        if self.is_required_override is not None:
            return self.is_required_override
        return self.task_template.is_required

    def __str__(self) -> str:
        return f"{self.checklist_template} — {self.task_template}"


class OperationChecklistRun(models.Model):
    """Daily/shift instance of an operational checklist."""

    template = models.ForeignKey(
        OperationChecklistTemplate,
        on_delete=models.PROTECT,
        related_name="runs",
        verbose_name="template",
    )
    business_date = models.DateField("data operacional", default=timezone.localdate)
    shift_ref = models.CharField("turno", max_length=50, blank=True, default="")
    status = models.CharField(
        "status",
        max_length=20,
        choices=OperationRunStatus.choices,
        default=OperationRunStatus.OPEN,
    )
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="operation_checklists_started",
        verbose_name="iniciado por",
    )
    started_at = models.DateTimeField("iniciado em", default=timezone.now)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="operation_checklists_completed",
        verbose_name="concluído por",
        null=True,
        blank=True,
    )
    completed_at = models.DateTimeField("concluído em", null=True, blank=True)
    notes = models.TextField("observações", blank=True)
    context = models.JSONField("contexto", default=dict, blank=True)

    class Meta:
        verbose_name = "execução de checklist operacional"
        verbose_name_plural = "execuções de checklists operacionais"
        ordering = ["-business_date", "template__sort_order", "-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "business_date", "shift_ref"],
                name="backstage_operation_checklist_run_unique",
            ),
        ]

    @property
    def total_tasks(self) -> int:
        return self.task_runs.count()

    @property
    def done_tasks(self) -> int:
        return self.task_runs.filter(status=OperationTaskStatus.DONE).count()

    @property
    def progress_percent(self) -> int:
        total = self.total_tasks
        if not total:
            return 0
        return round((self.done_tasks / total) * 100)

    def __str__(self) -> str:
        suffix = f" / {self.shift_ref}" if self.shift_ref else ""
        return f"{self.template} — {self.business_date}{suffix}"


class OperationTaskRun(models.Model):
    """Audit trail for a task execution inside an operational checklist."""

    checklist_run = models.ForeignKey(
        OperationChecklistRun,
        on_delete=models.CASCADE,
        related_name="task_runs",
        verbose_name="checklist",
    )
    template = models.ForeignKey(
        OperationTaskTemplate,
        on_delete=models.PROTECT,
        related_name="task_runs",
        verbose_name="template",
    )
    status = models.CharField(
        "status",
        max_length=20,
        choices=OperationTaskStatus.choices,
        default=OperationTaskStatus.PENDING,
    )
    is_required = models.BooleanField("obrigatória", default=True)
    evidence_required = models.CharField(
        "evidência exigida",
        max_length=20,
        choices=OperationEvidence.choices,
        default=OperationEvidence.NONE,
    )
    executed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="operation_tasks_executed",
        verbose_name="executada por",
        null=True,
        blank=True,
    )
    executed_at = models.DateTimeField("executada em", null=True, blank=True)
    supervised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="operation_tasks_supervised",
        verbose_name="supervisionada por",
        null=True,
        blank=True,
    )
    supervised_at = models.DateTimeField("supervisionada em", null=True, blank=True)
    evidence_text = models.TextField("evidência textual", blank=True)
    evidence_number = models.DecimalField("evidência numérica", max_digits=12, decimal_places=3, null=True, blank=True)
    evidence_data = models.JSONField("evidência estruturada", default=dict, blank=True)
    notes = models.TextField("observações", blank=True)
    linked_domain = models.CharField("domínio vinculado", max_length=80, blank=True)
    linked_ref = models.CharField("ref vinculada", max_length=120, blank=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizada em", auto_now=True)

    class Meta:
        verbose_name = "execução de tarefa operacional"
        verbose_name_plural = "execuções de tarefas operacionais"
        ordering = ["checklist_run", "template__sort_order", "template__title"]
        constraints = [
            models.UniqueConstraint(
                fields=["checklist_run", "template"],
                name="backstage_operation_task_run_unique",
            ),
        ]

    @property
    def requires_supervision(self) -> bool:
        return self.evidence_required == OperationEvidence.DOUBLE_CHECK

    @property
    def is_supervised(self) -> bool:
        return bool(self.supervised_at and self.supervised_by_id)

    def __str__(self) -> str:
        return f"{self.checklist_run} — {self.template.title}"
