from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
NUXT_APP = REPO_ROOT / "surfaces" / "storefront-nuxt" / "app"
PARITY_CONTRACT = REPO_ROOT / "docs" / "reference" / "storefront-surface-parity-contract.md"
PORTING_LEDGER = REPO_ROOT / "docs" / "reference" / "storefront-surface-porting-ledger.json"
PARITY_TEST = "shopman/storefront/tests/test_storefront_nuxt_parity_contract.py"

WP00_GUARDRAIL_CONTRACT_IDS = {
    "AUTH-PHONE-BR-002",
    "AUTH-SESSION-002",
    "CHECKOUT-PAYLOAD-001",
    "REORDER-001",
    "COPY-FACT-001",
    "A11Y-ACTION-001",
    "NUXT-ROUTE-001",
}

CANONICAL_PUBLIC_ROUTES = {
    "/account": "/conta",
    "/logout": "/sair",
    "/how-it-works": "/como-funciona",
    "/product/": "/produto/",
    "/order/": "/pedido/",
}

OPERATIONAL_COPY_KEYWORDS = (
    "acompanha",
    "confirma",
    "dispon",
    "entrega",
    "estoque",
    "horario",
    "horário",
    "pagamento",
    "pedido mínimo",
    "preparo",
    "produção",
    "reserva",
    "retirada",
)

