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

// Write-side of the open sale: cart draft + every session command. The shell
// owns the Nuxt-bound primitives and hands them to the composable (a plain .ts
// must not call Nuxt composables after the await above).
const {
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
  tenderFresh,
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
  tenderBackspace,
  tenderClear,
  tenderAdd,
  productQty,
  addProduct,
  setQty,
  setLineDiscount,
  sanitizeTabRef,
  requestTabAssociation,
  openTab,
  openTabFromDialog,
  applySavedAddress,
  lookupCustomer,
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
            <PosPaymentResult v-if="result.payment?.hasProof" :proof="result.payment" />
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
        @tender-backspace="tenderBackspace"
        @tender-clear="tenderClear"
        @tender-add="tenderAdd"
        @tender-exact="addTender('cash')"
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
              :fire-action="fireAction"
              :unfire-action="unfireAction"
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

          <PosProductGrid
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

    <UiSonner />
  </main>
</template>
