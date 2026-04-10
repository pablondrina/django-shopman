"""
ModifyService — Modifica sessões aplicando operações (ops).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction

from shopman.omniman import registry
from shopman.omniman.exceptions import SessionError, ValidationError
from shopman.omniman.ids import generate_line_id
from shopman.omniman.models import Directive, Session


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
    def _op_add_line(items: list[dict], data: dict, op: dict, session: Session) -> tuple[list[dict], dict]:
        if not op.get("sku"):
            raise ValidationError(code="missing_sku", message="SKU é obrigatório")
        qty = ModifyService._parse_positive_qty(op.get("qty"))

        if session.pricing_policy == "external" and "unit_price_q" not in op:
            raise ValidationError(
                code="missing_unit_price_q",
                message="unit_price_q é obrigatório quando pricing_policy=external",
            )

        line = {
            "line_id": generate_line_id(),
            "sku": op["sku"],
            "qty": qty,
            "meta": op.get("meta", {}),
        }
        if "unit_price_q" in op:
            line["unit_price_q"] = int(op["unit_price_q"])
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
                    item["unit_price_q"] = int(op["unit_price_q"])
                if "meta" in op:
                    item["meta"] = op["meta"]
                break
        else:
            raise ValidationError(code="unknown_line_id", message="line_id não encontrado")
        return items, data

    @staticmethod
    def _op_set_data(items: list[dict], data: dict, op: dict) -> tuple[list[dict], dict]:
        path = op["path"]
        value = op["value"]

        keys = path.split(".")
        target = data
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
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
