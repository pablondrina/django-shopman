from __future__ import annotations

import json
import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie

from shopman.shop.services import account as account_service
from shopman.storefront.projections.account import build_account
from shopman.storefront.services.address_picker import address_picker_context

from .auth import get_authenticated_customer

logger = logging.getLogger(__name__)


def _get_customer_addresses(customer_ref: str):
    return account_service.addresses(customer_ref)


def _account_picker_context() -> dict:
    """Picker context for the account page (empty saved list + shop location)."""
    return address_picker_context()


def _get_customer_preferences(customer_ref: str):
    return account_service.preferences(customer_ref)


def _get_active_food_keys(customer_ref: str) -> set[str]:
    return account_service.active_food_keys(customer_ref)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class AccountView(View):
    """Account page: session-based auth → CustomerProfileProjection."""

    def get(self, request: HttpRequest) -> HttpResponse:
        customer = get_authenticated_customer(request)
        if not customer:
            return redirect("/login/?next=/minha-conta/")
        return self._render_account(request, customer)

    def _render_account(self, request: HttpRequest, customer) -> HttpResponse:
        account = build_account(customer)
        addresses = _get_customer_addresses(customer.ref)
        tmpl = "storefront/account.html"
        return render(request, tmpl, {
            "account": account,
            "customer": customer,   # for HTMX partials (profile_display, address_form)
            "addresses": addresses, # for address_list include
            **_account_picker_context(),
        })

    def post(self, request: HttpRequest) -> HttpResponse:
        # POST no longer needed — login handles authentication
        return redirect("/login/?next=/minha-conta/")


class AddressCreateView(View):
    """HTMX: create new address, return updated address list."""

    def post(self, request: HttpRequest) -> HttpResponse:
        from ..intents.account import interpret_address_create

        customer = get_authenticated_customer(request)
        if not customer:
            return HttpResponse("Autenticação necessária.", status=401)

        result = interpret_address_create(request)
        if not result.intent:
            return render(request, "storefront/partials/address_form.html", {
                "customer": customer,
                "form_errors": result.errors,
                "form_data": result.form_data,
                **_account_picker_context(),
            })

        intent = result.intent
        created = account_service.add_address(customer.ref, intent)

        addresses = _get_customer_addresses(customer.ref)
        response = render(request, "storefront/partials/address_list.html", {
            "addresses": addresses,
            "customer": customer,
        })
        response["HX-Trigger"] = json.dumps({"address:created": {"id": created.pk}})
        return response


class AddressUpdateView(View):
    """HTMX: update existing address, return updated item."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        from ..intents.account import interpret_address_update

        auth_customer = get_authenticated_customer(request)
        if not auth_customer:
            return HttpResponse("Autenticação necessária.", status=401)

        if account_service.address_belongs_to_other_customer(auth_customer.ref, pk):
            return HttpResponse("Acesso não autorizado.", status=403)
        addr = account_service.get_address(auth_customer.ref, pk)
        if not addr:
            return HttpResponse("Endereço não encontrado.", status=404)

        result = interpret_address_update(request, addr)
        intent = result.intent
        if not intent:
            return HttpResponse("Dados inválidos.", status=400)

        account_service.update_address(auth_customer.ref, pk, intent)

        addresses = _get_customer_addresses(auth_customer.ref)
        return render(request, "storefront/partials/address_list.html", {
            "addresses": addresses,
            "customer": auth_customer,
        })


class AddressDeleteView(View):
    """HTMX: delete address, return updated list."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        auth_customer = get_authenticated_customer(request)
        if not auth_customer:
            return HttpResponse("Autenticação necessária.", status=401)

        if account_service.address_belongs_to_other_customer(auth_customer.ref, pk):
            return HttpResponse("Acesso não autorizado.", status=403)
        if not account_service.get_address(auth_customer.ref, pk):
            return HttpResponse("Endereço não encontrado.", status=404)

        account_service.delete_address(auth_customer.ref, pk)

        addresses = _get_customer_addresses(auth_customer.ref)
        list_tmpl = "storefront/partials/address_list.html"
        return render(request, list_tmpl, {
            "addresses": addresses,
            "customer": auth_customer,
        })


class ProfileDisplayView(View):
    """HTMX: return profile display partial (read-only)."""

    def get(self, request: HttpRequest) -> HttpResponse:
        customer = get_authenticated_customer(request)
        if not customer:
            return HttpResponse("Autenticação necessária.", status=401)
        tmpl = "storefront/partials/profile_display.html"
        return render(request, tmpl, {"customer": customer})


class ProfileEditView(View):
    """HTMX: return profile edit form partial."""

    def get(self, request: HttpRequest) -> HttpResponse:
        customer = get_authenticated_customer(request)
        if not customer:
            return HttpResponse("Autenticação necessária.", status=401)
        tmpl = "storefront/partials/profile_form.html"
        return render(request, tmpl, {"customer": customer})


