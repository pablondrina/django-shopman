import { vi } from "vitest";
import { computed, effectScope, ref, type Ref } from "vue";

import type { Action, POSProjection, POSTabProjection } from "~/types/pos";
import { usePosSale } from "~/composables/usePosSale";

// Projeção mínima porém válida do terminal — o suficiente para o write-side
// derivar defaults (payment_method/fulfillment/collection), preços de catálogo
// (override de preço) e capacidades de checkout (tab/fire/rename/cancel).
export function makeProjection(overrides: Partial<POSProjection> = {}): POSProjection {
  return {
    products: [
      { sku: "PAO", name: "Pão", price_q: 500, price_display: "R$ 5,00", collection_ref: "padaria", is_d1: false, image_url: "" },
      { sku: "CAFE", name: "Café", price_q: 300, price_display: "R$ 3,00", collection_ref: "bebidas", is_d1: false, image_url: "" },
    ],
    collections: [],
    payment_methods: [
      { ref: "cash", label: "Dinheiro" },
      { ref: "pix", label: "PIX" },
      { ref: "card", label: "Cartão" },
    ],
    fulfillment_options: [
      { ref: "pickup", label: "Retirada", description: "", requires_address: false },
      { ref: "delivery", label: "Entrega", description: "", requires_address: true },
    ],
    payment_collections: [
      {
        ref: "terminal" as POSProjection["payment_collections"][number]["ref"],
        label: "No caixa",
        description: "",
        fulfillment_types: ["pickup", "delivery"],
        payment_method_refs: ["cash", "pix", "card"],
      },
    ],
    checkout: { intent_version: 1, capabilities: {} } as POSProjection["checkout"],
    actions: [],
    has_open_cash_session: true,
    cash_runtime: {} as POSProjection["cash_runtime"],
    terminal_ref: "T1",
    terminal_label: "Caixa 1",
    terminal_default_fulfillment_type: "pickup",
    terminal_health_status: "ready",
    terminal_components: [],
    favorite_collection_refs: [],
    delivery_minimum_q: 0,
    delivery_minimum_display: "",
    fiscal_status: "ready",
    fiscal_label: "",
    fiscal_message: "",
    operators: [],
    auto_lock_seconds: 0,
    ...overrides,
  };
}

interface HarnessOptions {
  projection?: POSProjection | null;
  tabs?: POSTabProjection[];
  actions?: Action[];
  actionCall?: ReturnType<typeof vi.fn>;
}

/**
 * Instancia `usePosSale` com deps injetadas dentro de um `effectScope`, para que
 * os watchers (autosave/auto-review) e o `onScopeDispose` (polling PIX) fiquem
 * ativos e sejam encerráveis por `handles.dispose()`. As slices são refs mutáveis
 * expostas para o teste dirigir a Projection.
 */
export function makeSale(opts: HarnessOptions = {}) {
  const posValue: Ref<POSProjection | null> = ref(
    opts.projection === undefined ? makeProjection() : opts.projection,
  );
  const tabsValue = ref<POSTabProjection[]>(opts.tabs ?? []);
  const actionsValue = ref<Action[]>(opts.actions ?? []);
  const actionCall = opts.actionCall ?? vi.fn().mockResolvedValue({});
  const refresh = vi.fn().mockResolvedValue(undefined);

  const deps = {
    pos: computed(() => posValue.value),
    tabs: computed(() => tabsValue.value),
    actions: computed(() => actionsValue.value),
    refresh,
    action: { call: actionCall as <T = unknown>(...args: unknown[]) => Promise<T> },
    apiPath: (path: string) => path,
    requestHeaders: {} as Record<string, string>,
    djangoOrigin: computed(() => "http://api.test"),
  };

  const scope = effectScope();
  const sale = scope.run(() => usePosSale(deps))!;

  return {
    sale,
    deps,
    handles: {
      posValue,
      tabsValue,
      actionsValue,
      actionCall,
      refresh,
      dispose: () => scope.stop(),
    },
  };
}

/** Tab payload de teste — só os campos que `setFromTabPayload` lê. */
export function makeTabPayload(overrides: Record<string, unknown> = {}) {
  return {
    session_key: "sess-1",
    tab_session_key: "sess-1",
    tab_ref: "M1",
    tab_display: "M1",
    items: [],
    customer_phone: "",
    customer_name: "",
    customer_ref: "",
    customer_tax_id: "",
    customer_email: "",
    fulfillment_type: "pickup",
    delivery_address: "",
    delivery_address_structured: {},
    delivery_date: "",
    delivery_time_slot: "",
    delivery_fee_q: 0,
    order_notes: "",
    payment_method: "",
    payment_collection: "terminal",
    payment_tenders: [],
    tendered_amount_q: 0,
    issue_fiscal_document: false,
    receipt_mode: "none",
    receipt_email: "",
    discount_type: "percent",
    discount_value: "",
    discount_reason: "",
    ...overrides,
  };
}
