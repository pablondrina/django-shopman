"""
Catalog mutation facade — pausa/publica/preço por superfície + bulk.

Estratégia de projeção (ponte da Frente 1):
- **Célula única** → ``ListingItem.save()``: emite ``availability_changed`` /
  ``price_changed``; o auto-trigger enfileira a projeção só para superfícies com
  backend na registry canônica (as demais são no-op). Preserva history.
- **Bulk** (scoped a coleção/superfície/seleção) → ``queryset.update()`` (rápido,
  consistente com as bulk actions do admin) **+ reconciliação única** via
  ``CatalogService.project_listing`` quando a superfície é alvo de projeção
  (retract-aware, um reconcile em vez de N directives).

Escreve direto nos models do offerman (como as projections do backstage já leem).
Superfície = Channel; célula = ListingItem da listing de mesmo ref.
"""

from __future__ import annotations

from dataclasses import asdict

from shopman.backstage.services.exceptions import CatalogError


def _reconcile_if_projected(surface_ref: str) -> None:
    """Reconcilia a superfície (retract-aware) só se ela tem backend de projeção."""
    from shopman.offerman.conf import get_projection_backend

    if get_projection_backend(surface_ref) is None:
        return
    from shopman.offerman.exceptions import CatalogError as OffermanCatalogError
    from shopman.offerman.service import CatalogService

    try:
        CatalogService.project_listing(surface_ref)
    except OffermanCatalogError as exc:
        # Reconciliação é best-effort: a mutação no DB já valeu; a projeção externa
        # é retentada pelo auto-trigger/comando. Não derruba a operação do operador.
        raise CatalogError(f"Mudança aplicada, mas a sincronização falhou: {exc}") from exc


def _notify_surface(surface_ref: str) -> None:
    """Empurra o evento SSE da superfície (bulk não dispara post_save → menuboard)."""
    from shopman.shop.handlers._sse_emitters import emit_surface_changed

    emit_surface_changed(surface_ref)


# Sentinela "todos os canais" para as ações em lote (barra flutuante).
ALL_SURFACES = "*"


def _all_channel_refs() -> list[str]:
    from shopman.shop.models import Channel

    return list(Channel.objects.filter(is_active=True).order_by("display_order", "id").values_list("ref", flat=True))


def _is_showcase(surface_ref: str) -> bool:
    """A superfície é um Feed (menuboard/plataforma) e não um Canal transacional?"""
    from shopman.shop.models import Showcase

    return Showcase.objects.filter(ref=surface_ref).exists()


def set_cell(
    sku: str,
    surface_ref: str,
    *,
    is_published: bool | None = None,
    is_sellable: bool | None = None,
    price_q: int | None = None,
    actor: str = "",
):
    """Edita uma célula (produto × superfície). save() dispara o auto-trigger.

    Superfície de FEED (menuboard/plataforma) só aceita pausar/reativar: ``is_sellable``
    vira a pausa local do item (não há preço nem publicação — feed não transaciona).
    """
    if _is_showcase(surface_ref):
        from types import SimpleNamespace

        from shopman.backstage.services import showcase as showcase_service

        if is_sellable is None:
            raise CatalogError("Feed aceita apenas pausar/reativar (is_sellable).")
        showcase_service.set_item_paused(surface_ref, sku, paused=not is_sellable)
        # Duck-type com o que a API lê: feed está sempre "publicado", sem preço.
        return SimpleNamespace(is_published=True, is_sellable=bool(is_sellable), price_q=None)

    from shopman.offerman.models import ListingItem

    item = (
        ListingItem.objects.filter(listing__ref=surface_ref, product__sku=sku)
        .select_related("product", "listing")
        .order_by("min_qty")
        .first()
    )
    if item is None:
        raise CatalogError(f"Produto '{sku}' não está na superfície '{surface_ref}'.")

    if price_q is not None:
        if price_q < 0:
            raise CatalogError("Preço não pode ser negativo.")
        item.price_q = price_q
    if is_published is not None:
        item.is_published = is_published
    if is_sellable is not None:
        item.is_sellable = is_sellable

    item.save()
    return item


