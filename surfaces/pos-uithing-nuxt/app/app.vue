<script setup lang="ts">
import type {
  POSAddressAutocompleteProjection,
  POSCartItem,
  POSCloseSaleResponse,
  POSCustomerLookupProjection,
  POSCustomerLookupResponse,
  POSProductProjection,
  POSResponse,
  POSSaleReviewProjection,
  POSSaleReviewResponse,
  POSTabPayload,
  POSTabProjection,
  SavedAddressProjection,
  StructuredAddressProjection,
} from "~/types/pos";
import {
  actionHref,
  buildPosSaleIntent,
  cartTotalQ,
  concreteActionHref,
  formatBRL,
  moneyInputToQ,
} from "~/utils/posIntent";
import {
  draftAssociationTargetStates,
  requiresOpenTabForCart,
  requiresTabBeforeSave,
  tabCodeMaxDigits,
} from "~/utils/posTabLifecycle";

type FulfillmentType = "pickup" | "delivery";
type PaymentCollection = "terminal" | "on_delivery";

const apiPath = usePosApiPath();
const action = usePosAction();
const runtimeConfig = useRuntimeConfig();
const requestHeaders = import.meta.server ? useRequestHeaders(["cookie"]) : undefined;

const { data, pending, error, refresh } = await useFetch<POSResponse>(
  () => apiPath("/api/v1/backstage/pos/"),
  { credentials: "include", headers: requestHeaders },
);

const search = ref("");
const activeCollection = ref("");
const tabInput = ref("");
const busy = ref(false);
const saving = ref(false);
const lookupBusy = ref(false);
const serverError = ref("");
const result = ref<{ orderRef: string; nextUrl: string } | null>(null);
const checkoutMode = ref(false);
const review = ref<POSSaleReviewProjection | null>(null);
const customerLookup = ref<POSCustomerLookupProjection | null>(null);
const tabDialogOpen = ref(false);
const tabDialogReason = ref<"start" | "save" | "cart">("start");

const cart = reactive({
  tabCode: "",
  tabDisplay: "",
  tabSessionKey: "",
  items: [] as POSCartItem[],
  customerName: "",
  customerRef: "",
  customerPhone: "",
  customerTaxId: "",
  customerEmail: "",
  customerMemoryAction: "",
  fulfillmentType: "pickup" as FulfillmentType,
  deliveryAddress: "",
  deliveryAddressStructured: {} as StructuredAddressProjection,
  deliveryStreetNumber: "",
  deliveryNeighborhood: "",
  deliveryComplement: "",
  deliveryInstructions: "",
  deliveryDate: "",
  deliveryTimeSlot: "",
  deliveryFeeInput: "",
  orderNotes: "",
  paymentMethod: "",
  paymentCollection: "terminal" as PaymentCollection,
  paymentTenders: [] as Array<{ method: string; amount_q: number; collection: PaymentCollection; reference?: string }>,
  tenderedAmountInput: "",
  issueFiscalDocument: false,
  receiptMode: "none",
  receiptEmail: "",
  manualDiscount: null as Record<string, unknown> | null,
  managerApproval: null as Record<string, unknown> | null,
  clientRequestId: "",
});

const pos = computed(() => data.value?.pos || null);
const tabs = computed(() => data.value?.tabs || []);
const shift = computed(() => data.value?.shift || null);
const actions = computed(() => pos.value?.actions || []);
const checkoutContract = computed(() => pos.value?.checkout || null);
const checkoutCapabilities = computed(() => checkoutContract.value?.capabilities || {});
const tabMaxDigits = computed(() => tabCodeMaxDigits(checkoutCapabilities.value));
const tabDraftTargetStates = computed(() => draftAssociationTargetStates(checkoutCapabilities.value));
const tabRequiredForCart = computed(() => requiresOpenTabForCart(checkoutCapabilities.value));
const tabRequiredForSave = computed(() => requiresTabBeforeSave(checkoutCapabilities.value));
const addressAutocomplete = computed<POSAddressAutocompleteProjection | null>(() => {
  const raw = checkoutContract.value?.capabilities?.address_autocomplete;
  return raw && typeof raw === "object" ? raw as POSAddressAutocompleteProjection : null;
});
const totalDisplay = computed(() => formatBRL(cartTotalQ(cart.items)));
const itemCount = computed(() => cart.items.reduce((sum, item) => sum + item.qty, 0));
const hasOpenTab = computed(() => Boolean(cart.tabSessionKey));
const hasDraftWithoutTab = computed(() => !hasOpenTab.value && cart.items.length > 0);
const canUseCart = computed(() => !tabRequiredForCart.value || hasOpenTab.value);
const deliveryFeeQ = computed(() => moneyInputToQ(cart.deliveryFeeInput));
const tenderedAmountQ = computed(() => moneyInputToQ(cart.tenderedAmountInput));
const tabDialogTitle = computed(() => {
  if (tabDialogReason.value === "save") return "Associar comanda";
  return "Abrir comanda";
});
const tabDialogDescription = computed(() => {
  if (hasDraftWithoutTab.value) {
    return "Escolha uma comanda livre ou digite um número novo para salvar este atendimento sem perder recuperação no caixa.";
  }
  return "Digite uma comanda nova ou busque uma comanda salva para iniciar o atendimento.";
});

