"""Assist de IA por campo do catálogo (POST api/v1/backstage/catalog/ai-assist/).

Contrato: um campo por vez, o operador aceita ou descarta na superfície e nada é
gravado aqui. Os testes mockam o SDK do Anthropic — o que importa é (a) o prompt
montado ser ESPECÍFICO do campo pedido, (b) 503 sem chave configurada e (c) 400
em campo não assistível. Gate: ``shop.manage_catalog``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from shopman.offerman.models import Collection, CollectionItem, Product

from shopman.backstage.services import catalog as catalog_service
from shopman.backstage.services.exceptions import AiAssistNotConfigured
from shopman.shop.models import Shop

URL = "/api/v1/backstage/catalog/ai-assist/"


def _manage_catalog_perm() -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"),
        codename="manage_catalog",
    )


@pytest.fixture
def shop(db):
    return Shop.objects.create(name="Loja")


@pytest.fixture
def operator(db, shop):
    user = User.objects.create_user("ai-assist-api", password="pw", is_staff=True)
    user.user_permissions.add(_manage_catalog_perm())
    return user


@pytest.fixture
def product(db, shop):
    pao = Product.objects.create(sku="PAO", name="Pão francês", base_price_q=500, unit="un")
    pao.keywords.add("padaria")
    padaria = Collection.objects.create(ref="padaria", name="Padaria")
    CollectionItem.objects.create(collection=padaria, product=pao, is_primary=True)
    return pao


def _fake_message(text: str) -> MagicMock:
    """Resposta do SDK: lista de content blocks, só o de tipo "text" conta."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    message = MagicMock()
    message.content = [block]
    return message


@pytest.fixture
def anthropic_create(settings):
    """Mocka ``Anthropic().messages.create`` com a chave configurada."""
    settings.AI_ASSIST_API_KEY = "sk-ant-test"
    settings.AI_ASSIST_PROVIDER = "anthropic"
    settings.AI_ASSIST_MODEL = "claude-opus-4-8"
    with patch("anthropic.Anthropic") as client_cls:
        create = client_cls.return_value.messages.create
        create.return_value = _fake_message("Sugestão do assistente.")
        yield create


# ── prompt por campo ──────────────────────────────────────────────────────────


def test_short_description_prompt_asks_for_a_short_one(client, operator, product, anthropic_create):
    client.force_login(operator)
    resp = client.post(
        URL,
        data={"sku": "PAO", "field": "short_description", "current_value": ""},
        content_type="application/json",
    )

    assert resp.status_code == 200
    assert resp.json()["suggestion"] == "Sugestão do assistente."

    kwargs = anthropic_create.call_args.kwargs
    prompt = kwargs["messages"][0]["content"]
    assert "descrição curta" in prompt
    assert "1 a 2 frases" in prompt
    # contexto do produto viaja junto — a sugestão nasce coerente com o que existe
    assert "Pão francês" in prompt
    assert "Padaria" in prompt
    assert "padaria" in prompt  # palavra-chave
    assert kwargs["model"] == "claude-opus-4-8"


def test_long_description_prompt_differs_from_short(client, operator, product, anthropic_create):
    client.force_login(operator)
    client.post(
        URL, data={"sku": "PAO", "field": "long_description"}, content_type="application/json"
    )
    prompt = anthropic_create.call_args.kwargs["messages"][0]["content"]
    assert "descrição longa" in prompt
    assert "2 a 4 frases" in prompt
    assert "1 a 2 frases" not in prompt


def test_ingredients_prompt_asks_for_anvisa_order(client, operator, product, anthropic_create):
    client.force_login(operator)
    client.post(
        URL, data={"sku": "PAO", "field": "ingredients_text"}, content_type="application/json"
    )
    prompt = anthropic_create.call_args.kwargs["messages"][0]["content"]
    assert "ordem decrescente de peso" in prompt
    assert "ANVISA" in prompt


def test_social_caption_prompt_excludes_hashtags(client, operator, product, anthropic_create):
    client.force_login(operator)
    client.post(
        URL, data={"sku": "PAO", "field": "social_caption"}, content_type="application/json"
    )
    prompt = anthropic_create.call_args.kwargs["messages"][0]["content"]
    assert "Instagram/TikTok" in prompt
    assert "Sem hashtags" in prompt


