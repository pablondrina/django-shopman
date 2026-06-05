"""POSProjection — read models for the POS terminal (Fase 5).

Translates product listings, collections, and cash session state into
immutable projections for the POS page. Replaces the inline ``_load_products``
logic from ``shopman.backstage.views.pos``.

Never imports from ``shopman.backstage.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.conf import settings
from django.utils import timezone
from shopman.offerman.models import Collection, Product
from shopman.orderman.models import Session
from shopman.utils.monetary import format_money

from shopman.backstage.constants import POS_CHANNEL_REF
from shopman.backstage.services.integration_readiness import (
    build_provider_readiness,
    focus_nfe_readiness,
)
from shopman.shop.projections.types import (
    PAYMENT_METHOD_LABELS_PT,
    Action,
    AddressAutocompleteProjection,
    SavedAddressProjection,
)
from shopman.shop.projections.channel_policy import resolve_channel_policy
from shopman.shop.services.pos_intent import (
    POS_SALE_INTENT_PAYLOAD_KEYS,
    POS_SALE_INTENT_RECEIPT_MODES,
    POS_SALE_INTENT_VERSION,
)

logger = logging.getLogger(__name__)


# ── Projections ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class POSProductProjection:
    """A single product tile in the POS grid."""

    sku: str
    name: str
    price_q: int
    price_display: str
    collection_ref: str
    is_d1: bool
    image_url: str = ""


@dataclass(frozen=True)
class POSCollectionProjection:
    """A collection tab in the POS filter bar."""

    ref: str
    name: str


@dataclass(frozen=True)
class POSPaymentMethodProjection:
    """A payment method option in the POS."""

    ref: str
    label: str


@dataclass(frozen=True)
class POSFulfillmentOptionProjection:
    """A fulfillment option the POS is allowed to submit."""

    ref: str
    label: str
    description: str
    requires_address: bool


@dataclass(frozen=True)
class POSPaymentCollectionProjection:
    """Where payment is collected for a POS sale."""

    ref: str
    label: str
    description: str
    fulfillment_types: tuple[str, ...]
    payment_method_refs: tuple[str, ...]


@dataclass(frozen=True)
class POSCheckoutOptionProjection:
    """A stable option value accepted by the POS sale intent."""

    ref: str
    label: str
    description: str = ""


@dataclass(frozen=True)
class POSCheckoutFieldProjection:
    """A payload field a POS surface may collect during checkout."""

    ref: str
    payload_key: str
    section_ref: str
    label: str
    input_type: str
    required: bool = False
    required_when: dict[str, object] = field(default_factory=dict)
    placeholder: str = ""
    help_text: str = ""
    max_length: int = 0
    options: tuple[POSCheckoutOptionProjection, ...] = ()
    capability_ref: str = ""


@dataclass(frozen=True)
class POSCheckoutSectionProjection:
    """Logical checkout section independent from any concrete UI layout."""

    ref: str
    label: str
    description: str
    field_refs: tuple[str, ...]


@dataclass(frozen=True)
class POSCheckoutContractProjection:
    """Canonical headless checkout contract for POS operator surfaces."""

    intent_version: str
    allowed_payload_keys: tuple[str, ...]
    sections: tuple[POSCheckoutSectionProjection, ...]
    fields: tuple[POSCheckoutFieldProjection, ...]
    receipt_modes: tuple[POSCheckoutOptionProjection, ...]
    tender_methods: tuple[POSCheckoutOptionProjection, ...]
    cash_tender_delta_presets_q: tuple[int, ...]
    discount_types: tuple[POSCheckoutOptionProjection, ...]
    discount_reasons: tuple[POSCheckoutOptionProjection, ...]
    customer_memory_actions: tuple[POSCheckoutOptionProjection, ...]
    capabilities: dict[str, object]


@dataclass(frozen=True)
class POSCashRuntimeProjection:
    """Active cash runtime resolved for the current operator surface."""

    has_open_shift: bool
    shift_id: int | None
    terminal_ref: str
    terminal_label: str
    operator_username: str
    opened_at: str
    status: str = "closed"
    blocking_operator_username: str = ""
    blocking_shift_id: int | None = None
    blocking_message: str = ""


@dataclass(frozen=True)
class POSCustomerMemoryProjection:
    """Consumption memory resolved for an operator-assisted POS customer."""

    total_orders: int
    average_order_display: str
    favorite_product: str
    favorite_item: dict[str, object]
    last_order_items: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class POSCustomerLookupProjection:
    """Customer data a POS surface can prefill without reading Guestman."""

    ref: str
    name: str
    phone: str
    email: str
    loyalty_group: str
    is_staff: bool
    default_address: SavedAddressProjection | None
    saved_addresses: tuple[SavedAddressProjection, ...]
    memory: POSCustomerMemoryProjection


@dataclass(frozen=True)
class POSShiftSummaryProjection:
    """Today's shift totals for the POS."""

    count: int
    total_display: str
    pickup_count: int
    delivery_count: int
    cash_total_display: str
    digital_total_display: str
    last_ref: str
    last_total_display: str
    cod_pending_count: int
    cod_pending_display: str


@dataclass(frozen=True)
class POSTabProjection:
    """A visible POS tab card."""

    ref: str
    display_ref: str
    session_key: str
    state: str
    status_label: str
    status_class: str
    customer_name: str
    customer_phone: str
    item_count: int
    line_count: int
    total_display: str
    last_touched_display: str
    items_preview: str
    # "Disparado + não-pago" anti-fraud signal: an open comanda whose courses
    # already went to the kitchen is, by nature, still unpaid. Derived from
    # Session.data["fired_lines"] — no extra storage.
    fired: bool = False


