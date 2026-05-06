from pathlib import Path

STOREFRONT_ROOT = Path(__file__).parents[1]
TEMPLATES = STOREFRONT_ROOT / "templates" / "storefront"
STATIC_JS = STOREFRONT_ROOT / "static" / "storefront" / "js"
CSS_SOURCE = STOREFRONT_ROOT.parents[1] / "static" / "src" / "style.css"
OMOTENASHI_COPY_SOURCE = STOREFRONT_ROOT.parent / "shop" / "omotenashi" / "copy.py"


def _read_template(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def test_cart_actions_helper_is_loaded_before_alpine():
    tokens = _read_template("partials/_tokens.html")

    assert "cart-actions.js" in tokens
    assert tokens.index("cart-actions.js") < tokens.index("alpinejs")


def test_catalog_cards_use_canonical_cart_line_factory():
    grid = _read_template("partials/_catalog_item_grid.html")
    availability = _read_template("partials/availability_preview.html")

    assert "window.ShopmanCart.line" in grid
    assert "window.ShopmanCart.line" in availability
    assert "X-Shopman-Error-UI" not in grid
    assert "stock-error-modal" not in grid
    assert "X-Shopman-Error-UI" not in availability
    assert "stock-error-modal" not in availability


def test_menu_search_is_accent_insensitive_and_observable():
    menu = _read_template("menu.html")

    assert "normalize('NFD')" in menu
    assert r"/[\u0300-\u036f]/g" in menu
    assert "loadSearchIndex()" in menu
    assert "window.ShopmanCart.notify" in menu
    assert "role=\"searchbox\"" in menu
    assert "aria-live=\"polite\"" in menu


def test_checkout_when_step_blocks_ambiguous_advance():
    checkout = _read_template("checkout.html")
    omotenashi_copy = OMOTENASHI_COPY_SOURCE.read_text(encoding="utf-8")

    assert "canAdvance(s)" in checkout
    assert "continueFrom(s)" in checkout
    assert "CHECKOUT_WHEN_REQUIRED" in checkout
    assert "Escolha data e horário para seguir." in omotenashi_copy
    assert ":disabled=\"!canAdvance('when')\"" in checkout


def test_checkout_pickup_flow_cannot_enter_address_step():
    checkout = _read_template("checkout.html")

    assert "coerceStep(s)" in checkout
    assert "stepIndex >= 0 && currentIndex >= 0" in checkout
    assert "if (!this.effectiveSteps().includes(s)) return;" in checkout
    assert 'x-show="fulfillmentType === \'delivery\'"' in checkout
    assert 'fulfillmentType === \'delivery\' || isDone(\'address\')' not in checkout


def test_checkout_loyalty_switch_uses_penguin_toggle_structure():
    checkout = _read_template("checkout.html")
    omotenashi_copy = OMOTENASHI_COPY_SOURCE.read_text(encoding="utf-8")

    assert "CHECKOUT_LOYALTY_PROMPT" in checkout
    assert "Usar pontos de fidelidade?" in omotenashi_copy
    assert "Usar pontos de fidelidade ·" not in checkout
    assert 'for="use-loyalty"' in checkout
    assert 'id="use-loyalty"' in checkout
    assert 'role="switch"' in checkout
    assert "peer-checked:after:translate-x-5" in checkout
    assert "after:left-[0.0625rem]" in checkout
    assert "useLoyalty: {% if form_data.use_loyalty %}true{% else %}false{% endif %}" in checkout


def test_checkout_contact_summary_is_collapsed_without_extra_microcopy():
    checkout = _read_template("checkout.html")

    assert "CHECKOUT_PHONE_PURPOSE" not in checkout
    assert "Usamos só para avisar sobre seu pedido." not in checkout
    assert "customerName.split(' ')[0]" not in checkout

    contact_start = checkout.index(">Contato<")
    contact_end = checkout.index('<input type="hidden" name="phone"', contact_start)
    contact_block = checkout[contact_start:contact_end]

    assert "break-words" not in contact_block
    assert "truncate" in contact_block
    assert "Editar" in contact_block
    assert contact_block.index("truncate") < contact_block.index("Editar")


def test_checkout_submit_copy_sends_order_instead_of_confirming_it():
    copy_source = OMOTENASHI_COPY_SOURCE.read_text(encoding="utf-8")

    assert 'CopyEntry(title="Enviar pedido")' in copy_source
    assert 'CopyEntry(title="Confirmar pedido")' not in copy_source


def test_checkout_switch_account_requires_confirmation_modal():
    checkout = _read_template("checkout.html")
    omotenashi_copy = OMOTENASHI_COPY_SOURCE.read_text(encoding="utf-8")

    contact_start = checkout.index(">Contato<")
    contact_end = checkout.index("</section>", contact_start)
    contact_block = checkout[contact_start:contact_end]
    contact_summary = checkout[contact_start:checkout.index('<input type="hidden" name="phone"', contact_start)]

    assert "showSwitchAccountModal: false" in checkout
    assert '@click="showSwitchAccountModal = true"' in contact_summary
    assert "$dispatch('nav:logout'" not in contact_summary
    assert "fixed inset-0 z-[90]" in contact_block
    assert "CHECKOUT_SWITCH_ACCOUNT_TITLE" in checkout
    assert "CHECKOUT_SWITCH_ACCOUNT_KEEP_CTA" in checkout
    assert "Trocar conta?" in omotenashi_copy
    assert "Manter conta" in omotenashi_copy
    assert "$dispatch('nav:logout'" in contact_block


def test_pdp_does_not_use_multiline_single_line_django_comments():
    pdp = _read_template("product_detail.html")

    assert "{# Add button" not in pdp
    assert "requested quantity lives in this Alpine scope" in pdp


def test_cart_actions_reports_rich_stock_errors_and_network_errors():
    js = (STATIC_JS / "cart-actions.js").read_text(encoding="utf-8")

    assert "X-Shopman-Error-UI" in js
    assert "mountStockErrorModal" in js
    assert "Sem conexão. Verifique sua internet." in js
    assert "Não foi possível atualizar o carrinho" in js


def test_action_toasts_have_independent_dismiss_button():
    base = _read_template("base.html")

    assert "notification.actionLabel" in base
    action_idx = base.index("notification.actionLabel")
    dismiss_idx = base.index('aria-label="Dispensar aviso"', action_idx)

    assert dismiss_idx > action_idx
    assert "data-dismiss" in base[action_idx:dismiss_idx + 160]


def test_cart_surface_keeps_mobile_totals_readable():
    cart = _read_template("cart.html")
    cart_page = _read_template("partials/_cart_page_content.html")
    drawer = _read_template("partials/cart_drawer.html")

    assert "{% block title %}{% omotenashi 'CART_PAGE_TITLE'" in cart
    assert "flex flex-col sm:flex-row sm:items-center sm:justify-between" in cart_page
    assert "self-end sm:self-auto shrink-0" in cart_page
    assert "flex flex-wrap items-center justify-between" in drawer
    assert "ml-auto shrink-0" in drawer


def test_mobile_menu_layers_above_menu_pill_bar():
    base = _read_template("base.html")
    menu = _read_template("menu.html")

    assert "z-[80]" in base
    assert "z-[70]" in base
    assert "sticky top-0 z-50" in menu
    assert "fixed left-0 right-0 bottom-0 z-40" in menu


def test_home_reorder_closes_open_shell_overlays_before_htmx_swap():
    base = _read_template("base.html")
    home = _read_template("home.html")
    quick_reorder = _read_template("partials/quick_reorder.html")
    reorder_modal = _read_template("partials/reorder_conflict_modal.html")
    tracking = _read_template("order_tracking.html")
    history = _read_template("order_history.html")

    assert "x-on:close-mobile-menu.window=\"mobileMenuIsOpen = false\"" in base
    assert 'id="reorder-conflict-modal"' in base
    assert "days_since_last_order > 7" not in quick_reorder
    assert "material-symbols-rounded" in quick_reorder
    assert "autorenew" in quick_reorder
    assert "item do pedido" not in quick_reorder
    assert "bg-neutral-100" not in quick_reorder
    assert "bg-white" in quick_reorder
    assert "max-w-2xl" in quick_reorder
    assert "max-w-4xl" not in quick_reorder
    assert "flex flex-col items-center" in quick_reorder
    assert "text-center" in quick_reorder
    assert "size-16" not in quick_reorder
    assert "rounded-full bg-primary/10" not in quick_reorder
    assert "text-primary/70" not in quick_reorder
    assert 'aria-label="Dispensar"' not in quick_reorder
    assert "show = false" not in quick_reorder
    assert "flex flex-wrap justify-center" in quick_reorder
    assert "truncate" not in quick_reorder
    assert "sm:grid-cols" not in quick_reorder
    assert 'hx-target="#reorder-conflict-modal"' in quick_reorder
    assert 'hx-target="#reorder-conflict-modal"' in home
    assert 'hx-target="#reorder-conflict-modal"' in tracking
    assert 'hx-target="#reorder-conflict-modal"' in history
    assert 'name="reorder_mode" value="replace"' in reorder_modal
    assert 'name="reorder_mode" value="add"' in reorder_modal
    assert "Substituir carrinho" in reorder_modal
    assert "Adicionar ao carrinho atual" in reorder_modal
    assert "close-mobile-menu" in quick_reorder
    assert "close-cart-drawer" in quick_reorder
    assert quick_reorder.count("close-mobile-menu") >= 2
    assert quick_reorder.count("close-cart-drawer") >= 2
    assert "close-mobile-menu" in home
    assert "close-cart-drawer" in home


def test_cart_reorder_history_link_is_mobile_fullwidth_ghost_button():
    cart = _read_template("cart.html")

    start = cart.index("Ver outros pedidos")
    wrapper_start = cart.rindex("<div ", 0, start)
    wrapper_open = cart[wrapper_start:cart.index(">", wrapper_start)]
    link_start = cart.rindex("<a ", 0, start)
    link_open = cart[link_start:cart.index(">", link_start)]

    assert "justify-start" in wrapper_open
    assert "justify-end" not in wrapper_open
    assert "w-full" in link_open
    assert "sm:w-auto" in link_open
    assert "justify-center" in link_open
    assert "border border-outline" in link_open
    assert "bg-transparent" in link_open
    assert "text-center" in link_open


def test_home_whatsapp_cta_is_fullwidth_on_mobile_only():
    home = _read_template("home.html")

    start = home.index('id="home-whatsapp-cta"')
    section_open = home[start:home.index(">", start)]

    assert "-mx-4" in section_open
    assert "md:mx-auto" in section_open
    assert "md:max-w-5xl" in section_open


def test_menu_pills_keep_scroll_spy_centering():
    menu = _read_template("menu.html")

    assert "queueScrollSpy()" in menu
    assert "requestAnimationFrame" in menu
    assert "updateActiveFromScroll()" in menu
    assert "centerPillInRail(closest)" in menu
    assert menu.index('<div x-data="menuNav()"') < menu.index('<section id="section-{{ section.ref }}"')
    assert menu.index("catalog_search_index_json|json_script") < menu.index("px-4 py-6 space-y-10")


def test_ios_form_focus_does_not_auto_zoom():
    css = CSS_SOURCE.read_text(encoding="utf-8")
    base = _read_template("base.html")

    assert "maximum-scale" not in base
    assert "@media (max-width: 767px)" in css
    assert "font-size: 16px" in css
    assert "overflow-x: clip" in css


def test_customer_surfaces_keep_focus_first_hierarchy():
    menu = _read_template("menu.html")
    pdp = _read_template("product_detail.html")
    login = _read_template("login.html")
    how_it_works = _read_template("como_funciona.html")
    cart_page = _read_template("partials/_cart_page_content.html")

    assert "h-36 sm:h-44 md:h-auto md:aspect-square" in pdp
    assert "text-3xl" not in pdp
    assert "w-screen -translate-x-1/2 -my-6" in login
    assert "md:grid-cols-[minmax(0,0.95fr)_minmax(0,1fr)]" in login
    assert "hidden min-h-[560px] md:block" in login
    assert "bg-white shadow-2xl" in login
    assert "grid grid-cols-2 gap-2 text-xs" not in login
    assert "h-28 sm:h-32" not in login
    assert "h-44 sm:h-56" not in login
    assert "shopping_bag" in how_it_works
    assert "storefront" in how_it_works
    assert "size-9 rounded-full bg-secondary" not in how_it_works
    assert "text-2xl lg:text-3xl" not in menu
    assert "text-2xl lg:text-3xl" not in cart_page


def test_pdp_cta_price_updates_with_quantity_without_dash():
    pdp = _read_template("product_detail.html")

    assert "unitPriceQ: {{ product.base_price_q|default:0 }}" in pdp
    assert "ctaLabel()" in pdp
    assert "this.unitPriceQ * this.qty" in pdp
    assert "fixed inset-x-0 bottom-14" in pdp
    assert "Adicionar —" not in pdp
    assert "Atualizar para" not in pdp


def test_auth_inputs_stay_readable_on_mobile():
    login = _read_template("login.html")
    code = _read_template("partials/auth_verify_code.html")
    omotenashi_copy = OMOTENASHI_COPY_SOURCE.read_text(encoding="utf-8")

    assert "text-lg tabular-nums" in login
    assert "font-mono" not in login
    assert "text-lg sm:text-xl tabular-nums tracking-[0.18em]" in code
    assert "tracking-[0.5em]" not in code
    assert "Vamos enviar um código pelo WhatsApp." not in login
    assert "LOGIN_NO_PASSWORD_NOTE" in login
    assert "Sem senha. A entrada é temporária e segura." in omotenashi_copy
    assert "novalidate" in login
    assert "Usamos só para avisar sobre seu pedido." not in login
    assert "CHECKOUT_PHONE_PURPOSE" not in login
    assert "aria-label=\"Brasil, código do país +55\"" in login
    assert "pointer-events-none absolute left-4" in login
    assert "'pl-[5.75rem]'" in login
    assert "role=\"button\"" in login
    assert "x-on:click.prevent.stop" in login
    assert "function phoneInput(initialValue)" in login
    assert "function nationalDigits(value)" in login
    assert "Usar número de outro país" in login
    assert "name=\"phone_region\"" in login
    assert "name=\"phone\"" in login
    assert "name=\"phone_normalized\"" in login
    assert "submittedPhone()" in login
    assert "d.indexOf('0') === 0" in login
    assert "material-symbols-rounded icon-md\" aria-hidden=\"true\">sms" in login


def test_mobile_nav_labels_use_base_small_type():
    bottom_nav = _read_template("partials/_bottom_nav.html")

    assert "text-xs font-medium" in bottom_nav
    assert "text-[10px] font-medium" not in bottom_nav
    assert "text-[9px]" not in bottom_nav


def test_badges_use_canonical_surface_contract():
    css = CSS_SOURCE.read_text(encoding="utf-8")
    availability = _read_template("components/availability_badge.html")
    grid = _read_template("partials/_catalog_item_grid.html")
    preview = _read_template("partials/availability_preview.html")
    pdp = _read_template("product_detail.html")
    drawer = _read_template("partials/cart_drawer.html")

    assert "rounded-full text-xs font-semibold" in css
    assert ".badge .material-symbols-rounded" in css
    assert "badge-success" in availability
    assert "badge-warning" in availability
    assert "badge-info" in availability
    assert "badge-neutral" in availability
    assert "badge-warning commerce-promo-badge w-fit" in grid
    assert "badge-neutral w-fit" in preview
    assert "badge-neutral mt-3 w-fit" in pdp
    assert "badge-info self-start" in drawer


def test_storefront_visible_copy_avoids_micro_type_and_loose_dashes():
    templates = [
        "base.html",
        "cart.html",
        "como_funciona.html",
        "checkout.html",
        "home.html",
        "login.html",
        "menu.html",
        "offline.html",
        "order_tracking.html",
        "payment.html",
        "product_detail.html",
        "partials/_catalog_item_grid.html",
        "partials/availability_preview.html",
        "partials/profile_display.html",
    ]

    for template in templates:
        source = _read_template(template)
        assert "text-[10px]" not in source, template
        assert "text-[9px]" not in source, template
        assert "&mdash;" not in source, template

    omotenashi_copy = OMOTENASHI_COPY_SOURCE.read_text(encoding="utf-8")
    for phrase in (
        "Ainda nem abrimos —",
        "Olhe à vontade —",
        "Ainda processando —",
        "Geramos um novo para você —",
        "Últimos pedidos —",
        "Aberto —",
        "Fechado —",
        "Tente novamente em alguns minutos —",
    ):
        assert phrase not in omotenashi_copy


def test_storefront_contrast_uses_accessible_penguin_tokens():
    css = CSS_SOURCE.read_text(encoding="utf-8")
    assert "--color-warning: var(--color-amber-700);" in css
    assert "--color-warning-dark: var(--color-amber-400);" in css
    assert "--color-success-dark: var(--color-lime-400);" in css
    assert "--color-danger-dark: var(--color-orange-400);" in css
    assert "placeholder:text-on-surface/85" in css
    assert "dark:placeholder:text-on-surface-dark/60" in css

    templates = [
        "base.html",
        "cart.html",
        "como_funciona.html",
        "checkout.html",
        "home.html",
        "login.html",
        "menu.html",
        "offline.html",
        "order_tracking.html",
        "payment.html",
        "product_detail.html",
        "partials/_bottom_nav.html",
        "partials/_cart_page_content.html",
        "partials/_catalog_item_grid.html",
        "partials/availability_preview.html",
        "partials/cart_drawer.html",
        "partials/checkout_order_summary.html",
    ]

    low_contrast_tokens = (
        "text-on-surface/50",
        "text-on-surface/60",
        "text-on-surface/70",
        "text-on-surface-dark/50",
        "placeholder:text-on-surface/30",
        "placeholder:text-on-surface/40",
        "placeholder:text-on-surface/50",
        "placeholder:text-on-surface-dark/30",
        "placeholder:text-on-surface-dark/40",
        "placeholder:text-on-surface-dark/50",
    )
    for template in templates:
        source = _read_template(template)
        for token in low_contrast_tokens:
            assert token not in source, f"{template} uses {token}"


def test_checkout_account_switch_preserves_cart_and_returns_to_checkout_login():
    base = _read_template("base.html")
    checkout = _read_template("checkout.html")

    assert 'name="next" :value="next"' in base
    assert "$event.detail && $event.detail.next" in base
    assert "{ next: '{% url 'storefront:login' %}?next={% url 'storefront:checkout' %}' }" in checkout


def test_customer_surfaces_use_canonical_icon_scale():
    css = CSS_SOURCE.read_text(encoding="utf-8")
    menu = _read_template("menu.html")
    pdp = _read_template("product_detail.html")
    grid = _read_template("partials/_catalog_item_grid.html")
    drawer = _read_template("partials/cart_drawer.html")
    bottom_nav = _read_template("partials/_bottom_nav.html")

    for token in ("icon-xs", "icon-sm", "icon-md", "icon-lg", "icon-xl", "icon-display"):
        assert f".{token}" in css

    assert "material-symbols-rounded icon-lg" in menu
    assert "material-symbols-rounded icon-display" in pdp
    assert "material-symbols-rounded icon-xl" in grid
    assert "material-symbols-rounded icon-display" in drawer
    assert "material-symbols-rounded icon-md" in bottom_nav


def test_viewport_chrome_follows_top_surface_color():
    base = _read_template("base.html")
    tokens = _read_template("partials/_tokens.html")
    css = CSS_SOURCE.read_text(encoding="utf-8")

    assert 'apple-mobile-web-app-status-bar-style" content="{% if shop_status.message %}' in base
    assert "black-translucent" not in base
    assert "syncViewportChrome()" in tokens
    assert "document.elementFromPoint" in tokens
    assert "--shopman-safe-top-color" in tokens
    assert "h.style.backgroundColor = color" in tokens
    assert "env(safe-area-inset-top)" in css
    assert "body::before" in css
