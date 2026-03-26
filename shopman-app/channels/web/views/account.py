from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from shopman.ordering.models import Order
from shopman.utils.monetary import format_money
from shopman.utils.phone import normalize_phone

from ..constants import get_default_ddd
from .auth import get_authenticated_customer
from .tracking import STATUS_COLORS, STATUS_LABELS


def _get_loyalty_data(customer):
    """Fetch loyalty account and recent transactions if loyalty is installed."""
    try:
        from shopman.customers.contrib.loyalty.service import LoyaltyService

        account = LoyaltyService.get_account(customer.ref)
        if account:
            transactions = LoyaltyService.get_transactions(customer.ref, limit=5)
            return account, transactions
    except Exception:
        pass
    return None, []


def _enrich_orders(orders) -> list[dict]:
    """Build enriched order list with display info."""
    enriched = []
    for order in orders:
        enriched.append({
            "ref": order.ref,
            "created_at": order.created_at,
            "total_display": f"R$ {format_money(order.total_q)}",
            "status": order.status,
            "status_label": STATUS_LABELS.get(order.status, order.status),
            "status_color": STATUS_COLORS.get(order.status, "bg-gray-100 text-gray-800"),
        })
    return enriched


@method_decorator(ensure_csrf_cookie, name="dispatch")
class AccountView(View):
    """Account page: session-based auth → customer info + addresses + orders."""

    def get(self, request: HttpRequest) -> HttpResponse:
        customer = get_authenticated_customer(request)
        if customer:
            phone = customer.phone
            return self._render_account(request, customer, phone)
        return render(request, "storefront/account.html", {"customer": None})

    def _render_account(self, request: HttpRequest, customer, phone: str) -> HttpResponse:
        """Render account page with customer data."""
        addresses = customer.addresses.order_by("-is_default", "label")

        orders = Order.objects.filter(
            handle_type="phone",
            handle_ref=phone,
        ).order_by("-created_at")[:10]

        enriched_orders = _enrich_orders(orders)

        preferences = None
        try:
            from shopman.customers.contrib.preferences.models import CustomerPreference

            prefs = CustomerPreference.objects.filter(customer=customer).order_by("category", "key")
            if prefs.exists():
                preferences = prefs
        except Exception:
            pass

        loyalty_account, loyalty_transactions = _get_loyalty_data(customer)

        return render(request, "storefront/account.html", {
            "customer": customer,
            "addresses": addresses,
            "orders": enriched_orders,
            "preferences": preferences,
            "loyalty_account": loyalty_account,
            "loyalty_transactions": loyalty_transactions,
            "phone_value": phone,
            "is_verified": True,
        })

    def post(self, request: HttpRequest) -> HttpResponse:
        phone_raw = request.POST.get("phone", "").strip()
        errors = {}

        if not phone_raw:
            errors["phone"] = "Telefone é obrigatório."
            return render(request, "storefront/account.html", {
                "customer": None,
                "errors": errors,
                "phone_value": phone_raw,
            })

        try:
            phone = normalize_phone(phone_raw)
        except Exception:
            errors["phone"] = "Telefone inválido. Use formato com DDD, ex: (43) 99999-9999"
            return render(request, "storefront/account.html", {
                "customer": None,
                "errors": errors,
                "phone_value": phone_raw,
            })

        if not phone:
            # Try with default DDD
            digits = "".join(c for c in phone_raw if c.isdigit())
            if 8 <= len(digits) <= 9:
                try:
                    phone = normalize_phone(f"{get_default_ddd()}{digits}")
                except Exception:
                    pass
            if not phone:
                errors["phone"] = "Telefone inválido. Use formato com DDD, ex: (43) 99999-9999"
                return render(request, "storefront/account.html", {
                    "customer": None,
                    "errors": errors,
                    "phone_value": phone_raw,
                })

        from shopman.customers.services import customer as customer_service

        customer = customer_service.get_by_phone(phone)
        if not customer:
            return render(request, "storefront/account.html", {
                "customer": None,
                "not_found": True,
                "phone_value": phone_raw,
            })

        # If already verified in this session for this phone, show data
        auth_customer = get_authenticated_customer(request)
        if auth_customer and auth_customer.pk == customer.pk:
            return self._render_account(request, customer, phone)

        # Customer found but NOT verified — require OTP before showing data
        return render(request, "storefront/account.html", {
            "customer": None,
            "needs_verification": True,
            "customer_name": customer.first_name or customer.name,
            "phone_value": phone,
        })


