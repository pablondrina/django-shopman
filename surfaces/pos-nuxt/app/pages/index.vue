<script setup lang="ts">
import { resolveAffordance } from "~/presentation/actions";
import { requiresOpenShiftForSale } from "~/presentation/cash";
// Tela de VENDA — wires the read-side (usePosTerminal) and write-side (usePosSale)
// composables to the three core screens (PosTabBoard / PosProductGrid /
// PosPaymentWorkspace). O chrome comum (login, lock, offline) vive no shell
// (app.vue); a sessão de caixa (abrir/fechar/movimentos) vive na antesala
// (`/session`) — sem turno aberto, esta página manda o operador pra lá.
useHead({ title: "Shopman POS" });

const apiPath = usePosApiPath();
const action = usePosAction();
const runtimeConfig = useRuntimeConfig();
// The Django admin (login) lives on its own operator host (api.<zona>), a different
// subdomain from the POS — so the DANFE link must be ABSOLUTE to that host, not
// relative to the POS origin.
const djangoOrigin = computed(() => String(runtimeConfig.public.djangoPublicBaseUrl || ""));
// Gestor de Pedidos (orders-nuxt) — destino do link pós-venda "Abrir no gestor".
const ordersUrl = computed(() => String(runtimeConfig.public.ordersUrl || ""));
const requestHeaders = import.meta.server ? useRequestHeaders(["cookie"]) : undefined;

const { pos, tabs, actions, pending, refresh } = await usePosTerminal();

// ANTESALA (benchmark Odoo): sem turno aberto não há venda — o operador cai no
// lobby de sessão para abrir o caixa. O gate lê o contrato da Projection.
if (
  pos.value
  && requiresOpenShiftForSale(pos.value.checkout?.capabilities?.cash_management)
  && !pos.value.has_open_cash_session
) {
  await navigateTo("/session", { replace: true });
}

// Identidade do operador — mesmo estado compartilhado do shell (useFetch deduplicado).
const OPERATOR_PERM = "backstage.operate_pos";
const { operator: activeOperator, locked, lock } = useOperatorLock(OPERATOR_PERM);

// Write-side of the open sale: cart draft + every session command.
const {
  cart,
  tabInput,
  busy,
  saving,
  unsaved,
  firing,
  cancellingSale,
  cancelSaleReason,
  cancelSaleDialogOpen,
  cancelSaleError,
  saleCancelled,
  lookupBusy,
  managerApprovalError,
  result,
  pixStatus,
  checkoutMode,
  moveDialogOpen,
  review,
  customerLookup,
  tabDialogOpen,
  selectedTenderIndex,
  checkoutContract,
  canRenameTab,
  tabManipulation,
  canCancelRecentSale,
  saleCorrection,
  tabMaxLength,
  tabPlaceholder,
  tabDisallowedChars,
  tabDraftTargetStates,
  tabRequiredForCart,
  addressAutocomplete,
  hasOpenTab,
  inSaleView,
  hasDraftWithoutTab,
  canUseCart,
  paymentRemainingQ,
  paymentChangeQ,
  paymentCovered,
  selectedTenderMethod,
  tabDialogTitle,
  tabDialogDescription,
  sortedTabs,
  otherOpenTabs,
  suggestedSplitRef,
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
  clearCustomer,
  applyCustomerFavorite,
  repeatCustomerLastOrder,
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
  openCancelSaleDialog,
  cancelRecentSale,
} = usePosSale({ pos, tabs, actions, refresh, action, apiPath, requestHeaders, ordersUrl });

// Kitchen handoff affordances (spec §2.5): the fire/unfire CTAs come from the
// Projection's Actions (label + enabled), never invented in the screen.
const fireAction = computed(() => resolveAffordance(actions.value, "fire_tab"));
const unfireAction = computed(() => resolveAffordance(actions.value, "unfire_tab"));

// Top context bar title (unified layout language, Arc 5): one band names the
// current work-area screen across Board / Sale / Payment.
const screenTitle = computed(() => {
  if (checkoutMode.value) return cart.tabDisplay ? `Pagamento · #${cart.tabDisplay}` : "Pagamento";
  if (inSaleView.value) return cart.tabDisplay || "Venda";
  return "Comandas";
});

