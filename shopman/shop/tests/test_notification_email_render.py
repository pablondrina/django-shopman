"""Assunto/corpo de e-mail com template malformado do Admin não suprime o envio.

Regressão do code-review max-effort: o assunto era renderizado com
``format_map`` sem try/except (só o corpo tinha guard). Uma chave malformada
no ``NotificationTemplate.subject`` editado no Admin levantava ValueError e
suprimia o e-mail inteiro.
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from shopman.shop.adapters import notification_email
from shopman.shop.adapters._notification_templates import render_template

pytestmark = pytest.mark.django_db


def test_render_template_degrades_on_malformed_brace():
    # Chave solta / spec inválido → template cru, nunca exceção.
    assert render_template("Pedido {order_ref pronto", {"order_ref": "ORD-1"}) == "Pedido {order_ref pronto"
    assert render_template("Total {0}", {"order_ref": "ORD-1"}) == "Total {0}"


def test_render_template_fills_known_keys_and_keeps_missing():
    assert render_template("Oi {order_ref}, faltou {x}", {"order_ref": "ORD-9"}) == "Oi ORD-9, faltou {x}"


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_malformed_admin_subject_still_sends_email():
    from django.core import mail

    from shopman.shop.models import NotificationTemplate

    NotificationTemplate.objects.create(
        event="order_confirmed",
        subject="Pedido {order_ref pronto",  # chave malformada (sem fechar)
        body="Seu pedido {order_ref} está confirmado.",
        is_active=True,
    )
    mail.outbox = []

    ok = notification_email.send("cliente@example.com", "order_confirmed", {"order_ref": "ORD-9"})

    assert ok is True
    assert len(mail.outbox) == 1
    # Assunto degradou para o template cru; corpo renderizou normal.
    assert mail.outbox[0].subject.endswith("Pedido {order_ref pronto")
    assert "ORD-9" in mail.outbox[0].body
