"""GERADO por `manage.py omotenashi_usage_map` — não edite à mão.

Snapshot do mapa chave↔tela (ver usage.py). O teste de deriva compara
este arquivo com o scan real e falha quando o consumo de copy muda.
"""

USAGE: dict[str, tuple[tuple[str, str, str], ...]] = {
    "ACCOUNT_DELETE_WARNING": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "ACCOUNT_GREETING_PREFIX": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "ACCOUNT_PAGE_TITLE": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "ACCOUNT_TRUSTED_DEVICES_MESSAGE": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "ADDRESSES_EMPTY": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "AVAILABILITY_AVAILABLE": (
        ("shopman/storefront/presentation/status.py", "Loja", "Rótulos de status"),
    ),
    "AVAILABILITY_LOW_STOCK": (
        ("shopman/storefront/presentation/status.py", "Loja", "Rótulos de status"),
    ),
    "AVAILABILITY_PLANNED_OK": (
        ("shopman/storefront/presentation/status.py", "Loja", "Rótulos de status"),
    ),
    "AVAILABILITY_UNAVAILABLE": (
        ("shopman/storefront/presentation/status.py", "Loja", "Rótulos de status"),
    ),
    "BIRTHDAY_HERO_HEADING": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "BIRTHDAY_HERO_SUB": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "CART_CHECKOUT_BLOCK_CHANNEL": (
        ("shopman/storefront/presentation/checkout.py", "Loja", "Checkout"),
    ),
    "CART_CHECKOUT_BLOCK_EMPTY": (
        ("shopman/storefront/presentation/cart.py", "Loja", "Sacola"),
        ("shopman/storefront/presentation/checkout.py", "Loja", "Checkout"),
    ),
    "CART_CHECKOUT_BLOCK_MIN_ORDER": (
        ("shopman/storefront/presentation/cart.py", "Loja", "Sacola"),
    ),
    "CART_CHECKOUT_BLOCK_UNAVAILABLE": (
        ("shopman/storefront/presentation/cart.py", "Loja", "Sacola"),
    ),
    "CART_DISCOUNT_LABEL_AVAILABILITY": (
        ("shopman/shop/modifiers.py", "Loja", "Preços e promoções"),
    ),
    "CART_DISCOUNT_LABEL_TIME_WINDOW": (
        ("shopman/shop/modifiers.py", "Loja", "Preços e promoções"),
    ),
    "CART_EMPTY": (),
    "CART_UNAVAILABLE_BANNER": (
        ("shopman/storefront/presentation/cart.py", "Loja", "Sacola"),
    ),
    "CART_WAITLIST_NOTICE": (
        ("shopman/storefront/presentation/cart.py", "Loja", "Sacola"),
    ),
    "CART_WAITLIST_PLANNED_DATE": (
        ("shopman/storefront/presentation/cart.py", "Loja", "Sacola"),
    ),
    "CATALOG_EMPTY": (
        ("shopman/storefront/presentation/catalog.py", "Loja", "Cardápio"),
    ),
    "CHECKOUT_CLOSED_PREORDER_HINT": (
        ("shopman/storefront/api/views.py", "Loja", "Superfície geral"),
    ),
    "CHECKOUT_CONFIRM_CTA": (
        ("shopman/storefront/presentation/checkout.py", "Loja", "Checkout"),
    ),
    "CHECKOUT_LOYALTY_SAVINGS_PREFIX": (
        ("shopman/storefront/presentation/checkout.py", "Loja", "Checkout"),
    ),
    "CHECKOUT_REPRICING_MESSAGE": (
        ("shopman/storefront/presentation/checkout.py", "Loja", "Checkout"),
    ),
    "CHECKOUT_STOCK_LIMITED": (
        ("shopman/storefront/presentation/checkout.py", "Loja", "Checkout"),
    ),
    "CHECKOUT_STOCK_SOLD_OUT": (
        ("shopman/storefront/presentation/checkout.py", "Loja", "Checkout"),
    ),
    "CHECKOUT_SWITCH_ACCOUNT_CONFIRM_CTA": (
        ("shopman/storefront/presentation/checkout.py", "Loja", "Checkout"),
    ),
    "CHECKOUT_SWITCH_ACCOUNT_KEEP_CTA": (
        ("shopman/storefront/presentation/checkout.py", "Loja", "Checkout"),
    ),
    "CHECKOUT_SWITCH_ACCOUNT_MESSAGE": (
        ("shopman/storefront/presentation/checkout.py", "Loja", "Checkout"),
    ),
    "CHECKOUT_SWITCH_ACCOUNT_TITLE": (
        ("shopman/storefront/presentation/checkout.py", "Loja", "Checkout"),
    ),
    "CHECKOUT_WHEN_REQUIRED": (
        ("shopman/storefront/presentation/checkout.py", "Loja", "Checkout"),
    ),
    "CONFIRMATION_ETA_PREFIX": (
        ("shopman/storefront/api/confirmation.py", "Loja", "Confirmação do pedido"),
    ),
    "CONFIRMATION_HEADING": (
        ("shopman/storefront/api/confirmation.py", "Loja", "Confirmação do pedido"),
    ),
    "CONFIRMATION_ITEMS_HEADING": (
        ("shopman/storefront/api/confirmation.py", "Loja", "Confirmação do pedido"),
    ),
    "CONFIRMATION_PREORDER_WHEN_PREFIX": (
        ("shopman/storefront/api/confirmation.py", "Loja", "Confirmação do pedido"),
    ),
    "CONFIRMATION_SHARE_CTA": (
        ("shopman/storefront/api/confirmation.py", "Loja", "Confirmação do pedido"),
    ),
    "CONFIRMATION_TRACK_CTA": (
        ("shopman/shop/projections/payment_status.py", "Loja", "Pagamento"),
        ("shopman/storefront/api/confirmation.py", "Loja", "Confirmação do pedido"),
    ),
    "DEVICE_LIST_CURRENT": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "DEVICE_LIST_EMPTY": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "DEVICE_LIST_REGISTERED_PREFIX": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "DEVICE_LIST_UNKNOWN": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "DEVICE_REVOKE_ALL_CONFIRM": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "DEVICE_REVOKE_ALL_CTA": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "DEVICE_REVOKE_CONFIRM": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "DEVICE_REVOKE_CTA": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "DEVICE_TRUST_CTA": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "DEVICE_TRUST_PROMPT": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "DEVICE_TRUST_REDIRECTING": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "DEVICE_TRUST_SAVED": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "DEVICE_TRUST_SKIP_CTA": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "FAVORITES_EMPTY": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "FAVORITES_EMPTY_CTA": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "FOOTER_COPYRIGHT": (
        ("shopman/storefront/presentation/shop.py", "Loja", "Institucional"),
    ),
    "HISTORY_EMPTY": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "HOME_AVAILABILITY_HEADING": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_BIRTHDAY_CTA": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_FULL_MENU_CTA": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_HERO_HANDMADE_SUBTITLE": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_HERO_HANDMADE_TITLE_PREFIX": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_HERO_HANDMADE_TITLE_SUFFIX": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_HERO_ORDER_SUBTITLE": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_HERO_ORDER_TITLE_PREFIX": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_HERO_ORDER_TITLE_SUFFIX": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_HERO_REORDER_SUBTITLE": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_HERO_REORDER_TITLE_PREFIX": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_HERO_REORDER_TITLE_SUFFIX": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_HOW_COUNTER_LABEL": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_HOW_HOURS_EMPTY": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_HOW_HOURS_LABEL": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_HOW_IT_WORKS_HEADING": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_HOW_ONLINE_HEADING": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_HOW_SELF_SERVICE_LABEL": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_HOW_STEP_CHOOSE": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_HOW_STEP_FULFILL": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_HOW_STEP_PAY": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_HOW_STORE_HEADING": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_MENU_CTA": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_TOMORROW_LABEL": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_WHATSAPP_CTA": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOME_WHATSAPP_CTA_LABEL": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOW_DELIVERY_PREFIX": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOW_DELIVERY_SUFFIX": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOW_IT_WORKS_INTRO": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOW_IT_WORKS_META_DESCRIPTION": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOW_ONLINE_CHOOSE_MESSAGE": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOW_ONLINE_PAY_MESSAGE": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOW_ONLINE_TRACK_MESSAGE": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOW_PREORDER_MESSAGE": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOW_QUALITY_MESSAGE": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOW_STORE_COUNTER_MESSAGE": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOW_STORE_SELF_SERVICE_MESSAGE": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "HOW_TRACKING_MESSAGE": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "KINTSUGI_CANCEL_REFUSED": (
        ("shopman/storefront/api/tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "KINTSUGI_PAUSED_COPY": (
        ("shopman/storefront/api/surface.py", "Loja", "Disponibilidade e avisos"),
    ),
    "KINTSUGI_PLANNED_OFFER": (
        ("shopman/storefront/api/surface.py", "Loja", "Disponibilidade e avisos"),
    ),
    "KINTSUGI_SHORTAGE_GENERIC": (
        ("shopman/storefront/api/surface.py", "Loja", "Disponibilidade e avisos"),
    ),
    "KINTSUGI_SHORTAGE_SUBSTITUTES_INTRO": (
        ("shopman/storefront/api/surface.py", "Loja", "Disponibilidade e avisos"),
    ),
    "LOGIN_AUTH_CONFIRMED": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "LOGIN_CHANGE_PHONE_CTA": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "LOGIN_CODE_HEADING": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "LOGIN_CODE_HELP": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "LOGIN_HANDOFF_EXPIRED": (
        ("shopman/storefront/api/auth.py", "Loja", "Entrar"),
    ),
    "LOGIN_NAME_CTA": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "LOGIN_NAME_HEADING": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "LOGIN_NAME_SUBTITLE": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "LOGIN_NO_PASSWORD_NOTE": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "LOGIN_PHONE_CTA_SMS": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "LOGIN_PHONE_CTA_WA": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "LOGIN_PHONE_HEADING": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "LOGIN_PHONE_SUBTITLE": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "LOGIN_TERMS_NOTE": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "LOGIN_TRUSTED_DEVICE_CTA": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "LOGIN_TRUSTED_DEVICE_MESSAGE": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "LOGIN_TRUSTED_OTHER_PHONE": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "LOGIN_WA_CART_KEPT": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "LOGIN_WA_GLIMPSE": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "LOGIN_WA_MANUAL_INTRO": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "LOGIN_WA_MANUAL_TITLE": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "LOGOUT_FAREWELL": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "MIN_ORDER_WARNING": (
        ("shopman/storefront/presentation/cart.py", "Loja", "Sacola"),
    ),
    "MIN_ORDER_WARNING_MIDDLE": (
        ("shopman/storefront/presentation/cart.py", "Loja", "Sacola"),
    ),
    "MIN_ORDER_WARNING_PREFIX": (
        ("shopman/storefront/presentation/cart.py", "Loja", "Sacola"),
    ),
    "ORDER_STATUS_CANCELLED": (
        ("shopman/backstage/presentation/status.py", "Operador", "Rótulos de status"),
        ("shopman/storefront/presentation/status.py", "Loja", "Rótulos de status"),
    ),
    "ORDER_STATUS_COMPLETED": (
        ("shopman/backstage/presentation/status.py", "Operador", "Rótulos de status"),
        ("shopman/storefront/presentation/status.py", "Loja", "Rótulos de status"),
    ),
    "ORDER_STATUS_CONFIRMED": (
        ("shopman/backstage/presentation/status.py", "Operador", "Rótulos de status"),
        ("shopman/storefront/presentation/status.py", "Loja", "Rótulos de status"),
    ),
    "ORDER_STATUS_DELIVERED": (
        ("shopman/backstage/presentation/status.py", "Operador", "Rótulos de status"),
        ("shopman/storefront/presentation/status.py", "Loja", "Rótulos de status"),
    ),
    "ORDER_STATUS_DISPATCHED": (
        ("shopman/backstage/presentation/status.py", "Operador", "Rótulos de status"),
        ("shopman/storefront/presentation/status.py", "Loja", "Rótulos de status"),
    ),
    "ORDER_STATUS_NEW": (
        ("shopman/backstage/presentation/status.py", "Operador", "Rótulos de status"),
        ("shopman/storefront/presentation/status.py", "Loja", "Rótulos de status"),
    ),
    "ORDER_STATUS_PREPARING": (
        ("shopman/backstage/presentation/status.py", "Operador", "Rótulos de status"),
        ("shopman/storefront/presentation/status.py", "Loja", "Rótulos de status"),
    ),
    "ORDER_STATUS_READY": (
        ("shopman/backstage/presentation/status.py", "Operador", "Rótulos de status"),
        ("shopman/storefront/presentation/status.py", "Loja", "Rótulos de status"),
    ),
    "ORDER_STATUS_RETURNED": (
        ("shopman/backstage/presentation/status.py", "Operador", "Rótulos de status"),
        ("shopman/storefront/presentation/status.py", "Loja", "Rótulos de status"),
    ),
    "PAYMENT_CARD_INTRO": (
        ("shopman/storefront/api/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_CARD_SECURITY_NOTE": (
        ("shopman/storefront/api/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_DEV_CONFIRM_CTA": (
        ("shopman/shop/projections/payment_status.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_METHOD_CARD": (
        ("shopman/backstage/presentation/status.py", "Operador", "Rótulos de status"),
        ("shopman/storefront/presentation/status.py", "Loja", "Rótulos de status"),
    ),
    "PAYMENT_METHOD_CASH": (
        ("shopman/backstage/presentation/status.py", "Operador", "Rótulos de status"),
        ("shopman/storefront/presentation/status.py", "Loja", "Rótulos de status"),
    ),
    "PAYMENT_METHOD_EXTERNAL": (
        ("shopman/backstage/presentation/status.py", "Operador", "Rótulos de status"),
        ("shopman/storefront/presentation/status.py", "Loja", "Rótulos de status"),
    ),
    "PAYMENT_METHOD_MIXED": (
        ("shopman/backstage/presentation/status.py", "Operador", "Rótulos de status"),
        ("shopman/storefront/presentation/status.py", "Loja", "Rótulos de status"),
    ),
    "PAYMENT_METHOD_PIX": (
        ("shopman/backstage/presentation/status.py", "Operador", "Rótulos de status"),
        ("shopman/storefront/presentation/status.py", "Loja", "Rótulos de status"),
    ),
    "PAYMENT_ORDER_REF_LABEL": (
        ("shopman/storefront/api/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PAGE_META_DESCRIPTION": (
        ("shopman/storefront/api/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PIX_COPIED": (
        ("shopman/storefront/api/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PIX_COPY_BTN": (
        ("shopman/storefront/api/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PIX_COPY_LABEL": (
        ("shopman/storefront/api/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PIX_EXPIRES_LABEL": (
        ("shopman/storefront/api/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PIX_INSTRUCTION": (
        ("shopman/storefront/api/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CANCELLED_MESSAGE": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CANCELLED_RECOVERY": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CANCELLED_TITLE": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CARD_ACTION": (
        ("shopman/shop/projections/payment_status.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CARD_ACTIVE_NOTIFICATION": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CARD_AUTHORIZED_MESSAGE": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CARD_AUTHORIZED_NEXT_CONFIRMED": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CARD_AUTHORIZED_NEXT_NEW": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CARD_AUTHORIZED_TITLE": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CARD_MESSAGE": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CARD_NEXT": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CARD_PENDING_MESSAGE": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CARD_PENDING_NEXT": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CARD_PENDING_RECOVERY": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CARD_PENDING_TITLE": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CARD_PRECONFIRMATION_ACTION": (
        ("shopman/shop/projections/payment_status.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CARD_PRECONFIRMATION_ACTIVE_NOTIFICATION": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CARD_PRECONFIRMATION_MESSAGE": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CARD_PRECONFIRMATION_NEXT": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CARD_PRECONFIRMATION_RECOVERY": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CARD_PRECONFIRMATION_TITLE": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CARD_RECOVERY": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_CARD_TITLE": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_ERROR_MESSAGE": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_ERROR_NEXT": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_ERROR_RECOVERY": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_ERROR_TITLE": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_EXPIRED_ACTIVE_NOTIFICATION": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_EXPIRED_MESSAGE": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_EXPIRED_NEXT": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_EXPIRED_RECOVERY": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_EXPIRED_TITLE": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_PAID_MESSAGE": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_PAID_NEXT": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_PAID_TITLE": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_PIX_ACTION": (
        ("shopman/shop/projections/payment_status.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_PIX_ACTIVE_NOTIFICATION": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_PIX_MESSAGE": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_PIX_NEXT": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_PIX_PRECONFIRMATION_MESSAGE": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_PIX_PRECONFIRMATION_NEXT": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_PIX_PRECONFIRMATION_RECOVERY": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_PIX_PRECONFIRMATION_TITLE": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_PIX_RECOVERY": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_PROMISE_PIX_TITLE": (
        ("shopman/storefront/presentation/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_RETRY_CTA": (
        ("shopman/shop/projections/payment_status.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_TOTAL_LABEL": (
        ("shopman/storefront/api/payment.py", "Loja", "Pagamento"),
    ),
    "PAYMENT_VIEW_ORDER_CTA": (
        ("shopman/shop/projections/payment_status.py", "Loja", "Pagamento"),
    ),
    "PRODUCT_CROSS_SELL_HEADING": (
        ("shopman/storefront/presentation/product_detail.py", "Loja", "Página do produto"),
    ),
    "PROFILE_BIRTHDAY_FIELD": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "PROFILE_EDIT_CTA": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "PROFILE_EMAIL_FIELD": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "PROFILE_FIRST_NAME_FIELD": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "PROFILE_LAST_NAME_FIELD": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "PROFILE_MISSING_VALUE": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "PROFILE_NAME_FIELD": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "PROFILE_NAME_LABEL": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "PROFILE_PHONE_FIELD": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "PROFILE_SECTION_TITLE": (
        ("shopman/storefront/api/account.py", "Loja", "Conta do cliente"),
    ),
    "REORDER_CONFLICT_APPEND_HELP": (
        ("shopman/storefront/presentation/reorder.py", "Loja", "Pedir de novo"),
    ),
    "REORDER_CONFLICT_APPEND_LABEL": (
        ("shopman/storefront/presentation/reorder.py", "Loja", "Pedir de novo"),
    ),
    "REORDER_CONFLICT_CANCEL_LABEL": (
        ("shopman/storefront/presentation/reorder.py", "Loja", "Pedir de novo"),
    ),
    "REORDER_CONFLICT_CURRENT_CART_LABEL": (
        ("shopman/storefront/presentation/reorder.py", "Loja", "Pedir de novo"),
    ),
    "REORDER_CONFLICT_MESSAGE": (
        ("shopman/storefront/presentation/reorder.py", "Loja", "Pedir de novo"),
    ),
    "REORDER_CONFLICT_PREVIOUS_ORDER_LABEL": (
        ("shopman/storefront/presentation/reorder.py", "Loja", "Pedir de novo"),
    ),
    "REORDER_CONFLICT_REPLACE_ACK_LABEL": (
        ("shopman/storefront/presentation/reorder.py", "Loja", "Pedir de novo"),
    ),
    "REORDER_CONFLICT_REPLACE_HELP": (
        ("shopman/storefront/presentation/reorder.py", "Loja", "Pedir de novo"),
    ),
    "REORDER_CONFLICT_REPLACE_LABEL": (
        ("shopman/storefront/presentation/reorder.py", "Loja", "Pedir de novo"),
    ),
    "REORDER_CONFLICT_TITLE": (
        ("shopman/storefront/presentation/reorder.py", "Loja", "Pedir de novo"),
    ),
    "SEARCH_EMPTY": (
        ("shopman/storefront/presentation/catalog.py", "Loja", "Cardápio"),
    ),
    "SEARCH_EMPTY_CTA": (
        ("shopman/storefront/presentation/catalog.py", "Loja", "Cardápio"),
    ),
    "SHOP_STATUS_CLOSED": (
        ("shopman/storefront/presentation/shop_status.py", "Loja", "Status da loja"),
    ),
    "SHOP_STATUS_CLOSED_OPENS_AT": (
        ("shopman/storefront/presentation/shop_status.py", "Loja", "Status da loja"),
    ),
    "SHOP_STATUS_OPEN": (
        ("shopman/storefront/presentation/shop_status.py", "Loja", "Status da loja"),
    ),
    "SHOP_STATUS_OPEN_CLOSING_SOON": (
        ("shopman/storefront/presentation/shop_status.py", "Loja", "Status da loja"),
    ),
    "SHOP_STATUS_OPEN_UNTIL": (
        ("shopman/storefront/presentation/shop_status.py", "Loja", "Status da loja"),
    ),
    "SOLDOUT_NOTIFY_CTA": (
        ("shopman/storefront/api/surface.py", "Loja", "Disponibilidade e avisos"),
    ),
    "TRACKING_ACTION_CANCEL_ORDER": (
        ("shopman/shop/projections/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_ACTION_CONFIRM_RECEIVED": (
        ("shopman/shop/projections/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_ACTION_MOCK_CONFIRM_PAYMENT": (
        ("shopman/shop/projections/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_ACTION_RATE_ORDER": (
        ("shopman/shop/projections/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_ACTION_READY_PICKUP": (
        ("shopman/shop/projections/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_AUTO_CONFIRM_LABEL": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_CANCEL_ACK_LABEL": (
        ("shopman/shop/projections/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_CANCEL_BACK": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_CANCEL_CONFIRM": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_CANCEL_CONFIRM_CTA": (
        ("shopman/shop/projections/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_CANCEL_CONFIRM_MESSAGE": (
        ("shopman/shop/projections/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_CANCEL_CONFIRM_TITLE": (
        ("shopman/shop/projections/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_CANCEL_CTA": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_CANCEL_FAILED_MESSAGE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_CANCEL_HEADING": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_CANCEL_KEEP_CTA": (
        ("shopman/shop/projections/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_CANCEL_SUCCESS_MESSAGE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_CANCEL_SUCCESS_TITLE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_CANCEL_WARNING_MESSAGE": (
        ("shopman/shop/projections/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_CANCEL_WARNING_TITLE": (
        ("shopman/shop/projections/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_CANCEL_YES": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_CARD_AUTHORIZED": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_DELIVERED_YOIN": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_DELIVERY_FEE_LABEL": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_DELIVERY_HEADING": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_DELIVERY_WAITING_COURIER": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_FINISHED_BADGE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_ITEMS_HEADING": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_LIVE_BADGE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_MENU_CTA": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_MOCK_PAYMENT_FAILED_MESSAGE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_MOCK_PAYMENT_FAILED_TITLE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_MOCK_PAYMENT_SUCCESS_MESSAGE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_MOCK_PAYMENT_SUCCESS_TITLE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_NOT_FOUND_MESSAGE": (
        ("shopman/storefront/api/tracking.py", "Loja", "Acompanhamento do pedido"),
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_NOT_FOUND_TITLE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_ORDER_REF_LABEL": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PAGE_KICKER": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PAGE_META_DESCRIPTION": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PAYMENT_CONFIRMED_NOTICE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PAYMENT_CTA": (
        ("shopman/shop/projections/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PAYMENT_EXPIRED": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PAYMENT_PENDING": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PAYMENT_REQUESTED": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PAYMENT_TIME_LEFT": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PICKUP_DIRECTIONS_CTA": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PICKUP_HEADING": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_POLLING_BADGE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROGRESS_HEADING": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_ACTIVE_UPDATE_NOTIFICATION": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_AVAILABILITY_MESSAGE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_AVAILABILITY_NEXT": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_AVAILABILITY_RECOVERY": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_CANCELLED_NEXT": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_CARD_AUTHORIZED_NEXT_CONFIRMED": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_CARD_AUTHORIZED_NEXT_NEW": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_CLOSED_HOURS_MESSAGE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_CLOSED_HOURS_MESSAGE_NEXT": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_CLOSED_HOURS_NEXT_PREFIX": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_CLOSED_HOURS_NEXT_UNKNOWN": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_DELIVERED_NEXT": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_DISPATCHED_MESSAGE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_DISPATCHED_MESSAGE_ETA": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_DISPATCHED_NEXT": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_FALLBACK_MESSAGE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_LABEL_ACTIVE_NOTIFICATION": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_LABEL_DEADLINE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_LABEL_NEXT": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_LABEL_RECOVERY": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_PAYMENT_ACTIVE_NOTIFICATION": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_PAYMENT_CONFIRMED_NEXT_CONFIRMED": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_PAYMENT_CONFIRMED_NEXT_NEW": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_PAYMENT_EXPIRED_NEXT": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_PAYMENT_NEXT": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_PAYMENT_RECOVERY": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_PREORDER_MESSAGE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_PREORDER_MESSAGE_NO_DATE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_PREORDER_NEXT": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_PREORDER_TITLE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_PREPARING_NEXT_DELIVERY": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_PREPARING_NEXT_PICKUP": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_READY_DELIVERY_ACTIVE_NOTIFICATION": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_READY_DELIVERY_NEXT": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_READY_PICKUP_ACTIVE_NOTIFICATION": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_READY_PICKUP_NEXT": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_RECEIVED_NEXT": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_STALE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_PROMISE_UPDATED_NOW": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_RATE_LIMIT_TITLE": (
        ("shopman/storefront/api/tracking.py", "Loja", "Acompanhamento do pedido"),
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_RATE_THANKS": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_RATING_COMMENT_ARIA_LABEL": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_RATING_COMMENT_PLACEHOLDER": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_RATING_FAILED_MESSAGE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_RATING_SUBMIT_CTA": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_RATING_SUCCESS_TITLE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_REORDER_CTA": (
        ("shopman/shop/projections/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_RETRY_CTA": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_STATUS_CARD_AUTHORIZED": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_STATUS_PAYMENT_EXPIRED": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_STATUS_PAYMENT_PENDING": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_STATUS_PREORDER_SCHEDULED": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_STATUS_READY_DELIVERY": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_STATUS_READY_PICKUP": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_STATUS_WAITING_STORE_CONFIRMATION": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_STEP_AVAILABILITY_CONFIRMED": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_STEP_CANCELLED": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_STEP_COMPLETED": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_STEP_DELIVERED": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_STEP_DISPATCHED": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_STEP_PAYMENT_CONFIRMED": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_STEP_PREPARING": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_STEP_READY_DELIVERY": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_STEP_READY_GENERIC": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_STEP_READY_PICKUP": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_STEP_RECEIVED": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_SUPPORT_CTA": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_SUPPORT_WHATSAPP_MESSAGE": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_TOMORROW_HOOK": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
    "TRACKING_TOTAL_LABEL": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_TRACK_SHIPMENT": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "TRACKING_TRACK_SHIPMENT_WITH_CARRIER": (
        ("shopman/storefront/presentation/order_tracking.py", "Loja", "Acompanhamento do pedido"),
    ),
    "URGENCY_BANNER_MESSAGE": (
        ("shopman/storefront/presentation/home.py", "Loja", "Início"),
    ),
}