class AddressCreateView(View):
    """HTMX: create new address, return updated address list."""

    def post(self, request: HttpRequest) -> HttpResponse:
        from shopman.customers.models import CustomerAddress

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

        CustomerAddress.objects.create(
            customer=customer,
            label=label,
            label_custom=label_custom,
            formatted_address=formatted_address,
            route=route,
            street_number=street_number,
            neighborhood=neighborhood,
            city=city,
            complement=complement,
            delivery_instructions=delivery_instructions,
            is_default=is_default,
        )

        addresses = customer.addresses.order_by("-is_default", "label")
        return render(request, "storefront/partials/address_list.html", {
            "addresses": addresses,
            "customer": customer,
        })


class AddressUpdateView(View):
    """HTMX: update existing address, return updated item."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        from shopman.customers.models import CustomerAddress

        auth_customer = get_authenticated_customer(request)
        if not auth_customer:
            return HttpResponse("Autenticação necessária.", status=401)

        addr = get_object_or_404(CustomerAddress, pk=pk)
        customer = addr.customer

        if auth_customer.pk != customer.pk:
            return HttpResponse("Acesso não autorizado.", status=403)

        addr.label = request.POST.get("label", addr.label)
        addr.label_custom = request.POST.get("label_custom", "").strip()
        addr.formatted_address = request.POST.get("formatted_address", addr.formatted_address).strip()
        addr.route = request.POST.get("route", "").strip()
        addr.street_number = request.POST.get("street_number", "").strip()
        addr.neighborhood = request.POST.get("neighborhood", "").strip()
        addr.city = request.POST.get("city", "").strip()
        addr.complement = request.POST.get("complement", "").strip()
        addr.delivery_instructions = request.POST.get("delivery_instructions", "").strip()

        if not addr.formatted_address:
            parts = []
            if addr.route:
                parts.append(addr.route)
            if addr.street_number:
                parts.append(addr.street_number)
            if addr.neighborhood:
                parts.append(f"- {addr.neighborhood}")
            if addr.city:
                parts.append(f"- {addr.city}")
            addr.formatted_address = " ".join(parts) if parts else ""

        addr.save()

        addresses = customer.addresses.order_by("-is_default", "label")
        return render(request, "storefront/partials/address_list.html", {
            "addresses": addresses,
            "customer": customer,
        })


class AddressDeleteView(View):
    """HTMX: delete address, return updated list."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        from shopman.customers.models import CustomerAddress

        auth_customer = get_authenticated_customer(request)
        if not auth_customer:
            return HttpResponse("Autenticação necessária.", status=401)

        addr = get_object_or_404(CustomerAddress, pk=pk)
        customer = addr.customer

        if auth_customer.pk != customer.pk:
            return HttpResponse("Acesso não autorizado.", status=403)

        addr.delete()

        addresses = customer.addresses.order_by("-is_default", "label")
        return render(request, "storefront/partials/address_list.html", {
            "addresses": addresses,
            "customer": customer,
        })


class AddressSetDefaultView(View):
    """HTMX: set address as default, return updated list."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        from shopman.customers.models import CustomerAddress

        auth_customer = get_authenticated_customer(request)
        if not auth_customer:
            return HttpResponse("Autenticação necessária.", status=401)

        addr = get_object_or_404(CustomerAddress, pk=pk)
        customer = addr.customer

        if auth_customer.pk != customer.pk:
            return HttpResponse("Acesso não autorizado.", status=403)

        addr.is_default = True
        addr.save()  # save() handles unsetting other defaults

        addresses = customer.addresses.order_by("-is_default", "label")
        return render(request, "storefront/partials/address_list.html", {
            "addresses": addresses,
            "customer": customer,
        })
