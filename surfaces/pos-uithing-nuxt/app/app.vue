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
  tabRefDisallowedChars,
  tabRefMaxLength,
  tabRefPlaceholder,
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
const tabFilter = ref<"all" | "in_use">("all");
const tabView = ref<"grid" | "list">("grid");
const busy = ref(false);
const saving = ref(false);
const firing = ref(false);
const lookupBusy = ref(false);
const serverError = ref("");
const result = ref<{ orderRef: string; nextUrl: string } | null>(null);
const checkoutMode = ref(false);
const cashDialogOpen = ref(false);
const moveDialogOpen = ref(false);
const review = ref<POSSaleReviewProjection | null>(null);
const customerLookup = ref<POSCustomerLookupProjection | null>(null);
const tabDialogOpen = ref(false);
const tabDialogReason = ref<"start" | "save" | "cart">("start");

const cart = reactive({
  tabRef: "",
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
  discountType: "percent" as "percent" | "fixed",
  discountValue: "",
  discountReason: "",
  managerUsername: "",
  managerPin: "",
  clientRequestId: "",
});

const pos = computed(() => data.value?.pos || null);
const tabs = computed(() => data.value?.tabs || []);
const shift = computed(() => data.value?.shift || null);
const actions = computed(() => pos.value?.actions || []);

// Operator identity / lock screen (Phase 1: PIN attribution).
const operators = computed(() => pos.value?.operators || []);
const {
  activeOperator,
  locked,
  busy: lockBusy,
  error: lockError,
  unlock,
  lock,
} = useOperatorLock({
  initialOperator: data.value?.operator ?? null,
  autoLockSeconds: pos.value?.auto_lock_seconds ?? 60,
});
async function onUnlock(operatorId: number, pin: string) {
  if (await unlock(operatorId, pin)) await refresh();
}
const checkoutContract = computed(() => pos.value?.checkout || null);
const checkoutCapabilities = computed(() => checkoutContract.value?.capabilities || {});
const cashManagement = computed(() => (checkoutCapabilities.value as Record<string, any>)?.cash_management || null);
const kitchenHandoff = computed(() => (checkoutCapabilities.value as Record<string, any>)?.kitchen_handoff || null);
const canFireTab = computed(() => Boolean(kitchenHandoff.value?.fire_action_ref));
const movementKinds = computed<string[]>(() => cashManagement.value?.movement_kinds || ["sangria", "suprimento", "ajuste"]);
const tabMaxLength = computed(() => tabRefMaxLength(checkoutCapabilities.value));
const tabPlaceholder = computed(() => tabRefPlaceholder(checkoutCapabilities.value));
const tabDisallowedChars = computed(() => tabRefDisallowedChars(checkoutCapabilities.value));
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
    return "Escolha uma comanda livre ou digite uma nova referência para salvar este atendimento sem perder recuperação no caixa.";
  }
  return "Digite uma referência de comanda ou busque uma comanda salva para iniciar o atendimento.";
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
  return aOpen - bOpen || a.display_ref.localeCompare(b.display_ref, "pt-BR", { numeric: true });
}));

const openTabsCount = computed(() => tabs.value.filter((tab) => tab.state === "in_use").length);
const otherOpenTabs = computed(() =>
  sortedTabs.value.filter((tab) => tab.state === "in_use" && tab.session_key && tab.ref !== cart.tabRef),
);
const suggestedSplitRef = computed(() => (cart.tabDisplay ? `${cart.tabDisplay}-2` : ""));
const visibleTabs = computed(() =>
  tabFilter.value === "in_use"
    ? sortedTabs.value.filter((tab) => tab.state === "in_use")
    : sortedTabs.value,
);

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
  cart.discountType,
  cart.discountValue,
  cart.discountReason,
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
  cart.tabRef = "";
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
  cart.discountType = "percent";
  cart.discountValue = "";
  cart.discountReason = "";
  cart.managerUsername = "";
  cart.managerPin = "";
  cart.clientRequestId = "";
  customerLookup.value = null;
  checkoutMode.value = false;
  review.value = null;
}

function sanitizeTabRef(value: string): string {
  const disallowed = new Set(tabDisallowedChars.value);
  return String(value || "")
    .replace(/[\r\n\t]/g, "")
    .split("")
    .filter((char) => !disallowed.has(char))
    .join("")
    .replace(/\s+/g, " ")
    .slice(0, tabMaxLength.value);
}

function updateTabInput(value: unknown) {
  tabInput.value = sanitizeTabRef(String(value || ""));
}

