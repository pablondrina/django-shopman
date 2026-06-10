import type { ComputedRef } from "vue";

import type {
  Action,
  POSAddressAutocompleteProjection,
  POSCartItem,
  POSCloseSaleResponse,
  POSCustomerLookupProjection,
  POSCustomerLookupResponse,
  POSCustomerSearchResponse,
  POSCustomerSearchResult,
  POSProductProjection,
  POSProjection,
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
  isPaymentCovered,
  paymentChangeQ as computeChangeQ,
  type PaymentProofView,
  paymentProofView,
  paymentRemainingQ as computeRemainingQ,
  tenderSumQ as computeTenderSum,
} from "~/presentation/payment";
import {
  draftAssociationTargetStates,
  requiresOpenTabForCart,
  requiresTabBeforeSave,
  tabRefDisallowedChars,
  tabRefMaxLength,
  tabRefPlaceholder,
} from "~/utils/posTabLifecycle";
import type { PosReceiptSnapshot } from "~/presentation/receipt";
import { toast } from "vue-sonner";

type FulfillmentType = "pickup" | "delivery";
type PaymentCollection = "terminal" | "on_delivery";

interface PosSaleDeps {
  /** Read-side slices of the terminal Projection (from usePosTerminal). */
  pos: ComputedRef<POSProjection | null>;
  tabs: ComputedRef<POSTabProjection[]>;
  actions: ComputedRef<Action[]>;
  refresh: () => Promise<void>;
  /** Command transport (REST + Action) — created in the shell setup. */
  action: {
    call: <T = unknown>(
      path: string,
      options?: { method?: "POST" | "PUT" | "PATCH" | "DELETE"; body?: Record<string, unknown> },
    ) => Promise<T>;
  };
  apiPath: (path: string) => string;
  requestHeaders: Record<string, string> | undefined;
  /** Absolute Django origin (dev) for the post-sale "open in gestor" link. */
  djangoOrigin: ComputedRef<string>;
}

/**
 * Write-side of the POS sale: the open comanda's draft (`cart`) and every
 * session command (add/qty/discount, open/save/clear/rename/move/fire,
 * checkout/close, cash shift) emitted as idempotent intents via `action.call`
 * over the Projection's `Action[]`. The shell owns the Nuxt-bound primitives
 * (`action`/`apiPath`/`requestHeaders`/`djangoOrigin`) and passes them in, so
 * this stays a plain composable (no Nuxt composable runs after the shell's
 * `await`). It emits commands and tracks local draft state; the orchestrator
 * decides lifecycle/policy. Screens bind to the returned state and handlers.
 */
