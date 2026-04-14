from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie

logger = logging.getLogger(__name__)

from shopman.guestman.contrib.consent import ConsentService
from shopman.guestman.contrib.loyalty import LoyaltyService
from shopman.guestman.contrib.preferences import PreferenceService
from shopman.guestman.services import address as address_service
from shopman.guestman.services import customer as customer_service
from shopman.orderman.services import CustomerOrderHistoryService
from shopman.utils.monetary import format_money

from .auth import get_authenticated_customer
from .tracking import STATUS_COLORS, STATUS_LABELS

TAB_OPTIONS = [
    ("perfil", "Perfil"),
    ("pedidos", "Pedidos"),
    ("fidelidade", "Fidelidade"),
    ("config", "Configurações"),
]


def _get_loyalty_data(customer):
    """Fetch loyalty account and recent transactions."""

    try:
        account = LoyaltyService.get_account(customer.ref)
        if account:
            transactions = LoyaltyService.get_transactions(customer.ref, limit=5)
            return account, transactions
    except Exception as e:
        logger.warning("loyalty_data_failed customer=%s: %s", customer.ref, e, exc_info=True)
    return None, []


def _get_notification_prefs(customer) -> list[dict]:
    """Build notification preference list from ConsentService."""
    channels = [
        ("whatsapp", "WhatsApp", "Receber atualizações de pedidos via WhatsApp"),
        ("email", "Email", "Receber novidades e promoções por email"),
        ("sms", "SMS", "Receber notificações por SMS"),
        ("push", "Push", "Notificações push no navegador"),
    ]

    prefs = []
    try:
        for channel, label, description in channels:
            enabled = ConsentService.has_consent(customer.ref, channel)
            prefs.append({
                "key": channel,
                "label": label,
                "description": description,
                "enabled": enabled,
            })
    except Exception as e:
        logger.warning("notification_prefs_failed customer=%s: %s", customer.ref, e, exc_info=True)
    return prefs


def _enrich_orders(orders) -> list[dict]:
    """Build enriched order list with display info."""
    enriched = []
    for order in orders:
        enriched.append({
            "ref": getattr(order, "order_ref", getattr(order, "ref", "")),
            "created_at": getattr(order, "ordered_at", getattr(order, "created_at", None)),
            "total_display": f"R$ {format_money(order.total_q)}",
            "status": order.status,
            "status_label": STATUS_LABELS.get(order.status, order.status),
            "status_color": STATUS_COLORS.get(order.status, "bg-muted text-muted-foreground"),
        })
    return enriched


def _get_customer_addresses(customer_ref: str):
    return address_service.addresses(customer_ref)


def _get_customer_preferences(customer_ref: str):
    return PreferenceService.get_preferences(customer_ref)


def _get_active_food_keys(customer_ref: str) -> set[str]:
    return {pref.key for pref in PreferenceService.get_preferences(customer_ref, "alimentar")}


@method_decorator(ensure_csrf_cookie, name="dispatch")
class AccountView(View):
    """Account page: session-based auth → customer info + addresses + orders."""

    def get(self, request: HttpRequest) -> HttpResponse:
        customer = get_authenticated_customer(request)
        if not customer:
            return redirect("/login/?next=/minha-conta/")
        return self._render_account(request, customer, customer.phone)

    def _render_account(self, request: HttpRequest, customer, phone: str) -> HttpResponse:
        """Render account page with customer data."""
        addresses = _get_customer_addresses(customer.ref)
        orders = CustomerOrderHistoryService.list_customer_orders(customer.ref, limit=10)
        enriched_orders = _enrich_orders(orders)
        preferences = None
        try:
            prefs = _get_customer_preferences(customer.ref)
            if prefs:
                preferences = prefs
        except Exception as e:
            logger.warning("customer_preferences_failed: %s", e, exc_info=True)

        loyalty_account, loyalty_transactions = _get_loyalty_data(customer)

        # Stamps range for grid (2 rows × 5 cols = 10)
        stamps_range = []
        if loyalty_account and loyalty_account.stamps_target > 0:
            stamps_range = list(range(1, loyalty_account.stamps_target + 1))

        notification_prefs = _get_notification_prefs(customer)

        # Food preference options with active state
        active_food_keys = set()
        try:
            active_food_keys = _get_active_food_keys(customer.ref)
        except Exception as e:
            logger.warning("food_preferences_failed: %s", e, exc_info=True)
        food_pref_options = [
            (key, label, key in active_food_keys) for key, label in FOOD_PREFERENCE_OPTIONS
        ]

        return render(request, "storefront/account.html", {
            "customer": customer,
            "addresses": addresses,
            "orders": enriched_orders,
            "preferences": preferences,
            "loyalty_account": loyalty_account,
            "loyalty_transactions": loyalty_transactions,
            "stamps_range": stamps_range,
            "notification_prefs": notification_prefs,
            "food_pref_options": food_pref_options,
            "tab_options": TAB_OPTIONS,
            "phone_value": phone,
            "is_verified": True,
        })

    def post(self, request: HttpRequest) -> HttpResponse:
        # POST no longer needed — login handles authentication
        return redirect("/login/?next=/minha-conta/")


