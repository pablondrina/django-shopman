"""Sessão rotaciona no login (anti-fixation), preservando o carrinho anônimo.

Canoniza o positivo do pentest: ao autenticar, o ``session_key`` muda (um token
de sessão fixado por um atacante antes do login deixa de valer), mas os dados de
sessão que devem sobreviver — o ``cart_session_key`` do carrinho anônimo — são
preservados no rollover.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.doorman.models import AccessLink

pytestmark = pytest.mark.django_db


def test_login_rotates_session_key_and_preserves_cart(client, channel, customer):
    # Carrinho anônimo + um valor de sessão qualquer, antes do login.
    session = client.session
    session["cart_session_key"] = "cart-anon-xyz"
    session.save()
    key_before = client.session.session_key
    assert key_before is not None

    _link, raw_token = AccessLink.create_with_token(
        customer_id=customer.uuid,
        audience=AccessLink.Audience.WEB_GENERAL,
        source=AccessLink.Source.INTERNAL,
        expires_at=timezone.now() + timedelta(minutes=5),
    )

    resp = client.post("/api/v1/auth/access/", {"token": raw_token})
    assert resp.status_code == 200, resp.content

    key_after = client.session.session_key
    assert key_after is not None
    # Anti-fixation: o token de sessão pré-login não sobrevive à autenticação.
    assert key_after != key_before
    # Mas o carrinho anônimo é adotado no rollover.
    assert client.session.get("cart_session_key") == "cart-anon-xyz"
    assert client.session.get("_auth_user_id") is not None