@dataclass(frozen=True)
class POSProjection:
    """Top-level read model for the POS terminal page."""

    products: tuple[POSProductProjection, ...]
    collections: tuple[POSCollectionProjection, ...]
    payment_methods: tuple[POSPaymentMethodProjection, ...]
    fulfillment_options: tuple[POSFulfillmentOptionProjection, ...]
    payment_collections: tuple[POSPaymentCollectionProjection, ...]
    checkout: POSCheckoutContractProjection
    actions: tuple[Action, ...]
    has_open_cash_session: bool
    cash_runtime: POSCashRuntimeProjection
    terminal_ref: str
    terminal_label: str
    terminal_default_fulfillment_type: str
    terminal_health_status: str
    terminal_components: tuple[object, ...]
    favorite_collection_refs: tuple[str, ...]
    delivery_minimum_q: int
    delivery_minimum_display: str
    fiscal_status: str
    fiscal_label: str
    fiscal_message: str
    operators: tuple[dict, ...] = ()
    auto_lock_seconds: int = 60


# ── Constants ──────────────────────────────────────────────────────────

_POS_PAYMENT_METHOD_REFS = ("cash", "pix", "card", "mixed")
_POS_TENDER_METHOD_REFS = ("cash", "pix", "card", "external")

_PAYMENT_COLLECTIONS = (
    POSPaymentCollectionProjection(
        ref="terminal",
        label="Receber no caixa",
        description="Pagamento confirmado no atendimento de balcão.",
        fulfillment_types=("pickup", "delivery"),
        payment_method_refs=_POS_PAYMENT_METHOD_REFS,
    ),
    POSPaymentCollectionProjection(
        ref="on_delivery",
        label="Receber na entrega",
        description="Disponível apenas para entrega em dinheiro.",
        fulfillment_types=("delivery",),
        payment_method_refs=("cash", "mixed"),
    ),
)


# ── Builders ───────────────────────────────────────────────────────────


def build_pos(*, terminal=None, operator=None) -> POSProjection:
    """Build the POS terminal projection."""
    products = _load_products()

    collections = tuple(
        POSCollectionProjection(ref=c["ref"], name=c["name"])
        for c in Collection.objects.filter(is_active=True, parent__isnull=True)
        .order_by("sort_order", "name")
        .values("ref", "name")
    )

    cash_shift = _active_cash_shift(operator)
    if terminal is None and cash_shift is not None:
        terminal = cash_shift.terminal
    if terminal is None:
        from shopman.backstage.models import POSTerminal

        terminal = POSTerminal.default()
    terminal_cash_shift = _active_cash_shift_for_terminal(terminal)
    from shopman.backstage.services.pos_terminal import runtime_profile

    runtime = runtime_profile(terminal)
    policy = resolve_channel_policy(POS_CHANNEL_REF)
    delivery_minimum_q = _delivery_minimum_q()
    fiscal_status, fiscal_label, fiscal_message = _fiscal_runtime()

    return POSProjection(
        products=tuple(products),
        collections=collections,
        payment_methods=_payment_methods(),
        fulfillment_options=_fulfillment_options(policy.fulfillment_types),
        payment_collections=_PAYMENT_COLLECTIONS,
        checkout=_checkout_contract(
            fulfillment_types=policy.fulfillment_types,
            delivery_minimum_q=delivery_minimum_q,
            fiscal_status=fiscal_status,
            fiscal_label=fiscal_label,
            fiscal_message=fiscal_message,
        ),
        actions=_pos_actions(),
        has_open_cash_session=bool(cash_shift) if operator is not None else True,
        cash_runtime=_cash_runtime_projection(
            cash_shift,
            runtime,
            operator,
            terminal_cash_shift=terminal_cash_shift,
        ),
        terminal_ref=runtime.terminal_ref,
        terminal_label=runtime.terminal_label,
        terminal_default_fulfillment_type=runtime.default_fulfillment_type,
        terminal_health_status=runtime.status,
        terminal_components=runtime.components,
        favorite_collection_refs=runtime.favorite_collection_refs,
        delivery_minimum_q=delivery_minimum_q,
        delivery_minimum_display=f"R$ {format_money(delivery_minimum_q)}" if delivery_minimum_q else "",
        fiscal_status=fiscal_status,
        fiscal_label=fiscal_label,
        fiscal_message=fiscal_message,
        operators=_eligible_operator_cards(),
        auto_lock_seconds=int((getattr(terminal, "metadata", None) or {}).get("auto_lock_seconds", 60)),
    )


def _eligible_operator_cards() -> tuple[dict, ...]:
    """Operators (staff with operate_pos + a PIN) for the lock-screen picker."""
    from shopman.backstage.services.operator import eligible_operators, operator_card

    return tuple(operator_card(u) for u in eligible_operators())


