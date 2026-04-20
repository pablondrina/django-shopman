"""
Craftsman Admin (vNext).

Recipe + RecipeItem inline, WorkOrder + WorkOrderItem/Event inlines.
"""

from django.apps import apps
from django.contrib import admin
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder, WorkOrderEvent, WorkOrderItem

# Only register basic admin if Unfold contrib is NOT installed
if not apps.is_installed("shopman.craftsman.contrib.admin_unfold"):

    # ── Recipe ──

    class RecipeItemInline(admin.TabularInline):
        model = RecipeItem
        extra = 1
        fields = ("input_sku", "quantity", "unit", "sort_order", "is_optional")

    @admin.register(Recipe)
    class RecipeAdmin(admin.ModelAdmin):
        list_display = ("ref", "name", "output_sku", "batch_size", "is_active")
        list_filter = ("is_active",)
        search_fields = ("ref", "name", "output_sku")
        inlines = [RecipeItemInline]
        readonly_fields = ("created_at", "updated_at")

    # ── WorkOrder ──

    class WorkOrderItemInline(admin.TabularInline):
        model = WorkOrderItem
        extra = 0
        readonly_fields = ("kind", "item_ref", "quantity", "unit", "recorded_at", "recorded_by")

    class WorkOrderEventInline(admin.TabularInline):
        model = WorkOrderEvent
        extra = 0
        readonly_fields = ("seq", "kind", "payload", "actor", "idempotency_key", "created_at")

    @admin.register(WorkOrder)
    class WorkOrderAdmin(admin.ModelAdmin):
        list_display = ("ref", "recipe", "output_sku", "quantity", "finished", "status", "target_date", "source_ref")
        list_filter = ("status", "target_date")
        search_fields = ("ref", "output_sku", "source_ref")
        readonly_fields = ("ref", "rev", "created_at", "updated_at", "started_at", "finished_at")
        inlines = [WorkOrderItemInline, WorkOrderEventInline]
        actions = ["finish_work_orders", "void_work_orders"]

        @admin.action(description="Finalizar WOs selecionadas (resultado = quantidade planejada)")
        def finish_work_orders(self, request, queryset):
            from shopman.craftsman import craft

            finished = 0
            errors = 0
            for wo in queryset.filter(status__in=[WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED]):
                try:
                    if wo.status == WorkOrder.Status.PLANNED:
                        craft.start(wo, quantity=wo.quantity, actor=request.user.username)
                    craft.finish(wo, finished=wo.started_qty or wo.quantity, actor=request.user.username)
                    finished += 1
                except Exception as exc:
                    self.message_user(request, f"Erro ao finalizar {wo.ref}: {exc}", level="error")
                    errors += 1
            if finished:
                self.message_user(request, f"{finished} WO(s) finalizada(s).")

        @admin.action(description="Cancelar WOs selecionadas")
        def void_work_orders(self, request, queryset):
            from shopman.craftsman import craft

            voided = 0
            for wo in queryset.filter(status__in=[WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED]):
                try:
                    craft.void(wo, reason="Anulado via admin", actor=request.user.username)
                    voided += 1
                except Exception as exc:
                    self.message_user(request, f"Erro ao anular {wo.ref}: {exc}", level="error")
            if voided:
                self.message_user(request, f"{voided} WO(s) anulada(s).")