class AddressCreateView(View):
    """HTMX: create new address, return updated address list."""

    def post(self, request: HttpRequest) -> HttpResponse:
        customer = get_authenticated_customer(request)
        if not customer:
            return HttpResponse("Autenticação necessária.", status=401)

        label = request.POST.get("label", "home")
        label_custom = request.POST.get("label_custom", "").strip()
        formatted_address = request.POST.get("formatted_address", "").strip()
        route = request.POST.get("route", "").strip()
        street_number = request.POST.get("street_number", "").strip()
        neighborhood = request.POST.get("neighborhood", "").strip()
        city = request.POST.get("city", "").strip()
        complement = request.POST.get("complement", "").strip()
        delivery_instructions = request.POST.get("delivery_instructions", "").strip()
        is_default = request.POST.get("is_default") == "on"

        if not formatted_address:
            # Build formatted_address from components
            parts = []
            if route:
                parts.append(route)
            if street_number:
                parts.append(street_number)
            if neighborhood:
                parts.append(f"- {neighborhood}")
            if city:
                parts.append(f"- {city}")
            formatted_address = " ".join(parts) if parts else ""

        if not formatted_address:
            return render(request, "storefront/partials/address_form.html", {
                "customer": customer,
                "form_errors": {"formatted_address": "Endereço é obrigatório."},
                "form_data": request.POST,
            })

        address_service.add_address(
            customer_ref=customer.ref,
            label=label,
            label_custom=label_custom,
            formatted_address=formatted_address,
            complement=complement,
            delivery_instructions=delivery_instructions,
            is_default=is_default,
            components={
                "route": route,
                "street_number": street_number,
                "neighborhood": neighborhood,
                "city": city,
            },
        )

        addresses = _get_customer_addresses(customer.ref)
        return render(request, "storefront/partials/address_list.html", {
            "addresses": addresses,
            "customer": customer,
        })


