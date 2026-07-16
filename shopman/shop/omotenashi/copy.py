"""Omotenashi copy — single registry of user-facing interface strings.

This module holds the **defaults** (in code). Operators can override any entry
via the admin-backed `OmotenashiCopy` model; the resolver cascades from the
most specific (key + moment + audience) to the code-level default and always
returns a `CopyEntry`.

Keys follow UPPER_SNAKE_CASE; one key ⇒ one UX moment. A moment of "*" means
"same copy in every moment"; an audience of "*" means "same copy for anyone".

See docs/omotenashi.md and docs/plans/completed/OMOTENASHI-PLAN.md.
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
                title="Sacola vazia",
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

    # ── Checkout microcopy ────────────────────────────────────────
    "CHECKOUT_SWITCH_ACCOUNT_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Trocar conta?")},
    },
    "CHECKOUT_SWITCH_ACCOUNT_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Você vai sair desta conta para entrar com outro telefone. Sua sacola continua guardada.")},
    },
    "CHECKOUT_SWITCH_ACCOUNT_KEEP_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Manter conta")},
    },
    "CHECKOUT_SWITCH_ACCOUNT_CONFIRM_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Trocar conta")},
    },
    "CHECKOUT_WHEN_REQUIRED": {
        WILDCARD: {WILDCARD: CopyEntry(message="Escolha data e horário para seguir.")},
    },
    "CHECKOUT_LOYALTY_SAVINGS_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(message="Economize até")},
    },
    "CHECKOUT_CONFIRM_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Enviar pedido")},
    },
    # ``{name}`` / ``{price}`` interpolated by the checkout presentation.
    "CHECKOUT_REPRICING_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="O preço de {name} mudou para {price}. Deseja continuar?")},
    },
    # ``{name}`` / ``{qty}`` interpolated; ``{qty}`` is the available count.
    "CHECKOUT_STOCK_LIMITED": {
        WILDCARD: {WILDCARD: CopyEntry(message="{name}: disponível {qty} unidade(s) no momento.")},
    },
    "CHECKOUT_STOCK_SOLD_OUT": {
        WILDCARD: {WILDCARD: CopyEntry(message="{name} está esgotado no momento.")},
    },

    # ── Cart microcopy ────────────────────────────────────────────
    # Discount-line labels for the rule-driven pricing modifiers. Generic by
    # function; a deployment overrides with its brand wording (e.g. "D-1",
    # "Hora da Xepa") via an OmotenashiCopy row.
    "CART_DISCOUNT_LABEL_AVAILABILITY": {
        WILDCARD: {WILDCARD: CopyEntry(title="Liquidação")},
    },
    "CART_DISCOUNT_LABEL_TIME_WINDOW": {
        WILDCARD: {WILDCARD: CopyEntry(title="Happy Hour")},
    },
    "CART_UNAVAILABLE_BANNER": {
        WILDCARD: {WILDCARD: CopyEntry(message="O estoque de alguns itens mudou. Veja as opções em cada item abaixo.")},
    },
    # Aviso da linha em LISTA DE ESPERA na sacola: orienta o cliente a enviar o
    # pedido para entrar na fila com prioridade (decisão Pablo 2026-07-14). O
    # "avisamos quando ficar pronto" migrou para a revisão do pedido.
    "CART_WAITLIST_NOTICE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Envie o pedido para garantir a sua prioridade.")},
    },
    # Data prevista da fornada na linha em lista de espera. ``{date}`` vira
    # "hoje" / "amanhã" / "sábado, 19/07" na presentation da sacola.
    "CART_WAITLIST_PLANNED_DATE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Previsto para {date}")},
    },
    # Motivos do botão de checkout desabilitado — antes hardcoded na presentation,
    # agora no registro para o operador reescrever como qualquer outra microcopy.
    "CART_CHECKOUT_BLOCK_EMPTY": {
        WILDCARD: {WILDCARD: CopyEntry(message="Sacola vazia.")},
    },
    "CART_CHECKOUT_BLOCK_UNAVAILABLE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Revise itens indisponíveis antes de finalizar.")},
    },
    "CART_CHECKOUT_BLOCK_MIN_ORDER": {
        WILDCARD: {WILDCARD: CopyEntry(message="Pedido mínimo não atingido.")},
    },
    "CART_CHECKOUT_BLOCK_CHANNEL": {
        WILDCARD: {WILDCARD: CopyEntry(message="Checkout indisponível para este canal.")},
    },
    # "Me avise quando disponível" — CTA de reposição no erro de esgotado do carrinho
    # (reaproveita o fluxo de StockAlertSubscribe já existente).
    "SOLDOUT_NOTIFY_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Me avise quando disponível")},
    },
    # Checkout recusado por dia/horário fechado: enquadra a encomenda como caminho
    # adiante, em vez de só "escolha outra data".
    "CHECKOUT_CLOSED_PREORDER_HINT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Você pode encomendar para o próximo dia disponível.")},
    },
    "MIN_ORDER_WARNING": {
        WILDCARD: {WILDCARD: CopyEntry(message="Adicionar mais itens")},
    },
    "MIN_ORDER_WARNING_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(message="Faltam")},
    },
    "MIN_ORDER_WARNING_MIDDLE": {
        WILDCARD: {WILDCARD: CopyEntry(message="para o pedido mínimo de")},
    },

    # ── Menu empty state ──────────────────────────────────────────
    # Catálogo sem itens no canal (loja em preparo). Copy configurável no
    # payload do menu; o Vue mantém fallback só durante o carregamento.
    "CATALOG_EMPTY": {
        WILDCARD: {WILDCARD: CopyEntry(
            title="Cardápio em preparo",
            message="Estamos preparando as novidades. Volte em breve!",
        )},
    },
    # Busca client-side sem resultado — orienta a ajustar/limpar em vez de um beco.
    "SEARCH_EMPTY": {
        WILDCARD: {WILDCARD: CopyEntry(
            title="Nada por aqui",
            message="Não encontramos esse item. Tente outro termo ou veja o cardápio completo.",
        )},
    },
    "SEARCH_EMPTY_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Ver cardápio completo")},
    },

    # ── Home sections ─────────────────────────────────────────────
    "HOME_HERO_ORDER_TITLE_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(title="Peça. Acompanhe.")},
    },
    "HOME_HERO_ORDER_TITLE_SUFFIX": {
        WILDCARD: {WILDCARD: CopyEntry(title="Aproveite.")},
    },
    "HOME_HERO_ORDER_SUBTITLE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Retire na loja ou receba em casa.")},
    },
    "HOME_HERO_REORDER_TITLE_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(title="Quer repetir seu")},
    },
    "HOME_HERO_REORDER_TITLE_SUFFIX": {
        WILDCARD: {WILDCARD: CopyEntry(title="último pedido")},
    },
    "HOME_HERO_REORDER_SUBTITLE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Com um toque, seu favorito volta à sacola.")},
    },
    "HOME_HERO_HANDMADE_SUBTITLE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Do forno para a sua mesa.")},
    },
    "HOME_HERO_HANDMADE_TITLE_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(title="Feito à mão,")},
    },
    "HOME_HERO_HANDMADE_TITLE_SUFFIX": {
        WILDCARD: {WILDCARD: CopyEntry(title="todo dia")},
    },
    "HOME_MENU_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Ver Cardápio")},
    },
    "HOME_BIRTHDAY_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Ver minha oferta de aniversário")},
    },
    "HOME_FULL_MENU_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Ver cardápio completo")},
    },
    "HOME_AVAILABILITY_HEADING": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                title="Direto do forno",
                message="Disponibilidade em tempo real",
            ),
        },
    },
    "HOME_HOW_IT_WORKS_HEADING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Como Funciona")},
    },
    "HOME_HOW_ONLINE_HEADING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Peça online")},
    },
    "HOME_HOW_STORE_HEADING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Visite a loja")},
    },
    "HOME_HOW_STEP_CHOOSE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Escolha")},
    },
    "HOME_HOW_STEP_PAY": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pague")},
    },
    "HOME_HOW_STEP_FULFILL": {
        WILDCARD: {WILDCARD: CopyEntry(title="Retire ou Receba")},
    },
    "HOME_HOW_SELF_SERVICE_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pães no autosserviço")},
    },
    "HOME_HOW_COUNTER_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(title="Cafés e doces no balcão")},
    },
    "HOME_HOW_HOURS_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(title="Horários")},
    },
    "HOME_HOW_HOURS_EMPTY": {
        WILDCARD: {WILDCARD: CopyEntry(message="Consulte nossos horários")},
    },
    "HOME_TOMORROW_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(title="Amanhã")},
    },
    "HOME_WHATSAPP_CTA_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(title="Falar pelo WhatsApp")},
    },
    "HOW_IT_WORKS_META_DESCRIPTION": {
        WILDCARD: {WILDCARD: CopyEntry(message="Saiba como fazer seu pedido. Pedido online ou visita na loja.")},
    },
    "HOW_IT_WORKS_INTRO": {
        WILDCARD: {WILDCARD: CopyEntry(message="Do pedido à retirada, sem complicação.")},
    },
    "HOW_ONLINE_CHOOSE_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Navegue pelo cardápio e adicione à sacola. A disponibilidade aparece em tempo real.")},
    },
    "HOW_ONLINE_PAY_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="PIX rápido e seguro, com confirmação automática assim que o pagamento chega.")},
    },
    "HOW_ONLINE_TRACK_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Acompanhe o preparo em tempo real. Retire na loja ou receba em casa.")},
    },
    "HOW_STORE_SELF_SERVICE_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Escolha direto da prateleira. Pese, embale e leve ao caixa.")},
    },
    "HOW_STORE_COUNTER_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Peça ao atendente. Preparamos na hora.")},
    },
    "HOW_PREORDER_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Pedidos para o dia seguinte até as 18h. Encomendas com até 7 dias de antecedência.")},
    },
    "HOW_TRACKING_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Use seu telefone para consultar o status dos pedidos a qualquer momento.")},
    },
    "HOW_DELIVERY_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(message="Entregamos em")},
    },
    "HOW_DELIVERY_SUFFIX": {
        WILDCARD: {WILDCARD: CopyEntry(message="Retirada na loja no horário de funcionamento.")},
    },
    "HOW_QUALITY_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Produção artesanal com fermentação natural. Ingredientes selecionados.")},
    },
    "HOME_WHATSAPP_CTA": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                title="Dúvidas? Ou algum pedido especial?",
                message="Respondemos rápido, de pessoa para pessoa.",
            ),
        },
    },

    # ── Tracking tail ─────────────────────────────────────────────
    "TRACKING_PAGE_META_DESCRIPTION": {
        WILDCARD: {WILDCARD: CopyEntry(message="Acompanhe seu pedido")},
    },
    "TRACKING_PAGE_KICKER": {
        WILDCARD: {WILDCARD: CopyEntry(title="Acompanhamento")},
    },
    "TRACKING_ORDER_REF_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pedido")},
    },
    "TRACKING_REORDER_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Repetir pedido")},
    },
    "TRACKING_MENU_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Ver cardápio")},
    },
    "TRACKING_SUPPORT_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Ajuda")},
    },
    "TRACKING_ACTION_CANCEL_ORDER": {
        WILDCARD: {WILDCARD: CopyEntry(title="Cancelar pedido")},
    },
    "TRACKING_ACTION_RATE_ORDER": {
        WILDCARD: {WILDCARD: CopyEntry(title="Avaliar pedido")},
    },
    "TRACKING_ACTION_MOCK_CONFIRM_PAYMENT": {
        WILDCARD: {WILDCARD: CopyEntry(title="Capturar pagamento teste")},
    },
    "TRACKING_PROGRESS_HEADING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Etapas do pedido")},
    },
    "TRACKING_LIVE_BADGE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Ao vivo")},
    },
    "TRACKING_POLLING_BADGE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Atualização periódica")},
    },
    "TRACKING_FINISHED_BADGE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Finalizado")},
    },
    "TRACKING_TOTAL_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(title="Total")},
    },
    "TRACKING_DELIVERY_FEE_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(title="Entrega")},
    },
    "TRACKING_PROMISE_FALLBACK_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Acompanhando atualizações do pedido.")},
    },
    "TRACKING_PAYMENT_CONFIRMED_NOTICE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Pagamento confirmado. Acompanhe o próximo passo nesta página.")},
    },
    "TRACKING_RETRY_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Tentar novamente")},
    },
    "TRACKING_NOT_FOUND_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pedido não encontrado")},
    },
    "TRACKING_NOT_FOUND_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Confira o link do pedido ou fale com a equipe.")},
    },
    "TRACKING_RATE_LIMIT_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Atualização pausada por um instante")},
    },
    "TRACKING_CANCEL_SUCCESS_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pedido cancelado")},
    },
    "TRACKING_CANCEL_SUCCESS_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Recebemos o cancelamento. Acompanhe o status nesta página.")},
    },
    "TRACKING_CANCEL_FAILED_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Não foi possível cancelar este pedido agora.")},
    },
    "TRACKING_CANCEL_CONFIRM_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Cancelar pedido")},
    },
    "TRACKING_CANCEL_WARNING_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Essa ação altera o pedido em andamento")},
    },
    "TRACKING_CANCEL_WARNING_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="O cancelamento só é permitido enquanto o pagamento não foi capturado e a loja ainda permite reversão.")},
    },
    "TRACKING_CANCEL_CONFIRM_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Confirme apenas se não quiser mais seguir com este pedido.")},
    },
    "TRACKING_CANCEL_ACK_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(title="Entendo que o pedido será cancelado e deixará de ser preparado.")},
    },
    "TRACKING_CANCEL_KEEP_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Manter pedido")},
    },
    "TRACKING_CANCEL_CONFIRM_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Confirmar cancelamento")},
    },
    "TRACKING_MOCK_PAYMENT_SUCCESS_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pagamento teste capturado")},
    },
    "TRACKING_MOCK_PAYMENT_SUCCESS_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Atualizamos o pedido com o estado financeiro simulado.")},
    },
    "TRACKING_MOCK_PAYMENT_FAILED_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Não foi possível capturar o pagamento teste")},
    },
    "TRACKING_MOCK_PAYMENT_FAILED_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Atualize o pedido e tente novamente.")},
    },
    "TRACKING_RATING_SUCCESS_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Avaliação registrada")},
    },
    "TRACKING_RATING_FAILED_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Não foi possível registrar a avaliação agora.")},
    },
    "TRACKING_RATING_COMMENT_PLACEHOLDER": {
        WILDCARD: {WILDCARD: CopyEntry(title="Comentário opcional")},
    },
    "TRACKING_RATING_COMMENT_ARIA_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(title="Comentário da avaliação")},
    },
    "TRACKING_RATING_SUBMIT_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Enviar avaliação")},
    },
    "TRACKING_SUPPORT_WHATSAPP_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Oi! Posso ajudar com o pedido {order_ref}?")},
    },
    # Rótulo enxuto do countdown quando o prazo é a loja conferir disponibilidade
    # (deadline_kind="availability"). Consolidou o antigo par prefix/suffix num rótulo.
    "TRACKING_AUTO_CONFIRM_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(message="A loja está conferindo a disponibilidade:")},
    },
    "TRACKING_STATUS_PAYMENT_PENDING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Aguardando pagamento")},
    },
    "TRACKING_STATUS_PAYMENT_EXPIRED": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pagamento expirado")},
    },
    "TRACKING_STATUS_WAITING_STORE_CONFIRMATION": {
        WILDCARD: {WILDCARD: CopyEntry(title="Aguardando confirmação")},
    },
    "TRACKING_STATUS_CARD_AUTHORIZED": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pagamento autorizado")},
    },
    "TRACKING_STATUS_READY_DELIVERY": {
        WILDCARD: {WILDCARD: CopyEntry(title="Aguardando entregador")},
    },
    "TRACKING_STATUS_READY_PICKUP": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pronto para retirada")},
    },
    # Encomenda agendada (WP-D): pedido confirmado com data futura, entre a
    # confirmação e o dia combinado. ``{when}`` vira "sábado, 19/07 · A partir
    # das 09h" na presentation.
    "TRACKING_STATUS_PREORDER_SCHEDULED": {
        WILDCARD: {WILDCARD: CopyEntry(title="Encomenda confirmada")},
    },
    "TRACKING_PROMISE_PREORDER_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Encomenda confirmada")},
    },
    "TRACKING_PROMISE_PREORDER_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Seu pedido está garantido para {when}. Preparamos tudo fresco no dia.")},
    },
    "TRACKING_PROMISE_PREORDER_MESSAGE_NO_DATE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Seu pedido está garantido. Preparamos tudo fresco no dia combinado.")},
    },
    "TRACKING_PROMISE_PREORDER_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(message="No dia, avisamos você quando o preparo começar.")},
    },
    # Confirmação de encomenda: prefixo do combinado ("Pedido para" + "sábado,
    # 19/07 · A partir das 09h") no lugar do ETA de preparo.
    "CONFIRMATION_PREORDER_WHEN_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(message="Pedido para")},
    },
    "TRACKING_STEP_RECEIVED": {
        WILDCARD: {WILDCARD: CopyEntry(title="Recebemos seu pedido")},
    },
    "TRACKING_STEP_AVAILABILITY_CONFIRMED": {
        WILDCARD: {WILDCARD: CopyEntry(title="Disponibilidade confirmada")},
    },
    "TRACKING_STEP_PAYMENT_CONFIRMED": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pagamento confirmado")},
    },
    "TRACKING_STEP_PREPARING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Preparando seu pedido")},
    },
    "TRACKING_STEP_READY_PICKUP": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pronto para retirada")},
    },
    "TRACKING_STEP_READY_DELIVERY": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pedido pronto")},
    },
    "TRACKING_STEP_READY_GENERIC": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pedido pronto")},
    },
    "TRACKING_DELIVERY_WAITING_COURIER": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                title="Pedido pronto",
                message="Está tudo pronto! Logo sai para entrega. Avisamos você assim que sair.",
            ),
        },
    },
    "TRACKING_STEP_DISPATCHED": {
        WILDCARD: {WILDCARD: CopyEntry(title="Saiu para entrega")},
    },
    "TRACKING_STEP_DELIVERED": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pedido entregue")},
    },
    "TRACKING_STEP_COMPLETED": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pedido concluído")},
    },
    "TRACKING_STEP_CANCELLED": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pedido cancelado")},
    },
    "TRACKING_PAYMENT_PENDING": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                title="Recebemos seu pedido",
                message="Estamos só aguardando a confirmação do pagamento.",
            ),
        },
    },
    "TRACKING_PAYMENT_REQUESTED": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                title="Falta só o pagamento",
                message="Confirme o PIX e já começamos a preparar.",
            ),
        },
    },
    "TRACKING_PAYMENT_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pagar agora")},
    },
    "TRACKING_PAYMENT_TIME_LEFT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Tempo para pagamento:")},
    },
    "TRACKING_PAYMENT_EXPIRED": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                title="O prazo do pagamento acabou",
                message="Não recebemos a confirmação a tempo, então cancelamos o pedido e liberamos sua reserva. Se quiser, é só repetir o pedido.",
            ),
        },
    },
    "TRACKING_ACTION_READY_PICKUP": {
        WILDCARD: {WILDCARD: CopyEntry(title="Retirar pedido")},
    },
    "TRACKING_CARD_AUTHORIZED": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                title="Pagamento autorizado",
                message="Pronto! Não precisa fazer mais nada agora.",
            ),
        },
    },
    "TRACKING_PROMISE_UPDATED_NOW": {
        WILDCARD: {WILDCARD: CopyEntry(title="Atualizado agora")},
    },
    "TRACKING_PROMISE_LABEL_DEADLINE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Prazo:")},
    },
    "TRACKING_PROMISE_LABEL_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(title="Próximo passo:")},
    },
    "TRACKING_PROMISE_LABEL_RECOVERY": {
        WILDCARD: {WILDCARD: CopyEntry(title="Se o tempo acabar:")},
    },
    "TRACKING_PROMISE_LABEL_ACTIVE_NOTIFICATION": {
        WILDCARD: {WILDCARD: CopyEntry(title="Aviso:")},
    },
    # Affordância enxuta quando o dado está velho (um poll falhou): vira um "Atualizar"
    # tocável ao lado do carimbo de frescor, no lugar do técnico "reconectando…".
    "TRACKING_PROMISE_STALE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Atualizar")},
    },
    "TRACKING_PROMISE_PAYMENT_EXPIRED_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Você pode refazer o pedido quando quiser.")},
    },
    "TRACKING_PROMISE_CARD_AUTHORIZED_NEXT_NEW": {
        WILDCARD: {WILDCARD: CopyEntry(message="O estabelecimento vai conferir a disponibilidade.")},
    },
    "TRACKING_PROMISE_CARD_AUTHORIZED_NEXT_CONFIRMED": {
        WILDCARD: {WILDCARD: CopyEntry(message="Assim que a confirmação financeira terminar, seguimos com o pedido.")},
    },
    "TRACKING_PROMISE_PAYMENT_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Depois do pagamento, seguimos com o pedido.")},
    },
    "TRACKING_PROMISE_PAYMENT_RECOVERY": {
        WILDCARD: {WILDCARD: CopyEntry(message="Liberamos sua reserva e o pedido é cancelado.")},
    },
    "TRACKING_PROMISE_PAYMENT_ACTIVE_NOTIFICATION": {
        WILDCARD: {WILDCARD: CopyEntry(message="Também avisamos por um canal ativo habilitado, porque o PIX depende da sua ação.")},
    },
    "TRACKING_PROMISE_AVAILABILITY_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Estamos conferindo a disponibilidade dos itens.")},
    },
    "TRACKING_PROMISE_AVAILABILITY_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Se a disponibilidade for confirmada, liberamos o pagamento e avisamos você.")},
    },
    "TRACKING_PROMISE_AVAILABILITY_RECOVERY": {
        WILDCARD: {WILDCARD: CopyEntry(message="Se o estabelecimento não confirmar a tempo, atualizaremos o pedido aqui.")},
    },
    "TRACKING_PROMISE_CLOSED_HOURS_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Estamos fechados agora. Conferimos a disponibilidade assim que abrirmos.")},
    },
    "TRACKING_PROMISE_CLOSED_HOURS_MESSAGE_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Estamos fechados agora. Conferimos a disponibilidade quando abrirmos, {next}.")},
    },
    "TRACKING_PROMISE_CLOSED_HOURS_NEXT_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(message="Próxima abertura:")},
    },
    "TRACKING_PROMISE_CLOSED_HOURS_NEXT_UNKNOWN": {
        WILDCARD: {WILDCARD: CopyEntry(message="Atualizaremos o pedido assim que o próximo expediente estiver definido.")},
    },
    "TRACKING_PROMISE_PAYMENT_CONFIRMED_NEXT_NEW": {
        WILDCARD: {WILDCARD: CopyEntry(message="O estabelecimento está conferindo a disponibilidade.")},
    },
    "TRACKING_PROMISE_PAYMENT_CONFIRMED_NEXT_CONFIRMED": {
        WILDCARD: {WILDCARD: CopyEntry(message="Vamos começar o preparo do seu pedido.")},
    },
    "TRACKING_PROMISE_PREPARING_NEXT_PICKUP": {
        WILDCARD: {WILDCARD: CopyEntry(message="Quando estiver pronto, avisaremos você.")},
    },
    "TRACKING_PROMISE_PREPARING_NEXT_DELIVERY": {
        WILDCARD: {WILDCARD: CopyEntry(message="Quando estiver pronto, solicitaremos a coleta para entrega.")},
    },
    "TRACKING_PROMISE_READY_DELIVERY_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Assim que sair para entrega, avisamos você.")},
    },
    "TRACKING_PROMISE_READY_PICKUP_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Retire no estabelecimento quando puder.")},
    },
    "TRACKING_PROMISE_READY_PICKUP_ACTIVE_NOTIFICATION": {
        WILDCARD: {WILDCARD: CopyEntry(message="Avisamos você que o pedido está pronto para retirada.")},
    },
    "TRACKING_PROMISE_READY_DELIVERY_ACTIVE_NOTIFICATION": {
        WILDCARD: {WILDCARD: CopyEntry(message="Avisaremos você quando o pedido sair para entrega.")},
    },
    "TRACKING_PROMISE_DISPATCHED_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Seu pedido está a caminho.")},
    },
    "TRACKING_PROMISE_DISPATCHED_MESSAGE_ETA": {
        WILDCARD: {WILDCARD: CopyEntry(message="Seu pedido está a caminho. Deve chegar por volta das {eta}.")},
    },
    "TRACKING_ACTION_CONFIRM_RECEIVED": {
        WILDCARD: {WILDCARD: CopyEntry(title="Recebi meu pedido")},
    },
    "TRACKING_PROMISE_DISPATCHED_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Quando for entregue, atualizaremos o pedido.")},
    },
    "TRACKING_PROMISE_DELIVERED_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(message="O pedido será concluído em seguida.")},
    },
    "TRACKING_PROMISE_CANCELLED_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Você pode refazer o pedido quando quiser.")},
    },
    "TRACKING_PROMISE_ACTIVE_UPDATE_NOTIFICATION": {
        WILDCARD: {WILDCARD: CopyEntry(message="Avisamos você a cada atualização. Pode fechar a tela sem preocupação.")},
    },
    "TRACKING_PROMISE_RECEIVED_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(message="O estabelecimento vai conferir a disponibilidade.")},
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
    "TRACKING_PICKUP_DIRECTIONS_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Como chegar")},
    },
    "TRACKING_TRACK_SHIPMENT": {
        WILDCARD: {WILDCARD: CopyEntry(title="Rastrear envio")},
    },
    "TRACKING_TRACK_SHIPMENT_WITH_CARRIER": {
        WILDCARD: {WILDCARD: CopyEntry(title="Acompanhar via {carrier}")},
    },
    "TRACKING_CANCEL_HEADING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Cancelar pedido?")},
    },
    "TRACKING_CANCEL_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Cancelar pedido")},
    },
    "TRACKING_CANCEL_CONFIRM": {
        WILDCARD: {WILDCARD: CopyEntry(message="Vamos avisar a loja e atualizar o acompanhamento.")},
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
    "CONFIRMATION_ETA_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(message="Começamos a preparar")},
    },

    # ── Payment ───────────────────────────────────────────────────
    "PAYMENT_PAGE_META_DESCRIPTION": {
        WILDCARD: {WILDCARD: CopyEntry(message="Pague seu pedido para seguirmos com o preparo")},
    },
    "PAYMENT_ORDER_REF_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pedido")},
    },
    "PAYMENT_TOTAL_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(title="Total")},
    },
    "PAYMENT_DEV_CONFIRM_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="[DEV] Simular pagamento confirmado")},
    },
    "PAYMENT_RETRY_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Tentar novamente")},
    },
    "PAYMENT_PROMISE_PIX_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pagamento Pix")},
    },
    "PAYMENT_PROMISE_PIX_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="A disponibilidade foi confirmada. Use o Pix abaixo para liberar o preparo.")},
    },
    "PAYMENT_PROMISE_PIX_PRECONFIRMATION_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pagamento Pix")},
    },
    "PAYMENT_PROMISE_PIX_PRECONFIRMATION_MESSAGE": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                message="Use o Pix abaixo para registrar o pagamento. O estabelecimento ainda vai conferir a disponibilidade.",
            ),
        },
    },
    "PAYMENT_PROMISE_PIX_PRECONFIRMATION_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Depois do pagamento, acompanhe a confirmação do estabelecimento.")},
    },
    "PAYMENT_PROMISE_PIX_PRECONFIRMATION_RECOVERY": {
        WILDCARD: {WILDCARD: CopyEntry(message="Se o prazo expirar, o pedido será cancelado automaticamente e os itens serão liberados.")},
    },
    "PAYMENT_PROMISE_PIX_ACTION": {
        WILDCARD: {WILDCARD: CopyEntry(title="Use o QR Code ou copia e cola abaixo")},
    },
    "PAYMENT_PROMISE_PIX_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Assim que o banco confirmar, seguimos para o preparo do pedido.")},
    },
    "PAYMENT_PROMISE_PIX_RECOVERY": {
        WILDCARD: {WILDCARD: CopyEntry(message="Se o prazo expirar, o pedido será cancelado automaticamente e os itens serão liberados.")},
    },
    "PAYMENT_PROMISE_PIX_ACTIVE_NOTIFICATION": {
        WILDCARD: {WILDCARD: CopyEntry(message="Quando o pagamento for reconhecido, avisaremos pelos canais ativos da sua conta.")},
    },
    "PAYMENT_PROMISE_CARD_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pagamento seguro com cartão")},
    },
    "PAYMENT_PROMISE_CARD_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="A disponibilidade foi confirmada. Finalize o pagamento no ambiente seguro do cartão.")},
    },
    "PAYMENT_PROMISE_CARD_PRECONFIRMATION_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Autorizar cartão")},
    },
    "PAYMENT_PROMISE_CARD_PRECONFIRMATION_MESSAGE": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                message="Abra o ambiente seguro para autorizar o cartão. O estabelecimento ainda vai conferir a disponibilidade.",
            ),
        },
    },
    "PAYMENT_PROMISE_CARD_PRECONFIRMATION_ACTION": {
        WILDCARD: {WILDCARD: CopyEntry(title="Autorizar cartão")},
    },
    "PAYMENT_PROMISE_CARD_PRECONFIRMATION_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Depois da autorização, acompanhe a confirmação do estabelecimento.")},
    },
    "PAYMENT_PROMISE_CARD_PRECONFIRMATION_RECOVERY": {
        WILDCARD: {WILDCARD: CopyEntry(message="Se o ambiente seguro não abrir, tente novamente ou fale com o estabelecimento.")},
    },
    "PAYMENT_PROMISE_CARD_PRECONFIRMATION_ACTIVE_NOTIFICATION": {
        WILDCARD: {WILDCARD: CopyEntry(message="Avisaremos quando o pagamento ou a confirmação da loja avançar.")},
    },
    "PAYMENT_PROMISE_CARD_AUTHORIZED_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pagamento autorizado.")},
    },
    "PAYMENT_PROMISE_CARD_AUTHORIZED_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Você não precisa fazer nada agora.")},
    },
    "PAYMENT_PROMISE_CARD_AUTHORIZED_NEXT_NEW": {
        WILDCARD: {WILDCARD: CopyEntry(message="O estabelecimento vai conferir a disponibilidade.")},
    },
    "PAYMENT_PROMISE_CARD_AUTHORIZED_NEXT_CONFIRMED": {
        WILDCARD: {WILDCARD: CopyEntry(message="Assim que a confirmação financeira terminar, seguimos com o pedido.")},
    },
    "PAYMENT_PROMISE_CARD_ACTION": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pagar com cartão")},
    },
    "PAYMENT_PROMISE_CARD_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Voltamos para o acompanhamento assim que o pagamento for confirmado.")},
    },
    "PAYMENT_PROMISE_CARD_RECOVERY": {
        WILDCARD: {WILDCARD: CopyEntry(message="Se o ambiente seguro não abrir, tente novamente ou fale com o estabelecimento.")},
    },
    "PAYMENT_PROMISE_CARD_ACTIVE_NOTIFICATION": {
        WILDCARD: {WILDCARD: CopyEntry(message="Se houver confirmação ou falha, avisaremos pelos canais ativos da sua conta.")},
    },
    "PAYMENT_PROMISE_CARD_PENDING_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Preparando ambiente seguro")},
    },
    "PAYMENT_PROMISE_CARD_PENDING_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Estamos preparando o ambiente seguro do cartão.")},
    },
    "PAYMENT_PROMISE_CARD_PENDING_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Quando estiver pronto, o botão de pagamento aparecerá aqui.")},
    },
    "PAYMENT_PROMISE_CARD_PENDING_RECOVERY": {
        WILDCARD: {WILDCARD: CopyEntry(message="Se demorar, atualize a página ou fale com o estabelecimento.")},
    },
    "PAYMENT_PROMISE_ERROR_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Não conseguimos preparar o pagamento")},
    },
    "PAYMENT_PROMISE_ERROR_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Seu pedido continua registrado. Tente gerar o pagamento novamente.")},
    },
    "PAYMENT_PROMISE_ERROR_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Se a tentativa funcionar, mostramos o Pix ou o ambiente seguro do cartão.")},
    },
    "PAYMENT_PROMISE_ERROR_RECOVERY": {
        WILDCARD: {WILDCARD: CopyEntry(message="Se o erro continuar, fale com o estabelecimento para resolvermos sem perder o pedido.")},
    },
    "PAYMENT_PROMISE_PAID_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pagamento reconhecido")},
    },
    "PAYMENT_PROMISE_PAID_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Recebemos a confirmação do pagamento.")},
    },
    "PAYMENT_PROMISE_PAID_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Vamos mostrar o acompanhamento do pedido.")},
    },
    "PAYMENT_PROMISE_CANCELLED_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pedido cancelado")},
    },
    "PAYMENT_PROMISE_CANCELLED_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Este pedido não aceita mais pagamento.")},
    },
    "PAYMENT_PROMISE_CANCELLED_RECOVERY": {
        WILDCARD: {WILDCARD: CopyEntry(message="Confira os detalhes do pedido ou faça um novo pedido quando quiser.")},
    },
    "PAYMENT_PROMISE_EXPIRED_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="O prazo para pagamento expirou")},
    },
    "PAYMENT_PROMISE_EXPIRED_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="O pedido foi automaticamente cancelado e os itens foram liberados.")},
    },
    "PAYMENT_PROMISE_EXPIRED_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Você pode refazer o pedido quando quiser.")},
    },
    "PAYMENT_PROMISE_EXPIRED_RECOVERY": {
        WILDCARD: {WILDCARD: CopyEntry(message="Se precisar de ajuda, fale com o estabelecimento.")},
    },
    "PAYMENT_PROMISE_EXPIRED_ACTIVE_NOTIFICATION": {
        WILDCARD: {WILDCARD: CopyEntry(message="Também avisaremos pelos canais ativos da sua conta.")},
    },
    "PAYMENT_CARD_INTRO": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                message=(
                    "Conclua o pagamento no ambiente seguro do Stripe. "
                    "A confirmação é automática. Volte aqui se quiser acompanhar seu pedido."
                ),
            ),
        },
    },
    "PAYMENT_CARD_SECURITY_NOTE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Pagamento processado por provedor seguro. Nós não recebemos os dados do seu cartão.")},
    },
    "PAYMENT_PIX_INSTRUCTION": {
        WILDCARD: {WILDCARD: CopyEntry(message="Escaneie o QR Code ou copie o código Pix abaixo.")},
    },
    "PAYMENT_PIX_COPY_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(title="Copia e cola PIX")},
    },
    "PAYMENT_PIX_COPY_BTN": {
        WILDCARD: {WILDCARD: CopyEntry(title="Copiar código")},
    },
    "PAYMENT_PIX_COPIED": {
        WILDCARD: {WILDCARD: CopyEntry(title="Código PIX copiado.")},
    },
    "PAYMENT_PIX_EXPIRES_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(message="Tempo para pagar")},
    },
    "PAYMENT_VIEW_ORDER_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Ver pedido")},
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
    "LOGOUT_FAREWELL": {
        WILDCARD: {WILDCARD: CopyEntry(message="Até logo.")},
    },
    "LOGIN_PHONE_HEADING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Vamos entrar?")},
    },
    "LOGIN_PHONE_SUBTITLE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Sem senha, rápido e seguro.")},
    },
    # Vindo do checkout, a sacola é o que importa dizer no subtítulo (uma linha, sem alarde).
    "LOGIN_WA_CART_KEPT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Sua sacola está guardada.")},
    },
    # Lampejo do fluxo: o que vai acontecer ao tocar (você envia, recebe um link, entra).
    "LOGIN_WA_GLIMPSE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Envie a mensagem pronta e receba um link para entrar.")},
    },
    # Fallback manual (bloco "OU"): título com peso de seção + subtítulo (o número do
    # WhatsApp é anexado ao subtítulo na tela).
    "LOGIN_WA_MANUAL_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Quer fazer você mesmo?")},
    },
    "LOGIN_WA_MANUAL_INTRO": {
        WILDCARD: {WILDCARD: CopyEntry(message="Envie o código abaixo diretamente para o nosso WhatsApp")},
    },
    # Handoff do site expirou: entrou logado, mas a sacola não veio (link do WhatsApp venceu).
    # Aviso gentil, com caminho de volta, sem culpar o cliente.
    "LOGIN_HANDOFF_EXPIRED": {
        WILDCARD: {WILDCARD: CopyEntry(message="Você entrou! Sua sacola não veio desta vez porque o link expirou. É só montar de novo.")},
    },
    "LOGIN_PHONE_CTA_WA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Entrar pelo WhatsApp")},
    },
    "LOGIN_PHONE_CTA_SMS": {
        WILDCARD: {WILDCARD: CopyEntry(title="Receber por SMS")},
    },
    "LOGIN_TRUSTED_DEVICE_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Este aparelho já foi confirmado. Se quiser, entre direto.")},
    },
    "LOGIN_TRUSTED_DEVICE_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Entrar sem código")},
    },
    "LOGIN_TRUSTED_OTHER_PHONE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Ou confirme outro telefone abaixo.")},
    },
    "LOGIN_NO_PASSWORD_NOTE": {
        WILDCARD: {WILDCARD: CopyEntry(message="É prático e seguro, e não exige senha.")},
    },
    "LOGIN_TERMS_NOTE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Usamos seu telefone para autenticar a entrada. Seus dados não são compartilhados.")},
    },
    "LOGIN_CHANGE_PHONE_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Trocar telefone")},
    },
    "LOGIN_CODE_HEADING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Informe o código")},
    },
    "LOGIN_CODE_HELP": {
        WILDCARD: {WILDCARD: CopyEntry(message="Você pode colar o código. Ao completar, a confirmação é automática.")},
    },
    "LOGIN_NAME_HEADING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Como quer ser chamado?")},
    },
    "LOGIN_NAME_SUBTITLE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Pode ser só o primeiro nome ou um apelido.")},
    },
    "LOGIN_NAME_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Continuar")},
    },
    "LOGIN_AUTH_CONFIRMED": {
        WILDCARD: {WILDCARD: CopyEntry(title="Bem-vindo de volta", message="Tudo pronto. Levando você para a loja…")},
    },
    "DEVICE_TRUST_REDIRECTING": {
        WILDCARD: {WILDCARD: CopyEntry(message="Dispositivo reconhecido. Entrando automaticamente…")},
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

    # ── History / account empty states ────────────────────────────
    # Vazio da lista de pedidos — 3 estados por filtro (moment "active"/"past" e o
    # "*" padrão para "todos"). A tela recebe a copy do filtro atual no payload e
    # mantém um fallback client-side só para o intervalo de carregamento.
    "HISTORY_EMPTY": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                title="Você ainda não fez pedidos",
                message="Que tal começar? Escolha algo fresquinho no cardápio.",
            ),
        },
        "active": {
            WILDCARD: CopyEntry(
                title="Nenhum pedido em andamento",
                message="Quando você fizer um pedido, ele aparece aqui para você acompanhar de pertinho.",
            ),
        },
        "past": {
            WILDCARD: CopyEntry(
                title="Nenhum pedido finalizado ainda",
                message="Seus pedidos concluídos ficam guardados aqui para você repetir quando quiser.",
            ),
        },
    },
    "ADDRESSES_EMPTY": {
        WILDCARD: {WILDCARD: CopyEntry(
            title="Nenhum endereço salvo",
            message="Adicione um endereço para finalizar a próxima entrega com menos passos.",
        )},
    },
    # Vazio de Favoritos — mesma família de HISTORY_EMPTY/ADDRESSES_EMPTY, para a
    # copy do vazio vir do registro (configurável) e não ficar presa no Vue.
    "FAVORITES_EMPTY": {
        WILDCARD: {WILDCARD: CopyEntry(
            title="Você ainda não salvou favoritos",
            message="Toque no coração de um produto para encontrá-lo aqui na próxima visita.",
        )},
    },
    # CTA do vazio de Favoritos (leva ao cardápio).
    "FAVORITES_EMPTY_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Descobrir o cardápio")},
    },
    "ACCOUNT_GREETING_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(title="Olá")},
    },
    "ACCOUNT_PAGE_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Minha Conta")},
    },
    "ACCOUNT_TRUSTED_DEVICES_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Controle os dispositivos confiáveis e seus dados pessoais.")},
    },
    "ACCOUNT_DELETE_WARNING": {
        WILDCARD: {WILDCARD: CopyEntry(message="Esta ação é irreversível. Seus dados pessoais serão anonimizados conforme a LGPD e você sairá da loja neste dispositivo.")},
    },
    "DEVICE_LIST_EMPTY": {
        WILDCARD: {WILDCARD: CopyEntry(title="Nenhum dispositivo confiável", message="Quando você optar por confiar neste dispositivo no login, ele aparecerá aqui.")},
    },
    "DEVICE_LIST_UNKNOWN": {
        WILDCARD: {WILDCARD: CopyEntry(title="Dispositivo desconhecido")},
    },
    "DEVICE_LIST_CURRENT": {
        WILDCARD: {WILDCARD: CopyEntry(title="Este dispositivo")},
    },
    "DEVICE_LIST_REGISTERED_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(message="Registrado em")},
    },
    "DEVICE_REVOKE_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Remover")},
    },
    "DEVICE_REVOKE_CONFIRM": {
        WILDCARD: {WILDCARD: CopyEntry(message="Remover este dispositivo?")},
    },
    "DEVICE_REVOKE_ALL_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Remover todos os dispositivos")},
    },
    "DEVICE_REVOKE_ALL_CONFIRM": {
        WILDCARD: {WILDCARD: CopyEntry(message="Remover todos os dispositivos?")},
    },
    # Labels dos campos editáveis do Perfil — religados em perfil.vue via
    # ProfileView._profile_copy(). Nome dividido (given/family) é a decisão de UX
    # no ar: melhor pro autocomplete e pra saudar pelo primeiro nome.
    "PROFILE_FIRST_NAME_FIELD": {
        WILDCARD: {WILDCARD: CopyEntry(title="Primeiro nome")},
    },
    "PROFILE_LAST_NAME_FIELD": {
        WILDCARD: {WILDCARD: CopyEntry(title="Sobrenome")},
    },
    "PROFILE_EMAIL_FIELD": {
        WILDCARD: {WILDCARD: CopyEntry(title="E-mail")},
    },
    "PROFILE_BIRTHDAY_FIELD": {
        WILDCARD: {WILDCARD: CopyEntry(title="Aniversário")},
    },
    # ── Perfil "ler-depois-editar" (backlog, ainda não construído) ──
    # Um cartão de leitura do perfil (rótulo: valor, "Não informado" nos vazios)
    # com botão "Editar" e o convite humano "Como quer ser chamado?". A tela no
    # ar hoje é sempre-editável; estas guardam a intenção de omotenashi.
    # Ver docs/plans/completed/COPY-BACKLOG-UNBUILT.md.
    "PROFILE_SECTION_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Dados pessoais")},
    },
    "PROFILE_EDIT_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Editar")},
    },
    "PROFILE_NAME_FIELD": {
        WILDCARD: {WILDCARD: CopyEntry(title="Nome")},
    },
    "PROFILE_PHONE_FIELD": {
        WILDCARD: {WILDCARD: CopyEntry(title="Telefone")},
    },
    "PROFILE_MISSING_VALUE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Não informado")},
    },
    "PROFILE_NAME_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(title="Como quer ser chamado?")},
    },

    # ── Kintsugi ──────────────────────────────────────────────────
    # ── Rating ────────────────────────────────────────────────────
    "TRACKING_RATE_THANKS": {
        WILDCARD: {WILDCARD: CopyEntry(title="Obrigado!", message="Valorizamos muito seu retorno.")},
    },

    # ── Status banners ────────────────────────────────────────────
    "URGENCY_BANNER_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Últimos pedidos. Fechamos em breve")},
    },
    # BIRTHDAY_BANNER_* eram duplicatas órfãs do slide de aniversário do hero;
    # consolidadas aqui (o "!" veio do banner). O hero é o único lugar do aniversário.
    "BIRTHDAY_HERO_HEADING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Feliz aniversário!")},
    },
    "BIRTHDAY_HERO_SUB": {
        WILDCARD: {WILDCARD: CopyEntry(message="Seu desconto especial de aniversário já está ativo.")},
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
    "FOOTER_COPYRIGHT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Todos os direitos reservados.")},
    },

    # ── Kintsugi ──────────────────────────────────────────────────
    "KINTSUGI_CANCEL_REFUSED": {
        WILDCARD: {WILDCARD: CopyEntry(message="Seu pedido já está sendo preparado. Fale conosco para ajustar.")},
    },
    "KINTSUGI_SHORTAGE_GENERIC": {
        WILDCARD: {WILDCARD: CopyEntry(title="Ih, o último acabou de sair")},
    },
    "KINTSUGI_SHORTAGE_SUBSTITUTES_INTRO": {
        WILDCARD: {WILDCARD: CopyEntry(message="Que tal um destes no lugar?")},
    },
    "KINTSUGI_PLANNED_OFFER": {
        WILDCARD: {WILDCARD: CopyEntry(title="Já vem quentinho", message="Sai fresquinho no próximo lote. Quer garantir o seu?")},
    },
    "KINTSUGI_PAUSED_COPY": {
        WILDCARD: {WILDCARD: CopyEntry(title="Temporariamente indisponível", message="Voltamos em breve.")},
    },

    # ── Reorder ──────────────────────────────────────────────────
    "REORDER_CONFLICT_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Sua sacola já tem itens")},
    },
    "REORDER_CONFLICT_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Escolha como deseja repetir este pedido.")},
    },
    "REORDER_CONFLICT_CURRENT_CART_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(title="Na sacola agora")},
    },
    "REORDER_CONFLICT_PREVIOUS_ORDER_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pedido anterior")},
    },
    "REORDER_CONFLICT_APPEND_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(title="Adicionar à sacola atual")},
    },
    "REORDER_CONFLICT_APPEND_HELP": {
        WILDCARD: {WILDCARD: CopyEntry(message="Mantemos a sacola atual e somamos os itens disponíveis do pedido anterior.")},
    },
    "REORDER_CONFLICT_REPLACE_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(title="Substituir sacola")},
    },
    "REORDER_CONFLICT_REPLACE_HELP": {
        WILDCARD: {WILDCARD: CopyEntry(message="Os itens atuais serão removidos antes de recriar o pedido anterior.")},
    },
    "REORDER_CONFLICT_REPLACE_ACK_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(message="Entendo que os itens atuais serão removidos.")},
    },
    "REORDER_CONFLICT_CANCEL_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(title="Manter minha sacola")},
    },

    # ── Order status labels (shared: storefront tracking + operator queue) ─
    # One key per Order status; tone/colour is carried separately as semantic
    # data (``ORDER_STATUS_TONES``) and mapped to classes by each surface.
    "ORDER_STATUS_NEW": {WILDCARD: {WILDCARD: CopyEntry(title="Recebido")}},
    "ORDER_STATUS_CONFIRMED": {WILDCARD: {WILDCARD: CopyEntry(title="Confirmado")}},
    "ORDER_STATUS_PREPARING": {WILDCARD: {WILDCARD: CopyEntry(title="Em Preparo")}},
    "ORDER_STATUS_READY": {WILDCARD: {WILDCARD: CopyEntry(title="Pronto")}},
    "ORDER_STATUS_DISPATCHED": {WILDCARD: {WILDCARD: CopyEntry(title="Saiu para entrega")}},
    "ORDER_STATUS_DELIVERED": {WILDCARD: {WILDCARD: CopyEntry(title="Entregue")}},
    "ORDER_STATUS_COMPLETED": {WILDCARD: {WILDCARD: CopyEntry(title="Concluído")}},
    "ORDER_STATUS_CANCELLED": {WILDCARD: {WILDCARD: CopyEntry(title="Cancelado")}},
    "ORDER_STATUS_RETURNED": {WILDCARD: {WILDCARD: CopyEntry(title="Devolvido")}},

    # ── Payment method labels (checkout, POS, operator queue) ─────────────
    "PAYMENT_METHOD_PIX": {WILDCARD: {WILDCARD: CopyEntry(title="PIX")}},
    "PAYMENT_METHOD_CARD": {WILDCARD: {WILDCARD: CopyEntry(title="Cartão")}},
    "PAYMENT_METHOD_CASH": {WILDCARD: {WILDCARD: CopyEntry(title="Dinheiro")}},
    "PAYMENT_METHOD_MIXED": {WILDCARD: {WILDCARD: CopyEntry(title="Pagamento misto")}},
    "PAYMENT_METHOD_EXTERNAL": {WILDCARD: {WILDCARD: CopyEntry(title="Pago online")}},

    # ── Availability labels (storefront catalog + product detail) ─────────
    "AVAILABILITY_AVAILABLE": {WILDCARD: {WILDCARD: CopyEntry(title="Disponível")}},
    "AVAILABILITY_LOW_STOCK": {WILDCARD: {WILDCARD: CopyEntry(title="Últimas unidades")}},
    "AVAILABILITY_PLANNED_OK": {WILDCARD: {WILDCARD: CopyEntry(title="Lista de espera")}},
    "AVAILABILITY_UNAVAILABLE": {WILDCARD: {WILDCARD: CopyEntry(title="Indisponível")}},
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


MOMENT_CHOICES = [(WILDCARD, "(qualquer)")] + [(m, m) for m in ALL_MOMENTS]
AUDIENCE_CHOICES = [(WILDCARD, "(qualquer)")] + [
    (AUDIENCE_ANON, "anônima"),
    (AUDIENCE_NEW, "nova"),
    (AUDIENCE_RETURNING, "recorrente"),
    (AUDIENCE_VIP, "VIP"),
]
