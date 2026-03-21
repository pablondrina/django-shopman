"""
Gating adapters -- CustomerResolver implementations.

Available adapters:
- NoopCustomerResolver: Returns minimal GatingCustomerInfo using the
  phone/email as the customer UUID. For development and testing without
  a real customer backend.
- GuestmanCustomerResolver: Resolves customers via guestman.services.customer.
  This is the production adapter when Guestman is installed.

Configure via GATING["CUSTOMER_RESOLVER_CLASS"]:
    # Development / testing (no Guestman dependency)
    GATING = {
        "CUSTOMER_RESOLVER_CLASS": "shopman.gating.adapters.noop.NoopCustomerResolver",
    }

    # Production (with Guestman)
    GATING = {
        "CUSTOMER_RESOLVER_CLASS": "shopman.gating.adapters.guestman.GuestmanCustomerResolver",
    }
"""
