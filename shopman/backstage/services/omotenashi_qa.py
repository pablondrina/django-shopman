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

from shopman.backstage.models import CashRegisterSession, DayClosing, KDSInstance, OperatorAlert, POSTab

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

    def as_dict(self) -> dict[str, str]:
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
        _late_payment_after_cancel_check(),
        _tracking_ready_check(),
        _kds_station_check(),
        _customer_board_check(),
        _order_queue_check(),
        _ifood_stale_check(),
        _pos_check(),
        _production_kds_check(),
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
        url=_url("storefront:menu"),
        expectation="Menu e produto devem antecipar disponibilidade, preco, alergênicos e proxima acao.",
        evidence=evidence,
        blocker="Rode make seed; nenhum produto publicado/vendavel foi encontrado.",
    )


def _checkout_intent_check() -> OmotenashiQACheck:
    session = Session.objects.filter(state="open", channel_ref__in=["web", "delivery", "whatsapp"]).order_by("-id").first()
    evidence = f"session={session.session_key} channel={session.channel_ref}" if session else ""
    return _check(
        id="mobile.checkout.intent",
        surface="storefront",
        viewport="mobile 375x812",
        persona="cliente com baixa atencao",
        title="Carrinho/checkout guiando intencao sem pular guardrails",
        url=_url("storefront:checkout"),
        expectation="Checkout deve mostrar etapa atual, bloqueio claro, recuperacao e CTA unico.",
        evidence=evidence,
        blocker="Rode make seed; nenhuma sessao remota aberta foi encontrada.",
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
        url=_order_url("storefront:order_payment", order),
        expectation="Pagamento deve explicar prazo, acao do cliente, proximo evento e recuperacao sem confirmar por refresh.",
        evidence=evidence,
        blocker="Rode make seed; cenario security:payment-pending-near-expiry ausente.",
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
        url=_order_url("storefront:order_payment", order),
        expectation="Tela deve reconhecer expiracao, preservar contexto e oferecer proxima acao segura.",
        evidence=evidence,
        blocker="Rode make seed; cenario security:payment-expired-low-attention ausente.",
    )


def _late_payment_after_cancel_check() -> OmotenashiQACheck:
    order = _edge_order("security:payment-after-cancel")
    alert = OperatorAlert.objects.filter(type="payment_after_cancel", order_ref=getattr(order, "ref", "")).first()
    evidence = _order_evidence(order)
    if alert:
        evidence = f"{evidence} alert={alert.type}:{alert.severity}"
    return _check(
        id="desktop.payment.after_cancel",
        surface="backstage",
        viewport="desktop 1440x900",
        persona="suporte financeiro",
        title="Pagamento capturado depois de cancelamento",
        url=_order_url("admin_console_order_detail", order),
        expectation="Operador deve ver alerta critico, pedido cancelado e pista clara para reembolso/comunicacao.",
        evidence=evidence if alert else "",
        blocker="Rode make seed; pedido/alerta payment_after_cancel ausente.",
    )


def _tracking_ready_check() -> OmotenashiQACheck:
    order = Order.objects.filter(status=Order.Status.READY).order_by("-created_at", "-id").first()
    return _check(
        id="mobile.tracking.ready",
        surface="storefront",
        viewport="mobile 375x812",
        persona="cliente aguardando retirada ou entrega",
        title="Tracking de pedido pronto",
        url=_order_url("storefront:order_tracking", order),
        expectation="Tracking deve dizer o que aconteceu agora, se ha acao do cliente e o proximo evento.",
        evidence=_order_evidence(order),
        blocker="Rode make seed; nenhum pedido READY foi encontrado.",
    )


def _kds_station_check() -> OmotenashiQACheck:
    instance = KDSInstance.objects.filter(is_active=True).order_by("type", "ref").first()
    evidence = f"kds={instance.ref} type={instance.type}" if instance else ""
    return _check(
        id="tablet.kds.station",
        surface="kds",
        viewport="tablet 1024x768",
        persona="cozinha em pico de demanda",
        title="KDS operacional por estacao",
        url=_url("backstage:kds_station_runtime", instance.ref if instance else "cafes"),
        expectation="Cards devem priorizar acao, tempo, foco de toque e feedback sem poluir a cozinha.",
        evidence=evidence,
        blocker="Rode make seed; nenhuma KDSInstance ativa foi encontrada.",
    )


def _customer_board_check() -> OmotenashiQACheck:
    order = Order.objects.filter(status=Order.Status.READY).order_by("-created_at", "-id").first()
    return _check(
        id="tablet.kds.customer_board",
        surface="kds",
        viewport="tablet/display 1280x720",
        persona="cliente olhando painel de retirada",
        title="Painel de pedidos prontos para cliente",
        url=_url("backstage:kds_customer_board"),
        expectation="Painel deve revelar somente informacao necessaria, sem dados sensiveis nem ruido operacional.",
        evidence=_order_evidence(order),
        blocker="Rode make seed; painel precisa de pelo menos um pedido READY.",
    )


