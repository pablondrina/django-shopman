<script setup lang="ts">
import { resolveAffordance } from "~/presentation/actions";
// POS shell — wires the read-side (usePosTerminal) and write-side (usePosSale)
// composables to the operator lock and the three core screens. It holds only
// the Nuxt-bound primitives (apiPath/action/colorMode/runtimeConfig) and the
// terminal/lock setup, then hands them to usePosSale. No sale orchestration
// lives here anymore — the monolith's logic is drained into the composables and
// the screens (PosTabBoard / PosProductGrid / PosCartPanel) consume the
// Projection through the presentation layer.
const apiPath = usePosApiPath();
const action = usePosAction();
const colorMode = useColorMode();
function toggleColorMode() {
  colorMode.preference = colorMode.value === "dark" ? "light" : "dark";
}
const runtimeConfig = useRuntimeConfig();
// The Django admin (login) lives on its own operator host (api.<zona>), a different
// subdomain from the POS — so the login link must be ABSOLUTE to that host, not
// relative to the POS origin. After login the operator lands on the Admin home,
// whose sidebar links back to the apps (POS/Produção/…).
const djangoOrigin = computed(() => String(runtimeConfig.public.djangoPublicBaseUrl || ""));
const requestHeaders = import.meta.server ? useRequestHeaders(["cookie"]) : undefined;

// Login NO PRÓPRIO caixa (sem bounce pro Django admin): usuário+senha → sessão de
// dispositivo (cookie .<zona>) → recarrega já operando. Uma tela, um submit.
const loginUser = ref("");
const loginPass = ref("");
const loginPending = ref(false);
const loginError = ref("");
async function submitLogin() {
  if (loginPending.value) return;
  loginError.value = "";
  loginPending.value = true;
  try {
    await $fetch("/api/v1/backstage/operator/login/", {
      method: "POST",
      body: { username: loginUser.value.trim(), password: loginPass.value },
    });
    if (import.meta.client) window.location.reload();
  } catch (err: any) {
    loginError.value = err?.data?.detail || "Não foi possível entrar. Confira usuário e senha.";
    loginPending.value = false;
  }
}

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