class ProfileUpdateView(View):
    """HTMX: update customer profile, return display partial."""

    def post(self, request: HttpRequest) -> HttpResponse:
        from ..intents.account import interpret_profile_update

        customer = get_authenticated_customer(request)
        if not customer:
            return HttpResponse("Autenticação necessária.", status=401)

        result = interpret_profile_update(request)
        if not result.intent:
            return render(request, "storefront/partials/profile_form.html", {
                "customer": customer,
                "errors": result.errors,
            })

        intent = result.intent
        customer = account_service.update_profile(customer.ref, intent)
        return render(request, "storefront/partials/profile_display.html", {"customer": customer})


class AddressLabelUpdateView(View):
    """HTMX: lightweight label-only update invoked by the post-save modal.

    The address picker surfaces a gentle "Casa / Trabalho / Outro" prompt after
    a new address is saved. This endpoint updates just the label and
    label_custom fields without re-running the full create flow.
    """

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        customer = get_authenticated_customer(request)
        if not customer:
            return HttpResponse("", status=401)

        if account_service.address_belongs_to_other_customer(customer.ref, pk):
            return HttpResponse("", status=403)
        if not account_service.get_address(customer.ref, pk):
            return HttpResponse("", status=404)

        label = request.POST.get("label", "home")
        label_custom = request.POST.get("label_custom", "").strip()
        account_service.update_address_label(customer.ref, pk, label=label, label_custom=label_custom)
        return HttpResponse("", status=204)


class AddressSetDefaultView(View):
    """HTMX: set address as default, return updated list."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        auth_customer = get_authenticated_customer(request)
        if not auth_customer:
            return HttpResponse("Autenticação necessária.", status=401)

        if account_service.address_belongs_to_other_customer(auth_customer.ref, pk):
            return HttpResponse("Acesso não autorizado.", status=403)
        if not account_service.get_address(auth_customer.ref, pk):
            return HttpResponse("Endereço não encontrado.", status=404)

        account_service.set_default_address(auth_customer.ref, pk)

        addresses = _get_customer_addresses(auth_customer.ref)
        list_tmpl = "storefront/partials/address_list.html"
        return render(request, list_tmpl, {
            "addresses": addresses,
            "customer": auth_customer,
        })


class NotificationPrefsToggleView(View):
    """HTMX: toggle a notification consent channel (ConsentService)."""

    def post(self, request: HttpRequest) -> HttpResponse:
        customer = get_authenticated_customer(request)
        if not customer:
            return HttpResponse("", status=401)

        channel = request.POST.get("channel", "")
        if not channel:
            return HttpResponse("", status=400)

        notification_prefs = account_service.toggle_notification_consent(
            customer.ref,
            channel,
            ip_address=request.META.get("REMOTE_ADDR", ""),
        )
        tmpl = "storefront/partials/notification_prefs.html"
        return render(request, tmpl, {"notification_prefs": notification_prefs})


class FoodPreferenceToggleView(View):
    """HTMX: toggle a food preference tag (PreferenceService)."""

    def post(self, request: HttpRequest) -> HttpResponse:
        customer = get_authenticated_customer(request)
        if not customer:
            return HttpResponse("", status=401)

        key = request.POST.get("key", "")
        if not key:
            return HttpResponse("", status=400)

        food_pref_options = account_service.toggle_food_preference(customer.ref, key)
        tmpl = "storefront/partials/food_prefs.html"
        return render(request, tmpl, {"food_pref_options": food_pref_options})


class DataExportView(View):
    """LGPD: export all customer data as JSON download."""

    def get(self, request: HttpRequest) -> HttpResponse:

        from django.http import JsonResponse

        customer = get_authenticated_customer(request)
        if not customer:
            return redirect("/login/?next=/minha-conta/")

        data = account_service.export_customer_data(customer)

        response = JsonResponse(data, json_dumps_params={"ensure_ascii": False, "indent": 2})
        response["Content-Disposition"] = f'attachment; filename="meus-dados-{customer.ref}.json"'
        return response


class AccountDeleteView(View):
    """LGPD: anonymize customer data and deactivate account."""

    def post(self, request: HttpRequest) -> HttpResponse:
        customer = get_authenticated_customer(request)
        if not customer:
            return HttpResponse("", status=401)

        original_ref, phone_hash = account_service.anonymize_customer(customer)

        # Clear session
        request.session.flush()

        logger.info("account_deleted customer=%s phone_hash=%s", original_ref, phone_hash)

        response = HttpResponse("")
        response["HX-Redirect"] = "/"
        return response