def set_product(
    sku: str,
    *,
    is_published: bool | None = None,
    is_sellable: bool | None = None,
    actor: str = "",
):
    """Pausa/publica o produto em TODOS os canais de uma vez ("globalzinho").

    Escreve no switch produto-level (``Product.is_sellable`` / ``is_published``),
    que gateia toda superfície. ``save()`` emite ``product_updated`` → o auto-trigger
    re-projeta o produto em cada listing alvo (retract-aware). Um único ponto de
    verdade; não itera célula por célula.
    """
    from shopman.offerman.models import Product

    product = Product.objects.filter(sku=sku).first()
    if product is None:
        raise CatalogError(f"Produto '{sku}' não encontrado.")

    if is_published is None and is_sellable is None:
        raise CatalogError("Nada a atualizar (informe is_published e/ou is_sellable).")
    if is_published is not None:
        product.is_published = is_published
    if is_sellable is not None:
        product.is_sellable = is_sellable

    product.save()
    return product


def bulk_set(
    skus: list[str],
    surface_ref: str,
    *,
    is_published: bool | None = None,
    is_sellable: bool | None = None,
    actor: str = "",
) -> int:
    """Aplica pausa/publicação em lote numa superfície e reconcilia uma vez.

    Retorna o número de células afetadas.
    """
    from shopman.offerman.models import ListingItem

    if not skus:
        return 0
    if surface_ref == ALL_SURFACES:
        return sum(
            bulk_set(skus, ref, is_published=is_published, is_sellable=is_sellable, actor=actor)
            for ref in _all_channel_refs()
        )
    if _is_showcase(surface_ref):
        # Feed: bulk só pausa/reativa (is_sellable). Sem preço/publicação.
        if is_sellable is None:
            raise CatalogError("Feed aceita apenas pausar/reativar (is_sellable).")
        from shopman.backstage.services import showcase as showcase_service

        return showcase_service.set_items_paused(surface_ref, skus, paused=not is_sellable)
    updates: dict[str, bool] = {}
    if is_published is not None:
        updates["is_published"] = is_published
    if is_sellable is not None:
        updates["is_sellable"] = is_sellable
    if not updates:
        raise CatalogError("Nada a atualizar (informe is_published e/ou is_sellable).")

    count = (
        ListingItem.objects.filter(listing__ref=surface_ref, product__sku__in=skus).update(**updates)
    )
    if count:
        _reconcile_if_projected(surface_ref)
        _notify_surface(surface_ref)
    return count


def bulk_set_collection(
    collection_ref: str,
    surface_ref: str,
    *,
    is_published: bool | None = None,
    is_sellable: bool | None = None,
    actor: str = "",
) -> int:
    """Bulk scoped a uma COLEÇÃO (manual ou smart) numa superfície.

    Resolve os produtos da coleção (regra ou explícitos) e aplica em lote.
    """
    from shopman.offerman.models import Collection

    coll = Collection.objects.filter(ref=collection_ref).first()
    if coll is None:
        raise CatalogError(f"Coleção '{collection_ref}' não encontrada.")
    skus = list(coll.product_queryset().values_list("sku", flat=True))
    return bulk_set(
        skus, surface_ref, is_published=is_published, is_sellable=is_sellable, actor=actor
    )


_PRICE_OPS = ("set", "pct", "delta")


def _apply_price_op(old_q: int, op: str, value: int) -> int:
    """Aplica a operação de preço a um valor em centavos (nunca negativo)."""
    from decimal import ROUND_HALF_UP, Decimal

    if op == "set":
        new_q = int(value)
    elif op == "pct":
        factor = Decimal(1) + (Decimal(value) / Decimal(100))
        new_q = int((Decimal(old_q) * factor).to_integral_value(rounding=ROUND_HALF_UP))
    else:  # delta
        new_q = old_q + int(value)
    return max(new_q, 0)