// D3 receipt print (kiosk window.print): the receipt is already in the DOM
// (#pos-print-area) when a sale finalizes; @media print shows only it.
function printReceipt() {
  if (import.meta.client) window.print();
}

// Keyboard and scanner (spec: F2 tab board, F3 product search, F4 checkout/review,
// Escape backs out of checkout, "/" focuses product search when not editing).
const tabBoardRef = ref<{ focus: () => void } | null>(null);
const productGridRef = ref<{ focusSearch: () => void } | null>(null);

async function gotoTabInput() {
  checkoutMode.value = false;
  await nextTick();
  tabBoardRef.value?.focus();
}

async function gotoProductSearch() {
  if (!canUseCart.value) return;
  checkoutMode.value = false;
  await nextTick();
  productGridRef.value?.focusSearch();
}

function onGlobalKeydown(event: KeyboardEvent) {
  if (locked.value || !pos.value) return;
  const target = event.target as HTMLElement | null;
  const isEditing = !!target
    && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);

  // On the payment screen, the physical keyboard drives the value numpad of the
  // SELECTED tender (like the order screen's numpad): digits type, comma/period
  // enters centavos, Backspace trims. Requires a form already chosen.
  if (checkoutMode.value && !isEditing && !event.metaKey && !event.ctrlKey && !event.altKey && selectedTenderIndex.value >= 0) {
    if (event.key >= "0" && event.key <= "9") {
      event.preventDefault();
      tenderDigit(event.key);
      return;
    }
    if (event.key === "," || event.key === "." || event.key === "Decimal") {
      event.preventDefault();
      tenderComma();
      return;
    }
    if (event.key === "Backspace") {
      event.preventDefault();
      tenderBackspace();
      return;
    }
  }

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
  <main class="flex flex-wrap content-start min-h-dvh bg-background text-foreground md:h-[100dvh] md:min-h-0 md:flex-nowrap md:overflow-hidden">
    <PosFunctionRail
      v-if="pos"
      :pos="pos"
      :has-open-cash-session="pos.has_open_cash_session"
      :operator-name="activeOperator?.name || ''"
      :pending="pending"
      :view="checkoutMode ? 'checkout' : (inSaleView ? 'sale' : 'board')"
      @board="goToTabs"
      @cash="navigateTo('/session')"
      @lock="lock()"
      @refresh="refresh()"
    />

    <div class="flex min-w-0 flex-1 flex-col md:min-h-0 md:overflow-hidden">
      <header v-if="pos" class="flex shrink-0 items-center gap-3 border-b border-border bg-card px-4 py-2">
        <!-- Controle do rail (kit): cicla colapsado/compacto/estendido; mora no cabeçalho
             para que o rail suma por inteiro quando colapsado. -->
        <RailToggle />
        <UiButton
          v-if="inSaleView"
          variant="ghost"
          size="icon-sm"
          class="-ml-1 shrink-0"
          :aria-label="checkoutMode ? 'Voltar à comanda' : 'Voltar para comandas'"
          :title="checkoutMode ? 'Voltar à comanda' : 'Comandas'"
          @click="checkoutMode ? (checkoutMode = false) : goToTabs()"
        >
          <Icon name="lucide:arrow-left" class="size-5" />
        </UiButton>
        <span
          v-if="inSaleView && !checkoutMode && unsaved"
          class="inline-flex shrink-0 items-center gap-1 rounded-md border border-warning/50 bg-warning/10 px-2 py-1 text-xs font-medium text-amber-700 dark:text-amber-400"
          role="status"
          title="A comanda não pôde ser salva — tentando de novo"
        >
          <Icon name="lucide:cloud-off" class="size-3.5" /> Não salvo
        </span>
        <PosTabHeader
          v-if="inSaleView && !checkoutMode"
          v-model:customer-name="cart.customerName"
          v-model:customer-phone="cart.customerPhone"
          v-model:customer-tax-id="cart.customerTaxId"
          v-model:customer-email="cart.customerEmail"
          class="min-w-0 flex-1"
          :tab-display="cart.tabDisplay"
          :has-open-tab="hasOpenTab"
          :can-rename="canRenameTab"
          :customer-lookup="customerLookup"
          :lookup-busy="lookupBusy"
          :search-results="customerSearchResults"
          :search-busy="customerSearchBusy"
          :loading="busy"
          @rename="renameTab"
          @clear="clearCurrentTab"
          @clear-customer="clearCustomer"
          @lookup-customer="lookupCustomer"
          @resolve-customer="resolveCustomer"
          @search="searchCustomers"
          @select-result="selectCustomerResult"
          @apply-customer-favorite="applyCustomerFavorite"
          @repeat-customer-last-order="repeatCustomerLastOrder"
        />
        <h1 v-else class="min-w-0 truncate text-lg font-semibold leading-tight tracking-tight">{{ screenTitle }}</h1>
      </header>

      <div class="flex min-h-0 w-full flex-1 flex-col gap-3 px-4 py-3 md:min-h-0 md:overflow-hidden">
      <div class="grid shrink-0 gap-3 empty:hidden">
      <UiAlert v-if="result" class="border-success/30 bg-success/10 text-success">
        <Icon name="lucide:circle-check" class="size-4" />
        <UiAlertTitle>Pedido criado: {{ result.orderRef }}</UiAlertTitle>
        <UiAlertDescription>
          <div class="flex flex-col gap-2">
            <PosPaymentResult v-if="result.payment?.hasProof" :proof="result.payment" :status="pixStatus" />
            <div class="flex flex-wrap items-center gap-2">
              <UiButton variant="outline" size="sm" class="gap-1.5 border-success/40 text-success hover:bg-success/10" @click="printReceipt">
                <Icon name="lucide:printer" class="size-4" />
                Imprimir recibo
              </UiButton>
              <a
                v-if="result.issueFiscalDocument"
                class="inline-flex h-8 items-center gap-1.5 rounded-md border border-success/40 px-3 text-sm font-medium text-success transition hover:bg-success/10"
                :href="`${djangoOrigin}/fiscal/danfe/${encodeURIComponent(result.orderRef)}/`"
                target="_blank" rel="noopener"
              >
                <Icon name="lucide:receipt-text" class="size-4" />
                DANFE
              </a>
              <a class="font-semibold underline underline-offset-4" :href="result.nextUrl">Abrir no gestor</a>
              <!-- Cancelar é EXCEÇÃO, não fluxo: entrada discreta que abre a
                   confirmação destrutiva com desafio de PIN gerencial. -->
              <UiButton
                v-if="canCancelRecentSale"
                variant="ghost"
                size="sm"
                class="ml-auto text-muted-foreground hover:text-destructive"
                @click="openCancelSaleDialog"
              >
                Cancelar venda
              </UiButton>
            </div>
          </div>
        </UiAlertDescription>
      </UiAlert>

      <UiAlert v-if="saleCancelled" class="border-warning/30 bg-warning/10 text-amber-800">
        <Icon name="lucide:circle-check" class="size-4" />
        <UiAlertTitle>Venda cancelada</UiAlertTitle>
        <UiAlertDescription>O pedido foi cancelado dentro da janela do operador.</UiAlertDescription>
      </UiAlert>
      </div>

      <div class="flex-1 md:min-h-0 md:overflow-hidden">
      <div v-if="checkoutMode" class="h-full md:overflow-y-auto">
      <PosPaymentWorkspace
        v-model:discount-type="cart.discountType"
        v-model:discount-value="cart.discountValue"
        v-model:discount-reason="cart.discountReason"
        v-model:manager-username="cart.managerUsername"
        v-model:manager-pin="cart.managerPin"
        :manager-approval-error="managerApprovalError"
        v-model:fulfillment-type="cart.fulfillmentType"
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
        v-model:issue-fiscal-document="cart.issueFiscalDocument"
        v-model:receipt-mode="cart.receiptMode"
        v-model:receipt-email="cart.receiptEmail"
        :tab-display="cart.tabDisplay"
        :items="cart.items"
        :has-open-tab="hasOpenTab"
        :fulfillment-options="pos?.fulfillment_options || []"
        :payment-methods="pos?.payment_methods || []"
        :payment-collections="pos?.payment_collections || []"
        :checkout-contract="checkoutContract"
        :address-autocomplete="addressAutocomplete"
        :customer-lookup="customerLookup"
        :search-results="customerSearchResults"
        :search-busy="customerSearchBusy"
        :review="review"
        :discount-types="checkoutContract?.discount_types || []"
        :discount-reasons="checkoutContract?.discount_reasons || []"
        :payment-tenders="cart.paymentTenders"
        :selected-tender-index="selectedTenderIndex"
        :selected-tender-method="selectedTenderMethod"
        :payment-remaining-q="paymentRemainingQ"
        :payment-change-q="paymentChangeQ"
        :payment-covered="paymentCovered"
        :loading="busy"
        :lookup-busy="lookupBusy"
        @back="checkoutMode = false"
        @submit="submitSale"
        @add-tender="addTender"
        @remove-tender="removeTender"
        @select-tender="selectTender"
        @tender-digit="tenderDigit"
        @tender-comma="tenderComma"
        @tender-backspace="tenderBackspace"
        @tender-clear="tenderClear"
        @tender-add="tenderAdd"
        @tender-exact="tenderExact"
        @lookup-customer="lookupCustomer"
        @resolve-customer="resolveCustomer"
        @search="searchCustomers"
        @select-result="selectCustomerResult"
        @clear-customer="clearCustomer"
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

        <!-- SALE VIEW · product grid (the ticket/comanda is a full-height sibling
             of the work column, so it reaches the top edge like the rail) -->
        <PosProductGrid
          v-else
          ref="productGridRef"
          :products="pos?.products || []"
          :collections="pos?.collections || []"
          :favorite-refs="pos?.favorite_collection_refs || []"
          :cart-items="cart.items"
          :pending="pending"
          @add="addProduct"
        />
      </div>
      </div>
      </div>
    </div>

    <!-- TICKET / COMANDA — full-height right flank (cart-direita, reaches the top
         edge alongside the rail; on mobile it wraps below the product grid). -->
    <aside
      v-if="pos && inSaleView && !checkoutMode"
      class="flex w-full shrink-0 flex-col border-t border-border bg-card md:order-none md:h-full md:w-[360px] md:border-l md:border-t-0"
    >
        <div class="min-h-0 flex-1 md:overflow-hidden">
          <PosCartPanel
            :items="cart.items"
            :requires-tab="tabRequiredForCart"
            :has-open-tab="hasOpenTab"
            :loading="busy"
            :saving="saving"
            :fire-action="fireAction"
            :unfire-action="unfireAction"
            :firing="firing"
            :discount-reasons="checkoutContract?.discount_reasons || []"
            @increment="(sku) => setQty(sku, productQty(sku) + 1)"
            @decrement="(sku) => setQty(sku, productQty(sku) - 1)"
            @remove="(sku) => setQty(sku, 0)"
            @set-qty="(sku, qty) => setQty(sku, qty)"
            @set-discount="setLineDiscount"
            @set-price="setLinePrice"
            @prepare="prepareCheckout"
            @move="openMoveDialog"
            @fire="fireTab"
            @unfire="unfireTab"
            @fire-lines="fireTab"
            @unfire-lines="unfireSelected"
            @request-tab="requestTabAssociation('start')"
          />
        </div>
    </aside>

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

    <PosCancelSaleDialog
      v-model:open="cancelSaleDialogOpen"
      v-model:reason="cancelSaleReason"
      :order-ref="result?.orderRef || ''"
      :max-age-minutes="saleCorrection?.max_age_minutes || 0"
      :busy="cancellingSale"
      :error="cancelSaleError"
      @confirm="cancelRecentSale"
    />

    <PosMoveLinesDialog
      v-model:open="moveDialogOpen"
      :tab-display="cart.tabDisplay"
      :items="cart.items"
      :suggested-split-ref="suggestedSplitRef"
      :other-tabs="otherOpenTabs"
      :capability="tabManipulation"
      :busy="busy"
      @submit="submitMove"
    />

    <!-- D3 print surface: hidden on screen, the only thing visible in @media print. -->
    <div v-if="result" id="pos-print-area">
      <PosReceipt
        :receipt="result.receipt"
        :terminal-label="pos?.terminal_label || 'Ponto de venda'"
        :payment-methods="pos?.payment_methods || []"
      />
    </div>
  </main>
</template>