def build_pos_shift_summary(*, channel_ref: str = POS_CHANNEL_REF) -> POSShiftSummaryProjection:
    """Build today's shift summary for the POS."""
    from django.db.models import Sum
    from django.utils import timezone
    from shopman.orderman.models import Order

    today = timezone.localdate()
    qs = Order.objects.filter(
        channel_ref=channel_ref,
        created_at__date=today,
    ).exclude(status="cancelled")

    shift_count = qs.count()
    shift_total_q = qs.aggregate(t=Sum("total_q"))["t"] or 0
    pickup_count = 0
    delivery_count = 0
    cash_total_q = 0
    digital_total_q = 0
    cod_pending_count = 0
    cod_pending_q = 0
    for order in qs:
        data = order.data or {}
        if data.get("fulfillment_type") == "delivery":
            delivery_count += 1
        else:
            pickup_count += 1
        payment = data.get("payment") or {}
        if payment.get("collection") == "on_delivery" and not payment.get("cod_settled_at"):
            cod_pending_count += 1
            cod_pending_q += int(order.total_q or 0)
            continue
        if payment.get("cash_received_q") is not None:
            cash_total_q += int(payment.get("cash_received_q") or 0)
        elif payment.get("method") == "cash" and payment.get("collection", "terminal") != "on_delivery":
            cash_total_q += int(payment.get("cash_received_q") or order.total_q or 0)
        else:
            digital_total_q += int(order.total_q or 0)

    last_order = qs.order_by("-created_at").first()

    return POSShiftSummaryProjection(
        count=shift_count,
        total_display=format_money(shift_total_q),
        pickup_count=pickup_count,
        delivery_count=delivery_count,
        cash_total_display=format_money(cash_total_q),
        digital_total_display=format_money(digital_total_q),
        last_ref=last_order.ref if last_order else "",
        last_total_display=format_money(last_order.total_q) if last_order else "",
        cod_pending_count=cod_pending_count,
        cod_pending_display=format_money(cod_pending_q),
    )


def build_pos_tabs(
    *,
    channel_ref: str = POS_CHANNEL_REF,
    query: str = "",
    limit: int = 80,
) -> tuple[POSTabProjection, ...]:
    """Build POS tab cards with empty/in-use state."""
    from shopman.backstage.models import POSTab

    query_norm = _norm(query)
    sessions = {
        str((session.data or {}).get("tab_ref") or session.handle_ref or "").strip(): session
        for session in Session.objects.filter(
            channel_ref=channel_ref,
            state="open",
        ).filter(handle_type="pos_tab")
    }
    sessions.update({
        str((session.data or {}).get("tab_ref") or "").strip(): session
        for session in Session.objects.filter(
            channel_ref=channel_ref,
            state="open",
            data__has_key="tab_ref",
        )
    })
    sessions = {ref: session for ref, session in sessions.items() if ref}

    tab_displays = {
        row["ref"]: row["label"] or _display_ref(row["ref"])
        for row in POSTab.objects.filter(is_active=True)
        .order_by("ref")
        .values("ref", "label")
    }
    refs = list(tab_displays)
    for ref in sessions:
        if ref not in refs:
            refs.append(ref)

    tabs = []
    for ref in refs:
        session = sessions.get(ref)
        session_display = str(((session.data or {}) if session is not None else {}).get("tab_display") or "").strip()
        tab = _tab_projection(ref=ref, session=session, display_ref=session_display or tab_displays.get(ref, ""))
        if query_norm and query_norm not in _tab_haystack(tab, sessions.get(ref)):
            continue
        tabs.append(tab)

    tabs.sort(key=lambda tab: (tab.state != "in_use", tab.ref))
    return tuple(tabs[:limit])


def build_pos_customer_lookup(phone: str) -> POSCustomerLookupProjection | None:
    """Resolve POS customer lookup as a headless projection."""
    from shopman.shop.projections import customer_context
    from shopman.shop.services import pos as pos_service

    customer = pos_service.resolve_customer(phone)
    if customer is None:
        return None

    name = getattr(customer, "name", "") or f"{getattr(customer, 'first_name', '')} {getattr(customer, 'last_name', '')}".strip()
    group_ref = customer.group.ref if getattr(customer, "group_id", None) else ""
    summary = pos_service.customer_history_summary(customer.ref)
    addresses = customer_context.saved_addresses(customer.ref)
    default_address = next((addr for addr in addresses if addr.is_default), addresses[0] if addresses else None)
    saved_addresses = tuple(_saved_address_projection(addr) for addr in addresses)

    return POSCustomerLookupProjection(
        ref=getattr(customer, "ref", ""),
        name=name,
        phone=getattr(customer, "phone", "") or phone,
        email=getattr(customer, "email", "") or "",
        loyalty_group=group_ref,
        is_staff=group_ref == "staff",
        default_address=_saved_address_projection(default_address) if default_address else None,
        saved_addresses=saved_addresses,
        memory=POSCustomerMemoryProjection(
            total_orders=int(summary.get("total_orders") or 0),
            average_order_display=format_money(int(summary.get("average_order_q") or 0)) if summary.get("average_order_q") else "",
            favorite_product=str(summary.get("favorite_product") or ""),
            favorite_item=dict(summary.get("favorite_item") or {}),
            last_order_items=tuple(dict(item) for item in (summary.get("last_order_items") or ())),
        ),
    )


# ── Internals ──────────────────────────────────────────────────────────


def _load_products() -> list[POSProductProjection]:
    """Load products with prices and D-1 flags for the POS grid."""
    products: list[POSProductProjection] = []

    try:
        from shopman.offerman.models import ListingItem

        items = (
            ListingItem.objects.filter(
                listing__ref=POS_CHANNEL_REF,
                listing__is_active=True,
                is_published=True,
                is_sellable=True,
            )
            .select_related("product")
            .order_by("product__name")
        )
        for li in items:
            p = li.product
            price_q = li.price_q if li.price_q else p.base_price_q
            products.append(_product_projection(p, price_q))
    except Exception:
        logger.exception("pos_load_products_listing_failed")

    if not products:
        for p in Product.objects.filter(is_published=True, is_sellable=True).order_by("name"):
            products.append(_product_projection(p, p.base_price_q))

    return products


def _payment_methods() -> tuple[POSPaymentMethodProjection, ...]:
    """Return POS tender methods accepted by the canonical POS intent contract."""
    return tuple(
        POSPaymentMethodProjection(
            ref=ref,
            label=PAYMENT_METHOD_LABELS_PT.get(ref, ref),
        )
        for ref in _POS_PAYMENT_METHOD_REFS
    )