const favoriteCollections = computed(() => new Set(pos.value?.favorite_collection_refs || []));
const orderedCollections = computed(() => {
  const collections = pos.value?.collections || [];
  return [...collections].sort((a, b) => {
    const aFavorite = favoriteCollections.value.has(a.ref) ? 0 : 1;
    const bFavorite = favoriteCollections.value.has(b.ref) ? 0 : 1;
    return aFavorite - bFavorite || a.name.localeCompare(b.name, "pt-BR");
  });
});

const filteredProducts = computed<POSProductProjection[]>(() => {
  const normalized = search.value.trim().toLowerCase();
  return (pos.value?.products || []).filter((product) => {
    if (activeCollection.value && product.collection_ref !== activeCollection.value) return false;
    if (!normalized) return true;
    return product.name.toLowerCase().includes(normalized) || product.sku.toLowerCase().includes(normalized);
  });
});

const sortedTabs = computed(() => [...tabs.value].sort((a, b) => {
  const aOpen = a.state === "in_use" ? 0 : 1;
  const bOpen = b.state === "in_use" ? 0 : 1;
  return aOpen - bOpen || a.display_code.localeCompare(b.display_code, "pt-BR", { numeric: true });
}));

const availablePaymentCollections = computed(() =>
  (pos.value?.payment_collections || []).filter((collection) =>
    collection.fulfillment_types.includes(cart.fulfillmentType)
    && collection.payment_method_refs.includes(cart.paymentMethod),
  ),
);

watch(pos, (projection) => {
  if (!projection) return;
  if (!cart.paymentMethod) cart.paymentMethod = projection.payment_methods[0]?.ref || "cash";
  const defaultFulfillment = projection.terminal_default_fulfillment_type === "delivery" ? "delivery" : "pickup";
  if (!cart.fulfillmentType) cart.fulfillmentType = defaultFulfillment;
  if (!projection.fulfillment_options.some((option) => option.ref === cart.fulfillmentType)) {
    cart.fulfillmentType = projection.fulfillment_options[0]?.ref || "pickup";
  }
}, { immediate: true });

watch(availablePaymentCollections, (collections) => {
  if (!collections.some((collection) => collection.ref === cart.paymentCollection)) {
    cart.paymentCollection = collections[0]?.ref || "terminal";
  }
}, { immediate: true });

watch(() => [
  cart.customerTaxId,
  cart.customerEmail,
  cart.fulfillmentType,
  cart.deliveryAddress,
  cart.deliveryAddressStructured,
  cart.deliveryStreetNumber,
  cart.deliveryNeighborhood,
  cart.deliveryComplement,
  cart.deliveryInstructions,
  cart.deliveryDate,
  cart.deliveryTimeSlot,
  cart.deliveryFeeInput,
  cart.orderNotes,
  cart.paymentMethod,
  cart.paymentCollection,
  cart.tenderedAmountInput,
  cart.issueFiscalDocument,
  cart.receiptMode,
  cart.receiptEmail,
], () => {
  if (checkoutMode.value) review.value = null;
});

function productQty(sku: string): number {
  return cart.items.find((item) => item.sku === sku)?.qty || 0;
}

