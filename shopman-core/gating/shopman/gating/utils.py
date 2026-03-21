"""
Gating utilities.
"""

from django.utils.http import url_has_allowed_host_and_scheme

from shopman.utils.phone import normalize_phone  # noqa: F401


def get_client_ip(request, trusted_proxy_depth: int = 1) -> str:
    """
    Get client IP from request.

    Args:
        request: Django HttpRequest
        trusted_proxy_depth: Number of trusted proxies in front of the app.
            Use the rightmost N-th entry from X-Forwarded-For.
            Default 1 means trust the last proxy.
    """
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        parts = [p.strip() for p in xff.split(",")]
        # Use the entry at position -depth (rightmost trusted proxy)
        idx = max(0, len(parts) - trusted_proxy_depth)
        return parts[idx]
    return request.META.get("REMOTE_ADDR", "")


def safe_redirect_url(url: str | None, request=None) -> str:
    """
    Validate a redirect URL to prevent open redirect attacks.

    Only allows:
    - Relative paths (starting with /)
    - URLs matching ALLOWED_REDIRECT_HOSTS

    Rejects:
    - External URLs (https://evil.com)
    - Protocol-relative URLs (//evil.com)
    - Backslash URLs (\\evil.com)

    Args:
        url: The URL to validate
        request: Django request (used to get current host)

    Returns:
        The validated URL, or LOGIN_REDIRECT_URL if invalid
    """
    from .conf import get_gating_settings

    settings = get_gating_settings()
    fallback = settings.LOGIN_REDIRECT_URL

    if not url:
        return fallback

    # Build allowed hosts set
    allowed_hosts: set[str] = set(settings.ALLOWED_REDIRECT_HOSTS)
    if request:
        allowed_hosts.add(request.get_host())

    if url_has_allowed_host_and_scheme(url, allowed_hosts=allowed_hosts):
        return url

    return fallback
