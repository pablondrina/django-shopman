"""
Attending Manychat - Manychat integration for customer management.

This contrib module provides Manychat-specific fields and sync functionality.

Usage:
    INSTALLED_APPS = [
        ...
        "attending",
        "attending.contrib.identifiers",  # Required
        "attending.contrib.manychat",
    ]

    from shopman.attending.contrib.manychat import ManychatService

    customer = ManychatService.sync_subscriber(subscriber_data)
"""