function addProduct(product: POSProductProjection) {
  if (!canUseCart.value) {
    requestTabAssociation("cart");
    return;
  }
  result.value = null;
  review.value = null;
  checkoutMode.value = false;
  const existing = cart.items.find((item) => item.sku === product.sku);
  if (existing) {
    existing.qty += 1;
    return;
  }
  cart.items.push({
    sku: product.sku,
    name: product.name,
    price_q: product.price_q,
    qty: 1,
    notes: "",
    is_d1: product.is_d1,
  });
}

function setQty(sku: string, qty: number) {
  if (!canUseCart.value) return;
  review.value = null;
  checkoutMode.value = false;
  const existing = cart.items.find((item) => item.sku === sku);
  if (!existing) return;
  if (qty <= 0) {
    cart.items = cart.items.filter((item) => item.sku !== sku);
    return;
  }
  existing.qty = qty;
}

function resetCart() {
  cart.tabCode = "";
  cart.tabDisplay = "";
  cart.tabSessionKey = "";
  cart.items = [];
  cart.customerName = "";
  cart.customerRef = "";
  cart.customerPhone = "";
  cart.customerTaxId = "";
  cart.customerEmail = "";
  cart.customerMemoryAction = "";
  cart.deliveryAddress = "";
  cart.deliveryAddressStructured = {};
  cart.deliveryStreetNumber = "";
  cart.deliveryNeighborhood = "";
  cart.deliveryComplement = "";
  cart.deliveryInstructions = "";
  cart.deliveryDate = "";
  cart.deliveryTimeSlot = "";
  cart.deliveryFeeInput = "";
  cart.orderNotes = "";
  cart.paymentCollection = "terminal";
  cart.paymentTenders = [];
  cart.tenderedAmountInput = "";
  cart.issueFiscalDocument = false;
  cart.receiptMode = "none";
  cart.receiptEmail = "";
  cart.manualDiscount = null;
  cart.managerApproval = null;
  cart.clientRequestId = "";
  customerLookup.value = null;
  checkoutMode.value = false;
  review.value = null;
}

function sanitizeTabCode(value: string): string {
  return String(value || "").replace(/\D/g, "").slice(0, tabMaxDigits.value);
}

function updateTabInput(value: unknown) {
  tabInput.value = sanitizeTabCode(String(value || ""));
}

function assignTabIdentityFromPayload(payload: POSTabPayload) {
  cart.tabCode = payload.tab_code;
  cart.tabDisplay = payload.tab_display;
  cart.tabSessionKey = payload.tab_session_key || payload.session_key;
}

function setFromTabPayload(payload: POSTabPayload) {
  assignTabIdentityFromPayload(payload);
  cart.items = (payload.items || []).map((item) => ({ ...item }));
  cart.customerName = payload.customer_name || "";
  cart.customerRef = payload.customer_ref || "";
  cart.customerPhone = payload.customer_phone || "";
  cart.customerTaxId = payload.customer_tax_id || "";
  cart.customerEmail = payload.customer_email || "";
  cart.fulfillmentType = payload.fulfillment_type === "delivery" ? "delivery" : "pickup";
  cart.deliveryAddress = payload.delivery_address || "";
  cart.deliveryAddressStructured = payload.delivery_address_structured || {};
  cart.deliveryStreetNumber = payload.delivery_address_structured?.street_number || "";
  cart.deliveryNeighborhood = payload.delivery_address_structured?.neighborhood || "";
  cart.deliveryComplement = payload.delivery_address_structured?.complement || "";
  cart.deliveryInstructions = payload.delivery_address_structured?.delivery_instructions || payload.delivery_address_structured?.reference || "";
  cart.deliveryDate = payload.delivery_date || "";
  cart.deliveryTimeSlot = payload.delivery_time_slot || "";
  cart.deliveryFeeInput = payload.delivery_fee_q ? (Number(payload.delivery_fee_q) / 100).toFixed(2).replace(".", ",") : "";
  cart.orderNotes = payload.order_notes || "";
  cart.paymentMethod = payload.payment_method || cart.paymentMethod || pos.value?.payment_methods[0]?.ref || "cash";
  cart.paymentCollection = payload.payment_collection === "on_delivery" ? "on_delivery" : "terminal";
  cart.paymentTenders = payload.payment_tenders || [];
  cart.tenderedAmountInput = payload.tendered_amount_q ? (Number(payload.tendered_amount_q) / 100).toFixed(2).replace(".", ",") : "";
  cart.issueFiscalDocument = !!payload.issue_fiscal_document;
  cart.receiptMode = payload.receipt_mode || "none";
  cart.receiptEmail = payload.receipt_email || "";
  cart.manualDiscount = null;
  cart.managerApproval = null;
  cart.clientRequestId = "";
  customerLookup.value = null;
  checkoutMode.value = false;
  review.value = null;
}

