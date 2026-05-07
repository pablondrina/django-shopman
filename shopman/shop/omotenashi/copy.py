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
    "CHECKOUT_PAGE_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Finalizar pedido")},
    },
    "CHECKOUT_PAGE_META_DESCRIPTION": {
        WILDCARD: {WILDCARD: CopyEntry(message="Revise e finalize seu pedido")},
    },
    "CHECKOUT_SWITCH_ACCOUNT_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Trocar conta?")},
    },
    "CHECKOUT_SWITCH_ACCOUNT_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Você vai sair desta conta para entrar com outro telefone.")},
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
    "CHECKOUT_LOYALTY_PROMPT": {
        WILDCARD: {WILDCARD: CopyEntry(title="Usar pontos de fidelidade?")},
    },
    "CHECKOUT_LOYALTY_BALANCE_SUFFIX": {
        WILDCARD: {WILDCARD: CopyEntry(message="disponíveis.")},
    },
    "CHECKOUT_NOTES_PROMPT": {
        WILDCARD: {WILDCARD: CopyEntry(title="Algo mais que devemos saber?")},
    },
    "CHECKOUT_COUPON_PROMPT": {
        WILDCARD: {WILDCARD: CopyEntry(title="Tem cupom de desconto?")},
    },
    "CHECKOUT_CONFIRM_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Enviar pedido")},
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
    "MIN_ORDER_WARNING_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(message="Faltam")},
    },
    "MIN_ORDER_WARNING_MIDDLE": {
        WILDCARD: {WILDCARD: CopyEntry(message="para o pedido mínimo de")},
    },

    # ── Menu empty state ──────────────────────────────────────────
    "MENU_EMPTY": {
        WILDCARD: {WILDCARD: CopyEntry(message="Nenhum produto disponível no momento.")},
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
        WILDCARD: {WILDCARD: CopyEntry(message="Com um toque, seu favorito volta ao carrinho.")},
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
        WILDCARD: {WILDCARD: CopyEntry(title="Pedido Online")},
    },
    "HOME_HOW_STORE_HEADING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Na Loja")},
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
        WILDCARD: {WILDCARD: CopyEntry(message="Duas formas simples de aproveitar: peça pelo site ou venha escolher na loja.")},
    },
    "HOW_ONLINE_CHOOSE_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Navegue pelo cardápio e adicione ao carrinho. A disponibilidade aparece em tempo real.")},
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
                message="Fale com a gente direto pelo WhatsApp. Respondemos o mais rápido possível.",
            ),
        },
    },
    "WELCOME_WHATSAPP": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                title="Você entrou pelo WhatsApp",
                message="Pode continuar por aqui quando quiser.",
            ),
        },
    },

    # ── Tracking tail ─────────────────────────────────────────────
    "TRACKING_PAGE_META_DESCRIPTION": {
        WILDCARD: {WILDCARD: CopyEntry(message="Acompanhe seu pedido")},
    },
    "TRACKING_REORDER_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pedir novamente")},
    },
    "TRACKING_MENU_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Ver cardápio")},
    },
    "TRACKING_ETA_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(
            title="Estamos preparando seu pedido.",
            message="Previsão para ficar pronto às",
        )},
    },
    "TRACKING_AUTO_CONFIRM_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(message="O estabelecimento tem")},
    },
    "TRACKING_AUTO_CONFIRM_SUFFIX": {
        WILDCARD: {WILDCARD: CopyEntry(message="para conferir a disponibilidade.")},
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
    "TRACKING_STEP_RECEIVED": {
        WILDCARD: {WILDCARD: CopyEntry(title="Recebemos seu pedido.")},
    },
    "TRACKING_STEP_AVAILABILITY_CONFIRMED": {
        WILDCARD: {WILDCARD: CopyEntry(title="Confirmamos a disponibilidade.")},
    },
    "TRACKING_STEP_PAYMENT_CONFIRMED": {
        WILDCARD: {WILDCARD: CopyEntry(title="Reconhecemos o pagamento.")},
    },
    "TRACKING_STEP_PREPARING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Estamos preparando seu pedido.")},
    },
    "TRACKING_STEP_READY_PICKUP": {
        WILDCARD: {WILDCARD: CopyEntry(title="Seu pedido está pronto para retirada.")},
    },
    "TRACKING_STEP_READY_DELIVERY": {
        WILDCARD: {WILDCARD: CopyEntry(title="Seu pedido está pronto e aguardando entregador.")},
    },
    "TRACKING_STEP_READY_GENERIC": {
        WILDCARD: {WILDCARD: CopyEntry(title="Seu pedido está pronto.")},
    },
    "TRACKING_DELIVERY_WAITING_COURIER": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                title="Aguardando entregador.",
                message="Já solicitamos a coleta do seu pedido. Assim que sair para entrega avisamos.",
            ),
        },
    },
    "TRACKING_STEP_DISPATCHED": {
        WILDCARD: {WILDCARD: CopyEntry(title="Seu pedido saiu para entrega.")},
    },
    "TRACKING_STEP_DELIVERED": {
        WILDCARD: {WILDCARD: CopyEntry(title="Seu pedido foi entregue.")},
    },
    "TRACKING_STEP_COMPLETED": {
        WILDCARD: {WILDCARD: CopyEntry(title="O pedido foi concluído.")},
    },
    "TRACKING_STEP_CANCELLED": {
        WILDCARD: {WILDCARD: CopyEntry(title="O pedido foi cancelado.")},
    },
    "TRACKING_PAYMENT_PENDING": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                title="Recebemos seu pedido.",
                message="Aguardamos a confirmação do pagamento.",
            ),
        },
    },
    "TRACKING_PAYMENT_REQUESTED": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                title="Disponibilidade confirmada.",
                message="Para continuar, conclua o pagamento.",
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
                title="O prazo para pagamento expirou.",
                message="O pedido foi automaticamente cancelado. Você pode refazer o pedido ou falar com o estabelecimento.",
            ),
        },
    },
    "TRACKING_PAYMENT_CONFIRMED": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                title="Pagamento confirmado.",
                message="Recebemos a confirmação do pagamento deste pedido.",
            ),
        },
    },
    "TRACKING_ACTION_NONE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Nenhuma ação necessária")},
    },
    "TRACKING_ACTION_WAITING_COURIER": {
        WILDCARD: {WILDCARD: CopyEntry(title="Aguardando entregador")},
    },
    "TRACKING_ACTION_READY_PICKUP": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pronto para retirada")},
    },
    "TRACKING_CARD_AUTHORIZED": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                title="Pagamento autorizado.",
                message="Você não precisa fazer nada agora.",
            ),
        },
    },
    "TRACKING_PROMISE_UPDATED_NOW": {
        WILDCARD: {WILDCARD: CopyEntry(title="Atualizado agora")},
    },
    "TRACKING_PROMISE_LABEL_ACTION": {
        WILDCARD: {WILDCARD: CopyEntry(title="Sua ação:")},
    },
    "TRACKING_PROMISE_LABEL_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(title="Próximo passo:")},
    },
    "TRACKING_PROMISE_LABEL_RECOVERY": {
        WILDCARD: {WILDCARD: CopyEntry(title="Se algo mudar:")},
    },
    "TRACKING_PROMISE_LABEL_ACTIVE_NOTIFICATION": {
        WILDCARD: {WILDCARD: CopyEntry(title="Aviso ativo:")},
    },
    "TRACKING_PROMISE_STALE": {
        WILDCARD: {
            WILDCARD: CopyEntry(
                message="Estamos conferindo uma atualização. Se a tela não mudar, toque em atualizar.",
            ),
        },
    },
    "TRACKING_PROMISE_PAYMENT_EXPIRED_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Você pode refazer o pedido quando quiser.")},
    },
    "TRACKING_PROMISE_RECOVERY_HELP": {
        WILDCARD: {WILDCARD: CopyEntry(message="Se precisar de ajuda, fale com o estabelecimento.")},
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
        WILDCARD: {WILDCARD: CopyEntry(message="Se o prazo expirar, o pedido será cancelado automaticamente e o estoque reservado será liberado.")},
    },
    "TRACKING_PROMISE_PAYMENT_ACTIVE_NOTIFICATION": {
        WILDCARD: {WILDCARD: CopyEntry(message="Também avisamos por um canal ativo habilitado, porque o PIX depende da sua ação.")},
    },
    "TRACKING_PROMISE_AVAILABILITY_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="O estabelecimento está conferindo a disponibilidade.")},
    },
    "TRACKING_PROMISE_AVAILABILITY_NEXT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Se a disponibilidade for confirmada, liberamos o pagamento e avisamos você.")},
    },
    "TRACKING_PROMISE_AVAILABILITY_RECOVERY": {
        WILDCARD: {WILDCARD: CopyEntry(message="Se o estabelecimento não confirmar a tempo, atualizaremos o pedido aqui.")},
    },
    "TRACKING_PROMISE_CLOSED_HOURS_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Estamos fechados agora. Vamos conferir a disponibilidade quando abrirmos.")},
    },
    "TRACKING_PROMISE_CLOSED_HOURS_NEXT_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(message="Próxima abertura:")},
    },
    "TRACKING_PROMISE_CLOSED_HOURS_NEXT_UNKNOWN": {
        WILDCARD: {WILDCARD: CopyEntry(message="Atualizaremos o pedido assim que o próximo expediente estiver definido.")},
    },
    "TRACKING_PROMISE_PAYMENT_CONFIRMED_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Nenhuma ação necessária agora.")},
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
        WILDCARD: {WILDCARD: CopyEntry(message="Avisamos ativamente quando o pedido fica pronto para retirada.")},
    },
    "TRACKING_PROMISE_READY_DELIVERY_ACTIVE_NOTIFICATION": {
        WILDCARD: {WILDCARD: CopyEntry(message="Avisamos ativamente quando o pedido sair para entrega.")},
    },
    "TRACKING_PROMISE_DISPATCHED_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Estamos acompanhando a entrega.")},
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
        WILDCARD: {WILDCARD: CopyEntry(message="Avisamos ativamente sobre esta atualização.")},
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
    "CONFIRMATION_ETA_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(message="Começamos a preparar")},
    },

    # ── Payment ───────────────────────────────────────────────────
    "PAYMENT_PAGE_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Concluir pagamento")},
    },
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
    "PAYMENT_ERROR_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Não conseguimos gerar o pagamento agora.")},
    },
    "PAYMENT_ERROR_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Tente novamente em instantes. Se o problema continuar, fale com o estabelecimento.")},
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
    "PAYMENT_DEADLINE_NOTICE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Conclua dentro do prazo indicado abaixo.")},
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
    "PAYMENT_CARD_SECURITY_NOTE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Pagamento processado pelo Stripe. Nós não recebemos os dados do seu cartão.")},
    },
    "PAYMENT_PIX_INSTRUCTION": {
        WILDCARD: {WILDCARD: CopyEntry(message="Escaneie o QR Code ou copie o código Pix abaixo.")},
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
                message="Seguimos com o preparo do seu pedido.",
            ),
            AUDIENCE_VIP: CopyEntry(
                title="Pagamento recebido",
                message="Seguimos com o preparo do seu pedido.",
            ),
            WILDCARD: CopyEntry(
                title="Pagamento recebido",
                message="Seguimos com o preparo do seu pedido.",
            ),
        },
    },
    "PAYMENT_REDIRECTING_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(message="Redirecionando em")},
    },
    "PAYMENT_REDIRECTING_SUFFIX": {
        WILDCARD: {WILDCARD: CopyEntry(message="s...")},
    },
    "PAYMENT_PIX_REGENERATE_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Gerar novo PIX")},
    },
    "PAYMENT_VIEW_ORDER_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Ver pedido")},
    },
    "PAYMENT_CANCELLED": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pedido cancelado")},
    },
    "PAYMENT_CANCELLED_DETAILS_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Ver detalhes")},
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
        WILDCARD: {WILDCARD: CopyEntry(message="Entre pelo WhatsApp ou confirme seu telefone por SMS.")},
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
        WILDCARD: {WILDCARD: CopyEntry(message="Sem senha. A entrada é temporária e segura.")},
    },
    "LOGIN_CHANGE_PHONE_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Trocar de telefone?")},
    },
    "LOGIN_CHANGE_PHONE_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Ao trocar, o código enviado deixa de valer. Você recebe outro em seguida.")},
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
        WILDCARD: {WILDCARD: CopyEntry(title="Como podemos te chamar?")},
    },
    "LOGIN_NAME_SUBTITLE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Pode ser seu primeiro nome ou um apelido. O que for mais natural.")},
    },
    "LOGIN_NAME_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Continuar")},
    },
    "LOGIN_AUTH_CONFIRMED": {
        WILDCARD: {WILDCARD: CopyEntry(title="Pronto", message="Identidade confirmada")},
    },
    "DEVICE_TRUST_ERROR": {
        WILDCARD: {WILDCARD: CopyEntry(message="Não foi possível salvar. Tente novamente.")},
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
    "DEVICE_TRUST_GREETING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Bem-vindo de volta")},
    },
    "WELCOME_PAGE_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Boas-vindas")},
    },
    "WELCOME_GREETING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Que bom te ver aqui!")},
    },
    "WELCOME_NAME_HEADING": {
        WILDCARD: {WILDCARD: CopyEntry(title="Como você quer ser chamado(a)?")},
    },
    "WELCOME_NAME_HEADING_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(title="Como você quer")},
    },
    "WELCOME_NAME_HEADING_SUFFIX": {
        WILDCARD: {WILDCARD: CopyEntry(title="ser chamado(a)?")},
    },
    "WELCOME_SUGGESTED_NAME_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Encontramos esse nome nos seus dados. Se estiver bom, é só confirmar.")},
    },
    "WELCOME_CONFIRM_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Confirmar")},
    },
    "WELCOME_ACCOUNT_NOTE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Você pode mudar isso depois em Minha Conta.")},
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
    "ACCOUNT_GREETING_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(title="Olá")},
    },
    "ACCOUNT_PAGE_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Minha Conta")},
    },
    "ACCOUNT_TRUSTED_DEVICES_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Dispositivos que podem acessar sua conta sem código de verificação.")},
    },
    "ACCOUNT_DELETE_WARNING": {
        WILDCARD: {WILDCARD: CopyEntry(message="Esta ação é irreversível. Todos os seus dados serão anonimizados conforme a LGPD:")},
    },
    "DEVICE_LIST_EMPTY": {
        WILDCARD: {WILDCARD: CopyEntry(message="Nenhum dispositivo registrado ainda. Após fazer login com código de verificação, seu dispositivo aparecerá aqui.")},
    },
    "DEVICE_LIST_UNKNOWN": {
        WILDCARD: {WILDCARD: CopyEntry(title="Dispositivo desconhecido")},
    },
    "DEVICE_LIST_CURRENT": {
        WILDCARD: {WILDCARD: CopyEntry(title="Este dispositivo")},
    },
    "DEVICE_LIST_LAST_USED_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(message="Último uso:")},
    },
    "DEVICE_LIST_REGISTERED_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(message="Registrado em")},
    },
    "DEVICE_REVOKE_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Revogar")},
    },
    "DEVICE_REVOKE_CONFIRM": {
        WILDCARD: {WILDCARD: CopyEntry(message="Revogar acesso deste dispositivo?")},
    },
    "DEVICE_REVOKE_ALL_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Revogar todos os dispositivos")},
    },
    "DEVICE_REVOKE_ALL_CONFIRM": {
        WILDCARD: {WILDCARD: CopyEntry(message="Revogar TODOS os dispositivos? Você precisará fazer login novamente.")},
    },
    "NOTIFICATION_PREFS_EMPTY": {
        WILDCARD: {WILDCARD: CopyEntry(message="Nenhuma preferência de notificação configurável no momento.")},
    },
    "LOYALTY_UNAVAILABLE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Programa de fidelidade não disponível.")},
    },
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
    "PROFILE_EMAIL_FIELD": {
        WILDCARD: {WILDCARD: CopyEntry(title="Email")},
    },
    "PROFILE_BIRTHDAY_FIELD": {
        WILDCARD: {WILDCARD: CopyEntry(title="Data de nascimento")},
    },
    "PROFILE_MISSING_VALUE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Não informado")},
    },
    "PROFILE_NAME_LABEL": {
        WILDCARD: {WILDCARD: CopyEntry(title="Como quer ser chamado?")},
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
    "FOOTER_COPYRIGHT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Todos os direitos reservados.")},
    },
    "MENU_PAGE_META_DESCRIPTION": {
        WILDCARD: {WILDCARD: CopyEntry(message="Cardápio com disponibilidade em tempo real")},
    },
    "OFFLINE_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Sem conexão")},
    },
    "OFFLINE_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Verifique sua internet e tente novamente.")},
    },
    "OFFLINE_RETRY_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Tentar novamente")},
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
    "KINTSUGI_RATE_LIMITED_RETRY_PREFIX": {
        WILDCARD: {WILDCARD: CopyEntry(message="Tente novamente em")},
    },
    "KINTSUGI_RATE_LIMITED_RETRY_CTA": {
        WILDCARD: {WILDCARD: CopyEntry(title="Tentar novamente")},
    },
    "KINTSUGI_RATE_LIMITED_CONTACT": {
        WILDCARD: {WILDCARD: CopyEntry(message="Prefere falar com a gente?")},
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

    # ── Reorder ──────────────────────────────────────────────────
    "REORDER_CONFLICT_TITLE": {
        WILDCARD: {WILDCARD: CopyEntry(title="Seu carrinho já tem itens")},
    },
    "REORDER_CONFLICT_MESSAGE": {
        WILDCARD: {WILDCARD: CopyEntry(message="Escolha como deseja repetir este pedido.")},
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
