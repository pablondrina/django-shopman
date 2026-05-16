"""
Unfold-themed admin for shopman.refs.

Install by adding 'shopman.refs.contrib.admin_unfold' to INSTALLED_APPS
AFTER 'shopman.refs'. This replaces the basic admin with Unfold badges,
filters, bulk actions, and the RefInline helper.

Usage in any other admin:

    from shopman.refs.contrib.admin_unfold.admin import RefInline

    class SessionAdmin(BaseModelAdmin):
        inlines = [RefInline]
"""

from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.db.models import Count, Q
from django.template.response import TemplateResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from shopman.utils.contrib.admin_unfold.badges import unfold_badge
from shopman.utils.contrib.admin_unfold.base import BaseModelAdmin, BaseTabularInline
from unfold.decorators import display
from unfold.widgets import UnfoldAdminTextInputWidget

from shopman.refs.bulk import RefBulk
from shopman.refs.models import Ref, RefSequence

# ── Unregister basic admins ───────────────────────────────────────────────────

for _model in [Ref, RefSequence]:
    try:
        admin.site.unregister(_model)
    except admin.sites.NotRegistered:
        pass


# ── Custom filters ────────────────────────────────────────────────────────────

class RefTypeFilter(admin.SimpleListFilter):
    """Filter by ref_type slug (auto-populated from existing refs)."""
    title = _("Tipo")
    parameter_name = "ref_type"

    def lookups(self, request, model_admin):
        types = Ref.objects.values_list("ref_type", flat=True).distinct().order_by("ref_type")
        return [(t, t) for t in types]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(ref_type=self.value())
        return queryset


class TargetTypeFilter(admin.SimpleListFilter):
    """Filter by target_type (e.g., 'orderman.Session')."""
    title = _("Tipo do alvo")
    parameter_name = "target_type"

    def lookups(self, request, model_admin):
        types = Ref.objects.values_list("target_type", flat=True).distinct().order_by("target_type")
        return [(t, t) for t in types]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(target_type=self.value())
        return queryset


class RenameValueForm(forms.Form):
    new_value = forms.CharField(
        label=_("Novo valor"),
        widget=UnfoldAdminTextInputWidget(
            attrs={"placeholder": _("Valor normalizado (ex: CROISSANT-FR)")}
        ),
    )


# ── Ref admin ─────────────────────────────────────────────────────────────────

@admin.register(Ref)
class RefUnfoldAdmin(BaseModelAdmin):
    """Read-mostly admin for Ref. Creates via services only; admin allows manual deactivation."""

    list_display = [
        "ref_type_display",
        "value",
        "target_type",
        "target_id",
        "status_badge",
        "actor",
        "created_at",
    ]
    list_filter = [RefTypeFilter, "is_active", TargetTypeFilter]
    search_fields = ["value", "target_id", "actor"]
    ordering = ["-created_at"]
    readonly_fields = [
        "id", "ref_type", "value",
        "target_type", "target_id",
        "scope", "actor",
        "created_at", "deactivated_at", "deactivated_by",
        "metadata",
    ]
    actions = ["deactivate_selected", "rename_value_action"]

    # Unfold options
    compressed_fields = True
    list_filter_submit = True

    def has_add_permission(self, request):
        return False

    # ── Display columns ───────────────────────────────────────────────────────

    @display(description=_("Tipo"))
    def ref_type_display(self, obj):
        return unfold_badge(obj.ref_type, "blue")

    @display(description=_("Status"))
    def status_badge(self, obj):
        if obj.is_active:
            return unfold_badge(_("ativo"), "green")
        return unfold_badge(_("inativo"), "red")

    # ── Bulk actions ──────────────────────────────────────────────────────────

    @admin.action(description=_("Desativar selecionados"))
    def deactivate_selected(self, request, queryset):
        now = timezone.now()
        actor = str(request.user)
        count = queryset.filter(is_active=True).update(
            is_active=False,
            deactivated_at=now,
            deactivated_by=actor,
        )
        self.message_user(
            request,
            _("{count} referência(s) desativada(s).").format(count=count),
        )

    @admin.action(description=_("Rename value..."))
    def rename_value_action(self, request, queryset):
        """Intermediate page to rename ref values for the selected refs."""
        form = RenameValueForm(request.POST or None)
        if request.POST.get("_rename_confirm"):
            if form.is_valid():
                new_value = form.cleaned_data["new_value"].strip()
                actor = str(request.user)
                total = 0
                for ref_type, old_value in queryset.values_list("ref_type", "value").distinct():
                    total += RefBulk.rename(ref_type, old_value, new_value, actor=actor)

                self.message_user(
                    request,
                    _("{total} referência(s) renomeadas para '{new_value}'.").format(
                        total=total, new_value=new_value
                    ),
                )
                return
            self.message_user(request, _("Novo valor não pode ser vazio."), messages.ERROR)

        return TemplateResponse(
            request,
            "admin/refs/rename_confirm.html",
            {
                "form": form,
                "queryset": queryset,
                "action_checkbox_name": admin.helpers.ACTION_CHECKBOX_NAME,
                "opts": self.model._meta,
                "app_label": self.model._meta.app_label,
                "title": _("Rename refs"),
            },
        )


