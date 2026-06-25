"""OperatorSessionDomainMiddleware — scopes session/CSRF cookies to the operator
zone's parent domain ONLY on the operator API host, leaving the customer's
host-only session intact (OPERATOR-AUTH-PLAN, Opção A / WP-AUTH-1).
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from shopman.shop.middleware import OperatorSessionDomainMiddleware

OPERATOR_COOKIE_DOMAIN = ".boulangerie.com.br"
OPERATOR_API_HOST = "api.boulangerie.com.br"


def _run(host: str) -> HttpResponse:
    def get_response(_request):
        response = HttpResponse()
        response.set_cookie(settings.SESSION_COOKIE_NAME, "sess-value")
        response.set_cookie(settings.CSRF_COOKIE_NAME, "csrf-value")
        return response

    request = RequestFactory().get("/api/v1/backstage/production/", HTTP_HOST=host)
    return OperatorSessionDomainMiddleware(get_response)(request)


def _domain(response: HttpResponse, name: str) -> str:
    return response.cookies[name]["domain"]


@override_settings(ALLOWED_HOSTS=["*"], SHOPMAN_OPERATOR_COOKIE_DOMAIN="", SHOPMAN_OPERATOR_API_HOST="")
def test_noop_when_feature_disabled():
    # Default (empty cookie domain) → host-only cookies, current behaviour for everyone.
    response = _run(OPERATOR_API_HOST)
    assert _domain(response, settings.SESSION_COOKIE_NAME) == ""
    assert _domain(response, settings.CSRF_COOKIE_NAME) == ""


@override_settings(
    ALLOWED_HOSTS=["*"],
    SHOPMAN_OPERATOR_COOKIE_DOMAIN=OPERATOR_COOKIE_DOMAIN,
    SHOPMAN_OPERATOR_API_HOST=OPERATOR_API_HOST,
)
def test_scopes_cookie_on_operator_api_host():
    response = _run(OPERATOR_API_HOST)
    assert _domain(response, settings.SESSION_COOKIE_NAME) == OPERATOR_COOKIE_DOMAIN
    assert _domain(response, settings.CSRF_COOKIE_NAME) == OPERATOR_COOKIE_DOMAIN


@override_settings(
    ALLOWED_HOSTS=["*"],
    SHOPMAN_OPERATOR_COOKIE_DOMAIN=OPERATOR_COOKIE_DOMAIN,
    SHOPMAN_OPERATOR_API_HOST=OPERATOR_API_HOST,
)
def test_scopes_cookie_on_host_under_operator_domain():
    # A host under the operator parent (e.g. the app's own host) is also scoped.
    response = _run("gestor.boulangerie.com.br")
    assert _domain(response, settings.SESSION_COOKIE_NAME) == OPERATOR_COOKIE_DOMAIN


@override_settings(
    ALLOWED_HOSTS=["*"],
    SHOPMAN_OPERATOR_COOKIE_DOMAIN=OPERATOR_COOKIE_DOMAIN,
    SHOPMAN_OPERATOR_API_HOST=OPERATOR_API_HOST,
)
def test_customer_host_stays_host_only():
    # The customer store / its API must keep host-only cookies — login intact.
    for host in ("nelsonboulangerie.com.br", "api.nelsonboulangerie.com.br"):
        response = _run(host)
        assert _domain(response, settings.SESSION_COOKIE_NAME) == "", host
        assert _domain(response, settings.CSRF_COOKIE_NAME) == "", host


@override_settings(
    ALLOWED_HOSTS=["*"],
    SHOPMAN_OPERATOR_COOKIE_DOMAIN=OPERATOR_COOKIE_DOMAIN,
    SHOPMAN_OPERATOR_API_HOST=OPERATOR_API_HOST,
)
def test_lookalike_suffix_is_not_matched():
    # "evilboulangerie.com.br" must NOT match ".boulangerie.com.br".
    response = _run("evilboulangerie.com.br")
    assert _domain(response, settings.SESSION_COOKIE_NAME) == ""
