"""
Auth adapters -- CustomerResolver implementations.

Available adapters:
- NoopCustomerResolver: Returns minimal AuthCustomerInfo using the
  phone/email as the customer UUID. For development and testing without
  a real customer backend.
- CustomersCustomerResolver: Resolves customers via shopman.customers.
  This is the production adapter when Customers is installed.

Configure via AUTH["CUSTOMER_RESOLVER_CLASS"]:
    # Development / testing (no Customers dependency)
    AUTH = {
        "CUSTOMER_RESOLVER_CLASS": "shopman.auth.adapters.noop.NoopCustomerResolver",
    }

    # Production (with Customers)
    AUTH = {
        "CUSTOMER_RESOLVER_CLASS": "shopman.customers.adapters.auth.CustomerResolver",
    }
"""
