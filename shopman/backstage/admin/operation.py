"""Admin for operational checklists."""

from __future__ import annotations

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from shopman.utils import unfold_badge, unfold_badge_numeric
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from shopman.backstage.models import (
    OperationChecklistRun,
    OperationChecklistTemplate,
    OperationChecklistTemplateTask,
    OperationRunStatus,
    OperationTaskRun,
    OperationTaskStatus,
    OperationTaskTemplate,
)
from shopman.backstage.services.operations import OperationChecklistError, complete_checklist_run


class OperationChecklistTemplateTaskInline(TabularInline):
    model = OperationChecklistTemplateTask
    extra = 0
    autocomplete_fields = ("task_template",)
    fields = ("task_template", "sort_order", "is_required_override")


@admin.register(OperationTaskTemplate)
class OperationTaskTemplateAdmin(ModelAdmin):
    list_display = (
        "ref",
        "title",
        "moment",
        "area",
        "evidence_required",
        "required_badge",
        "active_badge",
        "sort_order",
    )
    list_filter = ("moment", "area", "evidence_required", "is_required", "is_active", "is_system")
    search_fields = ("ref", "title", "description", "expected_role")
    ordering = ("moment", "sort_order", "title")
    list_fullwidth = True
    compressed_fields = True

    @display(description="obrigatória")
    def required_badge(self, obj):
        return unfold_badge("sim" if obj.is_required else "não", "green" if obj.is_required else "base")

    @display(description="ativa")
    def active_badge(self, obj):
        return unfold_badge("ativa" if obj.is_active else "inativa", "green" if obj.is_active else "base")


@admin.register(OperationChecklistTemplate)
class OperationChecklistTemplateAdmin(ModelAdmin):
    list_display = ("ref", "title", "moment", "active_badge", "task_count_display", "sort_order")
    list_filter = ("moment", "is_active")
    search_fields = ("ref", "title", "description", "task_links__task_template__title")
    ordering = ("moment", "sort_order", "title")
    inlines = [OperationChecklistTemplateTaskInline]
    list_fullwidth = True
    compressed_fields = True

    @display(description="ativo")
    def active_badge(self, obj):
        return unfold_badge("ativo" if obj.is_active else "inativo", "green" if obj.is_active else "base")

    @display(description="tarefas")
    def task_count_display(self, obj):
        return unfold_badge_numeric(str(obj.task_links.count()), "base")


class OperationTaskRunInline(TabularInline):
    model = OperationTaskRun
    extra = 0
    can_delete = False
    autocomplete_fields = ("template",)
    readonly_fields = (
        "template",
        "status",
        "is_required",
        "evidence_required",
        "executed_by",
        "executed_at",
        "supervised_by",
        "supervised_at",
        "evidence_text",
        "evidence_number",
        "evidence_data",
        "notes",
        "linked_domain",
        "linked_ref",
    )
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(OperationChecklistRun)
class OperationChecklistRunAdmin(ModelAdmin):
    list_display = (
        "business_date",
        "template",
        "shift_ref",
        "status_badge",
        "progress_display",
        "started_by",
        "started_at",
        "completed_by",
        "completed_at",
    )
    list_filter = ("status", "template__moment", "business_date")
    search_fields = ("template__ref", "template__title", "shift_ref", "notes")
    readonly_fields = ("started_at", "completed_at", "progress_display")
    autocomplete_fields = ("template", "started_by", "completed_by")
    inlines = [OperationTaskRunInline]
    actions = ["complete_selected"]
    ordering = ("-business_date", "template__sort_order", "-started_at")
    list_fullwidth = True
    compressed_fields = True

    @display(description="status")
    def status_badge(self, obj):
        colors = {
            OperationRunStatus.OPEN: "yellow",
            OperationRunStatus.COMPLETED: "green",
            OperationRunStatus.CANCELLED: "red",
        }
        return unfold_badge(obj.get_status_display(), colors.get(obj.status, "base"))

    @display(description="progresso")
    def progress_display(self, obj):
        return unfold_badge_numeric(f"{obj.done_tasks}/{obj.total_tasks} ({obj.progress_percent}%)", "base")

    @admin.action(description="Concluir checklists selecionados")
    def complete_selected(self, request, queryset):
        completed = 0
        for run in queryset:
            try:
                complete_checklist_run(run, user=request.user)
            except OperationChecklistError as exc:
                messages.error(request, f"{run}: {exc}")
            else:
                completed += 1
        if completed:
            messages.success(request, f"{completed} checklist(s) concluído(s).")
        return HttpResponseRedirect(reverse("admin:backstage_operationchecklistrun_changelist"))


@admin.register(OperationTaskRun)
class OperationTaskRunAdmin(ModelAdmin):
    list_display = (
        "checklist_run",
        "template",
        "status_badge",
        "required_badge",
        "evidence_required",
        "executed_by",
        "executed_at",
        "supervised_by",
        "supervised_at",
    )
    list_filter = ("status", "is_required", "evidence_required", "checklist_run__template__moment")
    search_fields = ("template__title", "template__ref", "checklist_run__template__title", "linked_ref", "notes")
    autocomplete_fields = ("checklist_run", "template", "executed_by", "supervised_by")
    ordering = ("-checklist_run__business_date", "template__sort_order", "template__title")
    list_fullwidth = True
    compressed_fields = True

    @display(description="status")
    def status_badge(self, obj):
        colors = {
            OperationTaskStatus.PENDING: "yellow",
            OperationTaskStatus.DONE: "green",
            OperationTaskStatus.SKIPPED: "base",
            OperationTaskStatus.BLOCKED: "red",
        }
        return unfold_badge(obj.get_status_display(), colors.get(obj.status, "base"))

    @display(description="obrigatória")
    def required_badge(self, obj):
        return unfold_badge("sim" if obj.is_required else "não", "green" if obj.is_required else "base")
