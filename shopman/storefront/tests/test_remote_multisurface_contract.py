from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
REMOTE_MATRIX = REPO_ROOT / "docs" / "reference" / "remote-order-e2e-matrix.md"
REMOTE_PLAN = REPO_ROOT / "docs" / "plans" / "completed" / "REMOTE-MULTISURFACE-PLAN.md"
PARITY_CONTRACT = REPO_ROOT / "docs" / "reference" / "storefront-surface-parity-contract.md"
MANYCHAT_ADR = REPO_ROOT / "docs" / "decisions" / "adr-009-whatsapp-via-manychat.md"
HEADLESS_ADR = REPO_ROOT / "docs" / "decisions" / "adr-012-headless-surface-contract.md"
HEADLESS_CONTRACT = REPO_ROOT / "docs" / "reference" / "headless-surface-contract.md"
REMOTE_MUTATION_CONTRACT = REPO_ROOT / "docs" / "reference" / "remote-mutation-contract.md"
REMOTE_RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "pedido-remoto-preso.md"
NUXT_TYPES = REPO_ROOT / "surfaces" / "storefront-uithing-nuxt" / "app" / "types" / "shopman.ts"
NUXT_TRACKING_PAGE = REPO_ROOT / "surfaces" / "storefront-uithing-nuxt" / "app" / "pages" / "pedido" / "[ref]" / "index.vue"

ORDER_STATUSES = {
    "new",
    "confirmed",
    "preparing",
    "ready",
    "dispatched",
    "delivered",
    "completed",
    "cancelled",
    "returned",
}

PAYMENT_STATUSES = {
    "pending",
    "authorized",
    "captured",
    "failed",
    "cancelled",
    "refunded",
}