def test_hashtags_prompt_asks_for_space_separated_list(client, operator, product, anthropic_create):
    client.force_login(operator)
    client.post(URL, data={"sku": "PAO", "field": "hashtags"}, content_type="application/json")
    prompt = anthropic_create.call_args.kwargs["messages"][0]["content"]
    assert "5 a 8 hashtags" in prompt
    assert "separadas por espaço" in prompt


def test_current_value_is_sent_as_the_text_to_improve(client, operator, product, anthropic_create):
    """Campo já preenchido: a sugestão é uma reescrita, não um texto do zero."""
    client.force_login(operator)
    client.post(
        URL,
        data={
            "sku": "PAO",
            "field": "short_description",
            "current_value": "Pão francês crocante",
        },
        content_type="application/json",
    )
    prompt = anthropic_create.call_args.kwargs["messages"][0]["content"]
    assert "Pão francês crocante" in prompt
    assert "versão melhor" in prompt


def test_voice_rules_travel_in_the_system_prompt(client, operator, product, anthropic_create):
    client.force_login(operator)
    client.post(
        URL, data={"sku": "PAO", "field": "short_description"}, content_type="application/json"
    )
    system = anthropic_create.call_args.kwargs["system"]
    assert "português do Brasil" in system
    assert "travessão" in system  # copy do cliente não usa —


# ── nada é gravado ────────────────────────────────────────────────────────────


def test_assist_does_not_persist_anything(client, operator, product, anthropic_create):
    client.force_login(operator)
    client.post(
        URL, data={"sku": "PAO", "field": "short_description"}, content_type="application/json"
    )
    product.refresh_from_db()
    assert product.short_description == ""


# ── erros ─────────────────────────────────────────────────────────────────────


def test_missing_api_key_returns_503(client, operator, product, settings):
    settings.AI_ASSIST_API_KEY = ""
    client.force_login(operator)
    resp = client.post(
        URL, data={"sku": "PAO", "field": "short_description"}, content_type="application/json"
    )
    assert resp.status_code == 503
    assert "AI_ASSIST_API_KEY" in resp.json()["detail"]


def test_unassistable_field_returns_400(client, operator, product, anthropic_create):
    client.force_login(operator)
    resp = client.post(URL, data={"sku": "PAO", "field": "sku"}, content_type="application/json")
    assert resp.status_code == 400
    anthropic_create.assert_not_called()


def test_unknown_sku_returns_400(client, operator, product, anthropic_create):
    client.force_login(operator)
    resp = client.post(
        URL, data={"sku": "NAO-EXISTE", "field": "short_description"}, content_type="application/json"
    )
    assert resp.status_code == 400


def test_missing_field_returns_400(client, operator, product, anthropic_create):
    client.force_login(operator)
    resp = client.post(URL, data={"sku": "PAO"}, content_type="application/json")
    assert resp.status_code == 400


def test_empty_completion_returns_502(client, operator, product, anthropic_create):
    anthropic_create.return_value = _fake_message("   ")
    client.force_login(operator)
    resp = client.post(
        URL, data={"sku": "PAO", "field": "short_description"}, content_type="application/json"
    )
    assert resp.status_code == 502


# ── gate ──────────────────────────────────────────────────────────────────────


def test_staff_without_permission_is_blocked(client, db, shop, product, anthropic_create):
    user = User.objects.create_user("sem-perm", password="pw", is_staff=True)
    client.force_login(user)
    resp = client.post(
        URL, data={"sku": "PAO", "field": "short_description"}, content_type="application/json"
    )
    assert resp.status_code in (403, 404)
    anthropic_create.assert_not_called()


# ── service ───────────────────────────────────────────────────────────────────


def test_service_raises_not_configured_by_type(db, shop, product, settings):
    """A camada HTTP mapeia por TIPO para 503 — a falta de chave não é 400."""
    settings.AI_ASSIST_API_KEY = ""
    with pytest.raises(AiAssistNotConfigured):
        catalog_service.ai_assist_field("PAO", "short_description")
