"""Shopman middleware — App Platform host probe, API version header, operator cookie domain.

As superfícies de cliente/operador são apps Nuxt; a captura de ?channel=, o
onboarding e o welcome-gate vivem nos apps de superfície (storefront/backstage) —
não aqui. Este módulo guarda só os middlewares realmente wired em settings.
"""

from __future__ import annotations

from ipaddress import ip_address, ip_network

from django.conf import settings

API_V1_PREFIX = "/api/v1/"
API_VERSION = "1"
HEALTH_PROBE_PATHS = {"/health/", "/ready/"}
APP_PLATFORM_PROBE_NETWORK = ip_network("100.64.0.0/10")


class AppPlatformHealthCheckHostMiddleware:
    """Let DigitalOcean internal probes reach health views without wildcard hosts.

    App Platform probes the container through a private CGNAT address and sends
    that IP as the Host header. Rewriting only health/readiness probe hosts keeps
    Django's normal ALLOWED_HOSTS protection intact for every business route.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info in HEALTH_PROBE_PATHS and _is_app_platform_probe_host(
            request.META.get("HTTP_HOST", "")
        ):
            request.META["HTTP_HOST"] = _canonical_allowed_host()
        return self.get_response(request)


def _is_app_platform_probe_host(raw_host: str) -> bool:
    host = _strip_port(raw_host)
    try:
        return ip_address(host) in APP_PLATFORM_PROBE_NETWORK
    except ValueError:
        return False


def _strip_port(raw_host: str) -> str:
    host = raw_host.strip()
    if host.startswith("["):
        return host[1:].split("]", 1)[0]
    return host.rsplit(":", 1)[0]


def _canonical_allowed_host() -> str:
    for host in settings.ALLOWED_HOSTS:
        if host and host != "*" and not host.startswith("."):
            return host
    return "localhost"


class APIVersionHeaderMiddleware:
    """Stamp every `/api/v1/` response with `X-API-Version: 1`.

    Informational header for debugging, telemetry and client-side assertion
    (clients can sanity-check they're talking to the expected major version
    without parsing the URL). Applied only to the versioned storefront API;
    OpenAPI schema/docs and core-app APIs are unaffected.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(API_V1_PREFIX):
            response["X-API-Version"] = API_VERSION
        return response


class OperatorSessionDomainMiddleware:
    """Scope the session/CSRF cookies to the operator zone's parent domain.

    The operator apps (gestor./kds./pos./fournil.) live on a registrable domain
    SEPARATE from the customer store, so one login works across all of them while
    the cookie stays physically isolated from the public store (OPERATOR-AUTH-PLAN,
    Opção A). One Django serves both audiences, so ``SESSION_COOKIE_DOMAIN`` cannot
    be set globally (it would break the customer's host-only session). Instead, this
    middleware rewrites the cookie ``Domain`` only when the request is served on the
    operator API host — keying on ``request.get_host()`` (the operator apps proxy to
    ``SHOPMAN_OPERATOR_API_HOST``; the proxy rewrites Host to that alias).

    Feature-gated: with ``SHOPMAN_OPERATOR_COOKIE_DOMAIN`` empty (default), it is a
    no-op and the current host-only behaviour is preserved for everyone.

    Placed high in ``MIDDLEWARE`` so its response phase runs AFTER Session/CSRF
    middleware have written their cookies. Settings are read per-request so
    ``override_settings`` works in tests.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        cookie_domain = (getattr(settings, "SHOPMAN_OPERATOR_COOKIE_DOMAIN", "") or "").strip()
        if not cookie_domain:
            return response
        if not self._is_operator_host(request, cookie_domain):
            return response
        for name in (settings.SESSION_COOKIE_NAME, settings.CSRF_COOKIE_NAME):
            if name in response.cookies:
                response.cookies[name]["domain"] = cookie_domain
        return response

    @staticmethod
    def _is_operator_host(request, cookie_domain: str) -> bool:
        host = request.get_host().split(":")[0].lower()
        api_host = (getattr(settings, "SHOPMAN_OPERATOR_API_HOST", "") or "").strip().lower()
        if api_host and host == api_host:
            return True
        bare = cookie_domain.lstrip(".").lower()
        return host == bare or host.endswith("." + bare)