def _fulfillment_options(fulfillment_types: tuple[str, ...]) -> tuple[POSFulfillmentOptionProjection, ...]:
    """Expose POS fulfillment choices resolved from channel policy."""
    options = []
    for ref in fulfillment_types:
        if ref == "delivery":
            options.append(POSFulfillmentOptionProjection(
                ref="delivery",
                label="Entrega",
                description="Entrega local com endereço informado pelo operador.",
                requires_address=True,
            ))
        elif ref == "pickup":
            options.append(POSFulfillmentOptionProjection(
                ref="pickup",
                label="Retirada",
                description="Retirada no balcão ou consumo local.",
                requires_address=False,
            ))
    return tuple(options)


def _pos_actions() -> tuple[Action, ...]:
    """Canonical POS mutations consumed by headless operator surfaces."""
    return (
        Action(
            ref="create_tab",
            kind="mutation",
            label="Cadastrar comanda",
            priority="quiet",
            method="POST",
            href="/api/v1/backstage/pos/tabs/",
            payload_schema={"required": ["tab_ref"], "optional": ["label"]},
            idempotency="none",
        ),
        Action(
            ref="open_tab",
            kind="mutation",
            label="Abrir comanda",
            priority="secondary",
            method="POST",
            href="/api/v1/backstage/pos/tabs/{tab_ref}/open/",
            payload_schema={"path": {"tab_ref": "string"}},
        ),
        Action(
            ref="save_tab",
            kind="mutation",
            label="Salvar comanda",
            priority="secondary",
            method="POST",
            href="/api/v1/backstage/pos/tabs/save/",
            payload_schema={
                "required": ["tab_session_key", "items"],
                "optional": ["customer_name", "customer_phone", "fulfillment_type", "payment_method"],
            },
        ),
        Action(
            ref="review_sale",
            kind="mutation",
            label="Revisar checkout",
            priority="secondary",
            method="POST",
            href="/api/v1/backstage/pos/sale/review/",
            payload_schema={
                "required": ["intent_version", "tab_session_key", "items"],
                "optional": POS_SALE_INTENT_PAYLOAD_KEYS,
            },
            idempotency="none",
        ),
        Action(
            ref="close_sale",
            kind="mutation",
            label="Finalizar venda",
            priority="primary",
            method="POST",
            href="/api/v1/backstage/pos/sale/close/",
            payload_schema={
                "required": ["tab_session_key", "items", "payment_method"],
                "optional": [
                    "customer_name",
                    "customer_phone",
                    "customer_tax_id",
                    "customer_email",
                    "customer_memory_action",
                    "fulfillment_type",
                    "delivery_address",
                    "delivery_address_structured",
                    "delivery_date",
                    "delivery_time_slot",
                    "delivery_fee_q",
                    "order_notes",
                    "payment_collection",
                    "payment_tenders",
                    "tendered_amount_q",
                    "issue_fiscal_document",
                    "receipt_mode",
                    "receipt_email",
                    "manual_discount",
                    "manager_approval",
                    "client_request_id",
                ],
            },
            idempotency="required",
        ),
        Action(
            ref="cancel_recent_sale",
            kind="mutation",
            label="Cancelar venda recente",
            priority="secondary",
            method="POST",
            href="/api/v1/backstage/pos/sale/recent/cancel/",
            payload_schema={
                "required": ["order_ref"],
                "optional": ["reason"],
            },
            confirmation={"style": "destructive"},
        ),
        Action(
            ref="open_cash_shift",
            kind="mutation",
            label="Abrir caixa",
            priority="secondary",
            method="POST",
            href="/api/v1/backstage/pos/cash/open/",
            payload_schema={"optional": ["opening_amount", "terminal_ref"]},
            idempotency="none",
        ),
        Action(
            ref="close_cash_shift",
            kind="mutation",
            label="Fechar caixa",
            priority="secondary",
            method="POST",
            href="/api/v1/backstage/pos/cash/close/",
            payload_schema={"required": ["closing_amount"], "optional": ["notes"]},
            confirmation={"style": "destructive"},
            idempotency="none",
        ),
        Action(
            ref="cash_movement",
            kind="mutation",
            label="Movimento de caixa",
            priority="quiet",
            method="POST",
            href="/api/v1/backstage/pos/cash/movement/",
            payload_schema={"required": ["kind", "amount", "reason"]},
            idempotency="none",
        ),
        Action(
            ref="customer_lookup",
            kind="query",
            label="Buscar cliente",
            priority="quiet",
            method="GET",
            href="/api/v1/backstage/pos/customer/lookup/?phone={phone}",
            payload_schema={"query": {"phone": "string"}},
            idempotency="none",
        ),
        Action(
            ref="reverse_geocode",
            kind="mutation",
            label="Resolver coordenadas",
            priority="quiet",
            method="POST",
            href="/api/v1/geocode/reverse",
            payload_schema={
                "required": ["lat", "lng"],
                "returns": {"shape": "delivery_address_structured"},
            },
            idempotency="none",
        ),
        Action(
            ref="clear_tab",
            kind="mutation",
            label="Liberar comanda",
            priority="quiet",
            method="DELETE",
            href="/api/v1/backstage/pos/tabs/{session_key}/clear/",
            payload_schema={"path": {"session_key": "string"}},
            confirmation={"style": "destructive"},
        ),
        Action(
            ref="rename_tab",
            kind="mutation",
            label="Renomear comanda",
            priority="quiet",
            method="POST",
            href="/api/v1/backstage/pos/tabs/rename/",
            payload_schema={"required": ["session_key", "new_tab_ref"]},
        ),
        Action(
            ref="move_tab_lines",
            kind="mutation",
            label="Mover itens (transferir/dividir/juntar)",
            priority="quiet",
            method="POST",
            href="/api/v1/backstage/pos/tabs/move-lines/",
            payload_schema={
                "required": ["from_session_key", "line_ids"],
                "optional": ["to_session_key", "to_tab_ref", "close_source_when_empty"],
            },
        ),
        Action(
            ref="fire_tab",
            kind="mutation",
            label="Enviar para cozinha",
            priority="normal",
            method="POST",
            href="/api/v1/backstage/pos/tabs/fire/",
            payload_schema={
                "required": ["session_key"],
                "optional": ["line_ids", "client_request_id"],
            },
            idempotency="client_request_id",
        ),
        Action(
            ref="unfire_tab",
            kind="mutation",
            label="Cancelar envio à cozinha",
            priority="quiet",
            method="POST",
            href="/api/v1/backstage/pos/tabs/unfire/",
            payload_schema={"required": ["session_key", "line_ids"]},
            confirmation={"style": "destructive"},
        ),
    )


