"""
Auth adapters -- CustomerResolver implementations.

Available adapters:
- NoopCustomerResolver: Returns minimal AuthCustomerInfo using the
  phone/email as the customer UUID. For development and testing without
  a real customer backend.
- GuestmanCustomerResolver: Resolves customers via shopman.guestman.
  This is the production adapter when Guestman is installed.

Configure via DOORMAN["CUSTOMER_RESOLVER_CLASS"]:
    # Development / testing (no Guestman dependency)
    DOORMAN = {
        "CUSTOMER_RESOLVER_CLASS": "shopman.doorman.adapters.noop.NoopCustomerResolver",
    }

    # Production (with Guestman)
    DOORMAN = {
        "CUSTOMER_RESOLVER_CLASS": "shopman.guestman.adapters.auth.CustomerResolver",
    }
"""