def bulk_price(
    skus: list[str],
    surface_ref: str,
    *,
    op: str,
    value: int,
    actor: str = "",
) -> int:
    """Reprecifica em lote o tier base de cada produto numa superfície.

    ``op``: ``set`` (preço absoluto, centavos) · ``pct`` (ajuste percentual, pontos
    +/-) · ``delta`` (ajuste absoluto, centavos +/-). Calcula em Python (arredonda),
    grava num único ``bulk_update`` e reconcilia uma vez (padrão do bulk).

    Reprecificação é PERMANENTE (muda o cardápio). Para promoção temporária, use o
    motor de regras (Happy Hour/D-1), não isto.
    """
    from shopman.offerman.models import ListingItem

    if op not in _PRICE_OPS:
        raise CatalogError(f"Operação de preço inválida: {op!r}.")
    if op == "set" and value < 0:
        raise CatalogError("Preço não pode ser negativo.")
    if not skus:
        return 0
    if surface_ref == ALL_SURFACES:
        return sum(bulk_price(skus, ref, op=op, value=value, actor=actor) for ref in _all_channel_refs())

    # tier base (menor min_qty) por SKU — 1 célula por produto, como a matriz mostra.
    items = (
        ListingItem.objects.filter(listing__ref=surface_ref, product__sku__in=skus)
        .select_related("product")
        .order_by("product__sku", "min_qty")
    )
    seen: set[str] = set()
    changed: list = []
    for item in items:
        sku = item.product.sku
        if sku in seen:
            continue
        seen.add(sku)
        new_q = _apply_price_op(item.price_q, op, value)
        if new_q != item.price_q:
            item.price_q = new_q
            changed.append(item)

    if changed:
        ListingItem.objects.bulk_update(changed, ["price_q"])
        _reconcile_if_projected(surface_ref)
        _notify_surface(surface_ref)
    return len(changed)


def bulk_price_collection(
    collection_ref: str,
    surface_ref: str,
    *,
    op: str,
    value: int,
    actor: str = "",
) -> int:
    """Reprecificação em lote scoped a uma COLEÇÃO (manual ou smart)."""
    from shopman.offerman.models import Collection

    coll = Collection.objects.filter(ref=collection_ref).first()
    if coll is None:
        raise CatalogError(f"Coleção '{collection_ref}' não encontrada.")
    skus = list(coll.product_queryset().values_list("sku", flat=True))
    return bulk_price(skus, surface_ref, op=op, value=value, actor=actor)


# ── detalhe do produto (edição completa no Gestor) ─────────────────────────────
# O painel de produto da matriz edita UM produto inteiro sem passar pelo Admin:
# campos escalares, tabela nutricional, rotulagem (alérgenos/restrições), atributos
# sociais e classificação fiscal. Escreve com ``save()`` (nunca ``update()``) para
# preservar o gatilho de re-projeção (``Product._PROJECTABLE_FIELDS``) e valida com
# ``full_clean()``. Fora do escopo: componentes de bundle, pertencimento a coleções
# e listings — seguem no Admin.
#
# Os três blocos que moram em JSONField têm dono de schema próprio, e é o dono que
# valida e serializa (nunca escrevemos as sub-chaves na mão):
#   - nutrition_facts → offerman.nutrition.NutritionFacts (invariantes ANVISA)
#   - metadata['social'] → offerman.contrib.social.schema
#   - metadata['fiscal'] → fiscalman.classification

# Campos escalares editáveis, agrupados por tipo para o merge parcial.
_DETAIL_TEXT_FIELDS = (
    "name",
    "short_description",
    "long_description",
    "unit",
    "storage_tip",
    "ingredients_text",
    "image_url",
    "availability_policy",
)
_DETAIL_INT_FIELDS = ("base_price_q",)
_DETAIL_NULLABLE_INT_FIELDS = ("unit_weight_g", "shelf_life_days", "production_cycle_hours")
_DETAIL_BOOL_FIELDS = ("is_published", "is_sellable", "is_batch_produced")