def _checkout_contract(
    *,
    fulfillment_types: tuple[str, ...],
    delivery_minimum_q: int,
    fiscal_status: str,
    fiscal_label: str,
    fiscal_message: str,
) -> POSCheckoutContractProjection:
    """Expose the mature POS sale intent as a headless checkout contract."""
    receipt_modes = (
        POSCheckoutOptionProjection(ref="none", label="Sem comprovante"),
        POSCheckoutOptionProjection(ref="print", label="Imprimir"),
        POSCheckoutOptionProjection(ref="email", label="Enviar por e-mail"),
    )
    tender_methods = tuple(
        POSCheckoutOptionProjection(ref=ref, label=PAYMENT_METHOD_LABELS_PT.get(ref, ref))
        for ref in _POS_TENDER_METHOD_REFS
    )
    fields = (
        POSCheckoutFieldProjection(
            ref="customer_phone",
            payload_key="customer_phone",
            section_ref="customer",
            label="WhatsApp",
            input_type="tel",
            placeholder="(43) 99999-0000",
            max_length=80,
        ),
        POSCheckoutFieldProjection(
            ref="customer_name",
            payload_key="customer_name",
            section_ref="customer",
            label="Nome",
            input_type="text",
            placeholder="Nome do cliente",
            max_length=160,
        ),
        POSCheckoutFieldProjection(
            ref="customer_tax_id",
            payload_key="customer_tax_id",
            section_ref="customer",
            label="CPF/CNPJ",
            input_type="tax_id",
            max_length=32,
            capability_ref="fiscal_document",
        ),
        POSCheckoutFieldProjection(
            ref="customer_email",
            payload_key="customer_email",
            section_ref="customer",
            label="E-mail do cliente",
            input_type="email",
            max_length=180,
        ),
        POSCheckoutFieldProjection(
            ref="customer_memory_action",
            payload_key="customer_memory_action",
            section_ref="customer",
            label="Ação de memória",
            input_type="select",
            options=(
                POSCheckoutOptionProjection(ref="favorite_item", label="Adicionar favorito"),
                POSCheckoutOptionProjection(ref="last_order", label="Repetir último pedido"),
            ),
            capability_ref="customer_memory",
        ),
        POSCheckoutFieldProjection(
            ref="fulfillment_type",
            payload_key="fulfillment_type",
            section_ref="fulfillment",
            label="Fulfillment",
            input_type="segmented",
            required=True,
            options=tuple(
                POSCheckoutOptionProjection(ref=ref, label="Entrega" if ref == "delivery" else "Retirada")
                for ref in fulfillment_types
            ),
        ),
        POSCheckoutFieldProjection(
            ref="delivery_address",
            payload_key="delivery_address",
            section_ref="fulfillment",
            label="Endereço de entrega",
            input_type="address_autocomplete",
            required_when={"fulfillment_type": "delivery"},
            placeholder="Rua, número, bairro e referência",
            max_length=400,
            capability_ref="delivery_address_autocomplete",
        ),
        POSCheckoutFieldProjection(
            ref="delivery_address_structured",
            payload_key="delivery_address_structured",
            section_ref="fulfillment",
            label="Endereço estruturado",
            input_type="object",
            required_when={"fulfillment_type": "delivery"},
            help_text="Objeto aceito: formatted_address, route, street_number, neighborhood, city, state_code, postal_code, latitude, longitude, place_id, complement, delivery_instructions, reference.",
            capability_ref="delivery_address_autocomplete",
        ),
        POSCheckoutFieldProjection(
            ref="delivery_date",
            payload_key="delivery_date",
            section_ref="fulfillment",
            label="Data combinada",
            input_type="date",
            max_length=32,
        ),
        POSCheckoutFieldProjection(
            ref="delivery_time_slot",
            payload_key="delivery_time_slot",
            section_ref="fulfillment",
            label="Horário combinado",
            input_type="text",
            placeholder="Ex: 14:00-14:30",
            max_length=80,
        ),
        POSCheckoutFieldProjection(
            ref="delivery_fee_q",
            payload_key="delivery_fee_q",
            section_ref="fulfillment",
            label="Taxa de entrega",
            input_type="money_q",
            required_when={"fulfillment_type": "delivery"},
        ),
        POSCheckoutFieldProjection(
            ref="order_notes",
            payload_key="order_notes",
            section_ref="fulfillment",
            label="Observações do pedido",
            input_type="textarea",
            max_length=500,
        ),
        POSCheckoutFieldProjection(
            ref="payment_method",
            payload_key="payment_method",
            section_ref="payment",
            label="Forma principal",
            input_type="segmented",
            required=True,
            options=tuple(
                POSCheckoutOptionProjection(ref=ref, label=PAYMENT_METHOD_LABELS_PT.get(ref, ref))
                for ref in _POS_PAYMENT_METHOD_REFS
            ),
        ),
        POSCheckoutFieldProjection(
            ref="payment_collection",
            payload_key="payment_collection",
            section_ref="payment",
            label="Recebimento",
            input_type="segmented",
            required=True,
            options=tuple(
                POSCheckoutOptionProjection(ref=collection.ref, label=collection.label, description=collection.description)
                for collection in _PAYMENT_COLLECTIONS
            ),
        ),
        POSCheckoutFieldProjection(
            ref="payment_tenders",
            payload_key="payment_tenders",
            section_ref="payment",
            label="Pagamentos divididos",
            input_type="tender_list",
            required_when={"payment_method": "mixed"},
            capability_ref="split_payment",
        ),
        POSCheckoutFieldProjection(
            ref="tendered_amount_q",
            payload_key="tendered_amount_q",
            section_ref="payment",
            label="Valor recebido",
            input_type="money_q",
            required_when={"payment_method": "cash", "payment_collection": "terminal"},
            capability_ref="cash_change",
        ),
        POSCheckoutFieldProjection(
            ref="issue_fiscal_document",
            payload_key="issue_fiscal_document",
            section_ref="receipt",
            label="Emitir fiscal",
            input_type="boolean",
            capability_ref="fiscal_document",
        ),
        POSCheckoutFieldProjection(
            ref="receipt_mode",
            payload_key="receipt_mode",
            section_ref="receipt",
            label="Comprovante",
            input_type="segmented",
            options=receipt_modes,
        ),
        POSCheckoutFieldProjection(
            ref="receipt_email",
            payload_key="receipt_email",
            section_ref="receipt",
            label="E-mail do comprovante",
            input_type="email",
            required_when={"receipt_mode": "email"},
            max_length=180,
        ),
        POSCheckoutFieldProjection(
            ref="manual_discount",
            payload_key="manual_discount",
            section_ref="approval",
            label="Desconto manual",
            input_type="discount",
            capability_ref="manual_discount",
        ),
        POSCheckoutFieldProjection(
            ref="manager_approval",
            payload_key="manager_approval",
            section_ref="approval",
            label="Aprovação gerencial",
            input_type="credentials",
            required_when={"manual_discount.discount_q": {"gt": _discount_approval_threshold_q()}},
            capability_ref="manager_approval",
        ),
    )
    sections = (
        POSCheckoutSectionProjection(
            ref="customer",
            label="Cliente",
            description="Identificação, WhatsApp e memória de atendimento.",
            field_refs=("customer_phone", "customer_name", "customer_tax_id", "customer_email", "customer_memory_action"),
        ),
        POSCheckoutSectionProjection(
            ref="fulfillment",
            label="Entrega ou retirada",
            description="Campos que viram fulfillment e dados de entrega no Orderman.",
            field_refs=(
                "fulfillment_type",
                "delivery_address",
                "delivery_address_structured",
                "delivery_date",
                "delivery_time_slot",
                "delivery_fee_q",
                "order_notes",
            ),
        ),
        POSCheckoutSectionProjection(
            ref="payment",
            label="Pagamento",
            description="Recebimento no terminal, na entrega, dinheiro e pagamentos divididos.",
            field_refs=("payment_method", "payment_collection", "payment_tenders", "tendered_amount_q"),
        ),
        POSCheckoutSectionProjection(
            ref="receipt",
            label="Fiscal e comprovante",
            description="Dados opcionais para fiscal e comprovante.",
            field_refs=("issue_fiscal_document", "receipt_mode", "receipt_email"),
        ),
        POSCheckoutSectionProjection(
            ref="approval",
            label="Controle comercial",
            description="Desconto manual e aprovação gerencial quando configurada.",
            field_refs=("manual_discount", "manager_approval"),
        ),
    )
    return POSCheckoutContractProjection(
        intent_version=POS_SALE_INTENT_VERSION,
        allowed_payload_keys=POS_SALE_INTENT_PAYLOAD_KEYS,
        sections=sections,
        fields=fields,
        receipt_modes=tuple(option for option in receipt_modes if option.ref in POS_SALE_INTENT_RECEIPT_MODES),
        tender_methods=tender_methods,
        cash_tender_delta_presets_q=(0, 1000, 2000, 5000, 10000),
        discount_types=(
            POSCheckoutOptionProjection(ref="percent", label="Percentual"),
            POSCheckoutOptionProjection(ref="fixed", label="Valor fixo"),
        ),
        discount_reasons=(
            POSCheckoutOptionProjection(ref="cortesia", label="Cortesia"),
            POSCheckoutOptionProjection(ref="fidelidade", label="Fidelidade"),
            POSCheckoutOptionProjection(ref="ajuste_operacional", label="Ajuste operacional"),
            POSCheckoutOptionProjection(ref="qualidade", label="Qualidade"),
        ),
        customer_memory_actions=(
            POSCheckoutOptionProjection(ref="favorite_item", label="Adicionar favorito"),
            POSCheckoutOptionProjection(ref="last_order", label="Repetir último pedido"),
        ),
        capabilities={
            "prepare_checkout_action_ref": "save_tab",
            "review_action_ref": "review_sale",
            "submit_action_ref": "close_sale",
            "customer_lookup_action_ref": "customer_lookup",
            "supports_split_payment": True,
            "supports_cash_change": True,
            "supports_on_delivery_cash": "delivery" in fulfillment_types,
            "supports_customer_lookup": True,
            "supports_customer_memory": True,
            "supports_delivery_address_autocomplete": bool(getattr(settings, "GOOGLE_MAPS_API_KEY", "")),
            "supports_receipt_email": True,
            "supports_manual_discount": True,
            "provider_readiness": tuple(
                item.as_projection()
                for item in build_provider_readiness(mode="runtime")
            ),
            "fiscal_document": fiscal_status,
            "fiscal_label": fiscal_label,
            "fiscal_message": fiscal_message,
            "delivery_minimum_q": delivery_minimum_q,
            "delivery_minimum_display": f"R$ {format_money(delivery_minimum_q)}" if delivery_minimum_q else "",
            "requires_manager_approval_above_q": _discount_approval_threshold_q(),
            "address_autocomplete": _address_autocomplete_capability(),
            "tab_lifecycle": {
                "create_action_ref": "create_tab",
                "open_action_ref": "open_tab",
                "save_action_ref": "save_tab",
                "clear_action_ref": "clear_tab",
                "tab_ref_format": "free_text",
                "tab_ref_max_length": 64,
                "tab_ref_placeholder": "Mesa, nome ou referência",
                "tab_ref_disallowed_chars": ("/", "\\", "?", "#", "%"),
                "numeric_refs_zero_padded_to": 8,
                "requires_open_tab_for_cart": False,
                "requires_tab_before_save": True,
                "allows_direct_checkout_without_tab": True,
                "allows_operator_tab_creation": True,
                "draft_association_target_states": ("empty",),
                "occupied_tab_selection": "open_existing_not_merge",
            },
            "tab_manipulation": {
                "move_action_ref": "move_tab_lines",
                "rename_action_ref": "rename_tab",
                "allows_transfer": True,
                "allows_split": True,
                "allows_merge": True,
                "freezes_price_on_move": True,
            },
            "kitchen_handoff": {
                "fire_action_ref": "fire_tab",
                "unfire_action_ref": "unfire_tab",
                "progressive": True,
                "per_line_state_key": "fired",
                "fires_whole_tab_when_no_lines": True,
            },
            "cash_management": {
                "open_action_ref": "open_cash_shift",
                "close_action_ref": "close_cash_shift",
                "movement_action_ref": "cash_movement",
                "movement_kinds": ("sangria", "suprimento", "ajuste"),
                "requires_open_shift_for_sale": True,
                "blocks_close_when_offline_queue_pending": True,
            },
            "sale_correction": {
                "cancel_recent_action_ref": "cancel_recent_sale",
                "max_age_minutes": 5,
                "supports_reason": True,
                "allowed_statuses": ("new", "confirmed"),
            },
            "idempotent_replay": {
                "request_key": "client_request_id",
                "required_for_close": True,
                "close_action_ref": "close_sale",
                "safe_for_offline_queue": True,
            },
            "customer_lookup": {
                "action_ref": "customer_lookup",
                "lookup_key": "phone",
                "returns_default_address": True,
                "returns_saved_addresses": True,
                "returns_memory": True,
            },
            "live_refresh": {
                "product_projection_refresh": "pos",
                "shift_projection_refresh": "pos.shift",
                "tab_projection_refresh": "pos.tabs",
                "supports_push_updates": False,
            },
        },
    )


