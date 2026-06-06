<script setup lang="ts">
import type {
  POSAddressAutocompleteProjection,
  POSCartItem,
  POSCloseSaleResponse,
  POSCustomerLookupProjection,
  POSCustomerLookupResponse,
  POSProductProjection,
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
  resolvePayment,
} from "~/utils/posIntent";
import { sanitizeTabRef as sanitizeTabRefShape, sortTabs } from "~/presentation/tabBoard";
import {
  draftAssociationTargetStates,
  requiresOpenTabForCart,
  requiresTabBeforeSave,
  tabRefDisallowedChars,
  tabRefMaxLength,
  tabRefPlaceholder,
} from "~/utils/posTabLifecycle";
import { toast } from "vue-sonner";

type FulfillmentType = "pickup" | "delivery";
type PaymentCollection = "terminal" | "on_delivery";

const apiPath = usePosApiPath();
const action = usePosAction();
const colorMode = useColorMode();
function toggleColorMode() {
  colorMode.preference = colorMode.value === "dark" ? "light" : "dark";
}
const runtimeConfig = useRuntimeConfig();
// In prod the POS and Django share one domain (path-routed), so admin links are
// relative and resolve against the current origin. Only dev needs the absolute
// Django host (POS :3002 vs Django :8000).
const djangoOrigin = computed(() => (import.meta.dev ? String(runtimeConfig.public.djangoPublicBaseUrl || "") : ""));
const loginUrl = computed(() => {
  const next = String(runtimeConfig.public.operatorLoginNextPath || "/pos/");
  return `${djangoOrigin.value}/admin/login/?next=${encodeURIComponent(next)}`;
});
const requestHeaders = import.meta.server ? useRequestHeaders(["cookie"]) : undefined;

const { data, pos, shift, tabs, operators, actions, pending, error, refresh } = await usePosTerminal();

// Operator identity / lock screen (PIN attribution). Instantiated here in the
// shell's <script setup> so its lifecycle hooks (auto-lock idle timer) survive
// the await above — Vue/Nuxt only preserve setup context across awaits inside
// `<script setup>`, not inside a plain composable module.
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

const search = ref("");
const activeCollection = ref("");
const tabInput = ref("");
const busy = ref(false);
const saving = ref(false);
// Auto-persist the comanda (Odoo-style): no manual "Salvar". tabLoading guards
// against re-saving right after a programmatic load (setFromTabPayload).
const tabLoading = ref(false);
const firing = ref(false);
const renamingTab = ref(false);
const cancellingSale = ref(false);
const cancelSaleReason = ref("");
const saleCancelled = ref(false);
const lookupBusy = ref(false);
const serverError = ref("");
// Errors surface as a dismissible floating toast (UI Thing Sonner), not an
// inline banner. Clear the ref after showing so it doesn't linger.
watch(serverError, (message) => {
  if (!message) return;
  toast.error(message);
  serverError.value = "";
});
const result = ref<{ orderRef: string; nextUrl: string } | null>(null);
const checkoutMode = ref(false);
// Odoo-style: the Tabs screen is the first screen; opening a tab moves to the
// sale workspace. "Comandas" returns to the Tabs screen with the tab still open.
const showTabs = ref(true);
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

const checkoutContract = computed(() => pos.value?.checkout || null);
const checkoutCapabilities = computed(() => checkoutContract.value?.capabilities || {});
const cashManagement = computed(() => (checkoutCapabilities.value as Record<string, any>)?.cash_management || null);
const kitchenHandoff = computed(() => (checkoutCapabilities.value as Record<string, any>)?.kitchen_handoff || null);
const canFireTab = computed(() => Boolean(kitchenHandoff.value?.fire_action_ref));
const tabManipulation = computed(() => (checkoutCapabilities.value as Record<string, any>)?.tab_manipulation || null);
const canRenameTab = computed(() => Boolean(tabManipulation.value?.rename_action_ref));
const saleCorrection = computed(() => (checkoutCapabilities.value as Record<string, any>)?.sale_correction || null);
const canCancelRecentSale = computed(() => Boolean(saleCorrection.value?.cancel_recent_action_ref));
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
const inSaleView = computed(() => !showTabs.value && hasOpenTab.value);
function goToTabs() {
  showTabs.value = true;
}
const hasDraftWithoutTab = computed(() => !hasOpenTab.value && cart.items.length > 0);
const canUseCart = computed(() => !tabRequiredForCart.value || hasOpenTab.value);
const deliveryFeeQ = computed(() => moneyInputToQ(cart.deliveryFeeInput));
const tenderedAmountQ = computed(() => moneyInputToQ(cart.tenderedAmountInput));

