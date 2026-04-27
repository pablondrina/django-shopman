"""Omotenashi copy — single registry of user-facing interface strings.

This module holds the **defaults** (in code). Operators can override any entry
via the admin-backed `OmotenashiCopy` model; the resolver cascades from the
most specific (key + moment + audience) to the code-level default and always
returns a `CopyEntry`.

Keys follow UPPER_SNAKE_CASE; one key ⇒ one UX moment. A moment of "*" means
"same copy in every moment"; an audience of "*" means "same copy for anyone".

See docs/omotenashi.md and docs/plans/OMOTENASHI-PLAN.md.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

from collections.abc import Iterable
from dataclasses import dataclass

from .context import (
    ALL_MOMENTS,
    AUDIENCE_ANON,
    AUDIENCE_NEW,
    AUDIENCE_RETURNING,
    AUDIENCE_VIP,
    MOMENT_ALMOCO,
    MOMENT_FECHADO,
    MOMENT_FECHANDO,
    MOMENT_MADRUGADA,
    MOMENT_MANHA,
    MOMENT_TARDE,
)

WILDCARD = "*"


@dataclass(frozen=True)
class CopyEntry:
    title: str = ""
    message: str = ""

    def __bool__(self) -> bool:
        return bool(self.title or self.message)


# ── Defaults ───────────────────────────────────────────────────────────
#
# Layout: OMOTENASHI_DEFAULTS[key][moment][audience] = CopyEntry
# Use WILDCARD ("*") for the moment/audience axis when tone doesn't shift.

OMOTENASHI_DEFAULTS: dict[str, dict[str, dict[str, CopyEntry]]] = {
    # ── Menu ──────────────────────────────────────────────────────
    "MENU_SUBTITLE": {
        MOMENT_MADRUGADA: {WILDCARD: CopyEntry(message="Abrimos em breve. Pode escolher com calma.")},
        MOMENT_MANHA: {WILDCARD: CopyEntry(message="Fresquinho do forno.")},
        MOMENT_ALMOCO: {WILDCARD: CopyEntry(message="Cardápio do almoço.")},
        MOMENT_TARDE: {WILDCARD: CopyEntry(message="Para o café da tarde.")},
        MOMENT_FECHANDO: {WILDCARD: CopyEntry(message="Últimos pedidos do dia.")},
        MOMENT_FECHADO: {WILDCARD: CopyEntry(message="Olhe à vontade. Atendemos assim que abrirmos.")},
    },

    # ── Cart empty ────────────────────────────────────────────────
    "CART_EMPTY": {
        MOMENT_MADRUGADA: {
            WILDCARD: CopyEntry(
                title="Acordou cedo?",
                message="Abrimos em breve. Pode ir escolhendo o que quer.",
            ),
        },
        MOMENT_MANHA: {
            AUDIENCE_ANON: CopyEntry(
                title="Carrinho vazio",
                message="Pão fresquinho acabou de sair do forno.",
            ),
            AUDIENCE_RETURNING: CopyEntry(
                title="Vamos montar seu café da manhã?",
                message="Quer repetir o de sempre?",
            ),
            WILDCARD: CopyEntry(
                title="Vamos montar seu café da manhã?",
                message="Pão fresquinho acabou de sair do forno.",
            ),
        },
        MOMENT_ALMOCO: {
            WILDCARD: CopyEntry(
                title="Pausa para o almoço?",
                message="Sanduíches e saladas prontos.",
            ),
        },
        MOMENT_TARDE: {
            WILDCARD: CopyEntry(
                title="Um café da tarde?",
                message="Doces artesanais e cafés especiais.",
            ),
        },
        MOMENT_FECHANDO: {
            WILDCARD: CopyEntry(
                title="Ainda dá tempo",
                message="Últimos pedidos do dia.",
            ),
        },
        MOMENT_FECHADO: {
            WILDCARD: CopyEntry(
                title="Já fechamos por hoje",
                message="Você pode encomendar para o próximo dia.",
            ),
        },
    },

    # ── Product states ────────────────────────────────────────────
    "PRODUCT_OUT_OF_STOCK": {
        WILDCARD: {WILDCARD: CopyEntry(title="Indisponível")},
    },
    "PRODUCT_SCHEDULED_UNAVAILABLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Indisponível")},
    },

    # ── Checkout microcopy ────────────────────────────────────────
    "CHECKOUT_PHONE_PURPOSE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Usamos só para avisar quando seu pedido estiver pronto.")},
    },
    "CHECKOUT_NOTES_PROMPT": {
        WILDCARD: {WILDCARD: CopyEntry(title="Algo mais que devemos saber?")},
    },
    "CHECKOUT_COUPON_PROMPT": {
        WILDCARD: {WILDCARD: CopyEntry(title="Tem cupom de desconto?")},
    },
    "CHECKOUT_CONFIRM_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Confirmar pedido")},
    },

    # ── Cart microcopy ────────────────────────────────────────────
    "CART_PAGE_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Seu carrinho")},
    },
    "CART_UNAVAILABLE_BANNER": {
        WILDCARD: {WILDCARD: CopyEntry(message="O estoque de alguns itens mudou. Veja as opções em cada item abaixo.")},
    },
    "PICKUP_READY_NOTICE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Avisamos quando ficar pronto.")},
    },
    "MIN_ORDER_WARNING": {
        WILDCARD: {WILDCARD: CopyEntry(message="Adicionar mais itens")},
    },

    # ── Menu empty state ──────────────────────────────────────────
    "MENU_EMPTY": {
        WILDCARD: {WILDCARD: CopyEntry(message="Nenhum produto disponível no momento.")},
    },

    # ── Home sections ─────────────────────────────────────────────
    "HOME_AVAILABILITY_HEADING": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                title="Direto do forno",
                message="Disponibilidade em tempo real",
            ),
        },
    },
    "HOME_WHATSAPP_CTA": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                title="Dúvidas? Ou algum pedido especial?",
                message="Fale com a gente direto pelo WhatsApp. Respondemos o mais rápido possível.",
            ),
        },
    },
    "WELCOME_WHATSAPP": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                title="Bem-vindo de volta",
                message="Seu carrinho e endereços estão salvos.",
            ),
        },
    },

    # ── Tracking tail ─────────────────────────────────────────────
    "TRACKING_REORDER_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pedir novamente")},
    },
    "TRACKING_MENU_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Ver cardápio")},
    },
    "TRACKING_ETA_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(title="Previsão:")},
    },
    "TRACKING_AUTO_CONFIRM_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(message="Confirmação automática em")},
    },
    "TRACKING_ITEMS_HEADING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Itens do pedido")},
    },
    "TRACKING_DELIVERY_HEADING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Entrega")},
    },
    "TRACKING_PICKUP_HEADING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Retirada")},
    },
    "TRACKING_TRACK_SHIPMENT": {
        WILDCARD: {WILDCARD: CopyEntry(title="Rastrear envio")},
    },
    "TRACKING_CANCEL_HEADING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Cancelar pedido")},
    },
    "TRACKING_CANCEL_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Cancelar este pedido")},
    },
    "TRACKING_CANCEL_CONFIRM": {
        WILDCARD: {WILDCARD: CopyEntry(message="Confirmar cancelamento?")},
    },
    "TRACKING_CANCEL_YES": {
        WILDCARD: {WILDCARD: CopyEntry(title="Sim, cancelar")},
    },
    "TRACKING_CANCEL_BACK": {
        WILDCARD: {WILDCARD: CopyEntry(title="Voltar")},
    },

    # ── Order confirmation ────────────────────────────────────────
    "CONFIRMATION_HEADING": {
        MOMENT_MANHA: {
            AUDIENCE_VIP: CopyEntry(title="Ótimo começo de dia"),
            WILDCARD: CopyEntry(title="Pedido recebido"),
        },
        WILDCARD: {WILDCARD: CopyEntry(title="Pedido recebido")},
    },
    "CONFIRMATION_ITEMS_HEADING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Você encomendou")},
    },
    "CONFIRMATION_TRACK_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Acompanhar pedido")},
    },
    "CONFIRMATION_SHARE_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Compartilhar")},
    },

    # ── Payment ───────────────────────────────────────────────────
    "PAYMENT_WAITING": {
        WILDCARD: {WILDCARD: CopyEntry(message="Aguardando seu banco confirmar…")},
    },
    "PAYMENT_WAITING_LONG": {
        WILDCARD: {WILDCARD: CopyEntry(message="Ainda processando. Pode levar até 1 minuto.")},
    },
    "PAYMENT_PIX_EXPIRED": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                title="Este PIX expirou",
                message="Geramos um novo para você. É só continuar.",
            ),
        },
    },
    "PAYMENT_CARD_INTRO": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                message=(
                    "Você será levado ao ambiente seguro do Stripe. "
                    "Voltamos assim que confirmar."
                ),
            ),
        },
    },
    "PAYMENT_PIX_COPY_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(title="Copia e cola:")},
    },
    "PAYMENT_PIX_COPY_BTN": {
        WILDCARD: {WILDCARD: CopyEntry(title="Copiar")},
    },
    "PAYMENT_PIX_COPIED": {
        WILDCARD: {WILDCARD: CopyEntry(title="Copiado!")},
    },
    "PAYMENT_PIX_EXPIRES_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(message="Expira em")},
    },
    "PAYMENT_CONFIRMED": {
        WILDCARD: {
            AUDIENCE_RETURNING: CopyEntry(
                title="Pagamento recebido",
                message="Começamos a preparar agora.",
            ),
            AUDIENCE_VIP: CopyEntry(
                title="Pagamento recebido",
                message="Como sempre, começamos a preparar agora.",
            ),
            WILDCARD: CopyEntry(
                title="Pagamento recebido",
                message="Começamos a preparar seu pedido agora.",
            ),
        },
    },

    # ── Tracking / yoin ───────────────────────────────────────────
    "TRACKING_DELIVERED_YOIN": {
        WILDCARD: {WILDCARD: CopyEntry(message="Bom apetite. Até a próxima.")},
    },
    "TRACKING_TOMORROW_HOOK": {
        MOMENT_FECHANDO: {WILDCARD: CopyEntry(message="Fornada fresca amanhã.")},
        MOMENT_FECHADO: {WILDCARD: CopyEntry(message="Fornada fresca amanhã.")},
    },

    # ── Auth ──────────────────────────────────────────────────────
    "LOGIN_WELCOME_BACK": {
        WILDCARD: {WILDCARD: CopyEntry(message="Pronto. Você está entrando.")},
    },
    "LOGOUT_FAREWELL": {
        WILDCARD: {WILDCARD: CopyEntry(message="Até logo.")},
    },
    "LOGIN_PHONE_HEADING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Entre com seu telefone")},
    },
    "LOGIN_PHONE_SUBTITLE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Enviamos um código pelo WhatsApp. Sem senha.")},
    },
    "LOGIN_PHONE_CTA_WA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Receber código no WhatsApp")},
    },
    "LOGIN_PHONE_CTA_SMS": {
        WILDCARD: {WILDCARD: CopyEntry(title="Receber por SMS")},
    },
    "LOGIN_CODE_HEADING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Informe o código")},
    },
    "LOGIN_NAME_HEADING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Como podemos te chamar?")},
    },
    "LOGIN_NAME_SUBTITLE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Pode ser seu primeiro nome ou um apelido. O que for mais natural.")},
    },
    "LOGIN_NAME_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Continuar")},
    },
    "DEVICE_TRUST_PROMPT": {
        WILDCARD: {WILDCARD: CopyEntry(title="Salvar este aparelho?", message="Use só em um aparelho seu. Por 30 dias, você entra sem código.")},
    },
    "DEVICE_TRUST_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Salvar por 30 dias")},
    },
    "DEVICE_TRUST_SKIP_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Agora não")},
    },
    "DEVICE_TRUST_SAVED": {
        WILDCARD: {WILDCARD: CopyEntry(message="Dispositivo salvo por 30 dias.")},
    },
    "DEVICE_TRUST_GREETING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Bem-vindo de volta")},
    },

    # ── History / account empty states ────────────────────────────
    "HISTORY_EMPTY": {
        WILDCARD: {
            AUDIENCE_ANON: CopyEntry(
                title="Nenhum pedido ainda",
                message="Entre para começar.",
            ),
            WILDCARD: CopyEntry(
                title="Primeiro pedido?",
                message="Conheça nosso cardápio.",
            ),
        },
    },
    "ADDRESSES_EMPTY": {
        WILDCARD: {WILDCARD: CopyEntry(message="Nenhum endereço cadastrado.")},
    },
    "LOYALTY_UNAVAILABLE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Programa de fidelidade não disponível.")},
    },

    # ── Kintsugi ──────────────────────────────────────────────────
    # ── Rating ────────────────────────────────────────────────────
    "TRACKING_RATE_PROMPT": {
        WILDCARD: {WILDCARD: CopyEntry(title="Como foi?", message="Sua opinião nos ajuda a melhorar.")},
    },
    "TRACKING_RATE_THANKS": {
        WILDCARD: {WILDCARD: CopyEntry(title="Obrigado!", message="Valorizamos muito seu retorno.")},
    },

    # ── Status banners ────────────────────────────────────────────
    "URGENCY_BANNER_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Últimos pedidos. Fechamos em breve")},
    },
    "BIRTHDAY_BANNER_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Feliz aniversário!")},
    },
    "BIRTHDAY_BANNER_SUB": {
        WILDCARD: {WILDCARD: CopyEntry(message="Que o seu dia seja especial. Aqui está tudo pronto para você.")},
    },
    "BIRTHDAY_HERO_HEADING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Feliz aniversário")},
    },
    "BIRTHDAY_HERO_SUB": {
        WILDCARD: {WILDCARD: CopyEntry(message="Seu desconto especial de aniversário já está ativo.")},
    },
    "CLOSING_AWARENESS_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(message="Últimos pedidos. Fechamos em")},
    },
    "CLOSING_AWARENESS_SUFFIX": {
        WILDCARD: {WILDCARD: CopyEntry(message="minutos")},
    },
    "CLOSING_AWARENESS_OLD_D1_ALERT": {
        WILDCARD: {WILDCARD: CopyEntry(message='Atenção: há estoque D-1 com mais de 1 dia na posição "ontem".')},
    },
    "SHOP_STATUS_OPEN": {
        WILDCARD: {WILDCARD: CopyEntry(message="Aberto agora")},
    },
    "SHOP_STATUS_OPEN_UNTIL": {
        WILDCARD: {WILDCARD: CopyEntry(message="Aberto até")},
    },
    "SHOP_STATUS_OPEN_CLOSING_SOON": {
        WILDCARD: {WILDCARD: CopyEntry(message="Aberto. Fecha em")},
    },
    "SHOP_STATUS_CLOSED": {
        WILDCARD: {WILDCARD: CopyEntry(message="Fechado")},
    },
    "SHOP_STATUS_CLOSED_OPENS_AT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Fechado. Abre às")},
    },

    # ── Kintsugi ──────────────────────────────────────────────────
    "KINTSUGI_ITEM_REMOVED": {
        WILDCARD: {WILDCARD: CopyEntry(title="Removido.")},
    },
    "KINTSUGI_CEP_NOT_FOUND": {
        WILDCARD: {WILDCARD: CopyEntry(message="Não encontrei esse CEP. Quer digitar o endereço?")},
    },
    "KINTSUGI_CANCEL_REFUSED": {
        WILDCARD: {WILDCARD: CopyEntry(message="Seu pedido já está sendo preparado. Fale com a gente para ajustar.")},
    },
    "KINTSUGI_RATE_LIMITED": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                title="Muitas tentativas",
                message="Tente novamente em alguns minutos ou fale com a gente pelo WhatsApp.",
            ),
        },
    },
    "KINTSUGI_SHORTAGE_GENERIC": {
        WILDCARD: {WILDCARD: CopyEntry(title="Ih, o último acabou de sair")},
    },
    "KINTSUGI_SHORTAGE_SUBSTITUTES_INTRO": {
        WILDCARD: {WILDCARD: CopyEntry(message="Que tal um destes no lugar?")},
    },
    "KINTSUGI_PLANNED_OFFER": {
        WILDCARD: {WILDCARD: CopyEntry(title="A caminho", message="O próximo lote sai em breve. Quer pré-reservar?")},
    },
    "KINTSUGI_PAUSED_COPY": {
        WILDCARD: {WILDCARD: CopyEntry(title="Voltamos em breve!", message="Esse item está temporariamente fora do cardápio.")},
    },
}


# ── Resolver ───────────────────────────────────────────────────────────

_DB_CACHE: dict[str, dict[tuple[str, str], CopyEntry]] | None = None


def _load_db_cache() -> dict[str, dict[tuple[str, str], CopyEntry]]:
    """Load all active DB overrides into memory. Lazily built, invalidated on save."""
    global _DB_CACHE
    if _DB_CACHE is not None:
        return _DB_CACHE

    cache: dict[str, dict[tuple[str, str], CopyEntry]] = {}
    try:
        from shopman.shop.models.omotenashi_copy import OmotenashiCopy
        for row in OmotenashiCopy.objects.filter(active=True).only(
            "key", "moment", "audience", "title", "message"
        ):
            cache.setdefault(row.key, {})[(row.moment, row.audience)] = CopyEntry(
                title=row.title or "",
                message=row.message or "",
            )
    except Exception:
        # Model not migrated yet, or DB not reachable — fall back to defaults.
        logger.debug("omotenashi.copy: DB cache load failed, using defaults", exc_info=True)

    _DB_CACHE = cache
    return cache


def invalidate_cache() -> None:
    """Invalidate the in-process DB cache. Hooked on model save/delete."""
    global _DB_CACHE
    _DB_CACHE = None


def resolve_copy(
    key: str,
    *,
    moment: str,
    audience: str = AUDIENCE_ANON,
) -> CopyEntry:
    """Resolve a copy entry with cascade: DB → defaults, specific → generic.

    Order of precedence:
      1. DB: (key, moment, audience)
      2. DB: (key, moment, *)
      3. DB: (key, *, *)
      4. Code: OMOTENASHI_DEFAULTS[key][moment][audience]
      5. Code: OMOTENASHI_DEFAULTS[key][moment][*]
      6. Code: OMOTENASHI_DEFAULTS[key][*][*]

    Returns an empty CopyEntry as last resort — never raises.
    """
    db = _load_db_cache().get(key, {})
    for m in (moment, WILDCARD):
        for a in (audience, WILDCARD):
            entry = db.get((m, a))
            if entry:
                return entry

    defaults = OMOTENASHI_DEFAULTS.get(key, {})
    for m in (moment, WILDCARD):
        by_audience = defaults.get(m, {})
        for a in (audience, WILDCARD):
            entry = by_audience.get(a)
            if entry:
                return entry

    return CopyEntry()


# ── Introspection (useful for admin preview and tests) ─────────────────


def all_keys() -> Iterable[str]:
    return OMOTENASHI_DEFAULTS.keys()


def default_for(key: str, moment: str = WILDCARD, audience: str = WILDCARD) -> CopyEntry:
    """Return the code-level default for (key, moment, audience). No DB lookup."""
    by_moment = OMOTENASHI_DEFAULTS.get(key, {})
    for m in (moment, WILDCARD):
        by_audience = by_moment.get(m, {})
        for a in (audience, WILDCARD):
            entry = by_audience.get(a)
            if entry:
                return entry
    return CopyEntry()


MOMENT_CHOICES = [(WILDCARD, "— qualquer —")] + [(m, m) for m in ALL_MOMENTS]
AUDIENCE_CHOICES = [(WILDCARD, "— qualquer —")] + [
    (AUDIENCE_ANON, "anônima"),
    (AUDIENCE_NEW, "nova"),
    (AUDIENCE_RETURNING, "recorrente"),
    (AUDIENCE_VIP, "VIP"),
]