def _active_cash_shift(operator):
    if operator is None:
        return None
    try:
        from shopman.backstage.models import CashShift

        return CashShift.get_open_for_operator(operator)
    except Exception:
        logger.debug("pos_active_cash_shift_lookup_failed", exc_info=True)
        return None


def _active_cash_shift_for_terminal(terminal):
    if terminal is None:
        return None
    try:
        from shopman.backstage.models import CashShift

        return CashShift.get_open_for_terminal(terminal)
    except Exception:
        logger.debug("pos_terminal_cash_shift_lookup_failed", exc_info=True)
        return None


def _cash_runtime_projection(cash_shift, runtime, operator, *, terminal_cash_shift=None) -> POSCashRuntimeProjection:
    if cash_shift is None:
        if terminal_cash_shift is not None:
            operator_username = terminal_cash_shift.operator.get_username()
            return POSCashRuntimeProjection(
                has_open_shift=False,
                shift_id=None,
                terminal_ref=runtime.terminal_ref,
                terminal_label=runtime.terminal_label,
                operator_username=getattr(operator, "username", "") if operator is not None else "",
                opened_at="",
                status="terminal_occupied",
                blocking_operator_username=operator_username,
                blocking_shift_id=terminal_cash_shift.pk,
                blocking_message=f"Terminal aberto por {operator_username}.",
            )
        return POSCashRuntimeProjection(
            has_open_shift=False,
            shift_id=None,
            terminal_ref=runtime.terminal_ref,
            terminal_label=runtime.terminal_label,
            operator_username=getattr(operator, "username", "") if operator is not None else "",
            opened_at="",
            status="closed",
        )
    return POSCashRuntimeProjection(
        has_open_shift=True,
        shift_id=cash_shift.pk,
        terminal_ref=cash_shift.terminal.ref,
        terminal_label=str(cash_shift.terminal),
        operator_username=cash_shift.operator.get_username(),
        opened_at=cash_shift.opened_at.isoformat() if cash_shift.opened_at else "",
        status="open",
    )


