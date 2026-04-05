"""
Stocking Alerts Dispatch — Signal-driven stock alert notifications.

Add 'stocking.contrib.alerts' to INSTALLED_APPS to enable:
- Signal handler on Move post_save to check alerts for affected SKU
- Directive creation for notification dispatch via Ordering (if available)
- Configurable cooldown to prevent alert flooding
"""