# Rotulagem de compra remota: o cliente não pega o produto na mão, então alérgenos,
# restrições, porção e medidas precisam estar escritos. Vivem em ``metadata``.
_DETAIL_META_LIST_FIELDS = ("allergens", "dietary_info")
_DETAIL_META_TEXT_FIELDS = ("serves", "approx_dimensions")


def _get_product(sku: str):
    from shopman.offerman.models import Product

    product = Product.objects.filter(sku=sku).first()
    if product is None:
        raise CatalogError(f"Produto '{sku}' não encontrado.")
    return product


def _nutrition_payload(product) -> dict:
    """Tabela nutricional como dict simples (chaves da dataclass, sem None)."""
    from dataclasses import asdict

    from shopman.offerman.nutrition import NutritionFacts

    facts = NutritionFacts.from_dict(product.nutrition_facts or {})
    return asdict(facts) if facts is not None else asdict(NutritionFacts())


def _fiscal_payload(product) -> dict:
    from dataclasses import asdict

    from shopman.fiscalman.classification import from_metadata

    return asdict(from_metadata(product.metadata))


def _fiscal_profile_choices() -> list[dict]:
    """Perfis fiscais disponíveis — a dataclass é a fonte, não uma lista no Nuxt."""
    from shopman.fiscalman.classification import FISCAL_PROFILES

    return [
        {"key": p.key, "name": p.name, "requires_cest": p.requires_cest}
        for p in FISCAL_PROFILES.values()
    ]


def _social_attrs_payload(product) -> dict:
    from dataclasses import asdict

    from shopman.offerman.contrib.social.schema import get_social_attributes

    return asdict(get_social_attributes(product))


def _detail_payload(product) -> dict:
    """Projection do detalhe: campos editáveis + contexto somente-leitura."""
    primary = next((ci for ci in product.collection_items.all() if ci.is_primary), None)
    metadata = product.metadata or {}
    return {
        "sku": product.sku,
        "name": product.name,
        "short_description": product.short_description,
        "long_description": product.long_description,
        "keywords": sorted(product.keywords.names()),
        "base_price_q": product.base_price_q,
        "unit": product.unit,
        "unit_weight_g": product.unit_weight_g,
        "availability_policy": product.availability_policy,
        "shelf_life_days": product.shelf_life_days,
        "storage_tip": product.storage_tip,
        "production_cycle_hours": product.production_cycle_hours,
        "is_batch_produced": product.is_batch_produced,
        "is_published": product.is_published,
        "is_sellable": product.is_sellable,
        "ingredients_text": product.ingredients_text,
        "image_url": product.image_url,
        # rotulagem de compra remota (metadata)
        "allergens": list(metadata.get("allergens") or []),
        "dietary_info": list(metadata.get("dietary_info") or []),
        "serves": str(metadata.get("serves") or ""),
        "approx_dimensions": str(metadata.get("approx_dimensions") or ""),
        "allows_next_day_sale": bool(metadata.get("allows_next_day_sale", False)),
        "nutrition_facts": _nutrition_payload(product),
        "social": _social_attrs_payload(product),
        "fiscal": _fiscal_payload(product),
        "primary_collection": primary.collection.ref if primary else "",
        "primary_collection_name": primary.collection.name if primary else "",
        # somente-leitura: o painel avisa que o dado veio da receita e que editar
        # à mão congela a derivação (ver ``dietary_from_recipe``).
        "dietary_auto_filled": bool(metadata.get("dietary_auto_filled", True)),
        "nutrition_auto_filled": bool((product.nutrition_facts or {}).get("auto_filled", False)),
        "fiscal_profiles": _fiscal_profile_choices(),
    }


def get_product_detail(sku: str) -> dict:
    """Todos os campos editáveis de um produto (para o painel do Gestor)."""
    return _detail_payload(_get_product(sku))


