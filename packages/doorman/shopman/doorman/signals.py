"""
Auth signals — Documented contracts (P6).

Each signal documents: kwargs, types, when emitted, and handler example.
"""

from django.dispatch import Signal


customer_authenticated = Signal()
"""
Dispatched when a Customer successfully authenticates via Auth.

Kwargs:
    customer (AuthCustomerInfo): The authenticated customer.
    user (django.contrib.auth.models.User): The Django User created/linked.
    method (str): Authentication method — "access_link" or "verification_code".
    request (HttpRequest): The Django request that triggered authentication.

When emitted:
    After successful AccessLink exchange (AccessLinkService.exchange).

Example::

    from django.dispatch import receiver
    from shopman.doorman.signals import customer_authenticated

    @receiver(customer_authenticated)
    def on_auth(sender, customer, user, method, request, **kwargs):
        logger.info(f"Customer {customer.uuid} logged in via {method}")
"""

access_link_created = Signal()
"""
Dispatched when an AccessLink is created.

Kwargs:
    token (AccessLink): The created token instance.
    customer (AuthCustomerInfo): The target customer.
    audience (str): Token audience (web_checkout, web_account, etc.).
    source (str): Token source (manychat, internal, api).

When emitted:
    After AccessLinkService.create_token() successfully creates a token.

Example::

    @receiver(access_link_created)
    def on_token(sender, token, customer, audience, source, **kwargs):
        analytics.track("access_link_created", customer_id=str(customer.uuid))
"""

verification_code_sent = Signal()
"""
Dispatched when a VerificationCode is sent to the customer.

Kwargs:
    code (VerificationCode): The VerificationCode instance (code_hash is HMAC, not raw).
    target_value (str): Phone (E.164) or email the code was sent to.
    delivery_method (str): How it was sent — "whatsapp", "sms", or "email".

When emitted:
    After AuthService.request_code() successfully sends the code.

Example::

    @receiver(verification_code_sent)
    def on_code_sent(sender, code, target_value, delivery_method, **kwargs):
        logger.info(f"Code sent to {target_value} via {delivery_method}")
"""

verification_code_verified = Signal()
"""
Dispatched when a VerificationCode is successfully verified.

Kwargs:
    code (VerificationCode): The verified VerificationCode instance.
    customer (AuthCustomerInfo): The customer who verified.
    purpose (str): Code purpose — "login" or "verify_contact".

When emitted:
    After AuthService.verify_for_login() succeeds.

Example::

    @receiver(verification_code_verified)
    def on_verified(sender, code, customer, purpose, **kwargs):
        if purpose == "login":
            logger.info(f"Customer {customer.uuid} verified via OTP")
"""

device_trusted = Signal()
"""
Dispatched when a device is marked as trusted after OTP verification.

Kwargs:
    device (TrustedDevice): The created TrustedDevice instance.
    customer_id (uuid.UUID): The customer's UUID.
    request (HttpRequest): The Django request.

When emitted:
    After DeviceTrustService.trust_device() creates a trusted device.

Example::

    @receiver(device_trusted)
    def on_device_trusted(sender, device, customer_id, request, **kwargs):
        logger.info(f"Device trusted for customer {customer_id}: {device.label}")
"""