function requestTabAssociation(reason: "start" | "save" | "cart" = "start") {
  tabDialogReason.value = reason;
  serverError.value = "";
  tabDialogOpen.value = true;
}

async function openTab(tab: POSTabProjection | string, options: { preserveDraft?: boolean } = {}) {
  const tabCode = sanitizeTabCode(typeof tab === "string" ? tab : tab.code);
  if (!tabCode) return;
  serverError.value = "";
  result.value = null;
  busy.value = true;
  try {
    const path = concreteActionHref(
      actions.value,
      "open_tab",
      "/api/v1/backstage/pos/tabs/{tab_code}/open/",
      { tab_code: tabCode },
    );
    const payload = await action.call<POSTabPayload>(path);
    if (options.preserveDraft && cart.items.length) {
      if ((payload.items || []).length) {
        throw new Error("Esta comanda já possui pedido. Abra a comanda separadamente ou escolha uma comanda livre.");
      }
      assignTabIdentityFromPayload(payload);
      checkoutMode.value = false;
      review.value = null;
    } else {
      setFromTabPayload(payload);
    }
    tabInput.value = "";
    await refresh();
  } catch (err: any) {
    serverError.value = err?.data?.detail || err?.message || "Falha ao abrir comanda.";
  } finally {
    busy.value = false;
  }
}

async function openTabFromDialog(tab: POSTabProjection | string) {
  const reason = tabDialogReason.value;
  const preserveDraft = hasDraftWithoutTab.value;
  await openTab(tab, { preserveDraft });
  if (!cart.tabSessionKey) return;
  tabDialogOpen.value = false;
  if (reason === "save" && cart.items.length) {
    await saveTab();
  }
}

function currentIntentState() {
  const structured: StructuredAddressProjection = {
    ...cart.deliveryAddressStructured,
    route: cart.deliveryAddress.trim() || cart.deliveryAddressStructured.route || "",
    street_number: cart.deliveryStreetNumber.trim() || cart.deliveryAddressStructured.street_number || "",
    neighborhood: cart.deliveryNeighborhood.trim() || cart.deliveryAddressStructured.neighborhood || "",
    complement: cart.deliveryComplement.trim() || cart.deliveryAddressStructured.complement || "",
    delivery_instructions: cart.deliveryInstructions.trim() || cart.deliveryAddressStructured.delivery_instructions || "",
    reference: cart.deliveryInstructions.trim() || cart.deliveryAddressStructured.reference || "",
  };
  const deliveryAddressParts = [
    structured.formatted_address || "",
    structured.route || "",
    structured.street_number || "",
    structured.neighborhood || "",
  ]
    .filter(Boolean);
  const deliveryAddress = structured.formatted_address || deliveryAddressParts.join(", ");
  return {
    tabCode: cart.tabCode,
    tabSessionKey: cart.tabSessionKey,
    items: cart.items,
    customerName: cart.customerName,
    customerRef: cart.customerRef,
    customerPhone: cart.customerPhone,
    customerTaxId: cart.customerTaxId,
    customerEmail: cart.customerEmail,
    customerMemoryAction: cart.customerMemoryAction,
    fulfillmentType: cart.fulfillmentType,
    deliveryAddress,
    deliveryAddressStructured: structured,
    deliveryComplement: cart.deliveryComplement,
    deliveryInstructions: cart.deliveryInstructions,
    deliveryDate: cart.deliveryDate,
    deliveryTimeSlot: cart.deliveryTimeSlot,
    deliveryFeeQ: deliveryFeeQ.value,
    orderNotes: cart.orderNotes,
    paymentMethod: cart.paymentMethod,
    paymentCollection: cart.paymentCollection,
    paymentTenders: cart.paymentTenders,
    tenderedAmountQ: tenderedAmountQ.value > 0 ? tenderedAmountQ.value : null,
    issueFiscalDocument: cart.issueFiscalDocument,
    receiptMode: cart.receiptMode,
    receiptEmail: cart.receiptEmail || cart.customerEmail,
    manualDiscount: cart.manualDiscount,
    managerApproval: cart.managerApproval,
    clientRequestId: cart.clientRequestId || newClientRequestId(),
  };
}

