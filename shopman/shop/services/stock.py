"""
Stock orchestration service.

Core: StockService (holds), CatalogService (expand bundles)
Adapter: get_adapter("stock") → stock

The order lifecycle is:

  cart-add → services.availability.reserve(session_key)        [creates PENDING hold]
  checkout → CommitService creates Order with session_key
  commit (in-transaction, non-external channels) →
             lifecycle.secure_stock → hold(order, require_all=True)
             [adopts session holds; shortfall irrecuperável DESFAZ o commit]
  on_commit → services.stock.hold(order)                       [idempotente: no-op se o
             gate já reservou; external channels reservam aqui, best-effort]
  on_paid/on_confirmed → services.stock.fulfill(order)          [PENDING→CONFIRMED→FULFILLED]
  cancel   → services.stock.release(order)                     [release adopted holds]

`hold(order)` ADOPTS session holds **by quantity, not by SKU-first**: multiple
session holds for the same SKU are summed up to meet the ordered qty, and a
fresh hold is created via the adapter for any unmet remainder. This is the
fix for the sangria where a stepper that created two holds of qty=2 each
ended up adopting only one of them.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.utils import timezone

from shopman.shop.adapters import get_adapter
from shopman.shop.services import lead_time as lead_time_service
from shopman.shop.services.order_helpers import get_commitment_date

logger = logging.getLogger(__name__)


def hold(order, *, require_all: bool = False) -> None:
    """
    Reserve stock for all order items, expanding bundles.

    Strategy:
      1. Look up session holds tagged with order.session_key (created by
         services.availability.reserve at cart-add time), indexed per SKU as
         a FIFO list of `(hold_id, qty)` pairs.
      2. For each order component, consume holds from the bucket until the
         component's required qty is met (possibly adopting multiple holds).
      3. Create a fresh hold via the adapter for any unmet remainder (POS,
         marketplace, reorder, or partial session coverage).
      4. Release any session holds not consumed (e.g. items removed before
         checkout that weren't reconciled on the cart side).

    Saves the resulting hold_ids in order.data["hold_ids"]. SYNC.

    Idempotente: se ``order.data["hold_ids"]`` já existe, a fase já rodou (gate de
    commit em transação, re-dispatch de on_commit após falha parcial, comando de
    diagnóstico). Reexecutar sobrescreveria a chave e deixaria os holds da 1ª passada
    órfãos — dupla reserva até o backstop de 48h. A presença da chave (não seu valor)
    é o sinal de "já executou".

    ``require_all=True`` (gate de commit, ``lifecycle.secure_stock``): componente
    rastreado sem reserva possível levanta ``ValidationError(insufficient_stock)``
    em vez do caminho brando (alerta + continue). Chamado DENTRO da transação do
    ``CommitService._do_commit`` — a exceção desfaz o pedido inteiro, e é isso que
    impede o oversell: o ``select_for_update`` de Quant no Stockman serializa os
    commits concorrentes do mesmo SKU, e quem chega sem estoque falha ANTES do
    pedido existir.

    Dois gates de política de canal vivem aqui, no mesmo molde do
    ``insufficient_stock`` (falha limpa no require_all: sem pedido, sem hold;
    alerta de operador no caminho brando):

    - ``unknown_sku``: SKU fora do CATÁLOGO em canal com
      ``stock.allow_untracked=False`` — typo de SKU não pode virar pedido sem
      reserva. Produto que existe no catálogo mas não é rastreado pelo
      Stockman segue passando como untracked.
    - ``lead_time``: registro de DEMANDA (encomenda para data sem fornada
      planejada) para data mais cedo que ``lead_time.earliest_allowed_date``.
      Encomenda com Quant planejado da data segue valendo (o hold ancora no
      plano e o gate nem dispara); venda imediata de estoque de hoje idem.
    """
    if "hold_ids" in (order.data or {}):
        logger.info("stock.hold: skip (holds já criados) order=%s", order.ref)
        return

    items = order.snapshot.get("items", [])
    if not items:
        return

    target_date = get_commitment_date(order)
    adopt_session_holds = target_date in (None, timezone.localdate())
    # Encomenda: pedido para data FUTURA não adota os holds da sacola (eles
    # miram a produção de HOJE) — reserva na data-alvo, e quando não há plano
    # para ela o canal com preorder REGISTRA A DEMANDA (hold quant=None) em
    # vez de recusar. Os holds de hoje da sessão caem no leftover-release no
    # fim desta função. Produto pausado continua recusando (gate do Stockman).
    allow_demand = (
        not adopt_session_holds
        and target_date is not None
        and _channel_allows_preorder(order)
    )
    allow_untracked = _channel_allows_untracked(order)
    session_key = getattr(order, "session_key", None)
    session_holds_by_sku = _load_session_holds(session_key) if session_key else {}

    adapter = get_adapter("stock")
    hold_ids: list[dict] = []

    # Prior availability decisions (from _check_availability at on_commit).
    # Keyed by item SKU. Empty for channels that skip the availability gate (e.g. POS).
    prior_decisions = {
        d["sku"]: d
        for d in (order.data or {}).get("availability_decision", {}).get("decisions", [])
        if d.get("sku")
    }

    for item in items:
        if (item.get("meta") or {}).get("non_production") or (item.get("meta") or {}).get("type") == "delivery_fee":
            continue
        sku = item["sku"]
        qty = Decimal(str(item["qty"]))

        # Expand bundles into components
        components = _expand_if_bundle(sku, qty)

        for comp in components:
            comp_sku = comp["sku"]
            comp_qty = Decimal(str(comp["qty"]))

            # SKUs not tracked by Stockman need no hold — skip silently.
            # Exceção (canal gated): SKU fora do CATÁLOGO não pode virar
            # pedido sem reserva quando stock.allow_untracked=False.
            if _is_untracked(comp_sku, prior_decisions, adapter):
                if not allow_untracked and not _sku_known_to_catalog(comp_sku):
                    if require_all:
                        raise _unknown_sku_error(item, comp_sku)
                    # Pedido já existe (caminho brando pós-commit, ex.: canal
                    # externo) — não dá para recusar; alertar o operador.
                    _alert_unknown_sku(order, comp_sku)
                hold_ids.append({"sku": comp_sku, "hold_id": None, "qty": 0, "untracked": True})
                continue

            # 1) Adopt session holds by quantity until comp_qty is met.
            if adopt_session_holds:
                adopted_pairs, unmet_qty, overshoot_ids = _adopt_holds_for_qty(
                    session_holds_by_sku, comp_sku, comp_qty,
                )
                # Release surplus holds (holds beyond the one that covered
                # the requirement).
                if overshoot_ids:
                    adapter.release_holds(overshoot_ids)
            else:
                adopted_pairs, unmet_qty = [], comp_qty
            for hid, hqty in adopted_pairs:
                _retag_hold_for_order(hid, order.ref)
                hold_ids.append(
                    {"sku": comp_sku, "hold_id": hid, "qty": float(hqty)}
                )

            if unmet_qty <= 0:
                continue

            # Lead time (política de encomenda): registrar DEMANDA só dentro
            # da antecedência do produto/canal. O plano da data segue valendo:
            # com Quant planejado o create_hold ancora nele e sucede — o gate
            # só morde quando a reserva viraria demanda (quant=None).
            comp_allow_demand = allow_demand
            lead_time_earliest = None
            if allow_demand and target_date is not None:
                channel_ref = getattr(order, "channel_ref", None)
                earliest = lead_time_service.earliest_allowed_date(comp_sku, channel_ref)
                if target_date < earliest:
                    comp_allow_demand = False
                    lead_time_earliest = earliest

            # 2) Fallback: create a fresh hold via the adapter for the remainder.
            # channel_ref aplica o escopo de POSIÇÕES do canal (excluded_positions,
            # ex.: D-1 staff-only). apply_safety_margin=False: a margem é buffer
            # de vitrine — um pedido JÁ commitado pode consumi-la.
            result = adapter.create_hold(
                sku=comp_sku,
                qty=unmet_qty,
                reference=f"order:{order.ref}",
                target_date=target_date,
                channel_ref=getattr(order, "channel_ref", None),
                apply_safety_margin=False,
                allow_demand=comp_allow_demand,
                priority=_ORDER_HOLD_PRIORITY,
            )
            if not result.get("success"):
                logger.warning(
                    "stock.hold: create_hold failed sku=%s qty=%s code=%s",
                    comp_sku, unmet_qty, result.get("error_code"),
                )
                if require_all:
                    if lead_time_earliest is not None and _sku_known_to_catalog(comp_sku):
                        # Sem plano para a data E demanda barrada por lead time:
                        # recusa limpa com a primeira data possível.
                        raise _lead_time_error(
                            order, item, comp_sku, lead_time_earliest
                        )
                    if _sku_known_to_catalog(comp_sku):
                        raise _insufficient_stock_error(
                            item, comp_sku, unmet_qty, result.get("error_code")
                        )
                    if not allow_untracked:
                        raise _unknown_sku_error(item, comp_sku)
                    # SKU fora do catálogo (sessão de integração/smoke): não há
                    # o que reservar — segue como untracked, sem travar o commit.
                    hold_ids.append(
                        {"sku": comp_sku, "hold_id": None, "qty": 0, "untracked": True}
                    )
                    continue
                _alert_hold_gap(
                    order, comp_sku, unmet_qty,
                    "lead_time" if lead_time_earliest is not None else result.get("error_code"),
                )
                continue

            hold_ids.append({
                "sku": comp_sku,
                "hold_id": result["hold_id"],
                "qty": float(unmet_qty),
            })

    # Any session holds left over (e.g. items removed before checkout without
    # calling availability.reconcile) — release.
    leftover_ids = [
        hid for pairs in session_holds_by_sku.values() for hid, _ in pairs
    ]
    if leftover_ids:
        adapter.release_holds(leftover_ids)

    order.data["hold_ids"] = hold_ids
    order.save(update_fields=["data", "updated_at"])

    logger.info("stock.hold: %d holds for order %s", len(hold_ids), order.ref)


def fulfill(order, *, pending_materialization_ok: bool = False) -> None:
    """
    Fulfill (decrement) all holds for the order.

    Uses adapter.fulfill_hold() which transparently handles the
    PENDING → CONFIRMED → FULFILLED state machine.

    ``pending_materialization_ok=True`` (ativação de encomenda): hold de
    DEMANDA ainda sem quant (fornada da data não materializou) não é erro —
    o receiver de ``holds_materialized`` completa a baixa quando o estoque
    existir. Sem a flag, HOLD_IS_DEMAND conta como falha (caminho de venda
    imediata, onde demanda pendente seria drift real).

    SYNC — must complete before notifying client.
    """
    hold_ids = (order.data or {}).get("hold_ids", [])
    if not hold_ids:
        return

    adapter = get_adapter("stock")
    errors = 0
    failed_skus: list[str] = []
    for entry in hold_ids:
        hold_id = entry.get("hold_id")
        if not hold_id:
            continue
        qty = Decimal(str(entry["qty"])) if entry.get("qty") is not None else None
        result = adapter.fulfill_hold(hold_id, qty=qty)
        if not result.get("success"):
            if pending_materialization_ok and result.get("error_code") == "HOLD_IS_DEMAND":
                logger.info(
                    "stock.fulfill: hold %s aguarda materialização (order=%s)",
                    hold_id, order.ref,
                )
                continue
            errors += 1
            failed_skus.append(str(entry.get("sku") or hold_id))
            logger.warning(
                "stock.fulfill: failed for %s: %s",
                hold_id, result.get("message"),
            )

    if errors:
        # Pedido pago/confirmado sem baixa de estoque é exatamente o drift que
        # o fechamento não enxerga — fail-loud, nunca só log.
        logger.error("stock.fulfill: %d errors for order %s", errors, order.ref)
        from shopman.shop.services.observability import create_operator_alert

        create_operator_alert(
            type="stock_fulfill_failed",
            severity="critical",
            message=(
                f"Baixa de estoque FALHOU para o pedido {order.ref} "
                f"({errors} item(ns): {', '.join(failed_skus) or 'ver logs'}). "
                "O estoque do sistema está acima do físico — conferir e ajustar."
            ),
            order_ref=order.ref,
            dedupe_key=f"stock_fulfill_failed:{order.ref}",
        )


def release(order) -> None:
    """
    Release all holds for the order (cancellation path).

    SYNC — immediate release.
    """
    hold_ids = (order.data or {}).get("hold_ids", [])
    if not hold_ids:
        return

    adapter = get_adapter("stock")
    ids = [entry.get("hold_id") for entry in hold_ids if entry.get("hold_id")]
    if ids:
        adapter.release_holds(ids)


def revert_fulfilled(order) -> None:
    """Devolve ao ledger o estoque de holds já FULFILLED (cancelamento tardio).

    PDV baixa estoque no ato da venda; um cancel na janela de arrependimento
    chega DEPOIS do fulfill — ``release`` é no-op e o sistema ficaria abaixo
    do físico. Devolve exatamente as quantidades baixadas via RETURN move.

    SYNC — roda no on_cancelled. IDEMPOTENTE: marca os holds já revertidos em
    ``order.data['reverted_hold_ids']`` para nunca devolver o mesmo estoque
    duas vezes (o RETURN move não muda o status do hold, então sem essa marca
    um on_cancelled re-disparado creditaria o estoque de novo).
    """
    hold_ids = (order.data or {}).get("hold_ids", [])
    if not hold_ids:
        return

    already = set((order.data or {}).get("reverted_hold_ids") or [])
    adapter = get_adapter("stock")
    reverted: list[str] = []
    for entry in hold_ids:
        hold_id = entry.get("hold_id")
        qty = entry.get("qty")
        if not hold_id or not qty or hold_id in already:
            continue
        try:
            if adapter.return_fulfilled_hold(
                hold_id,
                Decimal(str(qty)),
                reference=f"cancel:{order.ref}",
                reason=f"Cancelamento pós-baixa do pedido {order.ref}",
            ):
                reverted.append(hold_id)
        except Exception as exc:
            logger.warning(
                "stock.revert_fulfilled: failed sku=%s order=%s: %s",
                entry.get("sku"), order.ref, exc,
            )

    if reverted:
        data = dict(order.data or {})
        data["reverted_hold_ids"] = list(already | set(reverted))
        order.data = data
        order.save(update_fields=["data", "updated_at"])


def revert(order) -> None:
    """
    Revert stock for returned items (receive back into inventory).

    SYNC — devolução ao estoque.
    """
    adapter = get_adapter("stock")
    if not adapter:
        return

    for item in order.items.all():
        if (item.meta or {}).get("non_production") or (item.meta or {}).get("type") == "delivery_fee":
            continue
        try:
            adapter.receive_return(
                sku=item.sku,
                qty=item.qty,
                reference=f"return:{order.ref}",
            )
        except Exception as exc:
            logger.warning(
                "stock.revert: failed for sku=%s order=%s: %s",
                item.sku, order.ref, exc,
            )


# ── helpers ──


def _sku_known_to_catalog(sku: str) -> bool:
    """True quando o SKU existe no contrato de catálogo (offering).

    O gate de commit só pode exigir reserva de algo que o catálogo conhece;
    SKUs sintéticos (smoke de gateway, sessões de integração) não têm o que
    reservar. Fail-closed: se o contrato não responde, exigimos a reserva.
    """
    from shopman.stockman.adapters.sku_validation import get_sku_validator

    try:
        return get_sku_validator().get_sku_info(sku) is not None
    except Exception:
        logger.debug("stock._sku_known_to_catalog degraded sku=%s", sku, exc_info=True)
        return True


def _insufficient_stock_error(item: dict, comp_sku: str, qty, error_code):
    """ValidationError do gate de commit — o CommitService trata como falha
    conhecida (idempotency key vira failed) e a superfície mapeia para erro
    de checkout amigável (``checkout.map_checkout_error``)."""
    from shopman.orderman.exceptions import ValidationError

    display = item.get("name") or item.get("sku") or comp_sku
    return ValidationError(
        code="insufficient_stock",
        message=(
            f"{display} ficou indisponível antes de concluirmos a sua reserva. "
            "Ajuste o carrinho e tente novamente, por favor."
        ),
        context={
            "sku": item.get("sku") or comp_sku,
            "component_sku": comp_sku,
            "requested_qty": str(qty),
            "error_code": error_code or "",
        },
    )


def _unknown_sku_error(item: dict, comp_sku: str):
    """ValidationError do gate ``allow_untracked=False`` — mesmo dialeto do
    ``insufficient_stock``: o CommitService desfaz a transação (sem pedido,
    sem hold) e a superfície mapeia via ``checkout.map_checkout_error``."""
    from shopman.orderman.exceptions import ValidationError

    display = item.get("name") or item.get("sku") or comp_sku
    return ValidationError(
        code="unknown_sku",
        message=(
            f"{display} não está no nosso catálogo. "
            "Confira o item e tente novamente, por favor."
        ),
        context={
            "sku": item.get("sku") or comp_sku,
            "component_sku": comp_sku,
        },
    )


def _lead_time_error(order, item: dict, comp_sku: str, earliest):
    """ValidationError do gate de lead time — demanda para data mais cedo que a
    antecedência do produto/canal. Mensagem omotenashi com a primeira data
    possível; mesmo dialeto do ``insufficient_stock``."""
    from shopman.orderman.exceptions import ValidationError

    display = item.get("name") or item.get("sku") or comp_sku
    hours = lead_time_service.effective_lead_time_hours(
        comp_sku, getattr(order, "channel_ref", None)
    )
    return ValidationError(
        code="lead_time",
        message=(
            f"{display} precisa de {hours}h de antecedência — "
            f"primeira data possível: {earliest.strftime('%d/%m')}."
        ),
        context={
            "sku": item.get("sku") or comp_sku,
            "component_sku": comp_sku,
            "lead_time_hours": hours,
            "earliest_allowed_date": earliest.isoformat(),
        },
    )


def _alert_unknown_sku(order, sku: str) -> None:
    """Pedido já commitado (caminho brando) carregou SKU fora do catálogo em
    canal gated — o operador precisa saber que não há reserva possível."""
    from shopman.shop.services.observability import create_operator_alert

    create_operator_alert(
        type="stock_unknown_sku",
        severity="warning",
        message=(
            f"Pedido {order.ref} contém SKU fora do catálogo ({sku}) em canal "
            "que não permite item sem reserva. Conferir o pedido."
        ),
        order_ref=order.ref,
        dedupe_key=f"stock_unknown_sku:{order.ref}:{sku}",
    )


def _alert_hold_gap(order, sku: str, qty, error_code) -> None:
    """Pedido commitado sem reserva para um item — operador precisa saber."""
    from shopman.shop.services.observability import create_operator_alert

    create_operator_alert(
        type="stock_hold_gap",
        severity="warning",
        message=(
            f"Pedido {order.ref} ficou SEM reserva de estoque para {qty}× {sku} "
            f"({error_code or 'sem código'}). O item pode faltar na separação."
        ),
        order_ref=order.ref,
        dedupe_key=f"stock_hold_gap:{order.ref}:{sku}",
    )


def _expand_if_bundle(sku: str, qty: Decimal) -> list[dict]:
    """Expand bundle into components. Returns single-item list if not a bundle."""
    try:
        catalog = get_adapter("catalog")
        return catalog.expand_bundle(sku, qty)
    except Exception as exc:
        if getattr(exc, "code", "") == "NOT_A_BUNDLE":
            return [{"sku": sku, "qty": qty}]
        logger.exception("stock._expand_if_bundle: unexpected error expanding sku=%s", sku)
        return [{"sku": sku, "qty": qty}]


def _load_session_holds(session_key: str) -> dict[str, list[tuple[str, Decimal]]]:
    """Index active session holds by SKU, preserving (hold_id, qty) pairs.

    Returns {sku: [(hold_id, qty), ...]} for holds tagged with the given
    session_key that are still in PENDING/CONFIRMED state. Order within a
    bucket is FIFO (by Hold.pk).
    """
    adapter = get_adapter("stock")
    holds = adapter.find_holds_by_reference(session_key)
    indexed: dict[str, list[tuple[str, Decimal]]] = {}
    for hold_id, sku, qty in holds:
        indexed.setdefault(sku, []).append((hold_id, qty))
    return indexed


def _adopt_holds_for_qty(
    indexed: dict[str, list[tuple[str, Decimal]]],
    sku: str,
    required_qty: Decimal,
) -> tuple[list[tuple[str, Decimal]], Decimal, list[str]]:
    """Consume session holds for `sku` until `required_qty` is met.

    Returns `(adopted_pairs, unmet_qty, overshoot_ids)`:
    - `adopted_pairs`: holds adopted for this order (may over-cover qty).
    - `unmet_qty`: qty not covered by adopted holds; caller creates a fresh
      hold for exactly this amount.
    - `overshoot_ids`: surplus holds beyond what's needed, to be released.

    When a single hold exceeds the remaining requirement, it is adopted whole
    — the over-reservation is benign and avoids splitting (which would need a
    new Stockman API).  Any *subsequent* holds in the bucket are released.
    """
    bucket = indexed.get(sku, [])
    adopted: list[tuple[str, Decimal]] = []
    remaining = required_qty
    overshoot_ids: list[str] = []

    while bucket and remaining > 0:
        hid, hqty = bucket.pop(0)
        if hqty <= remaining:
            adopted.append((hid, hqty))
            remaining -= hqty
        else:
            # Hold exceeds remaining — adopt it whole (benign over-reservation),
            # mas registrar SÓ a qty do pedido: é ela que o fulfill baixa.
            # Registrar a qty do hold baixaria mais estoque que a venda.
            adopted.append((hid, remaining))
            remaining = Decimal("0")
            # Release any subsequent holds — they're surplus.
            while bucket:
                hid2, _ = bucket.pop(0)
                overshoot_ids.append(hid2)
            break

    unmet = remaining if remaining > 0 else Decimal("0")
    return adopted, unmet, overshoot_ids


# TTL de backstop do hold adotado por um pedido: longo o bastante para o PIX
# mais lento (e a confirmação do operador) NÃO expirar a reserva, mas finito —
# um pedido que trava sem fulfill/release (worker morto, canal manual
# abandonado) não pode reter estoque para sempre. release_expired reclama depois.
_ORDER_HOLD_BACKSTOP_HOURS = 48

# Prioridade de materialização (planning.realize): pedido ENVIADO materializa
# antes de reserva de sacola quando a fornada é menor que a demanda (decisão
# de produto — AVAILABILITY-SALE-PRODUCTION-PLAN §2). Menor = primeiro;
# holds sem priority (sacola) vêm depois, FIFO.
_ORDER_HOLD_PRIORITY = 0


def _retag_hold_for_order(hold_id: str, order_ref: str) -> None:
    """Update Hold.metadata.reference from session_key to order ref.

    This is bookkeeping so the hold can be discovered later via
    `release_holds_for_reference("order:<ref>")` if needed.

    Estende o TTL de carrinho para um backstop longo (não ``None``): o dono
    passa a ser o pedido e o ciclo normal termina por fulfill/release; mas se
    o pedido travar sem resolução, o hold ainda expira e devolve o estoque.
    """
    from datetime import timedelta

    adapter = get_adapter("stock")
    adapter.retag_hold_reference(hold_id, f"order:{order_ref}", priority=_ORDER_HOLD_PRIORITY)
    backstop = timezone.now() + timedelta(hours=_ORDER_HOLD_BACKSTOP_HOURS)
    adapter.extend_hold(hold_id, expires_at=backstop)


def _channel_allows_preorder(order) -> bool:
    """True quando o canal do pedido aceita encomenda (ChannelConfig.stock.preorder)."""
    from shopman.shop.config import ChannelConfig

    try:
        return bool(ChannelConfig.for_channel(order.channel_ref).stock.preorder)
    except Exception:
        # Defaults aceitam encomenda; config ilegível não pode virar recusa
        # de venda (o gate de estoque do Stockman continua valendo).
        logger.warning(
            "stock._channel_allows_preorder: config lookup failed channel=%s",
            getattr(order, "channel_ref", None),
        )
        return bool(ChannelConfig().stock.preorder)


def _channel_allows_untracked(order) -> bool:
    """True quando o canal aceita SKU fora do catálogo sem reserva
    (``ChannelConfig.stock.allow_untracked``)."""
    from shopman.shop.config import ChannelConfig

    try:
        return bool(ChannelConfig.for_channel(order.channel_ref).stock.allow_untracked)
    except Exception:
        # Defaults permitem untracked; config ilegível não pode virar recusa
        # de venda (mesma postura do _channel_allows_preorder).
        logger.warning(
            "stock._channel_allows_untracked: config lookup failed channel=%s",
            getattr(order, "channel_ref", None),
        )
        return bool(ChannelConfig().stock.allow_untracked)


def _is_untracked(sku: str, prior_decisions: dict[str, dict], adapter) -> bool:
    """Return True if the SKU is not tracked by Stockman (no Quants exist).

    Checks the cached availability decision first; falls back to a direct
    query for channels that skip the availability gate (e.g. POS).
    """
    if sku in prior_decisions:
        d = prior_decisions[sku]
        return d.get("untracked", False) or d.get("source") == "stock.untracked"
    info = adapter.get_availability(sku)
    return not info.get("is_paused", False) and not info.get("is_tracked", bool(info.get("positions")))
