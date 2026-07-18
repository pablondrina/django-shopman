"""Admin de broadcast — CRUD de regras e modelos, leitura dos posts.

Divisão de papéis (feedback_admin_crud_config_only): o Admin configura
(regras, modelos de post); a revisão e a publicação são operação e vivem nas
superfícies de operador. Por isso ``BroadcastPost`` entra aqui só para
auditoria, sem criação nem edição.
"""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.shop.models import BroadcastPost, BroadcastRule, PostTemplate


@admin.register(PostTemplate)
class PostTemplateAdmin(ModelAdmin):
    list_display = ("name", "image_source", "use_ai_generation", "is_active")
    list_filter = ("is_active", "use_ai_generation", "image_source")
    search_fields = ("name", "body")
    list_editable = ("is_active",)
    fieldsets = (
        (None, {"fields": ("name", "is_active")}),
        ("conteúdo", {"fields": ("body", "variables", "platform_variants", "image_source")}),
        ("inteligência artificial", {"fields": ("use_ai_generation", "ai_prompt")}),
    )


@admin.register(BroadcastRule)
class BroadcastRuleAdmin(ModelAdmin):
    list_display = ("name", "trigger_display", "template", "requires_approval", "is_active")
    list_filter = ("is_active", "trigger", "requires_approval")
    search_fields = ("name",)
    list_editable = ("is_active",)
    autocomplete_fields = ("template",)
    fieldsets = (
        (None, {"fields": ("name", "is_active")}),
        ("gatilho", {"fields": ("trigger", "trigger_filter")}),
        ("conteúdo", {"fields": ("template", "platforms")}),
        ("audiência", {"fields": ("audience_rules",)}),
        (
            "publicação",
            {"fields": ("requires_approval", "expires_after_minutes", "notify_users", "schedule")},
        ),
    )

    @display(description="gatilho")
    def trigger_display(self, obj):
        return obj.get_trigger_display()


@admin.register(BroadcastPost)
class BroadcastPostAdmin(ModelAdmin):
    list_display = ("created_at", "status_display", "rule", "audience_total", "published_at")
    list_filter = ("status", "rule")
    search_fields = ("content",)
    readonly_fields = (
        "rule", "template", "status", "content", "platform_content", "platforms",
        "audience", "platform_results", "trigger_context", "approved_by",
        "approved_at", "published_at", "expires_at", "created_at",
    )
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False  # posts nascem de eventos, nunca da mão do gestor no Admin

    def has_change_permission(self, request, obj=None):
        return False

    @display(
        description="situação",
        label={
            "aguardando aprovação": "warning",
            "publicado": "success",
            "falhou": "danger",
            "expirado": "danger",
        },
    )
    def status_display(self, obj):
        return obj.get_status_display()

    @display(description="audiência")
    def audience_total(self, obj):
        return (obj.audience or {}).get("total", 0)