// Payment by injection (Odoo-style): the operator adds tender lines in any form;
// the method is derived (no "mixed" selection). Finalize is gated until covered.
const paymentTotalQ = computed(() => review.value?.total_q || cartTotalQ(cart.items));
const tenderSumQ = computed(() => cart.paymentTenders.reduce((sum, tender) => sum + (tender.amount_q || 0), 0));
const paymentRemainingQ = computed(() => paymentTotalQ.value - tenderSumQ.value);
const paymentChangeQ = computed(() => Math.max(0, tenderSumQ.value - paymentTotalQ.value));
const paymentCovered = computed(() => cart.paymentTenders.length > 0 && paymentRemainingQ.value <= 0);

// Odoo-style payment: tapping a method adds a tender for the remaining due
// (the first one = the total). The numpad then edits the SELECTED line.
const selectedTenderIndex = ref(-1);
const tenderFresh = ref(true);

function addTender(method: string) {
  const amountQ = Math.max(0, paymentRemainingQ.value);
  if (amountQ <= 0) return;
  cart.paymentTenders.push({ method, amount_q: amountQ, collection: cart.paymentCollection });
  selectedTenderIndex.value = cart.paymentTenders.length - 1;
  tenderFresh.value = true;
}

// A cash bill (R$20/50/100/Exato) is, by definition, a cash payment — add it
// directly without making the operator also tap "Dinheiro". May overpay (change).
function addCashTender(amountQ: number) {
  if (!amountQ || amountQ <= 0) return;
  cart.paymentTenders.push({ method: "cash", amount_q: amountQ, collection: cart.paymentCollection });
  selectedTenderIndex.value = cart.paymentTenders.length - 1;
  tenderFresh.value = true;
}

function removeTender(index: number) {
  cart.paymentTenders.splice(index, 1);
  if (selectedTenderIndex.value >= cart.paymentTenders.length) {
    selectedTenderIndex.value = cart.paymentTenders.length - 1;
  }
}

function selectTender(index: number) {
  selectedTenderIndex.value = index;
  tenderFresh.value = true;
}

// Numpad edits the amount (cents) of the selected tender. First keystroke after
// selecting/adding replaces; the rest append.
function tenderDigit(digit: string) {
  const tender = cart.paymentTenders[selectedTenderIndex.value];
  if (!tender) return;
  const base = tenderFresh.value ? 0 : tender.amount_q;
  tenderFresh.value = false;
  tender.amount_q = Math.min(99_999_999, base * 10 + (Number.parseInt(digit, 10) || 0));
}
function tenderBackspace() {
  const tender = cart.paymentTenders[selectedTenderIndex.value];
  if (!tender) return;
  tenderFresh.value = false;
  tender.amount_q = Math.floor(tender.amount_q / 10);
}
function tenderClear() {
  const tender = cart.paymentTenders[selectedTenderIndex.value];
  if (!tender) return;
  tenderFresh.value = true;
  tender.amount_q = 0;
}
// Quick-add (+R$10/50/100): add to the selected tender, or open a cash line.
function tenderAdd(cents: number) {
  if (!cents) return;
  const tender = cart.paymentTenders[selectedTenderIndex.value];
  if (tender) {
    tenderFresh.value = false;
    tender.amount_q = Math.min(99_999_999, tender.amount_q + cents);
  } else {
    addCashTender(cents);
  }
}
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

const sortedTabs = computed(() => sortTabs(tabs.value));
const otherOpenTabs = computed(() =>
  sortedTabs.value.filter((tab) => tab.state === "in_use" && tab.session_key && tab.ref !== cart.tabRef),
);
const suggestedSplitRef = computed(() => (cart.tabDisplay ? `${cart.tabDisplay}-2` : ""));

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

