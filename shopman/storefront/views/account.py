from __future__ import annotations

import json
import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie

logger = logging.getLogger(__name__)

from shopman.guestman.contrib.consent import ConsentService
from shopman.guestman.contrib.preferences import PreferenceService
from shopman.guestman.services import address as address_service
from shopman.guestman.services import customer as customer_service

from shopman.shop.projections.types import FoodPrefProjection, NotificationPrefProjection
from shopman.storefront.projections.account import (
    FOOD_PREFERENCE_OPTIONS,
    NOTIFICATION_CHANNELS,
    build_account,
)
from shopman.storefront.services.address_picker import address_picker_context

from .auth import get_authenticated_customer


def _get_customer_addresses(customer_ref: str):
    return address_service.addresses(customer_ref)


def _account_picker_context() -> dict:
    """Picker context for the account page (empty saved list + shop location)."""
    return address_picker_context()


def _get_customer_preferences(customer_ref: str):
    return PreferenceService.get_preferences(customer_ref)


def _get_active_food_keys(customer_ref: str) -> set[str]:
    return {pref.key for pref in PreferenceService.get_preferences(customer_ref, "alimentar")}


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
        created = address_service.add_address(
            customer_ref=customer.ref,
            label=intent.label,
            label_custom=intent.label_custom,
            formatted_address=intent.formatted_address,
            place_id=intent.place_id,
            coordinates=intent.coordinates,
            complement=intent.complement,
            delivery_instructions=intent.delivery_instructions,
            is_default=intent.is_default,
            components={
                "route": intent.route,
                "street_number": intent.street_number,
                "neighborhood": intent.neighborhood,
                "city": intent.city,
                "state_code": intent.state_code,
                "postal_code": intent.postal_code,
            },
        )

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

        if address_service.address_belongs_to_other_customer(auth_customer.ref, pk):
            return HttpResponse("Acesso não autorizado.", status=403)
        addr = address_service.get_address(auth_customer.ref, pk)
        if not addr:
            return HttpResponse("Endereço não encontrado.", status=404)

        result = interpret_address_update(request, addr)
        intent = result.intent
        if not intent:
            return HttpResponse("Dados inválidos.", status=400)

        update_fields: dict = {
            "label": intent.label,
            "label_custom": intent.label_custom,
            "formatted_address": intent.formatted_address,
            "route": intent.route,
            "street_number": intent.street_number,
            "neighborhood": intent.neighborhood,
            "city": intent.city,
            "state_code": intent.state_code,
            "postal_code": intent.postal_code,
            "complement": intent.complement,
            "delivery_instructions": intent.delivery_instructions,
            "place_id": intent.place_id,
        }
        if intent.coordinates is not None:
            update_fields["latitude"] = intent.coordinates[0]
            update_fields["longitude"] = intent.coordinates[1]
            update_fields["is_verified"] = True

        address_service.update_address(auth_customer.ref, pk, **update_fields)

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

        if address_service.address_belongs_to_other_customer(auth_customer.ref, pk):
            return HttpResponse("Acesso não autorizado.", status=403)
        if not address_service.get_address(auth_customer.ref, pk):
            return HttpResponse("Endereço não encontrado.", status=404)

        address_service.delete_address(auth_customer.ref, pk)

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
        customer = customer_service.update(
            customer.ref,
            first_name=intent.first_name,
            last_name=intent.last_name,
            email=intent.email,
            birthday=intent.birthday,
        )
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

        if address_service.address_belongs_to_other_customer(customer.ref, pk):
            return HttpResponse("", status=403)
        if not address_service.get_address(customer.ref, pk):
            return HttpResponse("", status=404)

        label = request.POST.get("label", "home")
        label_custom = request.POST.get("label_custom", "").strip()
        address_service.update_address(
            customer.ref, pk, label=label, label_custom=label_custom,
        )
        return HttpResponse("", status=204)