function assignTabIdentityFromPayload(payload: POSTabPayload) {
  cart.tabRef = payload.tab_ref;
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
  cart.discountType = "percent";
  cart.discountValue = "";
  cart.discountReason = "";
  cart.managerUsername = "";
  cart.managerPin = "";
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
  const tabRef = sanitizeTabRef(typeof tab === "string" ? tab : tab.ref);
  if (!tabRef) return;
  if (hasDraftWithoutTab.value && !options.preserveDraft) {
    tabInput.value = tabRef;
    requestTabAssociation("start");
    return;
  }
  serverError.value = "";
  result.value = null;
  busy.value = true;
  try {
    const path = concreteActionHref(
      actions.value,
      "open_tab",
      "/api/v1/backstage/pos/tabs/{tab_ref}/open/",
      { tab_ref: tabRef },
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
  const discountValueNum = Number(String(cart.discountValue).replace(",", ".").replace(/[^0-9.]/g, "")) || 0;
  const manualDiscount = discountValueNum > 0
    ? { type: cart.discountType, value: discountValueNum, reason: cart.discountReason || "cortesia" }
    : null;
  const managerApproval = cart.managerUsername.trim() && cart.managerPin.trim()
    ? { username: cart.managerUsername.trim(), pin: cart.managerPin.trim() }
    : null;
  return {
    tabRef: cart.tabRef,
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
    manualDiscount,
    managerApproval,
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
  if (!cart.tabRef) return;
  const path = concreteActionHref(
    actions.value,
    "open_tab",
    "/api/v1/backstage/pos/tabs/{tab_ref}/open/",
    { tab_ref: cart.tabRef },
  );
  const payload = await action.call<POSTabPayload>(path);
  setFromTabPayload(payload);
  await refresh();
}

async function reviewSale() {
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
  if (!cart.items.length) return;
  serverError.value = "";
  result.value = null;
  busy.value = true;
  try {
    if (hasOpenTab.value) {
      await persistTab();
      await reloadCurrentTab();
    }
    await reviewSale();
    checkoutMode.value = true;
  } catch (err: any) {
    serverError.value = err?.data?.detail || err?.data?.error?.message || err?.message || "Falha ao revisar checkout.";
  } finally {
    busy.value = false;
  }
}

async function reviewCheckout() {
  if (!cart.items.length) return;
  serverError.value = "";
  result.value = null;
  busy.value = true;
  try {
    await reviewSale();
  } catch (err: any) {
    serverError.value = err?.data?.detail || err?.data?.error?.message || err?.message || "Falha ao revisar venda.";
  } finally {
    busy.value = false;
  }
}

async function submitSale() {
  if (!cart.items.length) return;
  if (!checkoutMode.value) {
    await prepareCheckout();
    return;
  }
  // Spec: the commit click must not hide an implicit review. If the review is
  // stale (sale data changed), return to review instead of committing.
  if (!review.value) {
    await reviewCheckout();
    return;
  }
  serverError.value = "";
  result.value = null;
  busy.value = true;
  try {
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

async function openMoveDialog() {
  if (!hasOpenTab.value || !cart.items.length) return;
  // Persist + reload so the lines carry server line_ids the move op needs.
  serverError.value = "";
  busy.value = true;
  try {
    await persistTab();
    await reloadCurrentTab();
    moveDialogOpen.value = true;
  } catch (err: any) {
    serverError.value = err?.data?.detail || err?.message || "Falha ao preparar a comanda para mover itens.";
  } finally {
    busy.value = false;
  }
}

async function submitMove(payload: {
  mode: "split" | "transfer" | "merge";
  lineIds: string[];
  toTabRef?: string;
  toSessionKey?: string;
  closeSource?: boolean;
}) {
  if (!cart.tabSessionKey) return;
  serverError.value = "";
  busy.value = true;
  try {
    const body: Record<string, unknown> = {
      from_session_key: cart.tabSessionKey,
      line_ids: payload.lineIds,
    };
    if (payload.toTabRef) body.to_tab_ref = payload.toTabRef;
    if (payload.toSessionKey) body.to_session_key = payload.toSessionKey;
    if (payload.closeSource) body.close_source_when_empty = true;
    const response = await action.call<{ source_closed: boolean; source: POSTabPayload | null }>(
      actionHref(actions.value, "move_tab_lines", "/api/v1/backstage/pos/tabs/move-lines/"),
      { body },
    );
    moveDialogOpen.value = false;
    if (response.source_closed || !response.source) {
      resetCart();
    } else {
      setFromTabPayload(response.source);
    }
    await refresh();
  } catch (err: any) {
    serverError.value = err?.data?.detail || err?.data?.error?.message || err?.message || "Falha ao mover itens.";
  } finally {
    busy.value = false;
  }
}

async function fireTab() {
  if (!cart.tabSessionKey) return;
  serverError.value = "";
  firing.value = true;
  try {
    const response = await action.call<{ tab: POSTabPayload | null }>(
      actionHref(actions.value, "fire_tab", "/api/v1/backstage/pos/tabs/fire/"),
      { body: { session_key: cart.tabSessionKey, client_request_id: newClientRequestId() } },
    );
    if (response.tab) setFromTabPayload(response.tab);
    await refresh();
  } catch (err: any) {
    serverError.value = err?.data?.detail || err?.data?.error?.message || err?.message || "Falha ao enviar à cozinha.";
  } finally {
    firing.value = false;
  }
}

async function unfireTab(lineId: string) {
  if (!cart.tabSessionKey || !lineId) return;
  serverError.value = "";
  firing.value = true;
  try {
    const response = await action.call<{ tab: POSTabPayload | null }>(
      actionHref(actions.value, "unfire_tab", "/api/v1/backstage/pos/tabs/unfire/"),
      { body: { session_key: cart.tabSessionKey, line_ids: [lineId] } },
    );
    if (response.tab) setFromTabPayload(response.tab);
    await refresh();
  } catch (err: any) {
    serverError.value = err?.data?.detail || err?.data?.error?.message || err?.message || "Falha ao cancelar envio à cozinha.";
  } finally {
    firing.value = false;
  }
}

async function openCashShift(amount: string) {
  serverError.value = "";
  busy.value = true;
  try {
    await action.call(actionHref(actions.value, "open_cash_shift", "/api/v1/backstage/pos/cash/open/"), {
      body: { opening_amount: amount || "0", terminal_ref: pos.value?.terminal_ref || "" },
    });
    cashDialogOpen.value = false;
    await refresh();
  } catch (err: any) {
    serverError.value = err?.data?.detail || err?.data?.error?.message || err?.message || "Falha ao abrir caixa.";
  } finally {
    busy.value = false;
  }
}

async function closeCashShift(payload: { amount: string; notes: string }) {
  serverError.value = "";
  busy.value = true;
  try {
    await action.call(actionHref(actions.value, "close_cash_shift", "/api/v1/backstage/pos/cash/close/"), {
      body: { closing_amount: payload.amount || "0", notes: payload.notes },
    });
    cashDialogOpen.value = false;
    await refresh();
  } catch (err: any) {
    serverError.value = err?.data?.detail || err?.data?.error?.message || err?.message || "Falha ao fechar caixa.";
  } finally {
    busy.value = false;
  }
}

async function registerCashMovement(payload: { kind: string; amount: string; reason: string }) {
  serverError.value = "";
  busy.value = true;
  try {
    await action.call(actionHref(actions.value, "cash_movement", "/api/v1/backstage/pos/cash/movement/"), {
      body: { kind: payload.kind, amount: payload.amount || "0", reason: payload.reason },
    });
    await refresh();
  } catch (err: any) {
    serverError.value = err?.data?.detail || err?.data?.error?.message || err?.message || "Falha ao registrar movimento.";
  } finally {
    busy.value = false;
  }
}

// Keyboard and scanner (spec: F2 tab board, F3 product search, F4 checkout/review,
// Escape backs out of checkout, "/" focuses product search when not editing).
const tabInputRef = ref<{ inputRef?: HTMLInputElement } | null>(null);
const searchInputRef = ref<{ inputRef?: HTMLInputElement } | null>(null);

function focusUiInput(component: { inputRef?: HTMLInputElement } | null) {
  component?.inputRef?.focus();
}

async function gotoTabInput() {
  checkoutMode.value = false;
  await nextTick();
  focusUiInput(tabInputRef.value);
}

async function gotoProductSearch() {
  if (!canUseCart.value) return;
  checkoutMode.value = false;
  await nextTick();
  focusUiInput(searchInputRef.value);
}

function onGlobalKeydown(event: KeyboardEvent) {
  if (locked.value || !pos.value) return;
  const target = event.target as HTMLElement | null;
  const isEditing = !!target
    && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);

  switch (event.key) {
    case "Escape":
      if (checkoutMode.value) {
        event.preventDefault();
        checkoutMode.value = false;
      }
      return;
    case "F2":
      event.preventDefault();
      gotoTabInput();
      return;
    case "F3":
      event.preventDefault();
      gotoProductSearch();
      return;
    case "F4":
      event.preventDefault();
      if (checkoutMode.value) reviewCheckout();
      else if (cart.items.length) prepareCheckout();
      return;
    case "/":
      if (!isEditing) {
        event.preventDefault();
        gotoProductSearch();
      }
  }
}

onMounted(() => window.addEventListener("keydown", onGlobalKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onGlobalKeydown));
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
          <PosTerminalHealth
            v-if="pos"
            :terminal-label="pos.terminal_label"
            :health-status="pos.terminal_health_status"
            :components="pos.terminal_components"
            :fiscal-status="pos.fiscal_status"
            :fiscal-label="pos.fiscal_label"
            :fiscal-message="pos.fiscal_message"
          />
          <UiButton
            v-if="pos"
            variant="outline"
            size="sm"
            class="gap-2 tabular-nums"
            :class="pos.has_open_cash_session ? '' : 'border-amber-500/50 text-amber-700 hover:text-amber-700'"
            aria-label="Caixa"
            title="Caixa"
            @click="cashDialogOpen = true"
          >
            <Icon name="lucide:wallet" class="size-4" />
            <span v-if="pos.has_open_cash_session && shift">{{ shift.count }} hoje · {{ shift.total_display }}</span>
            <span v-else>Abrir caixa</span>
          </UiButton>
          <UiBadge v-if="activeOperator" variant="default" class="gap-1">
            <Icon name="lucide:user" class="size-3.5" />
            {{ activeOperator.name }}
          </UiBadge>
          <UiButton
            v-if="activeOperator"
            variant="outline"
            size="icon-sm"
            aria-label="Travar caixa"
            title="Travar caixa"
            @click="lock()"
          >
            <Icon name="lucide:lock" class="size-4" />
          </UiButton>
          <UiButton variant="outline" size="icon-sm" aria-label="Atualizar" title="Atualizar" :disabled="pending" @click="refresh()">
            <Icon name="lucide:refresh-cw" class="size-4" :class="pending ? 'animate-spin' : ''" />
          </UiButton>
        </div>
      </div>
    </header>

    <PosLockScreen
      v-if="locked && !!pos"
      :operators="operators"
      :busy="lockBusy"
      :error="lockError"
      @unlock="onUnlock"
    />

    <div class="mx-auto grid max-w-screen-2xl gap-4 px-4 py-4">
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

      <PosCheckoutWorkspace
        v-if="checkoutMode"
        :tab-display="cart.tabDisplay"
        :items="cart.items"
        :has-open-tab="hasOpenTab"
        :fulfillment-options="pos?.fulfillment_options || []"
        :payment-methods="pos?.payment_methods || []"
        :payment-collections="pos?.payment_collections || []"
        :checkout-contract="checkoutContract"
        :address-autocomplete="addressAutocomplete"
        :customer-lookup="customerLookup"
        :review="review"
        :discount-types="checkoutContract?.discount_types || []"
        :discount-reasons="checkoutContract?.discount_reasons || []"
        v-model:discount-type="cart.discountType"
        v-model:discount-value="cart.discountValue"
        v-model:discount-reason="cart.discountReason"
        v-model:manager-username="cart.managerUsername"
        v-model:manager-pin="cart.managerPin"
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
        :lookup-busy="lookupBusy"
        @back="checkoutMode = false"
        @review="reviewCheckout"
        @submit="submitSale"
        @lookup-customer="lookupCustomer"
        @apply-customer-favorite="applyCustomerFavorite"
        @repeat-customer-last-order="repeatCustomerLastOrder"
        @pick-saved-address="applySavedAddress"
      />

      <div v-else class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_420px]">
      <section class="grid gap-4">
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
                ref="tabInputRef"
                :model-value="tabInput"
                class="max-w-40"
                :maxlength="tabMaxLength"
                :placeholder="tabPlaceholder"
                @update:model-value="updateTabInput"
              />
              <UiButton type="submit" :disabled="busy || !tabInput.trim()">Abrir / nova</UiButton>
            </form>
          </div>
          <div v-if="tabs.length" class="flex flex-wrap items-center gap-2">
            <div class="flex gap-1">
              <UiButton
                size="sm"
                variant="outline"
                :class="tabFilter === 'all' ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground' : ''"
                @click="tabFilter = 'all'"
              >
                Todas {{ tabs.length }}
              </UiButton>
              <UiButton
                size="sm"
                variant="outline"
                :class="tabFilter === 'in_use' ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground' : ''"
                @click="tabFilter = 'in_use'"
              >
                Em uso {{ openTabsCount }}
              </UiButton>
            </div>
            <div class="ml-auto flex gap-1">
              <UiButton
                size="icon-sm"
                variant="outline"
                aria-label="Ver em grade"
                title="Grade"
                :class="tabView === 'grid' ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground' : ''"
                @click="tabView = 'grid'"
              >
                <Icon name="lucide:layout-grid" class="size-4" />
              </UiButton>
              <UiButton
                size="icon-sm"
                variant="outline"
                aria-label="Ver em lista"
                title="Lista"
                :class="tabView === 'list' ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground' : ''"
                @click="tabView = 'list'"
              >
                <Icon name="lucide:list" class="size-4" />
              </UiButton>
            </div>
          </div>

          <p v-if="!tabs.length" class="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
            Nenhuma comanda ainda. Digite uma referência acima para abrir a primeira.
          </p>
          <p v-else-if="!visibleTabs.length" class="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
            Nenhuma comanda em uso agora.
            <button type="button" class="font-medium underline underline-offset-4" @click="tabFilter = 'all'">Ver todas</button>
          </p>
          <div
            v-else
            class="max-h-56 overflow-y-auto pr-1"
            :class="tabView === 'grid' ? 'grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4' : 'grid gap-2'"
          >
            <button
              v-for="tab in visibleTabs"
              :key="tab.ref"
              type="button"
              class="grid gap-1 rounded-lg border px-3 py-2 text-left transition hover:border-primary/50 hover:bg-accent"
              :class="[
                cart.tabRef === tab.ref ? 'border-primary bg-primary/5' : '',
                tab.state === 'in_use' ? 'border-amber-500/40 bg-amber-500/10' : ''
              ]"
              @click="hasDraftWithoutTab ? requestTabAssociation('start') : openTab(tab)"
            >
              <div class="flex items-baseline justify-between gap-2">
                <span class="font-semibold tabular-nums">#{{ tab.display_ref }}</span>
                <span class="text-xs text-muted-foreground">{{ tab.status_label }}</span>
              </div>
              <span v-if="tab.customer_name" class="truncate text-xs font-medium">{{ tab.customer_name }}</span>
              <span v-if="tab.items_preview" class="truncate text-xs text-muted-foreground">{{ tab.items_preview }}</span>
              <span v-if="tab.item_count" class="text-xs font-semibold tabular-nums">
                {{ tab.item_count }} {{ tab.item_count === 1 ? "item" : "itens" }} · {{ tab.total_display }}
              </span>
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
              <UiInput ref="searchInputRef" v-model="search" class="pl-9" type="search" placeholder="Buscar produto por nome ou SKU" autofocus />
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
          :customer-lookup="customerLookup"
          :requires-tab="tabRequiredForCart"
          :has-open-tab="hasOpenTab"
          v-model:customer-name="cart.customerName"
          v-model:customer-phone="cart.customerPhone"
          :loading="busy"
          :saving="saving"
          :lookup-busy="lookupBusy"
          :can-fire="canFireTab"
          :firing="firing"
          @increment="(sku) => setQty(sku, productQty(sku) + 1)"
          @decrement="(sku) => setQty(sku, productQty(sku) - 1)"
          @remove="(sku) => setQty(sku, 0)"
          @save="saveTab"
          @prepare="prepareCheckout"
          @move="openMoveDialog"
          @fire="fireTab"
          @unfire="unfireTab"
          @clear="clearCurrentTab"
          @request-tab="requestTabAssociation('start')"
          @lookup-customer="lookupCustomer"
          @apply-customer-favorite="applyCustomerFavorite"
          @repeat-customer-last-order="repeatCustomerLastOrder"
        />
        <p class="mt-3 text-xs text-muted-foreground">
          {{ itemCount }} item(ns) · {{ totalDisplay }}. O backend confirma disponibilidade, total final, status e gravação do pedido.
        </p>
      </aside>
      </div>
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
      :max-length="tabMaxLength"
      :placeholder="tabPlaceholder"
      :disallowed-chars="tabDisallowedChars"
      @confirm="openTabFromDialog"
      @select="openTabFromDialog"
    />

    <PosCashPanel
      v-if="pos"
      v-model:open="cashDialogOpen"
      :cash-runtime="pos.cash_runtime"
      :shift="shift"
      :has-open-shift="pos.has_open_cash_session"
      :movement-kinds="movementKinds"
      :operator-name="activeOperator?.name || ''"
      :busy="busy"
      @open-shift="openCashShift"
      @close-shift="closeCashShift"
      @movement="registerCashMovement"
    />

    <PosMoveLinesDialog
      v-model:open="moveDialogOpen"
      :tab-display="cart.tabDisplay"
      :items="cart.items"
      :suggested-split-ref="suggestedSplitRef"
      :other-tabs="otherOpenTabs"
      :busy="busy"
      @submit="submitMove"
    />
  </main>
</template>
