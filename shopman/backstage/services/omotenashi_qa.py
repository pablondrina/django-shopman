"""Omotenashi manual QA matrix backed by seeded operational scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from shopman.craftsman.models import WorkOrder
from shopman.offerman.models import Product
from shopman.orderman.models import Order, Session
from shopman.payman.models import PaymentIntent

from shopman.backstage.models import CashShift, DayClosing, KDSTicket, POSTab
from shopman.shop.services import operator_links, pos_links, storefront_links

Status = Literal["ready", "missing"]


@dataclass(frozen=True)
class OmotenashiQACheck:
    """One manual QA checkpoint with concrete seed evidence and a route to open."""

    id: str
    surface: str
    viewport: str
    persona: str
    title: str
    url: str
    expectation: str
    evidence: str
    status: Status
    blocker: str = ""
    # True when the surface deliberately gates on authentication (e.g. checkout),
    # so the browser runner treats landing on the login page as the EXPECTED state
    # for this checkpoint instead of an accidental session-expiry redirect.
    auth_gated: bool = False
    # Order ref for customer order-scoped store pages (payment/tracking). The
    # browser runner grants this ref to the QA session (shopman_order_access_refs),
    # exactly as a real customer's session carries it — so the page renders the
    # real state instead of the "not found" fallback.
    order_ref: str = ""

    def as_dict(self) -> dict:
        data = {
            "id": self.id,
            "surface": self.surface,
            "viewport": self.viewport,
            "persona": self.persona,
            "title": self.title,
            "url": self.url,
            "expectation": self.expectation,
            "evidence": self.evidence,
            "status": self.status,
        }
        if self.blocker:
            data["blocker"] = self.blocker
        if self.auth_gated:
            data["auth_gated"] = True
        if self.order_ref:
            data["order_ref"] = self.order_ref
        return data


@dataclass(frozen=True)
class OmotenashiQAReport:
    """Manual QA readiness report for a seeded Shopman instance."""

    generated_at: str
    checks: tuple[OmotenashiQACheck, ...]

    @property
    def status(self) -> str:
        return "ready" if self.missing_count == 0 else "missing_seed_data"

    @property
    def ready_count(self) -> int:
        return sum(1 for check in self.checks if check.status == "ready")

    @property
    def missing_count(self) -> int:
        return sum(1 for check in self.checks if check.status == "missing")

    @property
    def blocking(self) -> bool:
        return self.missing_count > 0

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "generated_at": self.generated_at,
            "counts": {
                "ready": self.ready_count,
                "missing": self.missing_count,
                "total": len(self.checks),
            },
            "checks": [check.as_dict() for check in self.checks],
        }


def build_omotenashi_qa_report() -> OmotenashiQAReport:
    """Build the canonical mobile/tablet/desktop manual QA checklist."""
    checks = (
        _catalog_check(),
        _checkout_intent_check(),
        _pix_pending_check(),
        _pix_expired_check(),
        _tracking_ready_check(),
        # Superfícies de operador = apps Nuxt dedicados (gestor./kds./fournil./pos.),
        # apontados por base URL configurável. O gate browser-QA da loja não as serve
        # → o harness as pula com "surface-not-served" (como o POS), mas a matriz fica
        # completa e documenta a expectativa omotenashi de cada superfície.
        _orders_check(),
        _kds_check(),
        _production_check(),
        _pos_check(),
        _day_closing_check(),
        _cash_register_check(),
    )
    return OmotenashiQAReport(
        generated_at=timezone.now().replace(microsecond=0).isoformat(),
        checks=checks,
    )


def _catalog_check() -> OmotenashiQACheck:
    product = Product.objects.filter(is_published=True, is_sellable=True).order_by("sku").first()
    evidence = f"sku={product.sku}" if product else ""
    return _check(
        id="mobile.catalog.browse",
        surface="storefront",
        viewport="mobile 375x812",
        persona="cliente anonimo ou novo",
        title="Explorar cardapio e PDP sem dead end",
        url=storefront_links.storefront_url(storefront_links.path_menu()),
        expectation="Menu e produto devem antecipar disponibilidade, preco, alergênicos e proxima acao.",
        evidence=evidence,
        blocker="Rode make seed; nenhum produto publicado/vendavel foi encontrado.",
    )


def _checkout_intent_check() -> OmotenashiQACheck:
    session = Session.objects.filter(state="open", channel_ref__in=["web", "whatsapp"]).order_by("-id").first()
    evidence = f"session={session.session_key} channel={session.channel_ref}" if session else ""
    return _check(
        id="mobile.checkout.intent",
        surface="storefront",
        viewport="mobile 375x812",
        persona="cliente com baixa atencao",
        title="Carrinho/checkout guiando intencao sem pular guardrails",
        url=storefront_links.storefront_url(storefront_links.path_checkout()),
        expectation="Checkout deve mostrar etapa atual, bloqueio claro, recuperacao e CTA unico.",
        evidence=evidence,
        blocker="Rode make seed; nenhuma sessao remota aberta foi encontrada.",
        auth_gated=True,
    )


def _pix_pending_check() -> OmotenashiQACheck:
    order = _edge_order("security:payment-pending-near-expiry")
    intent = _intent_for_order(order)
    evidence = _order_evidence(order)
    if intent:
        evidence = f"{evidence} intent={intent.ref} expires_at={intent.expires_at.isoformat() if intent.expires_at else '-'}"
    return _check(
        id="mobile.payment.pix_pending_near_expiry",
        surface="storefront",
        viewport="mobile 375x812",
        persona="cliente baixa atencao voltando pelo tracking",
        title="PIX pendente perto de expirar",
        url=_store_order_url(storefront_links.order_payment_url, order),
        expectation="Pagamento deve explicar prazo, acao do cliente, proximo evento e recuperacao sem confirmar por refresh.",
        evidence=evidence,
        blocker="Rode make seed; cenario security:payment-pending-near-expiry ausente.",
        order_ref=order.ref if order else "",
    )


def _pix_expired_check() -> OmotenashiQACheck:
    order = _edge_order("security:payment-expired-low-attention")
    intent = _intent_for_order(order)
    evidence = _order_evidence(order)
    if intent:
        evidence = f"{evidence} intent={intent.ref} expires_at={intent.expires_at.isoformat() if intent.expires_at else '-'}"
    return _check(
        id="mobile.payment.pix_expired",
        surface="storefront",
        viewport="mobile 375x812",
        persona="cliente distraido apos prazo",
        title="PIX expirado com caminho de recuperacao",
        url=_store_order_url(storefront_links.order_payment_url, order),
        expectation="Tela deve reconhecer expiracao, preservar contexto e oferecer proxima acao segura.",
        evidence=evidence,
        blocker="Rode make seed; cenario security:payment-expired-low-attention ausente.",
        order_ref=order.ref if order else "",
    )


def _tracking_ready_check() -> OmotenashiQACheck:
    order = Order.objects.filter(status=Order.Status.READY).order_by("-created_at", "-id").first()
    return _check(
        id="mobile.tracking.ready",
        surface="storefront",
        viewport="mobile 375x812",
        persona="cliente aguardando retirada ou entrega",
        title="Tracking de pedido pronto",
        url=_store_order_url(storefront_links.order_tracking_url, order),
        expectation="Tracking deve dizer o que aconteceu agora, se ha acao do cliente e o proximo evento.",
        evidence=_order_evidence(order),
        blocker="Rode make seed; nenhum pedido READY foi encontrado.",
        order_ref=order.ref if order else "",
    )


_ACTIVE_ORDER_STATUSES = (
    Order.Status.NEW,
    Order.Status.CONFIRMED,
    Order.Status.PREPARING,
    Order.Status.READY,
    Order.Status.DISPATCHED,
)


def _orders_check() -> OmotenashiQACheck:
    order = (
        Order.objects.filter(status__in=_ACTIVE_ORDER_STATUSES)
        .order_by("-created_at", "-id")
        .first()
    )
    evidence = f"order={order.ref} status={order.status}" if order else ""
    return _check(
        id="desktop.orders.queue",
        surface="orders",
        viewport="desktop 1440x900",
        persona="gerente acompanhando a fila de pedidos",
        title="Gestor de Pedidos com fila viva e ações sem dead end",
        url=operator_links.orders_url(),
        expectation="Operador deve confirmar/avançar/recusar/acertar e ver alertas sem tocar em admin genérico.",
        evidence=evidence,
        blocker="Rode make seed; nenhum pedido ativo foi encontrado.",
        auth_gated=True,
    )


def _kds_check() -> OmotenashiQACheck:
    ticket = (
        KDSTicket.objects.filter(status__in=["pending", "in_progress"])
        .order_by("created_at", "id")
        .first()
    )
    evidence = f"ticket={ticket.pk} status={ticket.status}" if ticket else ""
    return _check(
        id="tablet.kds.station",
        surface="kds",
        viewport="tablet/touch 1024x768",
        persona="cozinha montando o pedido",
        title="KDS com tickets vivos, toque e expedição",
        url=operator_links.kds_url(),
        expectation="Estação deve mostrar item, tempo e ação primária sem esconder atraso nem cancelamento.",
        evidence=evidence,
        blocker="Rode make seed; nenhum ticket KDS pendente/em andamento foi encontrado.",
        auth_gated=True,
    )


def _production_check() -> OmotenashiQACheck:
    work_order = (
        WorkOrder.objects.filter(status__in=[WorkOrder.Status.STARTED, WorkOrder.Status.PLANNED])
        .order_by("target_date", "id")
        .first()
    )
    evidence = (
        f"wo={work_order.ref} status={work_order.status} sku={work_order.output_sku}"
        if work_order
        else ""
    )
    return _check(
        id="tablet.production.floor",
        surface="production",
        viewport="tablet/touch 1024x768",
        persona="produção em lote no chão",
        title="Produção (chão ao vivo) com passo, conclusão e escassez de insumo",
        url=operator_links.production_url(),
        expectation="Tela deve mostrar lote, passo, ação primária e bloqueio de insumo sem esconder risco.",
        evidence=evidence,
        blocker="Rode make seed; nenhuma WorkOrder planejada/iniciada foi encontrada.",
        auth_gated=True,
    )


def _pos_check() -> OmotenashiQACheck:
    tab = POSTab.objects.filter(is_active=True).order_by("ref").first()
    shift = CashShift.objects.filter(status="open").order_by("-opened_at", "-id").first()
    evidence = ""
    if tab and shift:
        evidence = f"tab={tab.ref} cash_shift={shift.pk}"
    return _check(
        id="desktop.pos.counter",
        surface="pos",
        viewport="desktop/touch 1280x800",
        persona="balcao com cliente na frente",
        title="POS com comanda disponível e caixa vivo",
        url=pos_links.pos_url(pos_links.path_counter()),
        expectation="Operador deve vender, editar e fechar sem procurar funcao nem tocar em admin generico.",
        evidence=evidence,
        blocker="Rode make seed; POS tab ativa ou caixa aberto ausente.",
    )


def _day_closing_check() -> OmotenashiQACheck:
    closing = DayClosing.objects.order_by("-date").first()
    evidence = f"closing={closing.date.isoformat()} id={closing.pk}" if closing else ""
    return _check(
        id="desktop.closing.day",
        surface="pos",
        viewport="desktop 1440x900",
        persona="gerente fechando o dia",
        title="Fechamento do dia com sobras e reconciliacao",
        url=pos_links.pos_url(pos_links.path_day_closing()),
        expectation="Gerente deve conferir sobras, itens de ontem, caixa e divergencias sem planilha paralela.",
        evidence=evidence,
        blocker="Rode make seed; nenhum DayClosing foi encontrado.",
    )


def _cash_register_check() -> OmotenashiQACheck:
    register = CashShift.objects.order_by("-opened_at", "-id").first()
    evidence = f"cash_shift={register.pk} status={register.status}" if register else ""
    return _check(
        id="desktop.cash_register.shift",
        surface="pos",
        viewport="desktop/touch 1280x800",
        persona="operador abrindo ou fechando caixa",
        title="Caixa aberto/fechado com diferenca auditavel",
        url=pos_links.pos_url(pos_links.path_counter()),
        expectation="Caixa deve expor estado, sangria/fechamento e diferenca sem depender de memoria do operador.",
        evidence=evidence,
        blocker="Rode make seed; nenhuma sessao de caixa foi encontrada.",
    )


def _check(
    *,
    id: str,
    surface: str,
    viewport: str,
    persona: str,
    title: str,
    url: str,
    expectation: str,
    evidence: str,
    blocker: str,
    auth_gated: bool = False,
    order_ref: str = "",
) -> OmotenashiQACheck:
    status: Status = "ready" if evidence else "missing"
    return OmotenashiQACheck(
        id=id,
        surface=surface,
        viewport=viewport,
        persona=persona,
        title=title,
        url=url,
        expectation=expectation,
        evidence=evidence or "-",
        status=status,
        blocker="" if status == "ready" else blocker,
        auth_gated=auth_gated,
        order_ref=order_ref,
    )


def _edge_order(seed_key: str) -> Order | None:
    return Order.objects.filter(snapshot__seed_key=seed_key).order_by("-created_at", "-id").first()


def _intent_for_order(order: Order | None) -> PaymentIntent | None:
    if order is None:
        return None
    return PaymentIntent.objects.filter(order_ref=order.ref).order_by("-created_at", "-id").first()


def _order_evidence(order: Order | None) -> str:
    if order is None:
        return ""
    edge_case = (order.data or {}).get("edge_case") or (order.snapshot or {}).get("seed_key") or "-"
    return f"order={order.ref} status={order.status} channel={order.channel_ref} case={edge_case}"


def _order_url(name: str, order: Order | None) -> str:
    ref = order.ref if order is not None else "ORDER_REF"
    return _url(name, ref)


def _store_order_url(builder, order: Order | None) -> str:
    """Absolute Nuxt-store URL for an order-scoped customer surface (QA link)."""
    ref = order.ref if order is not None else "ORDER_REF"
    return builder(ref)


def _url(name: str, *args) -> str:
    try:
        return reverse(name, args=args)
    except NoReverseMatch:
        if args:
            suffix = "/" + "/".join(str(arg) for arg in args)
        else:
            suffix = ""
        return f"unresolved:{name}{suffix}"