class AddressSetDefaultView(View):
    """HTMX: set address as default, return updated list."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        auth_customer = get_authenticated_customer(request)
        if not auth_customer:
            return HttpResponse("Autenticação necessária.", status=401)

        if address_service.address_belongs_to_other_customer(auth_customer.ref, pk):
            return HttpResponse("Acesso não autorizado.", status=403)
        if not address_service.get_address(auth_customer.ref, pk):
            return HttpResponse("Endereço não encontrado.", status=404)

        address_service.set_default_address(auth_customer.ref, pk)

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


        if ConsentService.has_consent(customer.ref, channel):
            ConsentService.revoke_consent(customer.ref, channel)
        else:
            ip = request.META.get("REMOTE_ADDR", "")
            ConsentService.grant_consent(
                customer.ref, channel,
                source="storefront_settings",
                legal_basis="consent",
                ip_address=ip,
            )

        notification_prefs = tuple(
            NotificationPrefProjection(
                key=key,
                label=label,
                description=description,
                enabled=ConsentService.has_consent(customer.ref, key),
            )
            for key, label, description in NOTIFICATION_CHANNELS
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

        existing = PreferenceService.get_preference(customer.ref, "alimentar", key)
        if existing is not None:
            PreferenceService.delete_preference(customer.ref, "alimentar", key)
        else:
            PreferenceService.set_preference(
                customer.ref, "alimentar", key, value=True,
                preference_type="restriction", source="storefront_settings",
            )

        active_keys = _get_active_food_keys(customer.ref)
        food_pref_options = tuple(
            FoodPrefProjection(key=k, label=label, is_active=k in active_keys)
            for k, label in FOOD_PREFERENCE_OPTIONS
        )
        tmpl = "storefront/partials/food_prefs.html"
        return render(request, tmpl, {"food_pref_options": food_pref_options})


class DataExportView(View):
    """LGPD: export all customer data as JSON download."""

    def get(self, request: HttpRequest) -> HttpResponse:

        from django.http import JsonResponse

        customer = get_authenticated_customer(request)
        if not customer:
            return redirect("/login/?next=/minha-conta/")

        data = {
            "customer": {
                "ref": customer.ref,
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "phone": customer.phone,
                "email": customer.email,
                "birthday": str(customer.birthday) if customer.birthday else None,
                "created_at": customer.created_at.isoformat(),
            },
            "addresses": [
                {
                    "label": addr.label,
                    "formatted_address": addr.formatted_address,
                    "route": addr.route,
                    "street_number": addr.street_number,
                    "neighborhood": addr.neighborhood,
                    "city": addr.city,
                    "complement": addr.complement,
                    "delivery_instructions": addr.delivery_instructions,
                    "is_default": addr.is_default,
                }
                for addr in _get_customer_addresses(customer.ref)
            ],
        }

        # Orders
        from shopman.orderman.services import CustomerOrderHistoryService
        orders = CustomerOrderHistoryService.list_customer_orders(customer.ref, limit=100)
        data["orders"] = [
            {
                "ref": o.order_ref,
                "status": o.status,
                "total_q": o.total_q,
                "created_at": o.ordered_at.isoformat(),
                "items": o.items,
            }
            for o in orders
        ]

        # Preferences
        data["preferences"] = [
            {
                "category": pref.category,
                "key": pref.key,
                "value": pref.value,
                "preference_type": pref.preference_type,
            }
            for pref in _get_customer_preferences(customer.ref)
        ]

        # Consent
        data["consents"] = [
            {
                "channel": consent.channel,
                "status": consent.status,
                "consented_at": consent.consented_at,
                "revoked_at": consent.revoked_at,
            }
            for consent in ConsentService.get_consents(customer.ref)
        ]

        # Loyalty
        try:
            from shopman.guestman.contrib.loyalty import LoyaltyService
            account = LoyaltyService.get_account(customer.ref)
            if account:
                data["loyalty"] = {
                    "tier": account.tier,
                    "points_balance": account.points_balance,
                    "lifetime_points": account.lifetime_points,
                    "stamps_current": account.stamps_current,
                }
                txns = LoyaltyService.get_transactions(customer.ref, limit=100)
                data["loyalty"]["transactions"] = [
                    {
                        "type": t.transaction_type,
                        "points": t.points,
                        "description": t.description,
                        "created_at": t.created_at.isoformat(),
                    }
                    for t in txns
                ]
        except Exception as e:
            logger.warning("data_export_loyalty_failed: %s", e, exc_info=True)

        response = JsonResponse(data, json_dumps_params={"ensure_ascii": False, "indent": 2})
        response["Content-Disposition"] = f'attachment; filename="meus-dados-{customer.ref}.json"'
        return response


class AccountDeleteView(View):
    """LGPD: anonymize customer data and deactivate account."""

    def post(self, request: HttpRequest) -> HttpResponse:
        customer = get_authenticated_customer(request)
        if not customer:
            return HttpResponse("", status=401)

        import hashlib

        # Anonymize personal data
        original_ref = customer.ref
        original_phone = customer.phone
        phone_hash = hashlib.sha256(original_phone.encode()).hexdigest()[:12]

        # Revoke all consents while the customer is still active
        for channel in ("whatsapp", "email", "sms", "push"):
            try:
                ConsentService.revoke_consent(original_ref, channel)
            except Exception as e:
                logger.warning("consent_revoke_failed channel=%s: %s", channel, e, exc_info=True)

        # Delete addresses while the customer is still active
        try:
            address_service.delete_all_addresses(original_ref)
        except Exception as e:
            logger.warning("address_cleanup_failed customer=%s: %s", original_ref, e, exc_info=True)

        customer.first_name = "Anonimizado"
        customer.last_name = ""
        customer.email = ""
        customer.phone = ""
        customer.birthday = None
        customer.notes = ""
        customer.is_active = False
        customer.save()

        # Clear session
        request.session.flush()

        logger.info("account_deleted customer=%s phone_hash=%s", original_ref, phone_hash)

        response = HttpResponse("")
        response["HX-Redirect"] = "/"
        return response