OPERATIONAL_COPY_SOURCE_MAP = {
    "components/AddressAutocomplete.vue": {
        "tokens": ["useGoogleMaps", "isAvailable"],
        "sources": ["shopman/storefront/api/geocode.py"],
    },
    "components/AddressFormModal.vue": {
        "tokens": ["/api/v1/account/addresses/", "delivery_instructions"],
        "sources": ["shopman/storefront/api/account.py"],
    },
    "components/CartLineItem.vue": {
        "tokens": ["line.availability_warning", "line.available_qty"],
        "sources": ["shopman/storefront/projections/cart.py"],
    },
    "components/CartIssueModal.vue": {
        "tokens": ["stockIssue", "rateLimitRecovery", "retryLastCartMutation"],
        "sources": ["shopman/storefront/api/surface.py", "shopman/storefront/projections/cart.py"],
    },
    "components/ContextualBanners.vue": {
        "tokens": ["home.omotenashi", "home.last_order_ref", "closingHint"],
        "sources": ["shopman/storefront/projections/home.py", "shopman/shop/omotenashi/copy.py"],
    },
    "components/HeroCarousel.vue": {
        "tokens": ["props.home.hero_copy", "props.home.last_order_ref", "omo."],
        "sources": ["shopman/storefront/projections/home.py", "shopman/shop/omotenashi/copy.py"],
    },
    "components/HotFromOven.vue": {
        "tokens": ["CatalogItemProjection", "props.copy.availability_heading"],
        "sources": ["shopman/storefront/projections/home.py", "shopman/storefront/projections/catalog.py"],
    },
    "components/HowItWorks.vue": {
        "tokens": ["openingHours", "OpeningHoursEntry", "copy.how_it_works_heading"],
        "sources": ["shopman/storefront/projections/home.py", "shopman/storefront/projections/shop_status.py"],
    },
    "components/PlannedHoldBadge.vue": {
        "tokens": ["confirmation_deadline_iso", "confirmation_deadline_display"],
        "sources": ["shopman/storefront/projections/cart.py"],
    },
    "components/ProductStepper.vue": {
        "tokens": ["props.unavailableLabel", "props.canAdd"],
        "sources": ["shopman/storefront/projections/catalog.py", "shopman/storefront/projections/product_detail.py"],
    },
    "components/ReorderRecoveryModal.vue": {
        "tokens": ["skippedItems", "rateLimitRecovery", "retryRateLimitedReorder"],
        "sources": ["shopman/storefront/api/surface.py", "shopman/storefront/services/orders.py"],
    },
    "components/TomorrowHook.vue": {
        "tokens": ["props.omotenashi.moment", "props.copy.tomorrow_hook"],
        "sources": ["shopman/storefront/projections/home.py", "shopman/shop/omotenashi/copy.py"],
    },
    "composables/useCartState.ts": {
        "tokens": ["data.available_qty", "status === 409", "setFromServer"],
        "sources": ["shopman/storefront/api/views.py", "shopman/storefront/projections/cart.py"],
    },
    "composables/useReorder.ts": {
        "tokens": ["skipped_items", "rateLimitRecovery", "/api/v1/orders/"],
        "sources": ["shopman/storefront/api/surface.py", "shopman/storefront/services/orders.py"],
    },
    "pages/account.vue": {
        "tokens": ["accountSummary", "loyalty", "/api/v1/account/summary/"],
        "sources": ["shopman/storefront/projections/account.py", "shopman/storefront/api/account.py"],
    },
    "pages/cart.vue": {
        "tokens": ["cart.minimum_order_progress", "cart.has_unavailable_items", "releaseCandidate"],
        "sources": ["shopman/storefront/projections/cart.py", "shopman/storefront/api/views.py"],
    },
    "pages/checkout.vue": {
        "tokens": [
            "checkout.value?.pickup_hint",
            "checkout.value?.delivery_hint",
            "checkout.closed_dates_json",
            "checkout.max_preorder_days",
            "paymentOptions",
        ],
        "sources": ["shopman/storefront/projections/checkout.py", "shopman/storefront/api/views.py"],
    },
    "pages/how-it-works.vue": {
        "tokens": ["/api/v1/storefront/home/", "openingHours"],
        "sources": ["shopman/storefront/projections/home.py"],
    },
    "pages/login.vue": {
        "tokens": ["/api/auth/request-code/", "/api/auth/verify-code/", "response.phone"],
        "sources": ["shopman/storefront/api/auth.py", "shopman/storefront/templates/storefront/login.html"],
    },
    "pages/menu.vue": {
        "tokens": ["/api/v1/storefront/menu/", "availability_label", "available_qty"],
        "sources": ["shopman/storefront/projections/catalog.py"],
    },
    "pages/offline.vue": {
        "tokens": ["Offline", "Páginas já abertas"],
        "sources": ["shopman/storefront/templates/storefront/offline.html", "surfaces/storefront-nuxt/server/routes/sw.js.get.ts"],
    },
    "pages/order/[ref]/confirmation.vue": {
        "tokens": ["/api/v1/tracking/", "data.promise", "payment_gate_url"],
        "sources": ["shopman/storefront/projections/order_confirmation.py", "shopman/storefront/api/tracking.py"],
    },
    "pages/order/[ref]/payment.vue": {
        "tokens": ["/api/v1/payment/", "promise", "payment"],
        "sources": ["shopman/storefront/projections/payment.py", "shopman/storefront/api/payment.py"],
    },
    "pages/product/[sku].vue": {
        "tokens": ["/api/v1/storefront/products/", "product.availability_label", "product.available_qty"],
        "sources": ["shopman/storefront/projections/product_detail.py"],
    },
    "pages/tracking/[ref].vue": {
        "tokens": ["/api/v1/tracking/", "promiseRows", "fulfillment?.tracking_url"],
        "sources": ["shopman/storefront/presentation/order_tracking.py", "shopman/storefront/api/tracking.py"],
    },
    "utils/operationalCopy.ts": {
        "tokens": ["OPERATIONAL_COPY_SOURCE", "COPY-SOURCE-001", "retryAfterDescription", "supportUrlWithMessage"],
        "sources": [
            "docs/reference/storefront-surface-parity-contract.md",
            "docs/reference/omotenashi-audit-framework.md",
        ],
    },
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _nuxt_file(relative: str) -> str:
    return _read(NUXT_APP / relative)


def _ledger() -> dict:
    return json.loads(_read(PORTING_LEDGER))


def _contract_ids(severities: set[str] | None = None) -> set[str]:
    severities = severities or {"P0", "P1"}
    rows = re.findall(r"\| `([^`]+)` \| (P[0-2]) \|", _read(PARITY_CONTRACT))
    return {contract_id for contract_id, severity in rows if severity in severities}


def _nuxt_source_files() -> list[Path]:
    return sorted(
        path for path in NUXT_APP.rglob("*")
        if path.suffix in {".ts", ".vue"}
    )


def _all_nuxt_source() -> str:
    return "\n".join(_read(path) for path in _nuxt_source_files())


def _files_with_operational_copy() -> set[str]:
    files: set[str] = set()
    for path in _nuxt_source_files():
        relative = path.relative_to(NUXT_APP).as_posix()
        if relative.startswith("types/"):
            continue
        source = _read(path)
        for line in source.splitlines():
            normalized = " ".join(line.strip().split())
            if not normalized or normalized.startswith("//"):
                continue
            if not any(keyword in normalized.lower() for keyword in OPERATIONAL_COPY_KEYWORDS):
                continue
            if any(marker in normalized for marker in ["'", '"', "`", ">", "label=", "title=", "description="]):
                files.add(relative)
                break
    return files


def test_parity_contract_declares_blocking_surface_invariants():
    contract = _read(PARITY_CONTRACT)

    assert "Regra de corte" in contract
    for contract_id in [
        "AUTH-PHONE-BR-001",
        "AUTH-PHONE-BR-002",
        "AUTH-SESSION-001",
        "AUTH-SESSION-002",
        "AUTH-DEVICE-TRUST-001",
        "AUTH-ACCESS-LINK-001",
        "AUTH-WELCOME-GATE-001",
        "AUTH-PHONE-INTL-001",
        "CUSTOMER-MERGE-001",
        "CUSTOMER-HISTORY-001",
        "CUSTOMER-DEVICE-MGMT-001",
        "CUSTOMER-ADDRESS-FALLBACK-001",
        "CUSTOMER-ACCOUNT-DELETE-001",
        "CUSTOMER-CONSENT-PREFS-001",
        "CUSTOMER-DATA-EXPORT-001",
        "CUSTOMER-LOYALTY-DETAIL-001",
        "CATALOG-HAPPY-HOUR-001",
        "CATALOG-FAVORITE-CATEGORY-001",
        "CATALOG-SEARCH-NAV-001",
        "HOME-LIVE-AVAILABILITY-001",
        "PDP-RICH-DETAIL-001",
        "CHECKOUT-IDEMP-001",
        "CHECKOUT-PAYLOAD-001",
        "CHECKOUT-SWITCH-ACCOUNT-001",
        "CHECKOUT-STEP-INVARIANTS-001",
        "PAYMENT-GATE-001",
        "PAYMENT-NUXT-001",
        "PAYMENT-RECOVERY-001",
        "PAYMENT-ERROR-DETAIL-001",
        "ORDER-CONFIRMATION-001",
        "TRACKING-001",
        "TRACKING-PROMISE-LIVE-001",
        "TRACKING-RATING-001",
        "REORDER-001",
        "ORDER-HISTORY-FILTER-001",
        "ACTIVE-ORDER-BADGE-001",
        "CART-STOCK-ERROR-001",
        "RATE-LIMIT-RECOVERY-001",
        "COPY-SOURCE-001",
        "COPY-FACT-001",
        "MOBILE-LAYOUT-001",
        "A11Y-ACTION-001",
        "NUXT-ROUTE-001",
        "PWA-OFFLINE-001",
        "MOBILE-GESTURES-HAPTIC-001",
    ]:
        assert contract_id in contract

    assert WP00_GUARDRAIL_CONTRACT_IDS.issubset(_contract_ids())


def test_porting_ledger_maps_critical_routes_to_canonical_sources():
    ledger = _ledger()

    assert ledger["canonical_surface"] == "django_penguin_storefront"
    assert ledger["candidate_surface"] == "storefront_nuxt_v4"

    route_ids = {entry["id"] for entry in ledger["routes"]}
    assert {
        "ROUTE-HOME",
        "ROUTE-MENU",
        "ROUTE-PDP",
        "ROUTE-CART",
        "ROUTE-CHECKOUT",
        "ROUTE-AUTH",
        "ROUTE-ACCOUNT",
        "ROUTE-PAYMENT",
        "ROUTE-TRACKING-REORDER",
    }.issubset(route_ids)


def test_porting_ledger_maps_wp00_guardrail_contracts_to_parity_tests():
    ledger = _ledger()
    contracts_by_id = {entry["id"]: entry for entry in ledger["contracts"]}

    assert WP00_GUARDRAIL_CONTRACT_IDS.issubset(contracts_by_id)
    for contract_id in WP00_GUARDRAIL_CONTRACT_IDS:
        entry = contracts_by_id[contract_id]
        assert PARITY_TEST in entry["verification"], f"{contract_id} must be executable in parity suite"


def test_p0_p1_ledger_entries_have_existing_sources_and_verification():
    ledger = _ledger()
    entries = [*ledger["routes"], *ledger["contracts"]]

    for entry in entries:
        if entry["severity"] not in {"P0", "P1"}:
            continue
        for key in ["canonical_sources", "backend_contracts", "candidate_sources", "verification"]:
            assert entry.get(key), f"{entry['id']} missing {key}"
            for relative in entry[key]:
                path = REPO_ROOT / relative
                assert path.exists(), f"{entry['id']} references missing {relative}"


def test_nuxt_critical_routes_consume_canonical_projection_endpoints():
    route_endpoints = {
        "pages/index.vue": ["/api/v1/storefront/home/"],
        "pages/menu.vue": ["/api/v1/storefront/menu/"],
        "pages/product/[sku].vue": ["/api/v1/storefront/products/"],
        "pages/cart.vue": ["/api/v1/storefront/cart/"],
        "pages/checkout.vue": ["/api/v1/storefront/checkout/", "/api/v1/checkout/"],
        "pages/login.vue": [
            "/api/auth/device-check/",
            "/api/auth/request-code/",
            "/api/auth/verify-code/",
            "/api/auth/trust-device/",
            "/api/auth/session/",
        ],
        "pages/account.vue": [
            "/api/v1/account/summary/",
            "/api/v1/account/profile/",
            "/api/v1/account/addresses/",
            "/api/v1/account/orders/",
        ],
        "pages/order/[ref]/payment.vue": ["/api/v1/payment/"],
        "pages/tracking/[ref].vue": ["/api/v1/tracking/", "/api/v1/orders/"],
    }

    for relative, endpoints in route_endpoints.items():
        source = _nuxt_file(relative)
        for endpoint in endpoints:
            assert endpoint in source, f"{relative} does not consume {endpoint}"


def test_nuxt_page_files_are_english_without_route_aliases():
    page_files = {
        str(path.relative_to(NUXT_APP)).replace("\\", "/")
        for path in (NUXT_APP / "pages").rglob("*.vue")
    }

    assert {
        "pages/account.vue",
        "pages/how-it-works.vue",
        "pages/logout.vue",
        "pages/welcome.vue",
        "pages/order/[ref]/confirmation.vue",
        "pages/order/[ref]/payment.vue",
        "pages/product/[sku].vue",
    }.issubset(page_files)

    for forbidden in [
        "pages/conta.vue",
        "pages/como-funciona.vue",
        "pages/sair.vue",
        "pages/bem-vindo.vue",
        "pages/pedido/[ref]/confirmacao.vue",
        "pages/pedido/[ref]/pagamento.vue",
        "pages/produto/[sku].vue",
    ]:
        assert forbidden not in page_files

    for relative in page_files:
        source = _nuxt_file(relative)
        assert "alias:" not in source, f"{relative} must not define route aliases"

    assert "path: '/conta'" in _nuxt_file("pages/account.vue")
    assert "path: '/sair'" in _nuxt_file("pages/logout.vue")
    assert "path: '/bem-vindo'" in _nuxt_file("pages/welcome.vue")
    assert "path: '/como-funciona'" in _nuxt_file("pages/how-it-works.vue")
    assert "path: '/produto/:sku'" in _nuxt_file("pages/product/[sku].vue")
    assert "path: '/pedido/:ref/pagamento'" in _nuxt_file("pages/order/[ref]/payment.vue")
    assert "path: '/pedido/:ref/confirmacao'" in _nuxt_file("pages/order/[ref]/confirmation.vue")

    all_source = _all_nuxt_source()
    for english_route, canonical_route in CANONICAL_PUBLIC_ROUTES.items():
        for quoted in [f"'{english_route}", f'"{english_route}', f"`{english_route}"]:
            assert quoted not in all_source, (
                f"{english_route} must not be a parallel public route; use {canonical_route}"
            )


def test_nuxt_server_routes_do_not_reintroduce_legacy_compatibility_paths():
    server_root = NUXT_APP.parent / "server"

    for forbidden in [
        "routes/auth/[...path].ts",
        "routes/checkout/request-code.post.ts",
        "routes/checkout/verify-code.post.ts",
        "auth/[...path].ts",
        "checkout/request-code.post.ts",
        "checkout/verify-code.post.ts",
    ]:
        assert not (server_root / forbidden).exists(), f"legacy compatibility route must not exist: {forbidden}"

    proxy = _read(server_root / "utils" / "djangoProxy.ts")
    assert "content-disposition" in proxy


def test_nuxt_route_surface_matches_porting_ledger_candidates():
    ledger = _ledger()

    candidate_pages = {
        source
        for route in ledger["routes"]
        for source in route["candidate_sources"]
        if source.startswith("surfaces/storefront-nuxt/app/pages/")
    }
    for source in candidate_pages:
        assert (REPO_ROOT / source).exists(), f"ledger route target missing: {source}"


def test_login_preserves_backend_phone_identity_contract():
    login = _nuxt_file("pages/login.vue")

    assert "digits.startsWith('55')" in login
    assert "requestedPhone.value = response.phone" in login
    assert "phoneRegion = ref<'BR' | 'INTL'>('BR')" in login
    assert "phone_region: phoneRegion.value" in login
    assert "body: { target: phoneTarget(), phone_region: phoneRegion.value, delivery_method: method }" in login
    assert "target: requestedPhone.value || phoneTarget()" in login
    assert "setIdentity({ phone: response.phone" in login

    assert "body: { target: cleanPhone" not in login
    assert "target: cleanPhone" not in login


def test_login_ports_penguin_phone_input_and_backend_copy():
    login = _nuxt_file("pages/login.vue")
    home_projection = _read(REPO_ROOT / "shopman" / "storefront" / "projections" / "home.py")

    for token in [
        "loginHome.value?.home.auth_copy",
        "copyTitle(authCopy.value?.phone_heading",
        "copyMessage(authCopy?.phone_subtitle",
        "copyTitle(authCopy?.phone_cta_wa",
        "copyTitle(authCopy?.phone_cta_sms",
        "copyMessage(authCopy?.no_password_note",
        "copyMessage(authCopy?.terms_note",
        "copyTitle(authCopy?.device_trust_cta",
        "copyTitle(authCopy?.device_trust_skip_cta",
        "type DeliveryMethod = 'whatsapp' | 'sms'",
        "aria-label=\"Brasil, código do país +55\"",
        "<UFieldGroup",
        "<UPinInput",
        "otp",
        "@complete=\"handleOtpComplete\"",
        "Usar número de outro país",
        "Usar número do Brasil",
        "nationalDigits",
        "internationalValue",
        "validatePhoneDisplay",
    ]:
        assert token in login

    for forbidden in [
        "i-lucide-cookie",
        "Entrar na casa",
        "casa vai te receber",
        "A casa não compartilha seus dados",
    ]:
        assert forbidden not in login

    for key in [
        "LOGIN_PHONE_HEADING",
        "LOGIN_PHONE_SUBTITLE",
        "LOGIN_PHONE_CTA_WA",
        "LOGIN_PHONE_CTA_SMS",
        "LOGIN_NO_PASSWORD_NOTE",
        "LOGIN_TERMS_NOTE",
        "DEVICE_TRUST_PROMPT",
        "DEVICE_TRUST_CTA",
        "DEVICE_TRUST_SKIP_CTA",
    ]:
        assert key in home_projection


def test_login_ports_trust_device_and_welcome_gate_contracts():
    login = _nuxt_file("pages/login.vue")
    welcome = _nuxt_file("pages/welcome.vue")
    middleware = _nuxt_file("middleware/welcome.global.ts")
    api = _read(REPO_ROOT / "shopman" / "storefront" / "api" / "auth.py")
    urls = _read(REPO_ROOT / "shopman" / "storefront" / "api" / "urls.py")

    assert "checkTrustedDevice" in login
    assert "/api/auth/device-check/" in login
    assert "/api/auth/trust-device/" in login
    assert "finishTrustedDeviceChoice(true)" in login
    assert "finishTrustedDeviceChoice(false)" in login
    assert "step = ref<'phone' | 'code' | 'name' | 'trust'>" in login
    assert "safeInternalPath" in login
    assert "candidate.startsWith('//')" in login

    assert "path: '/bem-vindo'" in welcome
    assert "/api/auth/session/" in welcome
    assert "/api/v1/account/profile/" in welcome
    assert "safeInternalPath" in welcome

    assert "defineNuxtRouteMiddleware" in middleware
    assert "session.requires_welcome" in middleware
    assert "path: '/bem-vindo'" in middleware
    assert "useRequestHeaders(['cookie'])" in middleware

    for view_name in ["DeviceCheckView", "TrustDeviceView"]:
        assert view_name in api
        assert view_name in urls


def test_auth_session_state_is_canonical_for_shell_and_bottom_tabs():
    header = _nuxt_file("components/AppHeader.vue")
    bottom_tabs = _nuxt_file("components/ShopBottomTabs.vue")
    bottom_cart = _nuxt_file("components/BottomCartBar.vue")
    session = _nuxt_file("composables/useShopSession.ts")

    for source in [header, bottom_tabs]:
        assert "useRequestHeaders(['cookie'])" in source
        assert "apiPath('/api/auth/session/')" in source
        assert "key: 'shopman-auth-session'" in source
        assert "watch(authSession" in source
        assert "setFromAuthSession(next)" in source

    assert "isAuthenticated.value ? 'Conta' : 'Entrar'" in bottom_tabs
    assert "const keepAuthenticated" not in session
    assert "homeAuthenticated || keepAuthenticated" not in session
    assert "lastOrderRef: homeAuthenticated ? home.last_order_ref : null" in session
    assert "lastOrderRef: null" in session
    assert "function setFromAuthSession" in session
    assert "function cleanOptionalText" in session
    assert "customerName: cleanOptionalText(session.customer_name)" in session
    assert "session.customer_name || state.value.customerName" not in session
    assert "const accountAriaLabel" in header
    assert "`Menu da conta de ${customerName}`" not in header
    assert "setFromServer(shellHome.value?.cart)" in header
    assert "setFromAuthSession(authSession.value)" in header
    assert "badge: isHydrated.value ? cart.value.items_count || undefined : undefined" in bottom_tabs
    assert "const isBrowsingSurface = computed(" in bottom_cart
    assert "route.path.startsWith('/pedido')" not in bottom_cart
    assert "const shouldShow = computed(() => isHydrated.value && !cart.value.is_empty && isBrowsingSurface.value)" in bottom_cart


def test_auth_session_002_home_projection_cannot_keep_stale_authenticated_state():
    session = _nuxt_file("composables/useShopSession.ts")
    index = _nuxt_file("pages/index.vue")
    header = _nuxt_file("components/AppHeader.vue")

    assert "home.omotenashi.audience !== 'anon'" in session
    assert "customerName: homeAuthenticated ? cleanOptionalText(home.omotenashi.customer_name) : null" in session
    assert "customerPhone: homeAuthenticated ? state.value.customerPhone : null" in session
    assert "isAuthenticated: homeAuthenticated" in session
    assert "lastOrderRef: homeAuthenticated ? home.last_order_ref : null" in session

    assert "keepAuthenticated" not in session
    assert "homeAuthenticated ||" not in session

    assert "setFromHome(next?.home)" in index
    assert "apiPath('/api/auth/session/')" in header
    assert "setFromAuthSession(next)" in header


def test_checkout_payload_uses_backend_canonical_field_names():
    checkout = _nuxt_file("pages/checkout.vue")
    serializer = _read(REPO_ROOT / "shopman" / "storefront" / "api" / "serializers.py")
    api = _read(REPO_ROOT / "shopman" / "storefront" / "api" / "views.py")

    for field in [
        "idempotency_key",
        "name",
        "phone",
        "fulfillment_type",
        "saved_address_id",
        "delivery_address",
        "delivery_address_structured",
        "delivery_complement",
        "delivery_instructions",
        "delivery_date",
        "delivery_time_slot",
        "payment_method",
        "notes",
        "use_loyalty",
    ]:
        assert f"{field}:" in checkout, f"checkout.vue must send canonical {field}"
        assert field in serializer, f"CheckoutSerializer must accept {field}"

    for field in ["latitude", "longitude", "place_id", "complement", "delivery_instructions"]:
        assert field in api, f"checkout API must preserve structured address field {field}"

    assert "idempotency_key: requestId" in checkout
    assert "saved_address_id: isDelivery ? state.saved_address_id : null" in checkout
    assert "interface CheckoutSubmitPayload" in checkout
    assert "function buildCheckoutPayload" in checkout
    assert "useRequestHeaders(['cookie'])" in checkout
    assert "headers: requestHeaders" in checkout
    assert "query: checkoutQuery" in checkout
    assert "state.delivery_date ? { delivery_date: state.delivery_date } : {}" in checkout
    assert "disabled: s.enabled === false" in checkout
    assert "function slotSelectionError" in checkout
    assert "Este horário não está disponível para este carrinho e esta data." in checkout
    assert ":disabled=\"requiresWhen && !state.delivery_date\"" in checkout
    assert "deliveryStructuredPayload()" in checkout
    assert "delivery_address_structured: isDelivery ? deliveryStructuredPayload() : {}" in checkout
    assert "if (formatted && !structured.formatted_address) structured.formatted_address = formatted" in checkout
    assert "checkout_data[\"payment\"] = {\"method\": payment_method}" in api
    assert "checkout_data[\"loyalty\"] = {\"redeem_points_q\": loyalty_balance_q}" in api
    assert "checkout_service.process(" in api
    assert "idempotency_key=idempotency_key" in api
    assert "\"error_code\": \"rate_limited\"" in api
    assert "headers={\"Retry-After\": str(CHECKOUT_RATE_LIMIT_RETRY_SECONDS)}" in api
    assert "\"errors\": {\"delivery_address\": \"Informe o endereço de entrega.\"}" in api
    assert "validate_pickup_slot_selection" in api


def test_checkout_step_invariants_and_recovery_contracts_are_enforced():
    checkout = _nuxt_file("pages/checkout.vue")
    step = _nuxt_file("components/CheckoutStep.vue")

    assert "function canOpenStep" in checkout
    assert "function isLocked" in checkout
    assert "function reconcileSteps" in checkout
    assert "watch(requiredSteps, () => reconcileSteps())" in checkout
    assert ":locked=\"isLocked('payment')\"" in checkout
    assert ":locked=\"isLocked('review')\"" in checkout
    assert "if (!canOpenStep(s)) return" in checkout
    assert "state.fulfillment_type === 'pickup'" in checkout
    assert "v-if=\"state.fulfillment_type === 'delivery'\"" in checkout

    assert "locked?: boolean" in step
    assert ":disabled=\"locked || (!done && active)\"" in step
    assert "@click=\"locked || active ? null" in step

    assert "rateLimitRecovery" in checkout
    assert "retry_after_seconds" in checkout
    assert "errorCode === 'in_progress'" in checkout
    assert "retryCheckoutAfterRecovery" in checkout
    assert "support_whatsapp_url" in checkout


def test_nuxt_sensitive_account_actions_require_confirmation():
    checkout = _nuxt_file("pages/checkout.vue")
    logout = _nuxt_file("pages/logout.vue")
    account = _nuxt_file("pages/account.vue")
    tracking = _nuxt_file("pages/tracking/[ref].vue")
    cart = _nuxt_file("pages/cart.vue")
    reorder_modal = _nuxt_file("components/ReorderConflictModal.vue")

    assert "intent: 'switch-account'" in checkout
    assert "if (!isSwitchAccount.value) clearCart()" in logout
    assert "Trocar conta?" in logout
    assert "UModal v-model:open=\"confirmOpen\"" in logout
    assert "performLogout" in logout

    assert "revokeDeviceCandidate = device" in account
    assert "UModal v-model:open=\"revokeDeviceOpen\"" in account
    assert "confirmRevokeDevice" in account
    assert "@click=\"revokeDevice(device)\"" not in account

    assert "UModal v-model:open=\"deleteModalOpen\"" in account
    assert "confirmDeleteAddress" in account
    assert "label=\"Manter endereço\"" in account
    assert "@click=\"confirmDeleteAddress\"" in account

    assert "UModal v-model:open=\"deleteAccountOpen\"" in account
    assert "deleteAccountAcknowledged" in account
    assert ":disabled=\"!deleteAccountAcknowledged\"" in account
    assert "@click=\"deleteAccount\"" in account

    assert "UModal v-model:open=\"cancelOpen\"" in tracking
    assert "cancelAcknowledged" in tracking
    assert ":disabled=\"!cancelAcknowledged\"" in tracking
    assert "@click=\"cancelOrder\"" in tracking

    assert "UModal" in cart
    assert "v-model:open=\"releaseModalOpen\"" in cart
    assert "releaseCandidate.value = line" in cart
    assert "@click=\"confirmReleaseReservation\"" in cart
    assert "upsellMeta" in cart
    assert "<ProductStepper" in cart
    assert "add-label=\"Adicionar\"" in cart
    assert ":to=\"`/produto/${cart.upsell.sku}`\"" not in cart

    assert "UModal v-model:open=\"open\"" in reorder_modal
    assert "replaceAcknowledged" in reorder_modal
    assert ":disabled=\"!replaceAction || !replaceAcknowledged\"" in reorder_modal
    assert "resolveConflict('replace')" in reorder_modal


def test_category_urls_are_canonical_menu_anchors_without_nuxt_adapter():
    menu_category_page = NUXT_APP / "pages" / "menu" / "[category].vue"
    catalog = _read(REPO_ROOT / "shopman" / "storefront" / "projections" / "catalog.py")
    product_detail = _read(REPO_ROOT / "shopman" / "storefront" / "projections" / "product_detail.py")

    assert not menu_category_page.exists()
    assert "/menu#" in catalog
    assert "/menu#" in product_detail
    assert "menu_collection" not in catalog
    assert "menu_collection" not in product_detail


def test_reorder_requires_explicit_mode_before_replacing_cart():
    reorder = _nuxt_file("composables/useReorder.ts")
    modal = _nuxt_file("components/ReorderConflictModal.vue")
    api = _read(REPO_ROOT / "shopman" / "storefront" / "api" / "surface.py")
    projection = _read(REPO_ROOT / "shopman" / "storefront" / "projections" / "reorder.py")

    assert "mode?: 'replace' | 'append'" in reorder
    assert "body: mode ? { mode, idempotency_key: idempotencyKey } : { idempotency_key: idempotencyKey }" in reorder
    assert "status === 409" in reorder
    assert "data?.error_code === 'cart_not_empty'" in reorder
    assert "setFromServer(data.cart)" in reorder
    assert "order_ref: conflictData.order_ref" in reorder

    assert "replaceAcknowledged" in modal
    assert "conflict.value?.cart.items" in modal
    assert "copy.value?.message.message" in modal
    assert ":label=\"appendAction?.label\"" in modal
    assert ":label=\"replaceAction?.label\"" in modal
    assert "resolveConflict('append')" in modal
    assert "resolveConflict('replace')" in modal
    assert ":disabled=\"!replaceAction || !replaceAcknowledged\"" in modal

    assert "mode not in {\"replace\", \"append\"}" in api
    assert "build_reorder_conflict" in api
    assert 'error_code="cart_not_empty"' in projection
    assert "cart=build_cart" in projection
    assert "if mode == \"replace\":" in api
    assert "CartService.clear(request)" in api


def test_operational_copy_is_mapped_to_projection_or_canonical_source():
    discovered = _files_with_operational_copy()
    missing = discovered - set(OPERATIONAL_COPY_SOURCE_MAP)
    assert not missing, f"operational copy files need source mapping: {sorted(missing)}"

    for relative, mapping in OPERATIONAL_COPY_SOURCE_MAP.items():
        source = _nuxt_file(relative)
        for token in mapping["tokens"]:
            assert token in source, f"{relative} no longer contains projection/source token {token}"
        for source_path in mapping["sources"]:
            assert (REPO_ROOT / source_path).exists(), f"{relative} maps to missing source {source_path}"

    all_source = _all_nuxt_source().lower()
    for forbidden in [
        "a gente avisa",
        "antes de cobrar",
        "disponibilidade real",
        "entrega garantida",
        "em alguns minutos",
        "fornada",
        "frete grátis",
        "no momento certo",
        "pagamento aprovado na hora",
        "preparo imediato",
        "próximo dia de produção",
        "produção da casa",
        "segue com o preparo",
        "sempre disponível",
        "sempre temos estoque",
    ]:
        assert forbidden not in all_source
    assert not re.search(r"\b(?:em\s+)?\d+\s*(?:minutos?|min)(?!-)\b", all_source)


def test_nuxt_mobile_shell_has_stable_spacing_and_no_competing_cart_bar():
    layout = _nuxt_file("layouts/default.vue")
    css = _nuxt_file("assets/css/main.css")
    bottom_tabs = _nuxt_file("components/ShopBottomTabs.vue")
    bottom_cart = _nuxt_file("components/BottomCartBar.vue")
    checkout = _nuxt_file("pages/checkout.vue")

    assert "--shop-bottom-nav-height" in css
    assert "--shop-mobile-action-height" in css
    assert ".shop-mobile-action-bar" in css
    assert "bottom: calc(var(--shop-bottom-nav-height)" in css
    assert "z-index: 50" in css
    assert "z-index: 45" in css
    assert "background: var(--ui-bg);" in css
    assert "linear-gradient" not in css

    assert "pb-[calc(var(--shop-bottom-nav-height)+1rem+env(safe-area-inset-bottom))]" in layout

    assert "text-[10px]" not in bottom_tabs
    assert "linkLabel: 'text-xs leading-4 font-medium'" in bottom_tabs
    assert "link: 'flex-col gap-1 px-3 min-w-16 relative'" in bottom_tabs

    assert "const isBrowsingSurface = computed(" in bottom_cart
    browsing_surface = bottom_cart[
        bottom_cart.index("const isBrowsingSurface = computed("):
        bottom_cart.index("const shouldShow = computed(")
    ]
    for allowed_path in ["route.path === '/'", "route.path.startsWith('/menu')", "route.path.startsWith('/produto')"]:
        assert allowed_path in browsing_surface
    for blocked_path in ["'/checkout'", "'/cart'", "'/pedido'", "'/tracking'", "'/login'", "'/conta'"]:
        assert blocked_path not in browsing_surface

    assert "shop-mobile-action-bar" in checkout
    assert "pb-48" in checkout


def test_nuxt_home_hero_uses_backend_copy_and_fullwidth_shell():
    hero = _nuxt_file("components/HeroCarousel.vue")
    home_projection = _read(REPO_ROOT / "shopman" / "storefront" / "projections" / "home.py")

    assert "const copy = props.home.hero_copy" in hero
    assert "props.home.shop_status.message" not in hero
    for token in [
        "copy.birthday_heading",
        "copy.birthday_sub",
        "copy.order_title_prefix",
        "copy.order_title_suffix",
        "copy.order_subtitle",
        "copy.reorder_title_prefix",
        "copy.reorder_title_suffix",
        "copy.reorder_subtitle",
        "copy.handmade_title_prefix",
        "copy.handmade_title_suffix",
        "copy.handmade_subtitle",
        "copy.menu_cta",
        "copy.birthday_cta",
    ]:
        assert token in hero

    assert "relative isolate overflow-hidden border-b border-default bg-default text-white" in hero
    assert "class=\"w-full overflow-hidden\"" in hero
    assert "sm:rounded-lg" not in hero

    for key in [
        "BIRTHDAY_HERO_HEADING",
        "BIRTHDAY_HERO_SUB",
        "HOME_HERO_ORDER_TITLE_PREFIX",
        "HOME_HERO_ORDER_TITLE_SUFFIX",
        "HOME_HERO_ORDER_SUBTITLE",
        "HOME_HERO_REORDER_TITLE_PREFIX",
        "HOME_HERO_REORDER_TITLE_SUFFIX",
        "HOME_HERO_REORDER_SUBTITLE",
        "HOME_HERO_HANDMADE_TITLE_PREFIX",
        "HOME_HERO_HANDMADE_TITLE_SUFFIX",
        "HOME_HERO_HANDMADE_SUBTITLE",
        "HOME_MENU_CTA",
        "HOME_BIRTHDAY_CTA",
    ]:
        assert key in home_projection


def test_nuxt_home_sections_use_backend_copy_projection():
    index = _nuxt_file("pages/index.vue")
    hot = _nuxt_file("components/HotFromOven.vue")
    how = _nuxt_file("components/HowItWorks.vue")
    tomorrow = _nuxt_file("components/TomorrowHook.vue")
    whatsapp = _nuxt_file("components/WhatsappCta.vue")
    home_projection = _read(REPO_ROOT / "shopman" / "storefront" / "projections" / "home.py")

    for token in [
        ':copy="home.sections_copy"',
        '<HotFromOven :items="home.featured_items" :copy="home.sections_copy"',
        '<TomorrowHook :omotenashi="home.omotenashi" :copy="home.sections_copy"',
        '<HowItWorks :opening-hours="home.opening_hours" :copy="home.sections_copy"',
        '<WhatsappCta :shop="home.shop" :copy="home.sections_copy"',
    ]:
        assert token in index

    for source, tokens in {
        hot: ["props.copy.availability_heading", ":title=\"heading.title\"", ":description=\"heading.message\""],
        how: [
            "copy.how_it_works_heading",
            "props.copy.how_online_choose_message",
            "props.copy.how_store_self_service_message",
            "copy.how_store_heading.title",
        ],
        tomorrow: ["props.copy.tomorrow_hook", "copy.tomorrow_label.title"],
        whatsapp: ["copy.whatsapp_cta.title", "copy.whatsapp_cta.message", "copy.whatsapp_cta_label.title"],
    }.items():
        for token in tokens:
            assert token in source

    for forbidden in ["Selecionados pela casa", "Na casa", "Canal direto com a casa"]:
        assert forbidden not in hot + how + tomorrow + whatsapp

    for key in [
        "HOME_AVAILABILITY_HEADING",
        "HOME_FULL_MENU_CTA",
        "HOME_HOW_IT_WORKS_HEADING",
        "HOW_IT_WORKS_INTRO",
        "HOME_HOW_ONLINE_HEADING",
        "HOME_HOW_STORE_HEADING",
        "HOW_ONLINE_CHOOSE_MESSAGE",
        "HOW_STORE_SELF_SERVICE_MESSAGE",
        "TRACKING_TOMORROW_HOOK",
        "HOME_WHATSAPP_CTA",
        "HOME_WHATSAPP_CTA_LABEL",
    ]:
        assert key in home_projection


def test_nuxt_cart_line_item_matches_two_row_compact_layout():
    cart_line = _nuxt_file("components/CartLineItem.vue")

    assert "row-span-2" in cart_line
    assert "{{ line.qty }} x {{ line.price_display }} · {{ line.total_display }}" in cart_line
    assert "{{ line.price_display }} cada" not in cart_line
    assert "<strong" not in cart_line


def test_nuxt_header_matches_penguin_nav_and_storefront_icon():
    header = _nuxt_file("components/AppHeader.vue")
    app = _nuxt_file("app.vue")
    css = _nuxt_file("assets/css/main.css")

    assert "{ label: 'Cardápio', to: '/menu' }" in header
    assert "{ label: 'Como funciona', to: '/como-funciona' }" in header
    assert "{ label: 'Início'" not in header
    assert "material-symbols-rounded" in header
    assert ">storefront</span>" in header
    assert "bg-primary/12 text-primary ring-1 ring-primary/20" not in header
    assert "{ path: '/conta', query: { tab: 'orders' } }" in header
    assert "{ path: '/conta', query: { tab: 'addresses' } }" in header
    assert "Cliente da casa" not in header
    assert "`Carrinho (${cartCount})`" in header
    assert "Material+Symbols+Rounded" in app
    assert "font-family: 'Material Symbols Rounded'" in css


def test_nuxt_account_menu_targets_real_account_tabs():
    account = _nuxt_file("pages/account.vue")

    for token in [
        "type AccountTab = 'profile' | 'orders' | 'addresses'",
        "const activeTab = ref<AccountTab>(normalizeAccountTab(route.query.tab))",
        "function normalizeAccountTab",
        "watch(() => route.query.tab",
        "router.replace({ path: '/conta', query })",
        'v-model="activeTab"',
    ]:
        assert token in account

    assert 'default-value="profile"' not in account
    assert "<UInputDate" in account
    assert 'type="date"' not in account


def test_nuxt_address_form_preserves_operational_label_fields():
    modal = _nuxt_file("components/AddressFormModal.vue")

    assert "label_key" in modal
    assert "label_custom" in modal
    assert "addressLabelKey" in modal
    assert "form.label === 'other'" in modal


def test_nuxt_cart_primary_and_secondary_actions_use_matching_size():
    cart = _nuxt_file("pages/cart.vue")

    footer = cart[cart.index("<template #footer>"):cart.index("</template>", cart.index("<template #footer>"))]
    assert 'label="Continuar comprando"' in footer
    assert 'size="lg"' in footer
    assert 'size="sm"' not in footer


def test_nuxt_pdp_accordion_keeps_content_mounted_for_smooth_collapse():
    pdp = _nuxt_file("pages/product/[sku].vue")
    css = _nuxt_file("assets/css/main.css")

    assert ':unmount-on-hide="false"' in pdp
    assert "shop-pdp-accordion" in pdp
    assert "data-[state=open]:animate-[accordion-down_220ms_ease-out]" in pdp
    assert "data-[state=closed]:animate-[accordion-up_180ms_ease-in]" in pdp
    assert "#components-body" in pdp
    assert "#nutrition-body" in pdp
    assert ".shop-pdp-accordion [data-slot=\"content\"]" in css


def test_nuxt_theme_follows_storefront_configuration():
    css = _nuxt_file("assets/css/main.css")
    app_config = _nuxt_file("app.config.ts")

    assert "--font-sans: 'Inter', sans-serif;" in css
    assert "--ui-primary: black;" in css
    assert "--ui-primary: white;" in css
    assert "primary: 'yellow'" in app_config
    assert "neutral: 'stone'" in app_config
    assert "button:" not in app_config
    assert "card:" not in app_config


def test_nuxt_operational_recovery_copy_uses_canonical_helper():
    copy = _nuxt_file("utils/operationalCopy.ts")

    assert "OPERATIONAL_COPY_SOURCE" in copy
    assert "COPY-SOURCE-001" in copy
    assert "COPY-FACT-001" in copy
    assert "retryAfterDescription" in copy
    assert "supportUrlWithMessage" in copy

    helper_consumers = {
        "components/CartIssueModal.vue": ["retryAfterDescription", "supportUrlWithMessage"],
        "components/ReorderRecoveryModal.vue": ["retryAfterDescription", "supportUrlWithMessage"],
        "composables/useCartState.ts": ["operationalCopy.availability", "operationalCopy.recovery"],
        "composables/useReorder.ts": ["operationalCopy.availability", "operationalCopy.recovery"],
        "pages/cart.vue": ["operationalCopy.loadFailure.cart"],
        "pages/checkout.vue": ["operationalCopy.recovery", "retryAfterDescription"],
        "pages/index.vue": ["operationalCopy.loadFailure.home"],
        "pages/menu.vue": ["operationalCopy.loadFailure.menu"],
        "pages/order/[ref]/payment.vue": ["operationalCopy.payment", "retryAfterDescription"],
        "pages/tracking/[ref].vue": ["operationalCopy.recovery.rateLimit", "retryAfterDescription"],
    }
    for relative, tokens in helper_consumers.items():
        source = _nuxt_file(relative)
        for token in tokens:
            assert token in source, f"{relative} must consume canonical operational copy token {token}"


def test_payment_surface_exposes_recovery_for_clipboard_and_polling_failures():
    payment = _nuxt_file("pages/order/[ref]/payment.vue")
    confirmation = _nuxt_file("pages/order/[ref]/confirmation.vue")
    api = _read(REPO_ROOT / "shopman" / "storefront" / "api" / "payment.py")
    copy = _nuxt_file("utils/operationalCopy.ts")

    assert "useRequestHeaders(['cookie'])" in payment
    assert "headers: requestHeaders" in payment
    assert "copyError" in payment
    assert "document.execCommand('copy')" in payment
    assert "copie manualmente" in payment
    assert "pollFailures" in payment
    assert "rateLimitRecovery" in payment
    assert "retry_after_seconds" in payment
    assert "retryAfterDescription" in payment
    assert "hasPendingPaymentAction" in payment
    assert "canRedirectToCardCheckout" in payment
    assert "redirectAction" in payment
    assert "status.should_redirect" in payment
    assert "Tente novamente em cerca de" in copy
    assert "stale_after_seconds" in payment
    assert "operationalCopy.payment.automaticStatusFailed" in payment
    assert "Não conseguimos atualizar o status automaticamente" in copy
    assert "Atualizar status" in payment
    assert "pixQrCodeFailed" in payment
    assert "isRenderablePixQrCode" in payment
    assert "payload.length >= 128" in payment
    assert "@error=\"markPixQrCodeFailed\"" in payment
    assert "QR Code indisponível" in payment

    assert "useRequestHeaders(['cookie'])" in confirmation
    assert "function shareOrder" in confirmation
    assert "whatsapp_url" in confirmation

    assert "PAYMENT_RATE_LIMIT_RETRY_SECONDS" in api
    assert "\"error_code\": \"rate_limited\"" in api
    assert "headers={\"Retry-After\": str(PAYMENT_RATE_LIMIT_RETRY_SECONDS)}" in api
    assert "block=False" in api


def test_tracking_surface_enforces_backend_payment_gate():
    tracking = _nuxt_file("pages/tracking/[ref].vue")
    checkout_api = _read(REPO_ROOT / "shopman" / "storefront" / "api" / "views.py")
    api = _read(REPO_ROOT / "shopman" / "storefront" / "api" / "tracking.py")
    serializer = _read(REPO_ROOT / "shopman" / "storefront" / "api" / "serializers.py")

    assert 'next_url = f"/pedido/{result.order_ref}/pagamento"' in checkout_api
    assert 'reverse("storefront:order_payment"' not in checkout_api
    assert "requires_payment_gate" in api
    assert "order_service.requires_payment_gate(order)" in api
    assert "payment_gate_url" in api
    assert "requires_payment_gate" in serializer
    assert "payment_gate_url" in serializer
    assert "actions = ActionSerializer(many=True" in serializer
    assert "can_mock_confirm_payment" not in serializer
    assert "requires_payment_gate" in tracking
    assert "payment_gate_url" in tracking
    assert "findTrackingAction('mock_confirm_payment')" in tracking
    assert "can_mock_confirm_payment" not in tracking
    assert "mockConfirmPayment" in tracking
    assert "Capturar pagamento teste" in tracking
    assert "Eventos do pedido" not in tracking
    assert "timelineItems" not in tracking
    assert "navigateTo(paymentGateUrl.value, { replace: true })" in tracking


def test_cart_release_reservation_is_confirmed_before_mutation():
    cart = _nuxt_file("pages/cart.vue")

    assert "function needsReleaseConfirmation" in cart
    assert "releaseCandidate.value = line" in cart
    assert 'title="Liberar reserva?"' in cart
    assert "remove <strong" in cart
    assert "label=\"Manter item\"" in cart
    assert "label=\"Liberar reserva\"" in cart
    assert "@click=\"confirmReleaseReservation\"" in cart


def test_account_surface_exposes_customer_lifecycle_contracts():
    account = _nuxt_file("pages/account.vue")
    bottom_tabs = _nuxt_file("components/ShopBottomTabs.vue")
    account_surface = account + bottom_tabs
    urls = _read(REPO_ROOT / "shopman" / "storefront" / "api" / "urls.py")
    api = _read(REPO_ROOT / "shopman" / "storefront" / "api" / "account.py")

    for endpoint in [
        "/api/v1/account/orders/active/",
        "/api/v1/account/preferences/food/",
        "/api/v1/account/preferences/notifications/",
        "/api/v1/account/devices/",
        "/api/v1/account/export/",
        "/api/v1/account/delete/",
    ]:
        assert endpoint in account_surface

    for view_name in [
        "ActiveOrderCountView",
        "FoodPreferenceToggleView",
        "NotificationPreferenceToggleView",
        "AccountDeviceListView",
        "AccountDeviceDetailView",
        "AccountExportView",
        "AccountDeleteView",
    ]:
        assert view_name in urls
        assert view_name in api

    assert "orderFilterOptions" in account
    assert "saveProfile" in account
    assert "profile.value = response" in account
    assert "session.setIdentity({ name: response.name" in account
    assert "profileError" in account
    assert "Salvar perfil" in account
    assert "stamps_completed" in account
    assert "transactions" in account
    assert "deleteAccountAcknowledged" in account
    assert "clearNuxtData('shopman-auth-session')" in account
    assert "clearCart()" in account


def test_catalog_and_pdp_surface_render_rich_projection_fields():
    menu = _nuxt_file("pages/menu.vue")
    home = _nuxt_file("pages/index.vue")
    pdp = _nuxt_file("pages/product/[sku].vue")
    types = _nuxt_file("types/shopman.ts")
    icon_helper = _nuxt_file("composables/useShopmanIcon.ts")

    assert "happyHour" in menu
    assert "favoriteCategoryRef" in menu
    assert "aria-live=\"polite\"" in menu
    assert "IntersectionObserver" in menu
    assert "search_terms" in menu
    assert "centerSectionRail" in menu
    assert "useShopmanIcon(section.icon)" in menu
    assert "new EventSource(apiPath('/storefront/stock/events/storefront/')" in home
    assert "SHOPMAN_ICON_MAP" in icon_helper
    assert "SHOPMAN_ICON_FALLBACK" in icon_helper

    for field in ["search_terms", "components", "allergen", "conservation", "nutrition"]:
        assert field in types
        if field != "search_terms":
            assert f"product.{field}" in pdp

    assert "Tabela nutricional" in pdp
    assert "Alérgenos e restrições" in pdp
    assert "Conservação" in pdp
    assert "hasAllergenInfo" in pdp
    assert "hasNutritionInfo" in pdp
    assert "hasConservationInfo" in pdp
    assert "Porções por embalagem" in pdp


def test_tracking_surface_supports_live_promise_details_and_rating():
    tracking = _nuxt_file("pages/tracking/[ref].vue")
    api = _read(REPO_ROOT / "shopman" / "storefront" / "api" / "tracking.py")
    urls = _read(REPO_ROOT / "shopman" / "storefront" / "api" / "urls.py")
    serializer = _read(REPO_ROOT / "shopman" / "storefront" / "api" / "serializers.py")

    assert "promiseRows" in tracking
    assert "promise_rows" in tracking
    assert "promise_deadline_label" in tracking
    assert "formatCountdown" in tracking
    assert "showInitialSkeleton" in tracking
    assert "data.copy.page_kicker" in tracking
    assert "data.pickup_info.directions_url" in tracking
    assert "data.pickup_info.directions_label" in tracking
    assert ":href=\"data.pickup_info.directions_url\"" in tracking
    assert "i-lucide-map-pin" in tracking
    assert "candidate.ref === 'pay_now'" in tracking
    assert "candidate.href || candidate.ref === 'pay_now'" not in tracking
    assert "fulfillment.tracking_label" in tracking
    assert "Seu pedido está pronto para retirada ou para sair em entrega." not in tracking
    assert "Abrir mapa" not in tracking
    assert "Acompanhar entrega" not in tracking
    assert "eventSource.onopen" in tracking
    assert "stopPolling()" in tracking
    assert "Aviso ativo" not in tracking
    assert "active_notification ? { label:" not in tracking
    for label in ("Próximo passo", "Ação necessária", "Recuperação", "Última atualização"):
        assert label not in tracking
    assert "rateOrderAction" in tracking
    assert "submitRating" in tracking
    assert "/api/v1/orders/" in tracking
    assert "/rate/" in tracking

    assert "OrderRateView" in api
    assert "OrderRateView" in urls
    assert "actions = ActionSerializer" in serializer
    assert "rate_order" in tracking


def test_wp05_stock_reorder_and_rate_limit_recovery_contracts():
    cart = _nuxt_file("composables/useCartState.ts")
    cart_modal = _nuxt_file("components/CartIssueModal.vue")
    csrf = _nuxt_file("composables/useShopmanCsrfHeaders.ts")
    reorder = _nuxt_file("composables/useReorder.ts")
    reorder_modal = _nuxt_file("components/ReorderRecoveryModal.vue")
    tracking = _nuxt_file("pages/tracking/[ref].vue")
    account = _nuxt_file("pages/account.vue")
    layout = _nuxt_file("layouts/default.vue")
    surface_api = _read(REPO_ROOT / "shopman" / "storefront" / "api" / "surface.py")
    tracking_api = _read(REPO_ROOT / "shopman" / "storefront" / "api" / "tracking.py")

    assert "stockIssueFromPayload" in cart
    assert "stockIssue" in cart
    assert "retryLastCartMutation" in cart
    assert "acceptStockIssueAvailable" in cart
    assert "rateLimitRecovery" in cart
    assert "useShopmanCsrfHeaders" in cart
    assert "CartIssueModal" in layout
    assert "Itens afetados" in cart_modal
    assert "Tentar novamente" in cart_modal
    assert "Falar com a equipe" in cart_modal

    assert "skipped_items" in reorder
    assert "skippedItems" in reorder
    assert "retryRateLimitedReorder" in reorder
    assert "useShopmanCsrfHeaders" in reorder
    assert "ReorderRecoveryModal" in layout
    assert "Itens indisponíveis" in reorder_modal
    assert 'v-model="activeTab"' in account
    assert "normalizeAccountTab(route.query.tab)" in account
    assert "value: 'orders'" in account
    assert "slot: 'orders'" in account
    assert "aria-label=\"Repetir pedido\"" in account

    assert "activeRateLimitRecovery" in tracking
    assert "retry_after_seconds" in tracking
    assert "refreshAfterRateLimit" in tracking
    assert "useShopmanCsrfHeaders" in tracking

    assert "csrftoken" in csrf
    assert "/api/v1/storefront/cart/" in csrf

    assert "CART_RATE_LIMIT_RETRY_SECONDS" in surface_api
    assert "REORDER_RATE_LIMIT_RETRY_SECONDS" in surface_api
    assert "\"skipped_items\": _skipped_reorder_items(skipped)" in surface_api
    assert "headers={\"Retry-After\": str(retry_after_seconds)}" in surface_api
    assert "TRACKING_RATE_LIMIT_RETRY_SECONDS" in tracking_api
    assert "headers={\"Retry-After\": str(TRACKING_RATE_LIMIT_RETRY_SECONDS)}" in tracking_api


def test_nuxt_pwa_and_confirmation_routes_exist():
    for relative in [
        "pages/offline.vue",
        "pages/how-it-works.vue",
        "pages/order/[ref]/confirmation.vue",
        "composables/useHaptics.ts",
        "plugins/gestures.client.ts",
        "plugins/haptics.client.ts",
        "../server/routes/manifest.json.get.ts",
        "../server/routes/pwa/[icon].png.get.ts",
        "../server/routes/sw.js.get.ts",
        "../server/routes/robots.txt.get.ts",
        "../server/routes/sitemap.xml.get.ts",
    ]:
        assert (NUXT_APP / relative).resolve().exists(), f"missing {relative}"

    app = _nuxt_file("app.vue")
    assert "rel: 'manifest'" in app


def test_wp09_pwa_offline_gestures_and_haptics_contracts():
    manifest = _nuxt_file("../server/routes/manifest.json.get.ts")
    sw = _nuxt_file("../server/routes/sw.js.get.ts")
    offline = _nuxt_file("pages/offline.vue")
    service_worker = _nuxt_file("plugins/service-worker.client.ts")
    gestures = _nuxt_file("plugins/gestures.client.ts")
    haptics = _nuxt_file("composables/useHaptics.ts")
    haptic_plugin = _nuxt_file("plugins/haptics.client.ts")
    stepper = _nuxt_file("components/ProductStepper.vue")
    cart_line = _nuxt_file("components/CartLineItem.vue")
    checkout = _nuxt_file("pages/checkout.vue")
    tracking = _nuxt_file("pages/tracking/[ref].vue")

    for icon in [
        "public/pwa/icon-192.png",
        "public/pwa/icon-512.png",
        "public/pwa/icon-maskable-512.png",
    ]:
        assert (NUXT_APP.parent / icon).exists(), f"missing PWA icon {icon}"

    assert "djangoBaseUrl" in manifest
    assert "/manifest.json" in manifest
    assert "/api/v1/storefront/home/" in manifest
    assert "normalizeManifest" in manifest
    assert "start_url: '/menu'" in manifest
    assert "/pwa/icon-192.png" in manifest
    assert "/pwa/icon-512.png" in manifest
    assert "purpose: 'maskable'" in manifest
    assert "Cache-Control" in manifest

    assert "CACHE_NAME = 'shopman-nuxt-pwa-v2'" in sw
    assert "OFFLINE_URL = '/offline'" in sw
    assert "credentials: 'omit'" in sw
    assert "request.method !== 'GET'" in sw
    assert "request.mode === 'navigate'" in sw
    assert "isSafeNavigation" in sw
    assert "CACHE_FIRST_PREFIXES" in sw
    assert "'/_nuxt/'" in sw
    assert "NETWORK_ONLY_PREFIXES" in sw
    for sensitive_prefix in [
        "'/api/'",
        "'/auth/'",
        "'/cart'",
        "'/checkout'",
        "'/login'",
        "'/conta'",
        "'/pedido/'",
        "'/order/'",
        "'/tracking/'",
    ]:
        assert sensitive_prefix in sw
    assert "if (matchesAny(url.pathname, NETWORK_ONLY_PREFIXES))" in sw
    assert "if (matchesAny(url.pathname, CACHE_FIRST_PREFIXES))" in sw

    assert "Páginas já abertas" in offline
    assert "carrinho, checkout, pagamento e acompanhamento precisam de conexão" in offline
    assert "serviceWorker.register('/sw.js')" in service_worker

    assert "data-pull-refresh" in tracking
    assert "@shopman-pull-refresh" in tracking
    assert "refreshAfterGesture" in tracking
    assert "data-swipe-dismiss" in tracking
    assert "@shopman-swipe-dismiss" in tracking
    assert "isInteractiveTarget" in gestures
    assert "hasOpenDialog" in gestures
    assert "shopman-pull-refresh" in gestures
    assert "shopman-swipe-dismiss" in gestures
    assert "window.history.back()" in gestures

    assert "navigator.vibrate" in haptics
    assert "triggerHaptic" in haptics
    assert "confirm: [50, 30, 50]" in haptics
    assert "[data-haptic]" in haptic_plugin
    assert "data-haptic=\"light\"" in stepper
    assert "data-haptic=\"double\"" in stepper
    assert "data-haptic=\"double\"" in cart_line
    assert "data-haptic=\"confirm\"" in checkout