// Write-side of the open sale: cart draft + every session command. The shell
// owns the Nuxt-bound primitives and hands them to the composable (a plain .ts
// must not call Nuxt composables after the await above).
const {
  cart,
  tabInput,
  busy,
  saving,
  unsaved,
  firing,
  renamingTab,
  cancellingSale,
  cancelSaleReason,
  saleCancelled,
  lookupBusy,
  serverError,
  result,
  paymentConfirmed,
  checkoutMode,
  showTabs,
  cashDialogOpen,
  moveDialogOpen,
  review,
  customerLookup,
  tabDialogOpen,
  tabDialogReason,
  selectedTenderIndex,
  checkoutContract,
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
  clearCustomer,
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
} = usePosSale({ pos, tabs, actions, refresh, action, apiPath, requestHeaders, djangoOrigin });

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
      v-if="pos && !error"
      :pos="pos"
      :shift="shift"
      :has-open-cash-session="pos.has_open_cash_session"
      :operator-name="activeOperator?.name || ''"
      :color-mode-value="colorMode.value"
      :pending="pending"
      :view="checkoutMode ? 'checkout' : (inSaleView ? 'sale' : 'board')"
      @board="goToTabs"
      @cash="cashDialogOpen = true"
      @lock="lock()"
      @refresh="refresh()"
      @toggle-theme="toggleColorMode"
    />

    <div class="flex min-w-0 flex-1 flex-col md:min-h-0 md:overflow-hidden">
      <PosLockScreen
        v-if="locked && !!pos"
        :operators="operators"
        :busy="lockBusy"
        :error="lockError"
        @unlock="onUnlock"
      />

      <header v-if="pos && !error" class="flex shrink-0 items-center gap-3 border-b border-border bg-card px-4 py-2">
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
          class="inline-flex shrink-0 items-center gap-1 rounded-md border border-amber-500/50 bg-amber-500/10 px-2 py-1 text-xs font-medium text-amber-700 dark:text-amber-400"
          role="status"
          title="A comanda não pôde ser salva — tentando de novo"
        >
          <Icon name="lucide:cloud-off" class="size-3.5" /> Não salvo
        </span>
        <PosComandaHeader
          v-if="inSaleView && !checkoutMode"
          class="min-w-0 flex-1"
          :tab-display="cart.tabDisplay"
          :has-open-tab="hasOpenTab"
          :can-rename="canRenameTab"
          v-model:customer-name="cart.customerName"
          v-model:customer-phone="cart.customerPhone"
          v-model:customer-tax-id="cart.customerTaxId"
          v-model:customer-email="cart.customerEmail"
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
      <UiAlert v-if="result" class="border-green-500/30 bg-green-500/10 text-green-800">
        <Icon name="lucide:circle-check" class="size-4" />
        <UiAlertTitle>Pedido criado: {{ result.orderRef }}</UiAlertTitle>
        <UiAlertDescription>
          <div class="flex flex-col gap-2">
            <PosPaymentResult v-if="result.payment?.hasProof" :proof="result.payment" :confirmed="paymentConfirmed" />
            <div class="flex flex-wrap items-center gap-2">
              <UiButton variant="outline" size="sm" class="gap-1.5 border-green-600/40 text-green-800 hover:bg-green-500/10" @click="printReceipt">
                <Icon name="lucide:printer" class="size-4" />
                Imprimir recibo
              </UiButton>
              <a
                v-if="result.issueFiscalDocument"
                class="inline-flex h-8 items-center gap-1.5 rounded-md border border-green-600/40 px-3 text-sm font-medium text-green-800 transition hover:bg-green-500/10"
                :href="`${djangoOrigin}/fiscal/danfe/${encodeURIComponent(result.orderRef)}/`"
                target="_blank" rel="noopener"
              >
                <Icon name="lucide:receipt-text" class="size-4" />
                DANFE
              </a>
              <a class="font-semibold underline underline-offset-4" :href="result.nextUrl">Abrir no gestor</a>
            </div>
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
        <form class="grid w-full max-w-sm gap-4 text-center" @submit.prevent="submitLogin">
          <div class="mx-auto grid size-14 place-items-center rounded-full border bg-muted">
            <Icon name="lucide:lock-keyhole" class="size-7 text-muted-foreground" />
          </div>
          <div class="grid gap-1.5">
            <h2 class="text-2xl font-semibold">Entre para operar o caixa</h2>
            <p class="text-sm text-muted-foreground">
              Acesse com sua conta autorizada a operar o caixa.
            </p>
          </div>
          <div class="grid gap-2.5 text-left">
            <input
              v-model="loginUser"
              type="text"
              autocomplete="username"
              autocapitalize="none"
              autocorrect="off"
              placeholder="Usuário"
              aria-label="Usuário"
              :disabled="loginPending"
              class="h-12 w-full rounded-md border bg-background px-3 text-base outline-none focus:ring-1 focus:ring-ring disabled:opacity-60"
            >
            <input
              v-model="loginPass"
              type="password"
              autocomplete="current-password"
              placeholder="Senha"
              aria-label="Senha"
              :disabled="loginPending"
              class="h-12 w-full rounded-md border bg-background px-3 text-base outline-none focus:ring-1 focus:ring-ring disabled:opacity-60"
            >
            <p v-if="loginError" class="text-sm text-destructive" role="alert">{{ loginError }}</p>
          </div>
          <UiButton type="submit" size="lg" :disabled="loginPending || !loginUser.trim() || !loginPass">
            <Icon :name="loginPending ? 'line-md:loading-loop' : 'lucide:log-in'" class="size-5" />
            {{ loginPending ? "Entrando…" : "Entrar" }}
          </UiButton>
        </form>
      </div>
      <div v-else-if="checkoutMode" class="h-full md:overflow-y-auto">
      <PosPaymentWorkspace
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
        v-model:discount-type="cart.discountType"
        v-model:discount-value="cart.discountValue"
        v-model:discount-reason="cart.discountReason"
        v-model:manager-username="cart.managerUsername"
        v-model:manager-pin="cart.managerPin"
        v-model:fulfillment-type="cart.fulfillmentType"
        v-model:payment-collection="cart.paymentCollection"
        :payment-tenders="cart.paymentTenders"
        :selected-tender-index="selectedTenderIndex"
        :selected-tender-method="selectedTenderMethod"
        :payment-remaining-q="paymentRemainingQ"
        :payment-change-q="paymentChangeQ"
        :payment-covered="paymentCovered"
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
      v-if="pos && !error && inSaleView && !checkoutMode"
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

    <UiSonner />
  </main>
</template>