export function usePosSale(deps: PosSaleDeps) {
  const { pos, tabs, actions, refresh, action, apiPath, requestHeaders, djangoOrigin } = deps;

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
  const result = ref<{ orderRef: string; nextUrl: string; payment: PaymentProofView | null; receipt: PosReceiptSnapshot } | null>(null);
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
    paymentTenders: [] as Array<{ method: string; amount_q: number; collection: PaymentCollection; reference?: string; _virgin?: boolean }>,
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
  const tenderSumQ = computed(() => computeTenderSum(cart.paymentTenders));
  const paymentRemainingQ = computed(() => computeRemainingQ(cart.paymentTenders, paymentTotalQ.value));
  const paymentChangeQ = computed(() => computeChangeQ(cart.paymentTenders, paymentTotalQ.value));
  const paymentCovered = computed(() => isPaymentCovered(cart.paymentTenders, paymentTotalQ.value));

  // Odoo-style payment: tapping a method adds a tender for the remaining due
  // (the first one = the total). The numpad then edits the SELECTED line.
  const selectedTenderIndex = ref(-1);
  // In-progress decimal entry (Odoo): digits build the integer REAIS first, the
  // comma switches to centavos (max 2 places). So "2","5" → R$25,00 and only
  // "2","5",",","5" → R$25,50 — far less error-prone than cents-first (where 25
  // would mean R$0,25). null = no keyed entry yet; the first digit/comma starts a
  // fresh entry (so it replaces the shown amount, then appends).
  const tenderEntry = ref<string | null>(null);
  function entryToQ(entry: string): number {
    const n = Number.parseFloat((entry || "0").replace(",", "."));
    if (!Number.isFinite(n) || n < 0) return 0;
    return Math.min(99_999_999, Math.round(n * 100));
  }
  // Virginity is PER-TENDER (the `_virgin` flag on the tender), NOT global: a
  // tender is virgin while its amount is still the untouched system auto-fill.
  // The first cédula on a virgin tender REPLACES it (the operator starts counting
  // the cash handed over); thereafter cédulas ACCUMULATE. Crucially, just
  // SELECTING a tender (tapping its line) must NOT change its virginity — only
  // editing the amount does. (`_virgin` is internal; stripped before the intent.)
  const selectedTender = () => cart.paymentTenders[selectedTenderIndex.value];

  function addTender(method: string) {
    const amountQ = Math.max(0, paymentRemainingQ.value);
    if (amountQ <= 0) return;
    cart.paymentTenders.push({ method, amount_q: amountQ, collection: cart.paymentCollection, _virgin: true });
    selectedTenderIndex.value = cart.paymentTenders.length - 1;
    tenderEntry.value = null;
  }

  // A cash bill with no tender yet opens a cash line at that bill's value — the
  // operator already started counting, so it's NOT virgin (next bill accumulates).
  function addCashTender(amountQ: number) {
    if (!amountQ || amountQ <= 0) return;
    cart.paymentTenders.push({ method: "cash", amount_q: amountQ, collection: cart.paymentCollection, _virgin: false });
    selectedTenderIndex.value = cart.paymentTenders.length - 1;
    tenderEntry.value = null;
  }

  function removeTender(index: number) {
    cart.paymentTenders.splice(index, 1);
    if (selectedTenderIndex.value >= cart.paymentTenders.length) {
      selectedTenderIndex.value = cart.paymentTenders.length - 1;
    }
    tenderEntry.value = null;
  }

  function selectTender(index: number) {
    selectedTenderIndex.value = index;
    tenderEntry.value = null; // typing on it starts fresh; its _virgin is untouched
  }

  // A digit grows the decimal entry (reais first; ≤2 places after the comma).
  function tenderDigit(digit: string) {
    const tender = selectedTender();
    if (!tender) return;
    let entry = tenderEntry.value ?? "";
    if (entry.includes(",")) {
      if ((entry.split(",")[1] ?? "").length >= 2) return; // centavos full
    } else if (entry.replace(/^0+/, "").length >= 7) {
      return; // keep the integer part sane
    }
    entry += digit;
    tenderEntry.value = entry;
    tender._virgin = false;
    tender.amount_q = entryToQ(entry);
  }
  // The comma key (USD would be a dot): switch to centavos.
  function tenderComma() {
    const tender = selectedTender();
    if (!tender) return;
    let entry = tenderEntry.value ?? "";
    if (entry === "") entry = "0";
    if (!entry.includes(",")) entry += ",";
    tenderEntry.value = entry;
    tender._virgin = false;
    tender.amount_q = entryToQ(entry);
  }
  function tenderBackspace() {
    const tender = selectedTender();
    if (!tender) return;
    // First backspace over an auto amount clears it (Odoo), then trims the entry.
    const entry = (tenderEntry.value ?? "").slice(0, -1);
    tenderEntry.value = entry;
    tender._virgin = false;
    tender.amount_q = entryToQ(entry);
  }
  function tenderClear() {
    const tender = selectedTender();
    if (!tender) return;
    tenderEntry.value = "";
    tender._virgin = false;
    tender.amount_q = 0;
  }
  // A cédula tap reflects a note the customer handed over. On a VIRGIN tender the
  // first tap REPLACES the auto value (start counting the cash handed: total
  // R$66,30 → +R$50 = R$50,00, restante; +R$50 = R$100,00, troco R$33,70).
  // Thereafter it ACCUMULATES. No tender yet → opens a cash line at that note.
  function tenderAdd(cents: number) {
    if (!cents) return;
    const tender = selectedTender();
    if (!tender) {
      addCashTender(cents);
      return;
    }
    const base = tender._virgin ? 0 : tender.amount_q;
    tender.amount_q = Math.min(99_999_999, base + cents);
    tender._virgin = false;
    tenderEntry.value = null;
  }

  // "Exato": set the selected tender to settle exactly what the OTHER tenders
  // still leave owed (so the sale is covered, change zero). Snaps a split line
  // back to the remainder after typing a partial amount.
  function tenderExact() {
    const tender = cart.paymentTenders[selectedTenderIndex.value];
    if (!tender) return;
    const others = cart.paymentTenders.reduce(
      (sum, line, idx) => (idx === selectedTenderIndex.value ? sum : sum + line.amount_q),
      0,
    );
    tender.amount_q = Math.max(0, paymentTotalQ.value - others);
    tender._virgin = true; // a system value again: a following cédula replaces it
    tenderEntry.value = null;
  }

  // The method of the line the instrument (numpad/cédulas) is editing, or "" when
  // none is selected — drives whether the cash cédulas are offered.
  const selectedTenderMethod = computed(
    () => cart.paymentTenders[selectedTenderIndex.value]?.method || "",
  );
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

  // Operator unit-price override (numpad "Preço"): set the line's price and flag
  // it when it differs from the catalog — the kernel then freezes it (the pricing
  // modifier skips re-pricing) and the server review requires manager approval.
  // Typing the catalog price back clears the override.
  function setLinePrice(sku: string, priceQ: number) {
    const item = cart.items.find((entry) => entry.sku === sku);
    if (!item) return;
    review.value = null;
    checkoutMode.value = false;
    const catalogQ = pos.value?.products.find((product) => product.sku === sku)?.price_q ?? item.price_q;
    const next = Math.max(0, Math.min(99_999_999, Math.round(priceQ)));
    item.price_q = next;
    item.price_overridden = next !== catalogQ;
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

  // Just-in-time get-or-create: when the operator finishes defining a customer
  // (picks a result, or types a new name+phone and concludes), resolve OR create
  // the record NOW — not deferred to order commit — so the customer (ref, memory,
  // address) exists and attaches to the cart/tab immediately. Idempotent: an
  // existing customer is found, a fresh one is created once.
  async function resolveCustomer() {
    const name = cart.customerName.trim();
    const phone = cart.customerPhone.trim();
    const taxId = cart.customerTaxId.trim();
    const email = cart.customerEmail.trim();
    if (!name && !phone && !taxId && !email) return;
    lookupBusy.value = true;
    serverError.value = "";
    try {
      const path = actionHref(actions.value, "customer_resolve", "/api/v1/backstage/pos/customer/resolve/");
      const response = await action.call<POSCustomerLookupResponse>(path, {
        body: { customer_name: name, customer_phone: phone, customer_tax_id: taxId, customer_email: email },
      });
      if (!response.customer) return;
      customerLookup.value = response.customer;
      cart.customerRef = response.customer.ref;
      cart.customerName = response.customer.name || cart.customerName;
      cart.customerPhone = response.customer.phone || cart.customerPhone;
      cart.customerEmail = response.customer.email || cart.customerEmail;
      if (cart.fulfillmentType === "delivery" && response.customer.default_address && !cart.deliveryAddress.trim()) {
        applySavedAddress(response.customer.default_address);
      }
    } catch (err: any) {
      serverError.value = err?.data?.detail || err?.message || "Falha ao salvar o cliente.";
    } finally {
      lookupBusy.value = false;
    }
  }

  // Multi-key customer search (name/phone/CPF/email): the customer modal's search
  // field hits this; results are a list to pick from. Picking one fills the cart
  // and runs the full lookup (memory + saved address).
  const customerSearchResults = ref<POSCustomerSearchResult[]>([]);
  const customerSearchBusy = ref(false);
  async function searchCustomers(query: string) {
    const q = (query || "").trim();
    if (q.length < 2) { customerSearchResults.value = []; return; }
    customerSearchBusy.value = true;
    try {
      const path = concreteActionHref(
        actions.value,
        "customer_search",
        "/api/v1/backstage/pos/customer/search/?q={query}",
        { query: q },
      );
      const response = await $fetch<POSCustomerSearchResponse>(apiPath(path), {
        method: "GET",
        credentials: "include",
        headers: requestHeaders,
      });
      customerSearchResults.value = response.results || [];
    } catch {
      customerSearchResults.value = [];
    } finally {
      customerSearchBusy.value = false;
    }
  }
  async function selectCustomerResult(result: POSCustomerSearchResult) {
    cart.customerRef = result.ref;
    cart.customerName = result.name;
    cart.customerPhone = result.phone || cart.customerPhone;
    cart.customerEmail = result.email || cart.customerEmail;
    cart.customerTaxId = result.document || cart.customerTaxId;
    customerSearchResults.value = [];
    // Load memory + saved address for the chosen customer.
    if (cart.customerPhone.trim()) await lookupCustomer();
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
        // Freeze a receipt snapshot before the cart resets (spec §D3): the
        // printed receipt is a record of what was sold, not live state.
        const receipt: PosReceiptSnapshot = {
          orderRef,
          tabDisplay: cart.tabDisplay,
          customerName: cart.customerName,
          items: cart.items.map((item) => ({
            name: item.name,
            qty: item.qty,
            price_q: item.price_q,
            discountPct: item.discount?.value || 0,
          })),
          totalDisplay: review.value?.total_display || "",
          payments: cart.paymentTenders.map((tender) => ({ method: tender.method, amount_q: tender.amount_q })),
          fulfillmentLabel: pos.value?.fulfillment_options.find((option) => option.ref === cart.fulfillmentType)?.label || cart.fulfillmentType,
          printedAtMs: Date.now(),
        };
        result.value = {
          orderRef,
          nextUrl: `${djangoOrigin.value}/admin/operacao/pedidos/${encodeURIComponent(orderRef)}/`,
          payment: paymentProofView(response.payment),
          receipt,
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

  // Resolve the live server line_ids for a set of cart skus after persisting:
  // save_tab regenerates line_ids, so we persist + reload (same pattern as the
  // move dialog) and read the fresh ids the kitchen endpoints expect.
  async function freshLineIdsForSkus(skus: string[], firedState: "fired" | "unfired"): Promise<string[]> {
    await persistTab(true);
    await reloadCurrentTab();
    const wantFired = firedState === "fired";
    return cart.items
      .filter((item) => skus.includes(item.sku) && item.line_id && Boolean(item.fired) === wantFired)
      .map((item) => item.line_id as string);
  }

  async function fireTab(selectedSkus?: string[]) {
    if (!cart.tabSessionKey) return;
    serverError.value = "";
    firing.value = true;
    try {
      const body: Record<string, unknown> = { client_request_id: newClientRequestId() };
      if (selectedSkus && selectedSkus.length) {
        // Multi-select (spec §2.2): fire exactly the chosen lines. Resolve their
        // fresh line_ids (persist regenerates them) before targeting.
        const lineIds = await freshLineIdsForSkus(selectedSkus, "unfired");
        if (!lineIds.length) return;
        body.line_ids = lineIds;
      } else {
        // Delta fire: persist on-screen items so the server fires exactly what the
        // operator sees, then fire all unfired lines (no line_ids = the delta).
        await persistTab(true);
      }
      body.session_key = cart.tabSessionKey;
      const response = await action.call<{ tab: POSTabPayload | null }>(
        actionHref(actions.value, "fire_tab", "/api/v1/backstage/pos/tabs/fire/"),
        { body },
      );
      if (response.tab) setFromTabPayload(response.tab);
      await refresh();
    } catch (err: any) {
      serverError.value = err?.data?.detail || err?.data?.error?.message || err?.message || "Falha ao enviar à cozinha.";
    } finally {
      firing.value = false;
    }
  }

  async function unfireLineIds(ids: string[]) {
    if (!cart.tabSessionKey || !ids.length) return;
    const response = await action.call<{ tab: POSTabPayload | null }>(
      actionHref(actions.value, "unfire_tab", "/api/v1/backstage/pos/tabs/unfire/"),
      { body: { session_key: cart.tabSessionKey, line_ids: ids } },
    );
    if (response.tab) setFromTabPayload(response.tab);
    await refresh();
  }

  async function unfireTab(lineId: string) {
    if (!cart.tabSessionKey || !lineId) return;
    serverError.value = "";
    firing.value = true;
    try {
      await unfireLineIds([lineId]);
    } catch (err: any) {
      serverError.value = err?.data?.detail || err?.data?.error?.message || err?.message || "Falha ao cancelar envio à cozinha.";
    } finally {
      firing.value = false;
    }
  }

  // Multi-select unfire (spec §2.2): resolve the chosen lines' fresh, fired
  // line_ids, then cancel their kitchen handoff in one call.
  async function unfireSelected(selectedSkus: string[]) {
    if (!cart.tabSessionKey || !selectedSkus.length) return;
    serverError.value = "";
    firing.value = true;
    try {
      const ids = await freshLineIdsForSkus(selectedSkus, "fired");
      if (!ids.length) return;
      await unfireLineIds(ids);
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

  return {
    // draft + flags
    cart,
    tabInput,
    busy,
    saving,
    firing,
    renamingTab,
    cancellingSale,
    cancelSaleReason,
    saleCancelled,
    lookupBusy,
    serverError,
    result,
    checkoutMode,
    showTabs,
    cashDialogOpen,
    moveDialogOpen,
    review,
    customerLookup,
    tabDialogOpen,
    tabDialogReason,
    selectedTenderIndex,
    // derived
    checkoutContract,
    canFireTab,
    canRenameTab,
    tabManipulation,
    canCancelRecentSale,
    movementKinds,
    tabMaxLength,
    tabPlaceholder,
    tabDisallowedChars,
    tabDraftTargetStates,
    tabRequiredForCart,
    tabRequiredForSave,
    addressAutocomplete,
    totalDisplay,
    itemCount,
    hasOpenTab,
    inSaleView,
    hasDraftWithoutTab,
    canUseCart,
    paymentTotalQ,
    paymentRemainingQ,
    paymentChangeQ,
    paymentCovered,
    selectedTenderMethod,
    tabDialogTitle,
    tabDialogDescription,
    sortedTabs,
    otherOpenTabs,
    suggestedSplitRef,
    // commands / handlers
    goToTabs,
    addTender,
    removeTender,
    selectTender,
    tenderDigit,
    tenderComma,
    tenderBackspace,
    tenderClear,
    tenderAdd,
    tenderExact,
    productQty,
    addProduct,
    setQty,
    setLineDiscount,
    setLinePrice,
    sanitizeTabRef,
    requestTabAssociation,
    openTab,
    openTabFromDialog,
    applySavedAddress,
    lookupCustomer,
    resolveCustomer,
    customerSearchResults,
    customerSearchBusy,
    searchCustomers,
    selectCustomerResult,
    applyCustomerFavorite,
    repeatCustomerLastOrder,
    saveTab,
    prepareCheckout,
    reviewCheckout,
    submitSale,
    clearCurrentTab,
    openMoveDialog,
    submitMove,
    fireTab,
    unfireTab,
    unfireSelected,
    renameTab,
    cancelRecentSale,
    openCashShift,
    closeCashShift,
    registerCashMovement,
  };
}
