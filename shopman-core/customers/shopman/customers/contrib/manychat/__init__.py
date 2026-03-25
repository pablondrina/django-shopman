"""
Customers Manychat - Manychat integration for customer management.

This contrib module provides Manychat-specific fields and sync functionality.

Usage:
    INSTALLED_APPS = [
        ...
        "customers",
        "customers.contrib.identifiers",  # Required
        "customers.contrib.manychat",
    ]

    from shopman.customers.contrib.manychat import ManychatService

    customer = ManychatService.sync_subscriber(subscriber_data)
"""
