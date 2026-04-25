"""Admin action for customer merge."""

from __future__ import annotations

from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from shopman.guestman.exceptions import CustomerError
from shopman.guestman.models import Customer


class MergeAdminMixin:
    """
    Mixin that adds a "Merge into..." action to CustomerAdmin.

    Usage: Add this mixin to CustomerAdmin's bases, or call
    register_merge_action() after admin is ready.
    """

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "merge/",
                self.admin_site.admin_view(self.merge_view),
                name="guestman_customer_merge",
            ),
        ]
        return custom + urls

    def merge_customers_action(self, request: HttpRequest, queryset):
        """Admin action: merge selected customers."""
        if queryset.count() != 2:
            self.message_user(
                request,
                "Selecione exatamente 2 clientes para merge.",
                messages.ERROR,
            )
            return

        ids = list(queryset.values_list("pk", flat=True))
        url = reverse("admin:guestman_customer_merge")
        return HttpResponseRedirect(
            f"{url}?source={ids[0]}&target={ids[1]}"
        )

    merge_customers_action.short_description = "Merge: primeiro → segundo (ordem de seleção)"

    def merge_view(self, request: HttpRequest):
        """Confirmation page + execute merge."""
        source_pk = request.GET.get("source") or request.POST.get("source")
        target_pk = request.GET.get("target") or request.POST.get("target")

        try:
            source = Customer.objects.get(pk=source_pk)
            target = Customer.objects.get(pk=target_pk)
        except (Customer.DoesNotExist, ValueError, TypeError):
            self.message_user(request, "Clientes inválidos.", messages.ERROR)
            return HttpResponseRedirect(
                reverse("admin:guestman_customer_changelist")
            )

        if request.method == "POST" and "confirm" in request.POST:
            from shopman.guestman.contrib.merge.service import MergeService

            try:
                result = MergeService.merge(
                    source_customer=source,
                    target_customer=target,
                    evidence={"staff_override": True},
                    actor=f"admin:{request.user}",
                )
                self.message_user(
                    request,
                    f"Merge concluído: {result.source_ref} → {result.target_ref}. "
                    f"Migrados: {result.migrated_contact_points} contatos, "
                    f"{result.migrated_preferences} preferências, "
                    f"{result.migrated_timeline_events} eventos.",
                    messages.SUCCESS,
                )
            except CustomerError as exc:
                self.message_user(
                    request,
                    f"Merge falhou: {exc}",
                    messages.ERROR,
                )

            return HttpResponseRedirect(
                reverse("admin:guestman_customer_changelist")
            )

        # GET — show confirmation page
        context = {
            **self.admin_site.each_context(request),
            "title": "Confirmar Merge de Clientes",
            "source": source,
            "target": target,
            "opts": self.model._meta,
        }
        return TemplateResponse(
            request,
            "admin/guestman/customer/merge_confirm.html",
            context,
        )


def register_merge_action(admin_class=None):
    """
    Register the merge action on CustomerAdmin.

    Can be called from AppConfig.ready() or used as a decorator.
    """
    if admin_class is None:
        # Find the registered CustomerAdmin
        try:
            admin_class = admin.site._registry[Customer].__class__
        except (KeyError, AttributeError):
            return

    if not hasattr(admin_class, "merge_customers_action"):
        # Dynamically add the action
        from shopman.guestman.contrib.merge.service import MergeService

        def merge_action(modeladmin, request, queryset):
            if queryset.count() != 2:
                modeladmin.message_user(
                    request,
                    "Selecione exatamente 2 clientes para merge.",
                    messages.ERROR,
                )
                return

            customers = list(queryset.order_by("pk"))
            source, target = customers[0], customers[1]

            try:
                result = MergeService.merge(
                    source_customer=source,
                    target_customer=target,
                    evidence={"staff_override": True},
                    actor=f"admin:{request.user}",
                )
                modeladmin.message_user(
                    request,
                    f"Merge concluído: {result.source_ref} → {result.target_ref}.",
                    messages.SUCCESS,
                )
            except CustomerError as exc:
                modeladmin.message_user(
                    request,
                    f"Merge falhou: {exc}",
                    messages.ERROR,
                )

        merge_action.short_description = "Merge: primeiro → segundo (por PK)"

        # Add to actions
        existing_actions = list(getattr(admin_class, "actions", []) or [])
        existing_actions.append(merge_action)
        admin_class.actions = existing_actions