# ── RefSequence admin ─────────────────────────────────────────────────────────

@admin.register(RefSequence)
class RefSequenceUnfoldAdmin(BaseModelAdmin):
    list_display = ["sequence_name", "scope_hash", "last_value"]
    search_fields = ["sequence_name", "scope_hash"]
    readonly_fields = ["id", "sequence_name", "scope_hash", "scope", "last_value"]
    ordering = ["sequence_name", "scope_hash"]
    compressed_fields = True

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ── RefInline ─────────────────────────────────────────────────────────────────

class RefInline(BaseTabularInline):
    """Read-only inline showing all Refs linked to the parent model instance.

    Add to any ModelAdmin to see attached refs::

        from shopman.refs.contrib.admin_unfold.admin import RefInline

        class OrderAdmin(BaseModelAdmin):
            inlines = [RefInline]

    The inline automatically detects target_type from the parent model's
    app_label + class name, and filters by the parent instance's pk.
    """

    model = Ref
    extra = 0
    fields = ["ref_type", "value", "is_active", "scope", "actor", "created_at"]
    readonly_fields = ["ref_type", "value", "is_active", "scope", "actor", "created_at"]
    verbose_name = _("Referência")
    verbose_name_plural = _("Referências vinculadas")
    can_delete = False

    def get_formset(self, request, obj=None, **kwargs):
        # Store parent object before super() calls get_queryset()
        self._parent_obj = obj
        return super().get_formset(request, obj, **kwargs)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        obj = getattr(self, "_parent_obj", None)
        if obj is not None:
            target_type = f"{obj._meta.app_label}.{obj._meta.object_name}"
            target_id = str(obj.pk)
            return qs.filter(target_type=target_type, target_id=target_id).order_by("-created_at")
        return qs.none()

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ── Dashboard widget callback ─────────────────────────────────────────────────

def refs_summary_callback(request, context: dict) -> dict:
    """Populate admin dashboard context with Ref statistics.

    Intended for use as (or called from) UNFOLD DASHBOARD_CALLBACK:

        UNFOLD = {
            "DASHBOARD_CALLBACK": "...",
        }

    Or called from an existing dashboard_callback::

        from shopman.refs.contrib.admin_unfold.admin import refs_summary_callback

        def dashboard_callback(request, context):
            context = refs_summary_callback(request, context)
            # ... other context updates
            return context

    Adds to context:
        refs_stats (dict):
            total_active (int)
            total_inactive (int)
            by_type (list[dict]):   ref_type, active_count, inactive_count
            recently_deactivated (int): deactivated in the last 24h
    """
    from datetime import timedelta

    now = timezone.now()
    yesterday = now - timedelta(hours=24)

    total_active = Ref.objects.filter(is_active=True).count()
    total_inactive = Ref.objects.filter(is_active=False).count()
    recently_deactivated = Ref.objects.filter(
        is_active=False, deactivated_at__gte=yesterday
    ).count()

    by_type = list(
        Ref.objects.values("ref_type")
        .annotate(
            active_count=Count("id", filter=Q(is_active=True)),
            inactive_count=Count("id", filter=Q(is_active=False)),
        )
        .order_by("ref_type")
    )

    context["refs_stats"] = {
        "total_active": total_active,
        "total_inactive": total_inactive,
        "recently_deactivated": recently_deactivated,
        "by_type": by_type,
    }
    return context
