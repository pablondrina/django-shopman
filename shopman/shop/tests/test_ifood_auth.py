from __future__ import annotations

from unittest import mock

from django.test import override_settings

from shopman.shop.services import ifood_auth

_CFG = {
    "client_id": "cid-123",
    "client_secret": "secret-xyz",
    "api_base": "https://merchant-api.ifood.com.br",
    "timeout": 5,
}


class _Resp:
    def __init__(self, status: int, body: dict):
        self.status_code = status
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


@override_settings(SHOPMAN_IFOOD=dict(_CFG, client_id="", client_secret=""))
def test_inert_without_credentials():
    ifood_auth.reset_cache()
    assert ifood_auth.get_access_token() is None


@override_settings(SHOPMAN_IFOOD=_CFG)
def test_fetches_and_caches_token():
    ifood_auth.reset_cache()
    captured = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        captured["ua"] = headers.get("User-Agent")
        captured["ctype"] = headers.get("Content-Type")
        return _Resp(200, {"accessToken": "tok-1", "expiresIn": 21599})

    with mock.patch.object(ifood_auth.requests, "post", fake_post):
        t1 = ifood_auth.get_access_token()
        t2 = ifood_auth.get_access_token()  # cacheado → não chama de novo

    assert t1 == "tok-1"
    assert t2 == "tok-1"
    assert captured["url"].endswith("/authentication/v1.0/oauth/token")
    assert captured["data"] == {
        "grantType": "client_credentials",
        "clientId": "cid-123",
        "clientSecret": "secret-xyz",
    }
    assert captured["ua"] == ifood_auth.USER_AGENT
    assert captured["ctype"] == "application/x-www-form-urlencoded"


@override_settings(SHOPMAN_IFOOD=_CFG)
def test_force_refetches():
    ifood_auth.reset_cache()
    calls = {"n": 0}

    def fake_post(url, data=None, headers=None, timeout=None):
        calls["n"] += 1
        return _Resp(200, {"accessToken": f"tok-{calls['n']}", "expiresIn": 21599})

    with mock.patch.object(ifood_auth.requests, "post", fake_post):
        ifood_auth.get_access_token()
        again = ifood_auth.get_access_token(force=True)

    assert calls["n"] == 2
    assert again == "tok-2"


@override_settings(SHOPMAN_IFOOD=_CFG)
def test_returns_none_on_http_error():
    ifood_auth.reset_cache()

    def fake_post(url, data=None, headers=None, timeout=None):
        return _Resp(403, {"error": {"code": "Forbidden", "message": "No permissions granted"}})

    with mock.patch.object(ifood_auth.requests, "post", fake_post):
        assert ifood_auth.get_access_token() is None


@override_settings(SHOPMAN_IFOOD=_CFG)
def test_authorized_headers_carry_bearer_and_ua():
    ifood_auth.reset_cache()

    def fake_post(url, data=None, headers=None, timeout=None):
        return _Resp(200, {"accessToken": "tok-h", "expiresIn": 21599})

    with mock.patch.object(ifood_auth.requests, "post", fake_post):
        headers = ifood_auth.authorized_headers({"X-Test": "1"})

    assert headers["Authorization"] == "Bearer tok-h"
    assert headers["User-Agent"] == ifood_auth.USER_AGENT
    assert headers["X-Test"] == "1"