REMOTE_SCENARIOS = {
    "REMOTE-PICKUP-CASH-IMMEDIATE",
    "REMOTE-PICKUP-PIX-AT-COMMIT",
    "REMOTE-PICKUP-PIX-POST-COMMIT",
    "REMOTE-DELIVERY-CARD-AUTH",
    "REMOTE-DELIVERY-EXTERNAL-MARKETPLACE",
    "REMOTE-WA-PREORDER-PLANNED",
    "REMOTE-WA-ACCESS-LINK-CHECKOUT",
    "REMOTE-OOS-RECOVERY",
    "REMOTE-LOW-STOCK-HOLD",
    "REMOTE-HOLD-EXPIRED",
    "REMOTE-PAYMENT-TIMEOUT",
    "REMOTE-CANCEL-ALLOWED",
    "REMOTE-CANCEL-BLOCKED",
    "REMOTE-RATING",
    "REMOTE-REORDER",
    "REMOTE-POS-COUNTER",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_remote_e2e_matrix_declares_channels_surfaces_and_scenarios():
    matrix = _read(REMOTE_MATRIX)

    for token in [
        "Orderman",
        "Payman",
        "Stockman",
        "Guestman",
        "Doorman",
        "ChannelConfig",
        "Directives",
        "Nuxt",
        "Ionic",
        "ManyChat",
        "Django/Penguin",
        "`web`",
        "`whatsapp`",
        "`mobile`",
        "`pdv`",
        "`ifood`/marketplace",
    ]:
        assert token in matrix

    for scenario in REMOTE_SCENARIOS:
        assert scenario in matrix

    for required_dimension in [
        "pickup",
        "delivery",
        "cash",
        "pix",
        "card",
        "external",
        "at_commit",
        "post_commit",
        "immediate",
        "manual",
        "auto_confirm",
        "auto_cancel",
        "available",
        "low_stock",
        "unavailable",
        "planned",
        "payment.timeout",
        "AccessLink",
        "reorder",
        "rating",
    ]:
        assert required_dimension in matrix


def test_remote_docs_name_core_as_canon_and_django_penguin_as_reference_only():
    matrix = _read(REMOTE_MATRIX)
    plan = _read(REMOTE_PLAN)
    contract = _read(PARITY_CONTRACT)

    for doc in [matrix, plan, contract]:
        assert "Django/Penguin" in doc
        assert re.search(r"Django/Penguin.+n[aã]o (?:e )?(?:o )?canon", doc, flags=re.IGNORECASE | re.DOTALL)

    for token in [
        "Orderman",
        "Payman",
        "Stockman",
        "Guestman",
        "Doorman",
        "ChannelConfig",
        "Directives",
        "services",
        "projections",
    ]:
        assert token in matrix
        assert token in plan
        assert token in contract

    forbidden_claims = [
        "Django/Penguin e canonico",
        "Django/Penguin e a fonte canonica",
        "Django/Penguin e a superficie canonica",
        "fonte canonica anterior",
    ]
    for forbidden in forbidden_claims:
        assert forbidden not in matrix
        assert forbidden not in plan
        assert forbidden not in contract


def test_manychat_contract_allows_rendering_shopman_data_but_not_authoritative_rules():
    adr = _read(MANYCHAT_ADR)
    matrix = _read(REMOTE_MATRIX)
    plan = _read(REMOTE_PLAN)

    for doc in [adr, matrix, plan]:
        assert "ManyChat" in doc
        assert "Shopman" in doc

    assert "não significa que o bot não possa" in adr
    assert "não pode ser a fonte de verdade" in adr
    assert "ManyChat coleta intenção" in adr
    assert "Shopman resolve preço" in adr
    assert "projection/resposta retornada por Shopman" in adr
    assert "regra" in adr
    assert "autoritativa de preço, estoque, disponibilidade" in adr

    for doc in [matrix, plan]:
        lower_doc = doc.lower()
        assert any(phrase in lower_doc for phrase in ["nao pode", "nao colocar", "nao criar"])
        assert "pricing" in doc
        assert "stock" in doc
        assert "payment gate" in doc
        assert "lifecycle" in doc


def test_core_status_and_projection_contracts_cover_remote_intermediate_states():
    order_model = _read(REPO_ROOT / "packages" / "orderman" / "shopman" / "orderman" / "models" / "order.py")
    payment_model = _read(REPO_ROOT / "packages" / "payman" / "shopman" / "payman" / "models" / "intent.py")
    # Post data/presentation cut: derived states + deadline fields live in the
    # data Projection; next_event/recovery/active_notification in the storefront
    # Presentation. The contract spans both.
    tracking = (
        _read(REPO_ROOT / "shopman" / "shop" / "projections" / "order_tracking.py")
        + _read(REPO_ROOT / "shopman" / "storefront" / "presentation" / "order_tracking.py")
    )
    # Same cut for payment: deadline fields + actions in the data Projection;
    # next_event/recovery/active_notification in the storefront Presentation.
    payment_projection = (
        _read(REPO_ROOT / "shopman" / "shop" / "projections" / "payment_status.py")
        + _read(REPO_ROOT / "shopman" / "storefront" / "presentation" / "payment.py")
    )

    for status in ORDER_STATUSES:
        assert f'"{status}"' in order_model

    for status in PAYMENT_STATUSES:
        assert f'"{status}"' in payment_model

    for derived_state in [
        "payment_pending",
        "payment_requested",
        "payment_expired",
        "availability_deferred",
        "availability_check",
        "payment_confirmed",
        "ready_delivery",
        "ready_pickup",
    ]:
        assert derived_state in tracking

    for projection_field in [
        "deadline_at",
        "deadline_kind",
        "deadline_action",
        "requires_active_notification",
        "actions",
        "next_event",
        "recovery",
        "active_notification",
    ]:
        assert projection_field in tracking
        assert projection_field in payment_projection


def test_nuxt_tracking_contract_consumes_status_as_backend_string_not_surface_union():
    """A superfície consome o status do backend como string e nunca inventa
    uma união própria de estados — labels/promise vêm da projection."""
    types = _read(NUXT_TYPES)
    tracking_page = _read(NUXT_TRACKING_PAGE)

    assert "export interface TrackingResponse" in types
    tracking_response = types[types.index("export interface TrackingResponse"):]
    tracking_response = tracking_response[:tracking_response.index("\n}", 1)]
    assert "status: string" in tracking_response

    forbidden_surface_statuses = {
        "awaiting_payment",
        "awaiting_confirmation",
        "out_for_delivery",
        "fulfilled",
        "payment_pending_status",
    }
    source = tracking_response + "\n" + tracking_page
    for forbidden in forbidden_surface_statuses:
        assert forbidden not in source


def test_manychat_conversation_api_is_thin_projection_adapter():
    urls = _read(REPO_ROOT / "shopman" / "storefront" / "api" / "urls.py")
    api = _read(REPO_ROOT / "shopman" / "storefront" / "api" / "conversation.py")
    serializer = _read(REPO_ROOT / "shopman" / "storefront" / "api" / "serializers.py")
    conversation = _read(REPO_ROOT / "shopman" / "shop" / "services" / "conversation.py")

    assert 'path("orders/<str:ref>/conversation/"' in urls
    assert "OrderConversationView" in urls
    assert "build_order_conversation(order, channel_ref=channel_ref)" in api
    assert "RemoteConversationSerializer(projection_data(projection))" in api
    assert "RemoteConversationSerializer" in serializer
    assert "can_cancel = serializers.BooleanField" not in serializer

    assert "OrderTrackingProjection" not in conversation
    assert "payment_status.build_payment" in conversation
    assert "resolve_channel_policy" in conversation
    assert "cancel_order" in conversation
    assert "rate_order" in conversation


def test_headless_surface_contract_crystallizes_projection_actions_vocabulary():
    adr = _read(HEADLESS_ADR)
    contract = _read(HEADLESS_CONTRACT)
    parity = _read(PARITY_CONTRACT)
    mutation_contract = _read(REMOTE_MUTATION_CONTRACT)
    docs_index = _read(REPO_ROOT / "docs" / "README.md")

    for doc in [adr, contract]:
        assert "Projection com Actions" in doc
        assert "InteractionContext -> Projection -> canonical node(actions[]) -> Action -> Intent -> Mutation -> Projection" in doc
        assert "ChannelPolicyResolution" in doc
        assert "insumo interno" in doc
        assert "Nao existe compatibilidade aberta" in doc
        assert "Recovery" in doc
        assert "Omotenashi" in doc
        assert "Django/Penguin" in doc
        assert "nao e canon" in doc

    assert "Projection com Actions resolvidas pelo backend" in parity
    assert "policy crua" in parity
    assert "nenhuma policy crua como contrato publico" in parity
    assert "Mutation idempotente e o unico nome canonico" in parity
    assert "Nao existe compatibilidade aberta" in parity

    assert "Remote Mutation Contract" in mutation_contract
    assert "Mutations remotas" in mutation_contract
    assert "Nao existe compatibilidade aberta" in mutation_contract

    assert "adr-012-headless-surface-contract.md" in docs_index
    assert "headless-surface-contract.md" in docs_index


def test_remote_mutation_contract_requires_idempotent_sensitive_mutations():
    mutation_contract = _read(REMOTE_MUTATION_CONTRACT)
    remote_mutations = _read(REPO_ROOT / "shopman" / "shop" / "services" / "remote_mutations.py")
    tracking_api = _read(REPO_ROOT / "shopman" / "storefront" / "api" / "tracking.py")
    surface_api = _read(REPO_ROOT / "shopman" / "storefront" / "api" / "surface.py")

    for token in [
        "checkout.process",
        "OrderTrackingProjection",
        "PaymentProjection",
        "RemoteConversationProjection",
        "AccessLink",
        "Idempotency-Key",
        "orderman.IdempotencyKey",
    ]:
        assert token in mutation_contract

    assert "RemoteOrder" in mutation_contract
    assert "status remoto" in mutation_contract
    assert "run_idempotent_mutation" in remote_mutations
    assert "order-cancel" in tracking_api
    assert "order-reorder" in surface_api
    assert "command_in_progress" not in tracking_api
    assert "command_in_progress" not in surface_api
    assert "idempotency_key_from_request" in tracking_api
    assert "idempotency_key_from_request" in surface_api


def test_remote_order_observability_has_runbook_and_read_only_diagnostic():
    runbook = _read(REMOTE_RUNBOOK)
    commands = _read(REPO_ROOT / "docs" / "reference" / "commands.md")
    diagnostic = _read(REPO_ROOT / "shopman" / "shop" / "management" / "commands" / "diagnose_remote_order.py")

    lower_runbook = runbook.lower()
    for token in [
        "aguardando pagamento",
        "aguardando confirmacao",
        "directive failed",
        "accesslink expirado",
        "manychat indisponivel",
        "stock hold expirado",
        "diagnose_remote_order",
    ]:
        assert token in lower_runbook

    assert "nao altera estado" in commands
    assert "Order.objects.get" in diagnostic
    assert "build_order_conversation" in diagnostic
    assert "transition_status(" not in diagnostic
    assert ".save(" not in diagnostic


def test_remote_plan_keeps_all_wp_prompts_self_contained():
    plan = _read(REMOTE_PLAN)

    for wp in [
        "WP-REMOTE-01",
        "WP-REMOTE-02",
        "WP-REMOTE-03",
        "WP-REMOTE-04",
        "WP-REMOTE-05",
        "WP-REMOTE-06",
    ]:
        assert f"## {wp}" in plan
        section = plan[plan.index(f"## {wp}"):]
        if "## WP-REMOTE-" in section[len(f"## {wp}"):]:
            section = section[:section.index("## WP-REMOTE-", len(f"## {wp}"))]
        assert "Prompt:" in section
        assert "Contexto obrigatorio:" in section
        assert "Leia antes de alterar:" in section
        assert "Restricoes:" in section
        assert "Verificacao esperada:" in section