function applyStructuredAddress(address: StructuredAddressProjection) {
  cart.deliveryAddressStructured = {
    ...cart.deliveryAddressStructured,
    ...address,
  };
  cart.deliveryAddress = address.route || address.formatted_address || cart.deliveryAddress;
  cart.deliveryStreetNumber = address.street_number || cart.deliveryStreetNumber;
  cart.deliveryNeighborhood = address.neighborhood || cart.deliveryNeighborhood;
  cart.deliveryComplement = address.complement || cart.deliveryComplement;
  cart.deliveryInstructions = address.delivery_instructions || address.reference || cart.deliveryInstructions;
}

function applySavedAddress(address: SavedAddressProjection) {
  applyStructuredAddress(address);
  cart.deliveryAddress = address.route || address.formatted_address;
}

async function lookupCustomer() {
  const phone = cart.customerPhone.trim();
  if (!phone) return;
  lookupBusy.value = true;
  serverError.value = "";
  try {
    const path = concreteActionHref(
      actions.value,
      "customer_lookup",
      "/api/v1/backstage/pos/customer/lookup/?phone={phone}",
      { phone },
    );
    const response = await $fetch<POSCustomerLookupResponse>(apiPath(path), {
      method: "GET",
      credentials: "include",
      headers: requestHeaders,
    });
    customerLookup.value = response.customer;
    if (!response.customer) return;
    cart.customerRef = response.customer.ref;
    cart.customerName = response.customer.name || cart.customerName;
    cart.customerPhone = response.customer.phone || cart.customerPhone;
    cart.customerEmail = response.customer.email || cart.customerEmail;
    if (response.customer.is_staff) cart.customerMemoryAction = "";
    if (cart.fulfillmentType === "delivery" && response.customer.default_address && !cart.deliveryAddress.trim()) {
      applySavedAddress(response.customer.default_address);
    }
  } catch (err: any) {
    serverError.value = err?.data?.detail || err?.message || "Falha ao buscar cliente.";
  } finally {
    lookupBusy.value = false;
  }
}

function productFromMemoryItem(item: Record<string, unknown>): POSProductProjection | null {
  const sku = String(item.sku || "");
  return pos.value?.products.find((product) => product.sku === sku) || null;
}

function addProductQty(product: POSProductProjection, qty: number) {
  for (let idx = 0; idx < Math.max(1, qty); idx += 1) addProduct(product);
}

function applyCustomerFavorite() {
  const item = customerLookup.value?.memory.favorite_item;
  if (!item) return;
  const product = productFromMemoryItem(item);
  if (!product) return;
  addProductQty(product, 1);
  cart.customerMemoryAction = "favorite_item";
}

function repeatCustomerLastOrder() {
  const items = customerLookup.value?.memory.last_order_items || [];
  for (const item of items) {
    const product = productFromMemoryItem(item);
    if (!product) continue;
    const qty = Number.parseInt(String(item.qty || 1), 10);
    addProductQty(product, Number.isFinite(qty) ? qty : 1);
  }
  if (items.length) cart.customerMemoryAction = "last_order";
}

function buildCurrentIntent() {
  return buildPosSaleIntent(
    currentIntentState(),
    checkoutContract.value?.intent_version,
  );
}

async function persistTab() {
  const state = currentIntentState();
  cart.clientRequestId = state.clientRequestId;
  await action.call(actionHref(actions.value, "save_tab", "/api/v1/backstage/pos/tabs/save/"), {
    body: buildPosSaleIntent(state, checkoutContract.value?.intent_version),
  });
  await refresh();
}

async function saveTab() {
  if (tabRequiredForSave.value && !hasOpenTab.value) {
    requestTabAssociation("save");
    return;
  }
  serverError.value = "";
  saving.value = true;
  try {
    await persistTab();
  } catch (err: any) {
    serverError.value = err?.data?.detail || err?.message || "Falha ao salvar comanda.";
  } finally {
    saving.value = false;
  }
}