// Odoo has no manual "review" step — the total is live. When something that
// affects the TOTAL changes during checkout (discount/fulfillment/delivery
// fee), auto re-review (debounced) so the total updates on its own. Finalize
// stays disabled while the fresh total is in flight. Payment tenders, method,
// fiscal/receipt and customer metadata do NOT change the total → no re-review.
let autoReviewTimer: ReturnType<typeof setTimeout> | null = null;
function scheduleAutoReview() {
  if (!checkoutMode.value) return;
  review.value = null;
  if (autoReviewTimer) clearTimeout(autoReviewTimer);
  autoReviewTimer = setTimeout(() => {
    autoReviewTimer = null;
    if (checkoutMode.value && cart.items.length) reviewCheckout();
  }, 450);
}
watch(() => [
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
  cart.discountType,
  cart.discountValue,
  cart.discountReason,
], () => scheduleAutoReview());

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

function setLineDiscount(sku: string, value: number, reason: string) {
  const item = cart.items.find((entry) => entry.sku === sku);
  if (!item) return;
  review.value = null;
  if (value > 0) item.discount = { value, reason };
  else delete item.discount;
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
  selectedTenderIndex.value = -1;
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
  showTabs.value = true;
}

function sanitizeTabRef(value: string): string {
  return sanitizeTabRefShape(value, {
    maxLength: tabMaxLength.value,
    disallowedChars: tabDisallowedChars.value,
  });
}

function assignTabIdentityFromPayload(payload: POSTabPayload) {
  cart.tabRef = payload.tab_ref;
  cart.tabDisplay = payload.tab_display;
  cart.tabSessionKey = payload.tab_session_key || payload.session_key;
  showTabs.value = false;
}