def _as_nullable_int(value, label: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise CatalogError(f"{label} deve ser um número inteiro.") from exc


def _as_str_list(value, label: str) -> list[str]:
    if not isinstance(value, list):
        raise CatalogError(f"{label} deve ser uma lista.")
    return [str(item).strip() for item in value if str(item).strip()]


def _apply_nutrition(product, raw) -> None:
    """Grava a tabela nutricional. As invariantes ANVISA são do ``Product.clean()``."""
    from dataclasses import fields as dataclass_fields

    from shopman.offerman.nutrition import NutritionFacts

    if not isinstance(raw, dict):
        raise CatalogError("nutrition_facts deve ser um objeto.")

    # A dataclass é a fonte dos nutrientes aceitos; ``auto_filled`` é sentinel
    # interno e nunca vem do operador.
    accepted = {f.name: f.type for f in dataclass_fields(NutritionFacts) if f.name != "auto_filled"}

    collected: dict = {}
    for key in accepted:
        if key not in raw:
            continue
        value = raw.get(key)
        if value in (None, ""):
            continue
        try:
            collected[key] = int(value) if "int" in str(accepted[key]) else float(value)
        except (TypeError, ValueError) as exc:
            raise CatalogError(f"{key} deve ser um número.") from exc

    # Editar à mão desliga a derivação a partir da receita — senão o próximo save
    # da Recipe sobrescreveria em silêncio o que o operador acabou de digitar.
    if collected:
        collected["auto_filled"] = False
    product.nutrition_facts = collected


def _apply_labelling(product, data: dict) -> None:
    """Alérgenos, restrições, porção e medidas — tudo em ``metadata``."""
    metadata = dict(product.metadata or {})
    original = dict(product.metadata or {})

    for field in _DETAIL_META_LIST_FIELDS:
        if field in data:
            values = _as_str_list(data.get(field), field)
            if values:
                metadata[field] = values
            else:
                metadata.pop(field, None)
    for field in _DETAIL_META_TEXT_FIELDS:
        if field in data:
            value = str(data.get(field) or "").strip()
            if value:
                metadata[field] = value
            else:
                metadata.pop(field, None)
    if "allows_next_day_sale" in data:
        metadata["allows_next_day_sale"] = bool(data.get("allows_next_day_sale"))

    # Mesmo sentinel do form do Admin: só congela a derivação quando a rotulagem
    # dietética REALMENTE mudou, para um save qualquer não travar a receita.
    touched_dietary = "allergens" in data or "dietary_info" in data
    if touched_dietary:
        changed = (metadata.get("allergens") or []) != (original.get("allergens") or []) or (
            metadata.get("dietary_info") or []
        ) != (original.get("dietary_info") or [])
        if changed and (metadata.get("allergens") or metadata.get("dietary_info")):
            metadata["dietary_auto_filled"] = False

    product.metadata = metadata


def _apply_social(product, raw) -> None:
    from shopman.offerman.contrib.social.schema import (
        ProductSocialAttributes,
        get_social_attributes,
        set_social_attributes,
    )

    if not isinstance(raw, dict):
        raise CatalogError("social deve ser um objeto.")

    current = get_social_attributes(product)
    merged = {**asdict(current), **raw}
    attrs = ProductSocialAttributes(
        brand=str(merged.get("brand") or "").strip(),
        gtin=str(merged.get("gtin") or "").strip(),
        mpn=str(merged.get("mpn") or "").strip(),
        condition=str(merged.get("condition") or "new"),
        google_product_category=str(merged.get("google_product_category") or "").strip(),
        tiktok_category_id=str(merged.get("tiktok_category_id") or "").strip(),
        hashtags=merged.get("hashtags") or [],
        social_caption=str(merged.get("social_caption") or "").strip(),
    )
    problems = attrs.errors()
    if problems:
        raise CatalogError(problems[0])
    product.metadata = set_social_attributes(product.metadata, attrs)


def _apply_fiscal(product, raw) -> None:
    from shopman.fiscalman.classification import (
        ProductFiscalClassification,
        from_metadata,
        to_metadata_fiscal,
    )

    if not isinstance(raw, dict):
        raise CatalogError("fiscal deve ser um objeto.")

    current = from_metadata(product.metadata)
    merged = {**asdict(current), **raw}
    classification = ProductFiscalClassification(
        profile=str(merged.get("profile") or "").strip(),
        ncm=str(merged.get("ncm") or "").strip(),
        cest=str(merged.get("cest") or "").strip(),
        unit=str(merged.get("unit") or "UN").strip() or "UN",
    )

    metadata = dict(product.metadata or {})
    # Classificação vazia = produto ainda não fiscalizado; só validamos quando há
    # algo preenchido (mesma regra do form do Admin — o NFC-e é que cobra depois).
    if not classification.ncm and not classification.cest:
        metadata.pop("fiscal", None)
        product.metadata = metadata
        return

    problems = classification.errors()
    if problems:
        raise CatalogError(problems[0])
    metadata["fiscal"] = to_metadata_fiscal(classification)
    product.metadata = metadata


def update_product_detail(sku: str, data: dict, *, actor: str = "") -> dict:
    """Merge parcial dos campos do produto (chave ausente = sem mudança).

    Valida com ``full_clean()`` (inclui as invariantes ANVISA de nutrition_facts) e
    persiste com ``save()``, que emite ``product_updated`` quando um campo projetável
    muda — o auto-trigger re-projeta nas plataformas alvo. Os blocos em JSONField
    (nutricional, social, fiscal) são validados pelo dono do schema antes disso.
    """
    from django.core.exceptions import ValidationError

    product = _get_product(sku)

    for field in _DETAIL_TEXT_FIELDS:
        if field in data:
            setattr(product, field, str(data.get(field) or "").strip())
    for field in _DETAIL_INT_FIELDS:
        if field in data:
            value = _as_nullable_int(data.get(field), field)
            if value is None:
                raise CatalogError(f"{field} é obrigatório.")
            setattr(product, field, value)
    for field in _DETAIL_NULLABLE_INT_FIELDS:
        if field in data:
            setattr(product, field, _as_nullable_int(data.get(field), field))
    for field in _DETAIL_BOOL_FIELDS:
        if field in data:
            setattr(product, field, bool(data.get(field)))

    if "nutrition_facts" in data:
        _apply_nutrition(product, data.get("nutrition_facts"))
    # Rotulagem e blocos de metadata em sequência: cada um lê o metadata já
    # atualizado pelo anterior, então não há escrita perdida.
    _apply_labelling(product, data)
    if "social" in data:
        _apply_social(product, data.get("social"))
    if "fiscal" in data:
        _apply_fiscal(product, data.get("fiscal"))

    try:
        product.full_clean()
    except ValidationError as exc:
        raise CatalogError(_first_validation_message(exc)) from exc

    product.save()

    if "keywords" in data:
        raw = data.get("keywords") or []
        if not isinstance(raw, list):
            raise CatalogError("keywords deve ser uma lista.")
        product.keywords.set([str(k).strip() for k in raw if str(k).strip()])

    product.refresh_from_db()
    return _detail_payload(product)


def _first_validation_message(exc) -> str:
    """Primeira mensagem legível de um ValidationError de campo (para o toast)."""
    messages = getattr(exc, "message_dict", None)
    if messages:
        for field, msgs in messages.items():
            if msgs:
                return f"{field}: {msgs[0]}"
    return "; ".join(exc.messages) if exc.messages else "Dados inválidos."


# ── assist de IA (sugestão POR CAMPO) ─────────────────────────────────────────
# O operador pede uma sugestão para UM campo e aceita ou descarta ela sozinha —
# não existe "gerar tudo". Por isso cada campo tem seu próprio prompt: pedir
# "descreva o produto" devolve o mesmo texto para a descrição curta, a longa e a
# legenda social, que são peças diferentes. O contexto do produto (nome, coleção,
# palavras-chave, campos já preenchidos) vai junto para a sugestão nascer coerente
# com o que já existe, em vez de genérica.

_AI_ASSIST_VOICE = (
    "Você escreve para a Nelson Boulangerie, uma padaria artesanal brasileira. "
    "Escreva em português do Brasil, na primeira pessoa do plural (\"nós\", \"conosco\"), "
    "nunca \"a gente\". Tom acolhedor e concreto, sem superlativo vazio, sem emoji e "
    "sem travessão (—). Responda APENAS com o texto do campo, sem aspas, sem rótulo "
    "e sem comentário."
)

# Um spec por campo assistível: o que pedir e quanto texto cabe na resposta.
_AI_ASSIST_FIELDS: dict[str, dict] = {
    "short_description": {
        "label": "descrição curta",
        "instruction": (
            "Escreva a descrição CURTA do produto: 1 a 2 frases, no máximo 200 caracteres, "
            "para listagens e vitrine. Destaque o que o cliente percebe (sabor, textura, "
            "método) em vez de repetir o nome do produto."
        ),
        "max_tokens": 300,
    },
    "long_description": {
        "label": "descrição longa",
        "instruction": (
            "Escreva a descrição COMPLETA da página do produto: 2 a 4 frases envolventes. "
            "Conte o método, os ingredientes que importam e quando esse produto cai bem. "
            "Não invente prêmios, origens, certificações nem prazos que não estejam no contexto."
        ),
        "max_tokens": 600,
    },
    "ingredients_text": {
        "label": "lista de ingredientes",
        "instruction": (
            "Escreva a lista de ingredientes em ordem decrescente de peso, como manda a "
            "ANVISA: nomes separados por vírgula, terminando em ponto final, sem quantidades "
            "e sem cabeçalho. Use apenas ingredientes plausíveis para este produto; se o "
            "contexto não permitir inferir com segurança, devolva a lista mais enxuta possível."
        ),
        "max_tokens": 300,
    },
    "social_caption": {
        "label": "legenda social",
        "instruction": (
            "Escreva a legenda para um post de Instagram/TikTok: 1 a 3 frases curtas, "
            "convidativas, que funcionem embaixo de uma foto do produto. Sem hashtags "
            "(elas têm campo próprio) e sem chamada para link na bio."
        ),
        "max_tokens": 400,
    },
    "hashtags": {
        "label": "hashtags",
        "instruction": (
            "Sugira de 5 a 8 hashtags relevantes para este produto em redes sociais, "
            "separadas por espaço, SEM o caractere '#' e sem vírgulas. Misture termos do "
            "produto, do método e da categoria. Exemplo de formato: paoartesanal fermentacaonatural padaria"
        ),
        "max_tokens": 200,
    },
}

ASSISTABLE_FIELDS: tuple[str, ...] = tuple(_AI_ASSIST_FIELDS)


def _ai_assist_context(product) -> str:
    """Contexto do produto para o prompt — só o que já está preenchido."""
    from shopman.offerman.contrib.social.schema import get_social_attributes

    social = get_social_attributes(product)
    primary = next((ci for ci in product.collection_items.all() if ci.is_primary), None)
    lines = [
        f"Nome do produto: {product.name}",
        f"SKU: {product.sku}",
    ]
    optional = (
        ("Coleção", primary.collection.name if primary else ""),
        ("Palavras-chave", ", ".join(sorted(product.keywords.names()))),
        ("Unidade de venda", product.unit),
        ("Peso por unidade (g)", product.unit_weight_g),
        ("Descrição curta atual", product.short_description),
        ("Descrição longa atual", product.long_description),
        ("Ingredientes atuais", product.ingredients_text),
        ("Dica de conservação", product.storage_tip),
        ("Marca", social.brand),
        ("Categoria Google", social.google_product_category),
        ("Legenda social atual", social.social_caption),
        ("Hashtags atuais", " ".join(social.hashtags)),
    )
    lines.extend(f"{label}: {value}" for label, value in optional if value)
    return "\n".join(lines)


def _ai_assist_prompt(product, field: str, current_value: str) -> str:
    """Prompt do campo: contexto do produto + a tarefa específica daquele campo."""
    spec = _AI_ASSIST_FIELDS[field]
    parts = [
        "Contexto do produto:",
        _ai_assist_context(product),
        "",
        f"Tarefa — campo \"{spec['label']}\":",
        spec["instruction"],
    ]
    if current_value.strip():
        parts += [
            "",
            "O campo já tem este texto. Proponha uma versão melhor, mantendo os fatos:",
            current_value.strip(),
        ]
    return "\n".join(parts)


def ai_assist_field(sku: str, field: str, current_value: str = "") -> str:
    """Sugestão de IA para UM campo de UM produto. Devolve o texto limpo.

    Levanta ``CatalogError`` (campo inválido / produto inexistente),
    ``AiAssistNotConfigured`` (sem ``AI_ASSIST_API_KEY`` → 503 na camada HTTP) ou
    ``AiAssistError`` (falha do provedor). ``hashtags`` volta como string separada
    por espaço — a superfície já normaliza texto livre em lista.
    """
    from django.conf import settings

    from shopman.backstage.services.exceptions import AiAssistError, AiAssistNotConfigured

    if field not in _AI_ASSIST_FIELDS:
        raise CatalogError(
            f"Campo '{field}' não aceita sugestão de IA. Assistíveis: {', '.join(ASSISTABLE_FIELDS)}."
        )

    api_key = (getattr(settings, "AI_ASSIST_API_KEY", "") or "").strip()
    if not api_key:
        raise AiAssistNotConfigured("AI assist não configurado. Defina AI_ASSIST_API_KEY.")

    provider = getattr(settings, "AI_ASSIST_PROVIDER", "anthropic")
    if provider != "anthropic":
        raise AiAssistError(f"Provedor de IA '{provider}' não suportado.")

    product = _get_product(sku)
    prompt = _ai_assist_prompt(product, field, current_value or "")

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    try:
        message = client.messages.create(
            model=getattr(settings, "AI_ASSIST_MODEL", "claude-opus-4-8"),
            max_tokens=_AI_ASSIST_FIELDS[field]["max_tokens"],
            system=_AI_ASSIST_VOICE,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as exc:
        raise AiAssistError(f"O assistente não respondeu: {exc}") from exc

    suggestion = "\n".join(
        block.text for block in message.content if getattr(block, "type", "") == "text"
    ).strip()
    if not suggestion:
        raise AiAssistError("O assistente devolveu uma sugestão vazia.")
    return suggestion


# ── reordenação (curadoria da vitrine) ─────────────────────────────────────────
# A ordem do cardápio vive em Collection.sort_order (seções) e CollectionItem.sort_order
# (produtos dentro da coleção). Storefront, menuboard e feeds usam essa ordem.


def reorder_collections(ordered_refs: list[str], *, actor: str = "") -> int:
    """Grava a ordem das coleções (Collection.sort_order) na sequência recebida."""
    from shopman.offerman.models import Collection

    if not ordered_refs:
        return 0
    colls = {c.ref: c for c in Collection.objects.filter(ref__in=ordered_refs)}
    changed = []
    for index, ref in enumerate(ordered_refs):
        coll = colls.get(ref)
        if coll is not None and coll.sort_order != index:
            coll.sort_order = index
            changed.append(coll)
    if changed:
        Collection.objects.bulk_update(changed, ["sort_order"])
    return len(changed)


def reorder_collection_items(collection_ref: str, ordered_skus: list[str], *, actor: str = "") -> int:
    """Grava a ordem dos produtos dentro de uma coleção MANUAL (CollectionItem.sort_order).

    Coleção por regra (smart) não tem ordem manual — a pertinência é por condição.
    """
    from shopman.offerman.models import Collection, CollectionItem

    coll = Collection.objects.filter(ref=collection_ref).first()
    if coll is None:
        raise CatalogError(f"Coleção '{collection_ref}' não encontrada.")
    if coll.is_smart:
        raise CatalogError("Coleção por regra não tem ordem manual.")
    if not ordered_skus:
        return 0

    items = {
        ci.product.sku: ci
        for ci in CollectionItem.objects.filter(collection=coll).select_related("product")
    }
    changed = []
    for index, sku in enumerate(ordered_skus):
        ci = items.get(sku)
        if ci is not None and ci.sort_order != index:
            ci.sort_order = index
            changed.append(ci)
    if changed:
        CollectionItem.objects.bulk_update(changed, ["sort_order"])
    return len(changed)