async function reloadCurrentTab() {
  if (!cart.tabCode) return;
  const path = concreteActionHref(
    actions.value,
    "open_tab",
    "/api/v1/backstage/pos/tabs/{tab_code}/open/",
    { tab_code: cart.tabCode },
  );
  const payload = await action.call<POSTabPayload>(path);
  setFromTabPayload(payload);
  await refresh();
}

async function reviewSale() {
  if (tabRequiredForSave.value && !hasOpenTab.value) return null;
  if (!cart.items.length) return null;
  const state = currentIntentState();
  cart.clientRequestId = state.clientRequestId;
  const response = await action.call<POSSaleReviewResponse>(
    actionHref(actions.value, "review_sale", "/api/v1/backstage/pos/sale/review/"),
    { body: buildPosSaleIntent(state, checkoutContract.value?.intent_version) },
  );
  review.value = response.review;
  return response.review;
}

async function prepareCheckout() {
  if (tabRequiredForSave.value && !hasOpenTab.value) {
    requestTabAssociation("start");
    return;
  }
  if (!cart.items.length) return;
  serverError.value = "";
  result.value = null;
  busy.value = true;
  try {
    await persistTab();
    await reloadCurrentTab();
    await reviewSale();
    checkoutMode.value = true;
  } catch (err: any) {
    serverError.value = err?.data?.detail || err?.data?.error?.message || err?.message || "Falha ao revisar checkout.";
  } finally {
    busy.value = false;
  }
}

async function submitSale() {
  if (tabRequiredForSave.value && !hasOpenTab.value) {
    requestTabAssociation("start");
    return;
  }
  if (!cart.items.length) return;
  if (!checkoutMode.value) {
    await prepareCheckout();
    return;
  }
  serverError.value = "";
  result.value = null;
  busy.value = true;
  try {
    const reviewed = await reviewSale();
    if (!reviewed) return;
    const response = await action.call<POSCloseSaleResponse>(
      actionHref(actions.value, "close_sale", "/api/v1/backstage/pos/sale/close/"),
      { body: buildCurrentIntent() },
    );
    if (response.ok && response.order_ref) {
      const orderRef = response.order_ref;
      result.value = {
        orderRef,
        nextUrl: `${runtimeConfig.public.djangoPublicBaseUrl}/admin/operacao/pedidos/${encodeURIComponent(orderRef)}/`,
      };
      resetCart();
      await refresh();
    }
  } catch (err: any) {
    serverError.value = err?.data?.detail || err?.data?.error?.message || err?.message || "Falha ao finalizar venda.";
  } finally {
    busy.value = false;
  }
}

async function clearCurrentTab() {
  if (!cart.tabSessionKey) {
    resetCart();
    return;
  }
  serverError.value = "";
  busy.value = true;
  try {
    const path = concreteActionHref(
      actions.value,
      "clear_tab",
      "/api/v1/backstage/pos/tabs/{session_key}/clear/",
      { session_key: cart.tabSessionKey },
    );
    await action.call(path, { method: "DELETE" });
    resetCart();
    await refresh();
  } catch (err: any) {
    serverError.value = err?.data?.detail || err?.message || "Falha ao liberar comanda.";
  } finally {
    busy.value = false;
  }
}

function newClientRequestId(): string {
  const random = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `pos-uithing:${random}`;
}
</script>