def _order_queue_check() -> OmotenashiQACheck:
    order = Order.objects.filter(status=Order.Status.NEW).order_by("-created_at", "-id").first()
    return _check(
        id="desktop.orders.queue",
        surface="backstage",
        viewport="desktop 1440x900",
        persona="gerente ou atendente",
        title="Fila de pedidos com acao primaria",
        url=_url("admin_console_orders"),
        expectation="Fila deve separar urgencia, bloqueio, pagamento e proxima acao sem exigir interpretacao.",
        evidence=_order_evidence(order),
        blocker="Rode make seed; nenhum pedido NEW foi encontrado.",
    )


def _ifood_stale_check() -> OmotenashiQACheck:
    order = _edge_order("security:ifood-stale-confirmation")
    alert = OperatorAlert.objects.filter(type="stale_new_order", order_ref=getattr(order, "ref", "")).first()
    evidence = _order_evidence(order)
    if alert:
        evidence = f"{evidence} alert={alert.type}:{alert.severity}"
    return _check(
        id="desktop.marketplace.ifood_stale",
        surface="backstage",
        viewport="desktop 1440x900",
        persona="operador marketplace",
        title="Pedido iFood parado aguardando confirmacao",
        url=_order_url("admin_console_order_detail", order),
        expectation="Detalhe deve preservar contexto externo, indicar atraso e oferecer acao operacional segura.",
        evidence=evidence if alert else "",
        blocker="Rode make seed; pedido/alerta security:ifood-stale-confirmation ausente.",
    )


def _pos_check() -> OmotenashiQACheck:
    tab = POSTab.objects.filter(is_active=True).order_by("code").first()
    session = Session.objects.filter(state="open", handle_type="pos_tab").order_by("-id").first()
    evidence = ""
    if tab and session:
        evidence = f"tab={tab.code} session={session.session_key}"
    return _check(
        id="desktop.pos.counter",
        surface="pos",
        viewport="desktop/touch 1280x800",
        persona="balcao com cliente na frente",
        title="POS com comanda aberta e caixa vivo",
        url=_url("backstage:pos"),
        expectation="Operador deve vender, editar e fechar sem procurar funcao nem tocar em admin generico.",
        evidence=evidence,
        blocker="Rode make seed; POS tab ativa ou sessao POS aberta ausente.",
    )


def _production_kds_check() -> OmotenashiQACheck:
    work_order = WorkOrder.objects.filter(status__in=[WorkOrder.Status.STARTED, WorkOrder.Status.PLANNED]).order_by(
        "target_date", "id"
    ).first()
    evidence = f"wo={work_order.ref} status={work_order.status} sku={work_order.output_sku}" if work_order else ""
    return _check(
        id="tablet.production.kds",
        surface="production",
        viewport="tablet 1024x768",
        persona="producao em lote",
        title="KDS de producao com passo manual e falta de insumo",
        url=_url("backstage:production_kds"),
        expectation="Tela deve mostrar lote, passo, acao primaria e bloqueio de estoque sem esconder risco.",
        evidence=evidence,
        blocker="Rode make seed; nenhuma WorkOrder planejada/iniciada foi encontrada.",
    )


def _day_closing_check() -> OmotenashiQACheck:
    closing = DayClosing.objects.order_by("-date").first()
    evidence = f"closing={closing.date.isoformat()} id={closing.pk}" if closing else ""
    return _check(
        id="desktop.closing.day",
        surface="backstage",
        viewport="desktop 1440x900",
        persona="gerente fechando o dia",
        title="Fechamento do dia com sobras e reconciliacao",
        url=_url("admin_console_day_closing"),
        expectation="Gerente deve conferir sobras, D-1, caixa e divergencias sem planilha paralela.",
        evidence=evidence,
        blocker="Rode make seed; nenhum DayClosing foi encontrado.",
    )


def _cash_register_check() -> OmotenashiQACheck:
    register = CashRegisterSession.objects.order_by("-opened_at", "-id").first()
    evidence = f"cash_session={register.pk} status={register.status}" if register else ""
    return _check(
        id="desktop.cash_register.shift",
        surface="pos",
        viewport="desktop/touch 1280x800",
        persona="operador abrindo ou fechando caixa",
        title="Caixa aberto/fechado com diferenca auditavel",
        url=_url("backstage:pos"),
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


def _url(name: str, *args) -> str:
    try:
        return reverse(name, args=args)
    except NoReverseMatch:
        if args:
            suffix = "/" + "/".join(str(arg) for arg in args)
        else:
            suffix = ""
        return f"unresolved:{name}{suffix}"