function setFromTabPayload(payload: POSTabPayload) {
  tabLoading.value = true;
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
  // Spec: do not replay saved/default tender lines as operator payment input.
  cart.paymentTenders = [];
  selectedTenderIndex.value = -1;
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
  void nextTick(() => { tabLoading.value = false; });
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
  const resolvedPayment = resolvePayment(cart.paymentTenders, paymentTotalQ.value);
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
    paymentMethod: resolvedPayment.paymentMethod,
    paymentCollection: cart.paymentCollection,
    paymentTenders: resolvedPayment.paymentTenders,
    tenderedAmountQ: resolvedPayment.tenderedAmountQ,
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

// Serialize all tab persistence so the debounced autosave can never race the
// explicit save inside checkout/fire/move (concurrent save_tab → DB lock).
let persistQueue: Promise<unknown> = Promise.resolve();
function persistTab(quiet = false): Promise<void> {
  const run = async () => {
    const state = currentIntentState();
    cart.clientRequestId = state.clientRequestId;
    await action.call(actionHref(actions.value, "save_tab", "/api/v1/backstage/pos/tabs/save/"), {
      body: buildPosSaleIntent(state, checkoutContract.value?.intent_version),
    });
    if (!quiet) await refresh();
  };
  persistQueue = persistQueue.then(run, run);
  return persistQueue as Promise<void>;
}

// Debounced auto-persist: fires on cart/sale-data changes while a tab is open,
// outside checkout. Quiet save (no projection refresh) to stay light.
let autosaveTimer: ReturnType<typeof setTimeout> | null = null;
function scheduleAutosave() {
  if (tabLoading.value || !hasOpenTab.value || checkoutMode.value) return;
  if (autosaveTimer) clearTimeout(autosaveTimer);
  autosaveTimer = setTimeout(() => {
    autosaveTimer = null;
    if (!hasOpenTab.value || checkoutMode.value || busy.value || saving.value) return;
    persistTab(true).catch(() => {});
  }, 1200);
}
watch(() => [
  cart.items,
  cart.customerName,
  cart.customerRef,
  cart.customerPhone,
  cart.customerTaxId,
  cart.customerEmail,
  cart.fulfillmentType,
  cart.deliveryAddress,
  cart.deliveryStreetNumber,
  cart.deliveryNeighborhood,
  cart.deliveryComplement,
  cart.deliveryInstructions,
  cart.deliveryDate,
  cart.deliveryTimeSlot,
  cart.deliveryFeeInput,
  cart.orderNotes,
], () => scheduleAutosave(), { deep: true });

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
  saleCancelled.value = false;
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
        nextUrl: `${djangoOrigin.value}/admin/operacao/pedidos/${encodeURIComponent(orderRef)}/`,
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
    // Persist on-screen items first so the server fires exactly what the
    // operator sees (the local draft may not be autosaved yet).
    await persistTab(true);
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

async function renameTab(newTabRef: string) {
  if (!cart.tabSessionKey || !newTabRef) return;
  serverError.value = "";
  renamingTab.value = true;
  try {
    const response = await action.call<{ tab: POSTabPayload | null }>(
      actionHref(actions.value, "rename_tab", "/api/v1/backstage/pos/tabs/rename/"),
      { body: { session_key: cart.tabSessionKey, new_tab_ref: newTabRef } },
    );
    if (response.tab) setFromTabPayload(response.tab);
    await refresh();
  } catch (err: any) {
    serverError.value = err?.data?.detail || err?.data?.error?.message || err?.message || "Falha ao renomear comanda.";
  } finally {
    renamingTab.value = false;
  }
}

async function cancelRecentSale() {
  if (!result.value) return;
  serverError.value = "";
  cancellingSale.value = true;
  try {
    const orderRef = result.value.orderRef;
    const reason = cancelSaleReason.value.trim();
    await action.call(
      actionHref(actions.value, "cancel_recent_sale", "/api/v1/backstage/pos/sale/recent/cancel/"),
      { body: { order_ref: orderRef, ...(reason ? { reason } : {}) } },
    );
    result.value = null;
    cancelSaleReason.value = "";
    saleCancelled.value = true;
    await refresh();
  } catch (err: any) {
    serverError.value = err?.data?.detail || err?.data?.error?.message || err?.message || "Falha ao cancelar venda.";
  } finally {
    cancellingSale.value = false;
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
const tabBoardRef = ref<{ focus: () => void } | null>(null);
const searchInputRef = ref<{ inputRef?: HTMLInputElement } | null>(null);

function focusUiInput(component: { inputRef?: HTMLInputElement } | null) {
  component?.inputRef?.focus();
}

async function gotoTabInput() {
  checkoutMode.value = false;
  await nextTick();
  tabBoardRef.value?.focus();
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
  <main class="flex min-h-dvh flex-col bg-background text-foreground md:h-[100dvh] md:min-h-0 md:overflow-hidden">
    <header class="shrink-0 bg-primary text-primary-foreground shadow-sm">
      <div class="mx-auto flex max-w-screen-2xl flex-wrap items-center justify-between gap-3 px-4 py-2">
        <div class="flex items-baseline gap-1.5">
          <span class="text-lg font-semibold tracking-tight">POS</span>
          <span class="text-xs font-medium uppercase tracking-wide text-primary-foreground/70">Shopman</span>
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
            variant="ghost"
            size="sm"
            class="gap-2 tabular-nums text-primary-foreground hover:bg-primary-foreground/15 hover:text-primary-foreground"
            :class="pos.has_open_cash_session ? '' : 'ring-1 ring-primary-foreground/40'"
            aria-label="Caixa"
            title="Caixa"
            @click="cashDialogOpen = true"
          >
            <Icon name="lucide:wallet" class="size-4" />
            <span v-if="pos.has_open_cash_session && shift">{{ shift.count }} hoje · {{ shift.total_display }}</span>
            <span v-else>Abrir caixa</span>
          </UiButton>
          <UiBadge v-if="activeOperator" class="gap-1 border-transparent bg-primary-foreground/20 text-primary-foreground">
            <Icon name="lucide:user" class="size-3.5" />
            {{ activeOperator.name }}
          </UiBadge>
          <UiButton
            v-if="activeOperator"
            variant="ghost"
            size="icon-sm"
            class="text-primary-foreground hover:bg-primary-foreground/15 hover:text-primary-foreground"
            aria-label="Travar caixa"
            title="Travar caixa"
            @click="lock()"
          >
            <Icon name="lucide:lock" class="size-4" />
          </UiButton>
          <ClientOnly>
            <UiButton
              variant="ghost"
              size="icon-sm"
              class="text-primary-foreground hover:bg-primary-foreground/15 hover:text-primary-foreground"
              :aria-label="colorMode.value === 'dark' ? 'Tema claro' : 'Tema escuro'"
              :title="colorMode.value === 'dark' ? 'Tema claro' : 'Tema escuro'"
              @click="toggleColorMode"
            >
              <Icon :name="colorMode.value === 'dark' ? 'lucide:sun' : 'lucide:moon'" class="size-4" />
            </UiButton>
            <template #fallback>
              <UiButton variant="ghost" size="icon-sm" class="text-primary-foreground hover:bg-primary-foreground/15" aria-label="Tema" title="Tema">
                <Icon name="lucide:sun-moon" class="size-4" />
              </UiButton>
            </template>
          </ClientOnly>
          <UiButton variant="ghost" size="icon-sm" class="text-primary-foreground hover:bg-primary-foreground/15 hover:text-primary-foreground" aria-label="Atualizar" title="Atualizar" :disabled="pending" @click="refresh()">
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

    <div class="mx-auto flex w-full max-w-screen-2xl flex-1 flex-col gap-3 px-4 py-3 md:min-h-0 md:overflow-hidden">
      <div class="grid shrink-0 gap-3 empty:hidden">
      <UiAlert v-if="result" class="border-green-500/30 bg-green-500/10 text-green-800">
        <Icon name="lucide:circle-check" class="size-4" />
        <UiAlertTitle>Pedido criado: {{ result.orderRef }}</UiAlertTitle>
        <UiAlertDescription>
          <div class="flex flex-col gap-2">
            <a class="font-semibold underline underline-offset-4" :href="result.nextUrl">Abrir no gestor</a>
            <div v-if="canCancelRecentSale" class="flex flex-col gap-2 border-t border-green-500/20 pt-2">
              <UiInput
                v-model="cancelSaleReason"
                placeholder="Motivo do cancelamento (opcional)"
                class="h-8 text-sm"
              />
              <UiButton
                variant="destructive"
                size="sm"
                class="self-start"
                :loading="cancellingSale"
                :disabled="cancellingSale"
                @click="cancelRecentSale"
              >
                <Icon name="lucide:rotate-ccw" class="size-4" />
                Cancelar venda
              </UiButton>
            </div>
          </div>
        </UiAlertDescription>
      </UiAlert>

      <UiAlert v-if="saleCancelled" class="border-amber-500/30 bg-amber-500/10 text-amber-800">
        <Icon name="lucide:circle-check" class="size-4" />
        <UiAlertTitle>Venda cancelada</UiAlertTitle>
        <UiAlertDescription>O pedido foi cancelado dentro da janela do operador.</UiAlertDescription>
      </UiAlert>
      </div>

      <div class="flex-1 md:min-h-0 md:overflow-hidden">
      <div v-if="error" class="grid h-full place-items-center p-4">
        <div class="grid max-w-sm gap-4 text-center">
          <div class="mx-auto grid size-14 place-items-center rounded-full border bg-muted">
            <Icon name="lucide:lock-keyhole" class="size-7 text-muted-foreground" />
          </div>
          <div class="grid gap-1.5">
            <h2 class="text-2xl font-semibold">Entre para operar o caixa</h2>
            <p class="text-sm text-muted-foreground">
              Faça login no gestor com uma conta autorizada a operar o POS e volte para esta tela.
            </p>
          </div>
          <a
            :href="loginUrl"
            class="inline-flex h-11 items-center justify-center gap-2 rounded-md bg-primary px-5 text-base font-medium text-primary-foreground transition hover:bg-primary/90"
          >
            <Icon name="lucide:log-in" class="size-5" />
            Entrar no gestor
          </a>
          <UiButton variant="outline" :disabled="pending" @click="refresh()">
            <Icon name="lucide:refresh-cw" class="size-4" :class="pending ? 'animate-spin' : ''" />
            Já entrei — atualizar
          </UiButton>
        </div>
      </div>
      <div v-else-if="checkoutMode" class="h-full md:overflow-y-auto">
      <PosCheckoutWorkspace
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
        :payment-tenders="cart.paymentTenders"
        :selected-tender-index="selectedTenderIndex"
        :payment-total-q="paymentTotalQ"
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
        v-model:issue-fiscal-document="cart.issueFiscalDocument"
        v-model:receipt-mode="cart.receiptMode"
        v-model:receipt-email="cart.receiptEmail"
        :loading="busy"
        :lookup-busy="lookupBusy"
        @back="checkoutMode = false"
        @review="reviewCheckout"
        @submit="submitSale"
        @add-tender="addTender"
        @add-cash-tender="addCashTender"
        @remove-tender="removeTender"
        @select-tender="selectTender"
        @tender-digit="tenderDigit"
        @tender-backspace="tenderBackspace"
        @tender-clear="tenderClear"
        @tender-add="tenderAdd"
        @lookup-customer="lookupCustomer"
        @apply-customer-favorite="applyCustomerFavorite"
        @repeat-customer-last-order="repeatCustomerLastOrder"
        @pick-saved-address="applySavedAddress"
      />
      </div>

      <div v-else class="h-full min-h-0">
        <!-- TABS VIEW — a tela de Comandas/Tabs é a PRIMEIRA (benchmark Odoo: tabs/mesas antes do pedido) -->
        <PosTabBoard
          v-if="!inSaleView"
          ref="tabBoardRef"
          v-model="tabInput"
          :tabs="tabs"
          :selected-tab-ref="cart.tabRef"
          :has-draft="hasDraftWithoutTab"
          :busy="busy"
          :max-length="tabMaxLength"
          :placeholder="tabPlaceholder"
          :disallowed-chars="tabDisallowedChars"
          @open="openTab"
          @request-association="requestTabAssociation('start')"
        />

        <!-- SALE VIEW — ticket à esquerda + produtos à direita (registradora Odoo) -->
        <div v-else class="grid h-full min-h-0 gap-4 md:grid-cols-[340px_minmax(0,1fr)]">
          <aside class="flex min-h-0 flex-col gap-3 md:order-1">
            <UiButton variant="outline" size="sm" class="w-fit shrink-0 gap-2" @click="goToTabs">
              <Icon name="lucide:arrow-left" class="size-4" />
              Comandas
            </UiButton>
            <div class="min-h-0 md:flex-1">
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
              :can-rename="canRenameTab"
              :discount-reasons="checkoutContract?.discount_reasons || []"
              @increment="(sku) => setQty(sku, productQty(sku) + 1)"
              @decrement="(sku) => setQty(sku, productQty(sku) - 1)"
              @remove="(sku) => setQty(sku, 0)"
              @set-qty="(sku, qty) => setQty(sku, qty)"
              @set-discount="setLineDiscount"
              @save="saveTab"
              @prepare="prepareCheckout"
              @move="openMoveDialog"
              @fire="fireTab"
              @unfire="unfireTab"
              @rename="renameTab"
              @clear="clearCurrentTab"
              @request-tab="requestTabAssociation('start')"
              @lookup-customer="lookupCustomer"
              @apply-customer-favorite="applyCustomerFavorite"
              @repeat-customer-last-order="repeatCustomerLastOrder"
            />
            </div>
            <p class="shrink-0 text-xs text-muted-foreground">
              {{ itemCount }} item(ns) · {{ totalDisplay }}. O backend confirma disponibilidade, total final, status e gravação do pedido.
            </p>
          </aside>

          <section class="flex min-h-0 flex-col gap-3 md:order-2">
            <div class="relative shrink-0">
              <Icon name="lucide:search" class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <UiInput ref="searchInputRef" v-model="search" class="h-11 pl-9 text-base" type="search" placeholder="Buscar produto por nome ou SKU" autofocus />
            </div>

            <div class="-mx-1 flex shrink-0 gap-1.5 overflow-x-auto px-1 pb-1 no-scrollbar">
              <button
                type="button"
                class="shrink-0 whitespace-nowrap rounded-md border px-3 py-1.5 text-sm font-medium transition"
                :class="activeCollection === '' ? 'border-primary bg-primary text-primary-foreground' : 'hover:border-primary/50 hover:bg-accent'"
                @click="activeCollection = ''"
              >
                Tudo
              </button>
              <button
                v-for="collection in orderedCollections"
                :key="collection.ref"
                type="button"
                class="shrink-0 whitespace-nowrap rounded-md border px-3 py-1.5 text-sm font-medium transition"
                :class="activeCollection === collection.ref ? 'border-primary bg-primary text-primary-foreground' : 'hover:border-primary/50 hover:bg-accent'"
                @click="activeCollection = collection.ref"
              >
                {{ collection.name }}
              </button>
            </div>

            <div class="-mx-1 px-1 md:min-h-0 md:flex-1 md:overflow-y-auto">
            <div v-if="pending" class="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
              <div v-for="idx in 12" :key="idx" class="aspect-[4/3] animate-pulse rounded-xl border bg-muted" />
            </div>
            <div v-else-if="!filteredProducts.length" class="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
              Nenhum produto encontrado.
            </div>
            <div v-else class="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
              <PosProductTile
                v-for="product in filteredProducts"
                :key="product.sku"
                :product="product"
                :qty="productQty(product.sku)"
                @add="addProduct"
              />
            </div>
            </div>
          </section>
        </div>
      </div>
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

    <UiSonner />
  </main>
</template>