<template>
  <main class="min-h-dvh bg-background text-foreground">
    <header class="sticky top-0 z-30 border-b bg-background/95 backdrop-blur">
      <div class="mx-auto flex max-w-screen-2xl flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div>
          <p class="text-xs font-medium uppercase text-muted-foreground">Shopman</p>
          <h1 class="text-xl font-semibold tracking-normal">POS</h1>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <UiBadge v-if="pos" :variant="pos.terminal_health_status === 'ready' ? 'success' : 'warning'">
            {{ pos.terminal_label }}
          </UiBadge>
          <UiBadge v-if="pos" variant="outline">
            Fiscal: {{ pos.fiscal_message || pos.fiscal_label }}
          </UiBadge>
          <UiBadge v-if="shift" variant="outline" class="tabular-nums">
            {{ shift.count }} hoje · {{ shift.total_display }}
          </UiBadge>
          <UiButton variant="outline" size="icon-sm" aria-label="Atualizar" title="Atualizar" :disabled="pending" @click="refresh()">
            <Icon name="lucide:refresh-cw" class="size-4" :class="pending ? 'animate-spin' : ''" />
          </UiButton>
        </div>
      </div>
    </header>

    <div class="mx-auto grid max-w-screen-2xl gap-4 px-4 py-4 lg:grid-cols-[minmax(0,1fr)_420px]">
      <section class="grid gap-4">
        <UiAlert v-if="error" variant="destructive">
          <Icon name="lucide:triangle-alert" class="size-4" />
          <UiAlertTitle>POS indisponível</UiAlertTitle>
          <UiAlertDescription>Confira login e permissão de operação no gestor.</UiAlertDescription>
        </UiAlert>

        <UiAlert v-if="serverError" variant="destructive">
          <Icon name="lucide:circle-x" class="size-4" />
          <UiAlertTitle>Ação recusada</UiAlertTitle>
          <UiAlertDescription>{{ serverError }}</UiAlertDescription>
        </UiAlert>

        <UiAlert v-if="result" class="border-green-500/30 bg-green-500/10 text-green-800">
          <Icon name="lucide:circle-check" class="size-4" />
          <UiAlertTitle>Pedido criado: {{ result.orderRef }}</UiAlertTitle>
          <UiAlertDescription>
            <a class="font-semibold underline underline-offset-4" :href="result.nextUrl">Abrir no gestor</a>
          </UiAlertDescription>
        </UiAlert>

        <section
          class="grid gap-3"
          :class="!canUseCart ? 'rounded-lg border border-primary/30 bg-primary/5 p-4' : ''"
        >
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 class="text-base font-semibold">Comandas</h2>
              <p v-if="!canUseCart" class="text-sm text-muted-foreground">
                Abra uma comanda para iniciar o pedido e manter o atendimento recuperável.
              </p>
            </div>
            <form class="flex min-w-0 flex-1 justify-end gap-2 sm:flex-none" @submit.prevent="openTab(tabInput)">
              <UiInput
                :model-value="tabInput"
                class="max-w-40"
                inputmode="numeric"
                :maxlength="tabMaxDigits"
                placeholder="Comanda"
                @update:model-value="updateTabInput"
              />
              <UiButton type="submit" :disabled="busy || !tabInput.trim()">Abrir / nova</UiButton>
            </form>
          </div>
          <div class="flex gap-2 overflow-x-auto pb-1">
            <button
              v-for="tab in sortedTabs"
              :key="tab.code"
              type="button"
              class="grid min-w-24 gap-1 rounded-lg border px-3 py-2 text-left transition hover:border-primary/50 hover:bg-accent"
              :class="[
                cart.tabCode === tab.code ? 'border-primary bg-primary/5' : '',
                tab.state === 'in_use' ? 'border-amber-500/40 bg-amber-500/10' : ''
              ]"
              @click="hasDraftWithoutTab ? requestTabAssociation('start') : openTab(tab)"
            >
              <span class="font-semibold tabular-nums">#{{ tab.display_code }}</span>
              <span class="text-xs text-muted-foreground">{{ tab.status_label }}</span>
              <span v-if="tab.item_count" class="text-xs font-semibold tabular-nums">{{ tab.item_count }} · {{ tab.total_display }}</span>
            </button>
          </div>
        </section>

        <section v-if="!canUseCart" class="grid gap-3 rounded-lg border border-dashed p-6 text-center">
          <div class="mx-auto grid size-12 place-items-center rounded-lg border bg-muted">
            <Icon name="lucide:lock-keyhole" class="size-5 text-muted-foreground" />
          </div>
          <div class="grid gap-1">
            <h2 class="text-base font-semibold">Catálogo bloqueado até abrir comanda</h2>
            <p class="mx-auto max-w-xl text-sm text-muted-foreground">
              O POS só deve montar carrinho depois de existir um handle canônico para recuperar, pausar ou finalizar o pedido.
            </p>
          </div>
          <div>
            <UiButton type="button" @click="requestTabAssociation('start')">
              Escolher comanda
            </UiButton>
          </div>
        </section>

        <section v-else class="grid gap-3">
          <div class="flex flex-wrap items-center gap-2">
            <div class="relative min-w-64 flex-1">
              <Icon name="lucide:search" class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <UiInput v-model="search" class="pl-9" type="search" placeholder="Buscar produto por nome ou SKU" autofocus />
            </div>
            <UiButton
              variant="outline"
              :class="activeCollection === '' ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground' : ''"
              @click="activeCollection = ''"
            >
              Tudo
            </UiButton>
            <UiButton
              v-for="collection in orderedCollections"
              :key="collection.ref"
              variant="outline"
              :class="activeCollection === collection.ref ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground' : ''"
              @click="activeCollection = collection.ref"
            >
              {{ collection.name }}
            </UiButton>
          </div>

          <div v-if="pending" class="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
            <div v-for="idx in 10" :key="idx" class="h-32 animate-pulse rounded-lg border bg-muted" />
          </div>
          <div v-else-if="!filteredProducts.length" class="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
            Nenhum produto encontrado.
          </div>
          <div v-else class="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
            <PosProductTile
              v-for="product in filteredProducts"
              :key="product.sku"
              :product="product"
              :qty="productQty(product.sku)"
              :disabled="!canUseCart"
              @add="addProduct"
            />
          </div>
        </section>
      </section>

      <aside>
        <PosCartPanel
          :tab-display="cart.tabDisplay"
          :items="cart.items"
          :fulfillment-options="pos?.fulfillment_options || []"
          :payment-methods="pos?.payment_methods || []"
          :payment-collections="pos?.payment_collections || []"
          :checkout-contract="checkoutContract"
          :address-autocomplete="addressAutocomplete"
          :customer-lookup="customerLookup"
          :checkout-mode="checkoutMode"
          :review="review"
          :requires-tab="tabRequiredForCart"
          :has-open-tab="hasOpenTab"
          v-model:fulfillment-type="cart.fulfillmentType"
          v-model:payment-method="cart.paymentMethod"
          v-model:payment-collection="cart.paymentCollection"
          v-model:customer-name="cart.customerName"
          v-model:customer-phone="cart.customerPhone"
          v-model:customer-tax-id="cart.customerTaxId"
          v-model:customer-email="cart.customerEmail"
          v-model:delivery-address="cart.deliveryAddress"
          v-model:delivery-address-structured="cart.deliveryAddressStructured"
          v-model:delivery-street-number="cart.deliveryStreetNumber"
          v-model:delivery-neighborhood="cart.deliveryNeighborhood"
          v-model:delivery-complement="cart.deliveryComplement"
          v-model:delivery-instructions="cart.deliveryInstructions"
          v-model:delivery-date="cart.deliveryDate"
          v-model:delivery-time-slot="cart.deliveryTimeSlot"
          v-model:delivery-fee-input="cart.deliveryFeeInput"
          v-model:order-notes="cart.orderNotes"
          v-model:tendered-amount-input="cart.tenderedAmountInput"
          v-model:issue-fiscal-document="cart.issueFiscalDocument"
          v-model:receipt-mode="cart.receiptMode"
          v-model:receipt-email="cart.receiptEmail"
          :loading="busy"
          :saving="saving"
          :lookup-busy="lookupBusy"
          @increment="(sku) => setQty(sku, productQty(sku) + 1)"
          @decrement="(sku) => setQty(sku, productQty(sku) - 1)"
          @remove="(sku) => setQty(sku, 0)"
          @save="saveTab"
          @prepare="prepareCheckout"
          @back="checkoutMode = false"
          @submit="submitSale"
          @clear="clearCurrentTab"
          @request-tab="requestTabAssociation('start')"
          @lookup-customer="lookupCustomer"
          @apply-customer-favorite="applyCustomerFavorite"
          @repeat-customer-last-order="repeatCustomerLastOrder"
          @pick-saved-address="applySavedAddress"
        />
        <p class="mt-3 text-xs text-muted-foreground">
          {{ itemCount }} item(ns) · {{ totalDisplay }}. O backend confirma disponibilidade, total final, status e gravação do pedido.
        </p>
      </aside>
    </div>

    <PosTabPickerDialog
      v-model:open="tabDialogOpen"
      v-model="tabInput"
      :tabs="sortedTabs"
      :busy="busy || saving"
      :has-draft="hasDraftWithoutTab"
      :allowed-target-states="tabDraftTargetStates"
      :title="tabDialogTitle"
      :description="tabDialogDescription"
      :max-digits="tabMaxDigits"
      @confirm="openTabFromDialog"
      @select="openTabFromDialog"
    />
  </main>
</template>
