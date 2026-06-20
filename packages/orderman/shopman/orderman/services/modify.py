"""
ModifyService — Modifica sessões aplicando operações (ops).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction
from shopman.orderman import registry
from shopman.orderman.exceptions import SessionError, ValidationError
from shopman.orderman.ids import generate_line_id
from shopman.orderman.models import Directive, Session


class ModifyService:
    """
    Serviço para modificar sessões aplicando operações (ops).

    Pipeline:
    1. Lock session (select_for_update)
    2. Apply ops
    3. Run modifiers
    4. Run validators (stage="draft")
    5. Increment rev
    6. Clear checks and issues
    7. Save session
    8. Enqueue directives (se necessário)
    """

    SUPPORTED_OPS = {
        "add_line",
        "remove_line",
        "set_qty",
        "replace_sku",
        "set_data",
        "merge_lines",
    }

    @staticmethod
    @transaction.atomic
    def modify_session(
        session_key: str,
        channel_ref: str,
        ops: list[dict],
        ctx: dict | None = None,
        channel_config: dict | None = None,
    ) -> Session:
        ctx = ctx or {}

        # 1. Lock session
        try:
            session = Session.objects.select_for_update().get(
                session_key=session_key,
                channel_ref=channel_ref,
            )
        except Session.DoesNotExist as exc:
            raise SessionError(
                code="not_found",
                message=f"Sessão não encontrada: {channel_ref}:{session_key}",
            ) from exc

        import types
        channel = types.SimpleNamespace(ref=channel_ref, config={})

        if session.state == "committed":
            raise SessionError(
                code="already_committed",
                message="Esta sessão já foi finalizada e não pode mais ser alterada.",
                context={"session_key": session_key, "channel": channel_ref},
            )
        if session.state == "abandoned":
            raise SessionError(
                code="already_abandoned",
                message="Esta sessão foi abandonada e não pode mais ser alterada.",
                context={"session_key": session_key, "channel": channel_ref},
            )

        if session.edit_policy == "locked":
            raise SessionError(
                code="locked",
                message=(
                    f"Pedidos do canal '{channel_ref}' não podem ser editados. "
                    "Este canal recebe pedidos prontos de uma plataforma externa."
                ),
                context={
                    "session_key": session_key,
                    "channel": channel_ref,
                    "edit_policy": session.edit_policy,
                },
            )

        # 2. Apply ops
        items = list(session.items)
        data = dict(session.data)

        for op in ops:
            items, data = ModifyService._apply_op(items, data, op, session)

        session.update_items(items)
        session.data = data

        # 3. Run modifiers (filtered by channel config)
        rules = (channel_config or {}).get("rules", {})
        allowed_modifiers = rules.get("modifiers")  # None = run all, [] = none

        # Infrastructure modifiers (pricing.*) always run
        INFRA_PREFIXES = ("pricing.",)

        for modifier in registry.get_modifiers():
            code = getattr(modifier, "code", "")
            is_infra = any(code.startswith(p) for p in INFRA_PREFIXES)
            if is_infra:
                modifier.apply(channel=channel, session=session, ctx=ctx)
            elif allowed_modifiers is None:
                # No rules.modifiers key → run all (backward compat)
                modifier.apply(channel=channel, session=session, ctx=ctx)
            elif code in allowed_modifiers:
                modifier.apply(channel=channel, session=session, ctx=ctx)

        # 4. Run validators (stage="draft", filtered by channel config)
        allowed_validators = rules.get("validators")  # None = run all, [] = none

        for validator in registry.get_validators(stage="draft"):
            code = getattr(validator, "code", "")
            if allowed_validators is None:
                validator.validate(channel=channel, session=session, ctx=ctx)
            elif code in allowed_validators:
                validator.validate(channel=channel, session=session, ctx=ctx)

        # 5. Increment rev
        session.rev += 1

        # 6. Clear checks and issues
        session.data["checks"] = {}
        session.data["issues"] = []

        # 7. Save session
        session.save()

        # 8. Enqueue directives for active checks
        check_codes = rules.get("checks", [])
        for check_code in check_codes:
            check = registry.get_check(check_code)
            if check:
                Directive.objects.create(
                    topic=check.topic,
                    payload={
                        "session_key": session.session_key,
                        "channel_ref": channel.ref,
                        "rev": session.rev,
                        "items": session.items,
                    },
                )

        return session

    @staticmethod
    @transaction.atomic
    def move_lines(
        *,
        from_session_key: str,
        to_session_key: str,
        channel_ref: str,
        line_ids: list[str],
    ) -> tuple[Session, Session]:
        """Move lines verbatim between two open sessions, freezing their price.

        Unlike ``modify_session`` (which re-runs pricing modifiers), this is a
        session-integrity operation: each moved line keeps its quoted
        ``unit_price_q``, ``line_total_q`` and ``meta`` exactly, so the customer
        pays what was quoted on the source comanda. Both sessions are locked and
        the move is atomic. Re-pricing is intentionally skipped; only the
        structural total is recomputed. Covers transfer (move some lines), split
        (target is a fresh session) and merge (move every line of B into A).
        """
        if from_session_key == to_session_key:
            raise ValidationError(
                code="same_session",
                message="Origem e destino não podem ser a mesma sessão.",
            )
        if not line_ids:
            raise ValidationError(code="no_line_ids", message="Nenhuma linha para mover.")

        # Lock both sessions in a deterministic order to avoid deadlocks.
        ordered_keys = sorted({from_session_key, to_session_key})
        locked = {
            session.session_key: session
            for session in (
                Session.objects.select_for_update().filter(
                    channel_ref=channel_ref,
                    session_key__in=ordered_keys,
                )
            )
        }
        source = locked.get(from_session_key)
        target = locked.get(to_session_key)
        for label, session in (("origem", source), ("destino", target)):
            if session is None:
                raise SessionError(
                    code="not_found",
                    message=f"Sessão de {label} não encontrada.",
                )
            if session.state != "open":
                raise SessionError(
                    code="not_open",
                    message=f"Sessão de {label} não está aberta.",
                    context={"session_key": session.session_key, "state": session.state},
                )
            if session.edit_policy == "locked":
                raise SessionError(
                    code="locked",
                    message=f"Sessão de {label} está bloqueada para edição.",
                    context={"session_key": session.session_key},
                )

        source_items = list(source.items)
        by_line_id = {item["line_id"]: item for item in source_items}
        missing = [line_id for line_id in line_ids if line_id not in by_line_id]
        if missing:
            raise ValidationError(
                code="unknown_line_id",
                message=f"line_id não encontrado na origem: {', '.join(missing)}",
                context={"missing": missing},
            )

        moving = set(line_ids)
        moved_lines = [
            {
                # New line_id: line_ids are unique per session, the price is what
                # carries over verbatim — never the identity.
                "line_id": generate_line_id(),
                "sku": src.get("sku", ""),
                "name": src.get("name", ""),
                "qty": src["qty"],
                "unit_price_q": int(src.get("unit_price_q", 0)),
                "line_total_q": int(src.get("line_total_q", 0)),
                "meta": src.get("meta", {}) or {},
            }
            for src in (by_line_id[line_id] for line_id in line_ids)
        ]

        source.update_items([item for item in source_items if item["line_id"] not in moving])
        target.update_items(list(target.items) + moved_lines)

        ModifyService._recompute_structural_total(source)
        ModifyService._recompute_structural_total(target)

        source.rev += 1
        target.rev += 1
        source.save()
        target.save()
        return source, target

    @staticmethod
    def _recompute_structural_total(session: Session) -> None:
        """Recompute the session total from stored line totals, without pricing.

        Mirrors the session-total modifier but never re-resolves item prices —
        used by ``move_lines`` to keep frozen line totals intact.
        """
        items = session.items
        if not session.pricing:
            session.pricing = {}
        session.pricing["total_q"] = sum(int(item.get("line_total_q", 0)) for item in items)
        session.pricing["items_count"] = len(items)

    @staticmethod
    def _apply_op(
        items: list[dict],
        data: dict,
        op: dict,
        session: Session,
    ) -> tuple[list[dict], dict]:
        op_type = op.get("op")

        if op_type not in ModifyService.SUPPORTED_OPS:
            raise ValidationError(
                code="unsupported_op",
                message=f"Operação não suportada: {op_type}",
            )

        if op_type == "add_line":
            return ModifyService._op_add_line(items, data, op, session)
        elif op_type == "remove_line":
            return ModifyService._op_remove_line(items, data, op)
        elif op_type == "set_qty":
            return ModifyService._op_set_qty(items, data, op)
        elif op_type == "replace_sku":
            return ModifyService._op_replace_sku(items, data, op, session)
        elif op_type == "set_data":
            return ModifyService._op_set_data(items, data, op)
        elif op_type == "merge_lines":
            return ModifyService._op_merge_lines(items, data, op)

        return items, data

    @staticmethod
    def _parse_positive_qty(value: Any) -> Decimal:
        try:
            qty = Decimal(str(value))
        except Exception as exc:
            raise ValidationError(code="invalid_qty", message="Quantidade inválida") from exc
        if qty <= 0:
            raise ValidationError(code="invalid_qty", message="Quantidade deve ser > 0")
        return qty

    @staticmethod
    def _parse_non_negative_price_q(value: Any) -> int:
        try:
            price = int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(code="invalid_unit_price_q", message="unit_price_q inválido") from exc
        if price < 0:
            raise ValidationError(code="invalid_unit_price_q", message="unit_price_q deve ser >= 0")
        return price

    @staticmethod
    def _op_add_line(items: list[dict], data: dict, op: dict, session: Session) -> tuple[list[dict], dict]:
        if not op.get("sku"):
            raise ValidationError(code="missing_sku", message="SKU é obrigatório")
        qty = ModifyService._parse_positive_qty(op.get("qty"))

        if session.pricing_policy == "external" and "unit_price_q" not in op:
            raise ValidationError(
                code="missing_unit_price_q",
                message="unit_price_q é obrigatório quando pricing_policy=external",
            )

        # line_id explícito é preservado (mesma semântica de Session.update_items:
        # `raw.get("line_id") or generate_line_id()`). Permite re-emitir uma linha
        # mantendo sua identidade durável — ex.: o PDV reconstrói a comanda no
        # fechamento sem perder o vínculo com o ticket de KDS já disparado.
        line = {
            "line_id": op.get("line_id") or generate_line_id(),
            "sku": op["sku"],
            "qty": qty,
            "meta": op.get("meta", {}),
        }
        name = str(op.get("name") or "").strip()
        if name:
            line["name"] = name
        if "unit_price_q" in op:
            line["unit_price_q"] = ModifyService._parse_non_negative_price_q(op["unit_price_q"])
        if op.get("is_d1"):
            line["is_d1"] = True
        items.append(line)
        return items, data

    @staticmethod
    def _op_remove_line(items: list[dict], data: dict, op: dict) -> tuple[list[dict], dict]:
        line_id = op["line_id"]
        if not any(item.get("line_id") == line_id for item in items):
            raise ValidationError(code="unknown_line_id", message="line_id não encontrado")
        items = [item for item in items if item["line_id"] != line_id]
        return items, data

    @staticmethod
    def _op_set_qty(items: list[dict], data: dict, op: dict) -> tuple[list[dict], dict]:
        line_id = op["line_id"]
        qty = ModifyService._parse_positive_qty(op.get("qty"))
        for item in items:
            if item["line_id"] == line_id:
                item["qty"] = qty
                # Clear line_total_q so _normalize_items recalculates it
                item.pop("line_total_q", None)
                break
        else:
            raise ValidationError(code="unknown_line_id", message="line_id não encontrado")
        return items, data

    @staticmethod
    def _op_replace_sku(items: list[dict], data: dict, op: dict, session: Session) -> tuple[list[dict], dict]:
        if not op.get("sku"):
            raise ValidationError(code="missing_sku", message="SKU é obrigatório")
        if session.pricing_policy == "external" and "unit_price_q" not in op:
            raise ValidationError(
                code="missing_unit_price_q",
                message="unit_price_q é obrigatório quando pricing_policy=external",
            )
        line_id = op["line_id"]
        for item in items:
            if item["line_id"] == line_id:
                item["sku"] = op["sku"]
                if "unit_price_q" in op:
                    item["unit_price_q"] = ModifyService._parse_non_negative_price_q(op["unit_price_q"])
                if "meta" in op:
                    item["meta"] = op["meta"]
                break
        else:
            raise ValidationError(code="unknown_line_id", message="line_id não encontrado")
        return items, data

    @staticmethod
    def _op_set_data(items: list[dict], data: dict, op: dict) -> tuple[list[dict], dict]:
        path = str(op["path"]).strip().lower()
        value = op["value"]

        keys = path.split(".")
        if any(not key for key in keys):
            raise ValidationError(code="invalid_data_path", message="Path de dados inválido")
        target = data
        for key in keys[:-1]:
            current = target.get(key)
            if current is None:
                target[key] = {}
                current = target[key]
            if not isinstance(current, dict):
                raise ValidationError(
                    code="invalid_data_path",
                    message=f"Path intermediário não é objeto: {key}",
                )
            target = target[key]
        target[keys[-1]] = value

        return items, data

    @staticmethod
    def _op_merge_lines(items: list[dict], data: dict, op: dict) -> tuple[list[dict], dict]:
        from_id = op["from_line_id"]
        into_id = op["into_line_id"]
        if from_id == into_id:
            raise ValidationError(code="invalid_merge", message="from_line_id e into_line_id devem ser diferentes")

        from_line = None
        into_line = None

        for item in items:
            if item["line_id"] == from_id:
                from_line = item
            elif item["line_id"] == into_id:
                into_line = item

        if from_line and into_line:
            if from_line.get("sku") != into_line.get("sku"):
                raise ValidationError(
                    code="sku_mismatch",
                    message="merge_lines exige que ambas linhas tenham o mesmo SKU",
                )
            into_qty = Decimal(str(into_line.get("qty", 0)))
            from_qty = Decimal(str(from_line.get("qty", 0)))
            if into_qty <= 0 or from_qty <= 0:
                raise ValidationError(code="invalid_qty", message="Quantidade deve ser > 0")
            into_line["qty"] = into_qty + from_qty
            items = [item for item in items if item["line_id"] != from_id]
        else:
            raise ValidationError(code="unknown_line_id", message="line_id não encontrado")

        return items, data