def _address_autocomplete_capability() -> AddressAutocompleteProjection:
    api_key = getattr(settings, "GOOGLE_MAPS_API_KEY", "") or ""
    lat, lng = _shop_coordinates()
    return AddressAutocompleteProjection(
        enabled=bool(api_key),
        public_api_key=api_key,
        shop_latitude=lat,
        shop_longitude=lng,
    )


def _shop_coordinates() -> tuple[float | None, float | None]:
    try:
        from shopman.shop.models import Shop

        shop = Shop.objects.order_by("pk").first()
    except Exception:
        logger.debug("pos_shop_coordinates_lookup_failed", exc_info=True)
        return None, None
    if shop is None or shop.latitude is None or shop.longitude is None:
        return None, None
    return float(shop.latitude), float(shop.longitude)


def _saved_address_projection(addr) -> SavedAddressProjection:
    return SavedAddressProjection(
        id=addr.id,
        formatted_address=addr.formatted_address,
        complement=addr.complement,
        label=addr.label,
        is_default=addr.is_default,
        label_key=addr.label_key,
        label_custom=addr.label_custom,
        route=addr.route,
        street_number=addr.street_number,
        neighborhood=addr.neighborhood,
        city=addr.city,
        state_code=addr.state_code,
        postal_code=addr.postal_code,
        latitude=addr.latitude,
        longitude=addr.longitude,
        place_id=addr.place_id,
        delivery_instructions=addr.delivery_instructions,
    )