class AddressUpdateView(View):
    """HTMX: update existing address, return updated item."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        auth_customer = get_authenticated_customer(request)
        if not auth_customer:
            return HttpResponse("Autenticação necessária.", status=401)

        if address_service.address_belongs_to_other_customer(auth_customer.ref, pk):
            return HttpResponse("Acesso não autorizado.", status=403)
        addr = address_service.get_address(auth_customer.ref, pk)
        if not addr:
            return HttpResponse("Endereço não encontrado.", status=404)
        customer = auth_customer

        label = request.POST.get("label", addr.label)
        label_custom = request.POST.get("label_custom", "").strip()
        formatted_address = request.POST.get("formatted_address", addr.formatted_address).strip()
        route = request.POST.get("route", "").strip()
        street_number = request.POST.get("street_number", "").strip()
        neighborhood = request.POST.get("neighborhood", "").strip()
        city = request.POST.get("city", "").strip()
        complement = request.POST.get("complement", "").strip()
        delivery_instructions = request.POST.get("delivery_instructions", "").strip()

        if not formatted_address:
            parts = []
            if route:
                parts.append(route)
            if street_number:
                parts.append(street_number)
            if neighborhood:
                parts.append(f"- {neighborhood}")
            if city:
                parts.append(f"- {city}")
            formatted_address = " ".join(parts) if parts else ""

        address_service.update_address(
            customer.ref,
            pk,
            label=label,
            label_custom=label_custom,
            formatted_address=formatted_address,
            route=route,
            street_number=street_number,
            neighborhood=neighborhood,
            city=city,
            complement=complement,
            delivery_instructions=delivery_instructions,
        )

        addresses = _get_customer_addresses(customer.ref)
        return render(request, "storefront/partials/address_list.html", {
            "addresses": addresses,
            "customer": customer,
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
        return render(request, "storefront/partials/address_list.html", {
            "addresses": addresses,
            "customer": auth_customer,
        })


class ProfileDisplayView(View):
    """HTMX: return profile display partial (read-only)."""

    def get(self, request: HttpRequest) -> HttpResponse:
        customer = get_authenticated_customer(request)
        if not customer:
            return HttpResponse("Autenticação necessária.", status=401)
        return render(request, "storefront/partials/profile_display.html", {
            "customer": customer,
        })


class ProfileEditView(View):
    """HTMX: return profile edit form partial."""

    def get(self, request: HttpRequest) -> HttpResponse:
        customer = get_authenticated_customer(request)
        if not customer:
            return HttpResponse("Autenticação necessária.", status=401)
        return render(request, "storefront/partials/profile_form.html", {
            "customer": customer,
        })


class ProfileUpdateView(View):
    """HTMX: update customer profile, return display partial."""

    def post(self, request: HttpRequest) -> HttpResponse:
        customer = get_authenticated_customer(request)
        if not customer:
            return HttpResponse("Autenticação necessária.", status=401)

        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        email = request.POST.get("email", "").strip()
        birthday_raw = request.POST.get("birthday", "").strip()

        errors = {}
        if not first_name:
            errors["first_name"] = "Nome é obrigatório."

        if errors:
            return render(request, "storefront/partials/profile_form.html", {
                "customer": customer,
                "errors": errors,
            })

        if birthday_raw:
            from datetime import date as date_type

            try:
                birthday = date_type.fromisoformat(birthday_raw)
            except ValueError:
                birthday = customer.birthday
        else:
            birthday = None

        customer = customer_service.update(
            customer.ref,
            first_name=first_name,
            last_name=last_name,
            email=email,
            birthday=birthday,
        )

        return render(request, "storefront/partials/profile_display.html", {
            "customer": customer,
        })


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
        return render(request, "storefront/partials/address_list.html", {
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

        prefs = _get_notification_prefs(customer)
        html_parts = []
        for pref in prefs:
            checked = "checked" if pref["enabled"] else ""
            html_parts.append(
                f'<label class="flex items-center justify-between py-2 cursor-pointer">'
                f'<div><p class="text-sm font-medium text-foreground">{pref["label"]}</p>'
                f'<p class="text-xs text-muted-foreground">{pref["description"]}</p></div>'
                f'<div class="relative inline-flex cursor-pointer">'
                f'<input type="hidden" name="channel" value="{pref["key"]}">'
                f'<button type="button" hx-post="/minha-conta/notificacoes/" '
                f'hx-vals=\'{{"channel": "{pref["key"]}"}}\' '
                f'hx-target="#notification-prefs" hx-swap="innerHTML" '
                f'class="w-11 h-6 rounded-full transition-colors '
                f'{"bg-primary" if pref["enabled"] else "bg-border"}" '
                f'style="min-height:24px">'
                f'<span class="block w-5 h-5 bg-white rounded-full shadow transform transition-transform '
                f'{"translate-x-5" if pref["enabled"] else "translate-x-0.5"}" '
                f'style="margin-top:2px"></span>'
                f'</button></div></label>'
            )
        return HttpResponse("".join(html_parts))


FOOD_PREFERENCE_OPTIONS = [
    ("sem_gluten", "Sem Glúten"),
    ("sem_lactose", "Sem Lactose"),
    ("vegano", "Vegano"),
    ("vegetariano", "Vegetariano"),
    ("sem_acucar", "Sem Açúcar"),
    ("sem_nozes", "Sem Nozes"),
    ("organico", "Orgânico"),
    ("integral", "Integral"),
]


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

        # Return updated tags
        active_keys = _get_active_food_keys(customer.ref)

        html_parts = []
        for opt_key, opt_label in FOOD_PREFERENCE_OPTIONS:
            active = opt_key in active_keys
            cls = "bg-primary text-white" if active else "bg-background text-muted-foreground border border-border"
            html_parts.append(
                f'<button type="button" '
                f'hx-post="/minha-conta/preferencias/" '
                f'hx-vals=\'{{"key": "{opt_key}"}}\' '
                f'hx-target="#food-prefs" hx-swap="innerHTML" '
                f'class="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium '
                f'transition-colors {cls}" '
                f'style="min-height:var(--touch-min)">'
                f'{opt_label}</button>'
            )
        return HttpResponse("".join(html_parts))


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