def _product_projection(product: Product, price_q: int) -> POSProductProjection:
    ci = (
        product.collection_items
        .filter(is_primary=True)
        .select_related("collection")
        .first()
    )

    try:
        from shopman.backstage.projections._helpers import _line_item_is_d1
        is_d1 = _line_item_is_d1(product, listing_ref=POS_CHANNEL_REF)
    except Exception:
        logger.exception("pos_d1_check_failed sku=%s", product.sku)
        is_d1 = False

    return POSProductProjection(
        sku=product.sku,
        name=product.name,
        price_q=price_q,
        price_display=f"R$ {format_money(price_q)}",
        collection_ref=ci.collection.ref if ci else "",
        is_d1=is_d1,
        image_url=product.image_url or "",
    )


def _tab_projection(*, ref: str, session: Session | None, display_ref: str = "") -> POSTabProjection:
    display_ref = display_ref or _display_ref(ref)
    if session is None:
        return POSTabProjection(
            ref=ref,
            display_ref=display_ref,
            session_key="",
            state="empty",
            status_label="Livre",
            status_class="badge-neutral",
            customer_name="",
            customer_phone="",
            item_count=0,
            line_count=0,
            total_display="R$ 0,00",
            last_touched_display="",
            items_preview="",
        )

    data = session.data or {}
    customer = data.get("customer") or {}
    items = session.items or []
    last_touched = _parse_dt(data.get("last_touched_at"), fallback=session.opened_at)
    item_count = sum(_qty_int(item.get("qty", 1)) for item in items)
    total_q = sum(
        _qty_int(item.get("qty", 1)) * int(item.get("unit_price_q", 0))
        for item in items
    )
    discount_q = int((data.get("manual_discount") or {}).get("discount_q", 0))

    return POSTabProjection(
        ref=ref,
        display_ref=display_ref,
        session_key=session.session_key,
        state="in_use",
        status_label="Em uso",
        status_class="badge-warning",
        customer_name=str(customer.get("name") or ""),
        customer_phone=str(customer.get("phone") or ""),
        item_count=item_count,
        line_count=len(items),
        total_display=f"R$ {format_money(max(0, total_q - discount_q))}",
        last_touched_display=_format_time(last_touched),
        items_preview=_items_preview(items),
        fired=bool(data.get("fired_lines")),
    )


def _parse_dt(value, *, fallback):
    if not value:
        return fallback
    from django.utils.dateparse import parse_datetime

    parsed = parse_datetime(str(value))
    if parsed is None:
        return fallback
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _format_time(value) -> str:
    return timezone.localtime(value).strftime("%H:%M")


def _qty_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def _items_preview(items: list[dict]) -> str:
    preview = []
    for item in items[:2]:
        qty = _qty_int(item.get("qty", 1))
        name = str(item.get("name") or item.get("sku") or "").strip()
        if not name:
            continue
        preview.append(f"{qty}x {name}")
    if len(items) > 2:
        preview.append(f"+{len(items) - 2}")
    return " · ".join(preview)


def _tab_haystack(tab: POSTabProjection, session: Session | None) -> str:
    item_parts = []
    if session is not None:
        for item in session.items or []:
            item_parts.extend([str(item.get("sku") or ""), str(item.get("name") or "")])
    return _norm(
        " ".join([
            tab.ref,
            tab.display_ref,
            tab.customer_name,
            tab.customer_phone,
            tab.items_preview,
            *item_parts,
        ])
    )


def _display_ref(ref: str) -> str:
    value = str(ref or "").strip()
    if value.isdigit():
        return value.lstrip("0") or "0"
    return value


def _norm(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _delivery_minimum_q() -> int:
    """Resolve the POS-visible delivery minimum from the active business rule."""
    try:
        from shopman.shop.rules.engine import get_rule_params

        params = get_rule_params("minimum_order") or get_rule_params("shop.minimum_order") or {}
        if params.get("minimum_q") is not None:
            return max(0, int(params.get("minimum_q") or 0))
    except Exception:
        logger.debug("pos_delivery_minimum_rule_lookup_failed", exc_info=True)

    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        raw = ((shop.defaults or {}).get("rules") or {}).get("minimum_order_q") if shop else None
        if raw:
            return max(0, int(raw))
    except Exception:
        logger.debug("pos_delivery_minimum_shop_lookup_failed", exc_info=True)
    return 0


def _discount_approval_threshold_q() -> int:
    """Return configured POS discount approval threshold in cents."""
    return max(0, int(getattr(settings, "SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q", 0) or 0))


def _fiscal_runtime() -> tuple[str, str, str]:
    """Return a compact fiscal health tuple for the POS terminal bar."""
    adapter_path = getattr(settings, "SHOPMAN_FISCAL_ADAPTER", None)
    if not adapter_path:
        return ("warning", "Fiscal", "sem adapter")

    if "fiscal_focusnfe.FocusNFeBackend" in str(adapter_path):
        readiness = focus_nfe_readiness(mode="runtime")
        return (readiness.status, readiness.label, readiness.message)

    return ("warning", "Fiscal", "adapter customizado")
