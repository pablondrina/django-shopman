<script setup lang="ts">
import type {
  POSAddressAutocompleteProjection,
  POSCartItem,
  POSCheckoutContractProjection,
  POSCheckoutOptionProjection,
  POSCustomerLookupProjection,
  POSFulfillmentOptionProjection,
  POSPaymentCollectionProjection,
  POSPaymentMethodProjection,
  POSPaymentTenderDraft,
  POSSaleReviewProjection,
  SavedAddressProjection,
  StructuredAddressProjection,
} from "~/types/pos";
import { cartTotalQ, formatBRL } from "~/utils/posIntent";

const props = defineProps<{
  tabDisplay: string;
  items: POSCartItem[];
  hasOpenTab: boolean;
  fulfillmentOptions: POSFulfillmentOptionProjection[];
  paymentMethods: POSPaymentMethodProjection[];
  paymentCollections: POSPaymentCollectionProjection[];
  checkoutContract: POSCheckoutContractProjection | null;
  addressAutocomplete: POSAddressAutocompleteProjection | null;
  customerLookup: POSCustomerLookupProjection | null;
  review: POSSaleReviewProjection | null;
  discountTypes: POSCheckoutOptionProjection[];
  discountReasons: POSCheckoutOptionProjection[];
  discountType: "percent" | "fixed";
  discountValue: string;
  discountReason: string;
  managerUsername: string;
  managerPin: string;
  fulfillmentType: "pickup" | "delivery";
  paymentMethod: string;
  paymentCollection: "terminal" | "on_delivery";
  paymentTenders: POSPaymentTenderDraft[];
  paymentTotalQ: number;
  customerName: string;
  customerPhone: string;
  customerTaxId: string;
  customerEmail: string;
  deliveryAddress: string;
  deliveryAddressStructured: StructuredAddressProjection;
  deliveryStreetNumber: string;
  deliveryNeighborhood: string;
  deliveryComplement: string;
  deliveryInstructions: string;
  deliveryDate: string;
  deliveryTimeSlot: string;
  deliveryFeeInput: string;
  orderNotes: string;
  tenderedAmountInput: string;
  issueFiscalDocument: boolean;
  receiptMode: string;
  receiptEmail: string;
  loading: boolean;
  lookupBusy: boolean;
}>();

const emit = defineEmits<{
  "update:discountType": ["percent" | "fixed"];
  "update:discountValue": [string];
  "update:discountReason": [string];
  "update:managerUsername": [string];
  "update:managerPin": [string];
  "update:fulfillmentType": ["pickup" | "delivery"];
  "update:paymentMethod": [string];
  "update:paymentCollection": ["terminal" | "on_delivery"];
  addTender: [string];
  addCashTender: [number];
  removeTender: [number];
  "update:customerName": [string];
  "update:customerPhone": [string];
  "update:customerTaxId": [string];
  "update:customerEmail": [string];
  "update:deliveryAddress": [string];
  "update:deliveryAddressStructured": [StructuredAddressProjection];
  "update:deliveryStreetNumber": [string];
  "update:deliveryNeighborhood": [string];
  "update:deliveryComplement": [string];
  "update:deliveryInstructions": [string];
  "update:deliveryDate": [string];
  "update:deliveryTimeSlot": [string];
  "update:deliveryFeeInput": [string];
  "update:orderNotes": [string];
  "update:tenderedAmountInput": [string];
  "update:issueFiscalDocument": [boolean];
  "update:receiptMode": [string];
  "update:receiptEmail": [string];
  back: [];
  review: [];
  submit: [];
  lookupCustomer: [];
  applyCustomerFavorite: [];
  repeatCustomerLastOrder: [];
  pickSavedAddress: [SavedAddressProjection];
}>();

const interimTotalDisplay = computed(() => formatBRL(cartTotalQ(props.items)));
const receiptModes = computed(() => props.checkoutContract?.receipt_modes || [
  { ref: "none", label: "Sem comprovante", description: "" },
  { ref: "print", label: "Imprimir", description: "" },
  { ref: "email", label: "E-mail", description: "" },
]);
const customerMemory = computed(() => props.customerLookup?.memory || null);
const savedAddresses = computed(() => props.customerLookup?.saved_addresses || []);
const needsReview = computed(() => !props.review);
const approvalBlocking = computed(() =>
  !!props.review?.requires_manager_approval
  && (!props.managerUsername.trim() || !props.managerPin.trim()),
);

// On-demand sale-data drawers (Odoo-style: customer/fulfillment/discount are
// actions that open a sheet, not a wall of fields next to the payment).
const fulfillmentSheetOpen = ref(false);
const customerSheetOpen = ref(false);
const discountSheetOpen = ref(false);

const fulfillmentLabel = computed(
  () => props.fulfillmentOptions.find((option) => option.ref === props.fulfillmentType)?.label || props.fulfillmentType,
);
const discountValueNum = computed(
  () => Number(String(props.discountValue).replace(",", ".").replace(/[^0-9.]/g, "")) || 0,
);
const hasDiscount = computed(() => discountValueNum.value > 0);
const discountSummary = computed(() =>
  props.discountType === "fixed" ? `R$ ${props.discountValue}` : `${props.discountValue}%`,
);
const customerSet = computed(() => Boolean(props.customerName.trim() || props.customerPhone.trim()));

// Payment by injection: methods become "add a tender" buttons; the operator
// covers the total in any combination of forms. No "mixed" selection.
const injectableMethods = computed(() => props.paymentMethods.filter((method) => method.ref !== "mixed"));
function methodLabel(ref: string): string {
  return props.paymentMethods.find((method) => method.ref === ref)?.label || ref;
}
const deliveryCollections = computed(() =>
  props.paymentCollections.filter((collection) => collection.fulfillment_types.includes(props.fulfillmentType)),
);
const tenderSumQ = computed(() => props.paymentTenders.reduce((sum, tender) => sum + (tender.amount_q || 0), 0));
const remainingQ = computed(() => props.paymentTotalQ - tenderSumQ.value);
const changeQ = computed(() => Math.max(0, tenderSumQ.value - props.paymentTotalQ));
const paymentCovered = computed(() => props.paymentTenders.length > 0 && remainingQ.value <= 0);
const nextAmountDisplay = computed(() =>
  props.tenderedAmountInput ? `R$ ${props.tenderedAmountInput}` : formatBRL(Math.max(0, remainingQ.value)),
);

const PAYMENT_ICONS: Record<string, string> = {
  cash: "lucide:banknote",
  pix: "lucide:qr-code",
  card: "lucide:credit-card",
  mixed: "lucide:layers",
  external: "lucide:ellipsis",
};
function paymentIcon(ref: string): string {
  return PAYMENT_ICONS[ref] || "lucide:wallet";
}

const cashDigits = ref("");
function inputToCents(value: string): number {
  const normalized = String(value || "").replace(/\./g, "").replace(",", ".");
  return Math.round((Number.parseFloat(normalized) || 0) * 100);
}
watch(() => props.tenderedAmountInput, (value) => {
  const cents = inputToCents(value);
  if (cents !== Number.parseInt(cashDigits.value || "0", 10)) {
    cashDigits.value = cents ? String(cents) : "";
  }
}, { immediate: true });
function emitCash() {
  const cents = Number.parseInt(cashDigits.value || "0", 10);
  emit("update:tenderedAmountInput", cents ? (cents / 100).toFixed(2).replace(".", ",") : "");
}
function pushCashDigit(digit: string) {
  cashDigits.value = `${cashDigits.value}${digit}`.replace(/^0+/, "").slice(0, 7);
  emitCash();
}
function cashBackspace() {
  cashDigits.value = cashDigits.value.slice(0, -1);
  emitCash();
}
function cashClear() {
  cashDigits.value = "";
  emitCash();
}

// Cash quick-bills (restored): notes set the amount to register absolutely;
// "Exato" sets the remaining due. The operator then taps a payment method.
const cashPresets = [2000, 5000, 10000];

function onAddressSelected(address: StructuredAddressProjection) {
  emit("update:deliveryAddressStructured", address);
  if (address.route) emit("update:deliveryAddress", address.route);
  if (address.street_number) emit("update:deliveryStreetNumber", address.street_number);
  if (address.neighborhood) emit("update:deliveryNeighborhood", address.neighborhood);
}
</script>

<template>
  <section class="flex h-full min-h-0 flex-col gap-3">
    <!-- Top bar: back + sale-data actions (each opens a sheet) -->
    <div class="flex shrink-0 flex-wrap items-center gap-2">
      <UiButton variant="outline" size="sm" class="gap-2" @click="$emit('back')">
        <Icon name="lucide:arrow-left" class="size-4" />
        Voltar à comanda
      </UiButton>
      <div class="ml-auto flex flex-wrap items-center gap-2">
        <button
          type="button"
          class="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition hover:bg-accent"
          :class="fulfillmentType === 'delivery' ? 'border-primary/60 bg-primary/5' : ''"
          @click="fulfillmentSheetOpen = true"
        >
          <Icon :name="fulfillmentType === 'delivery' ? 'lucide:bike' : 'lucide:store'" class="size-4 text-muted-foreground" />
          {{ fulfillmentLabel }}
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition hover:bg-accent"
          :class="customerSet ? 'border-primary/60 bg-primary/5' : ''"
          @click="customerSheetOpen = true"
        >
          <Icon name="lucide:user-round" class="size-4 text-muted-foreground" />
          <span class="max-w-40 truncate">{{ customerName || "Cliente & fiscal" }}</span>
        </button>
        <button
          v-if="discountTypes.length"
          type="button"
          class="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition hover:bg-accent"
          :class="hasDiscount ? 'border-primary/60 bg-primary/5' : ''"
          @click="discountSheetOpen = true"
        >
          <Icon name="lucide:tag" class="size-4 text-muted-foreground" />
          {{ hasDiscount ? discountSummary : "Desconto" }}
        </button>
      </div>
    </div>

    <!-- Main: order + totals (left) · payment controls (right) -->
    <div class="grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
      <!-- LEFT — total to pay, payment lines, remaining/change (Odoo: no item re-list) -->
      <div class="flex min-h-0 flex-col gap-3 rounded-lg border bg-card p-4">
        <div class="shrink-0">
          <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Total a pagar{{ hasOpenTab && tabDisplay ? ` · #${tabDisplay}` : "" }}
          </p>
          <strong class="text-4xl tabular-nums text-primary">{{ review ? review.total_display : interimTotalDisplay }}</strong>
          <div v-if="review" class="mt-2 grid gap-1 border-t pt-2 text-sm text-muted-foreground">
            <div class="flex items-baseline justify-between"><span>Subtotal</span><span class="tabular-nums">{{ review.subtotal_display }}</span></div>
            <div v-if="review.discount_q" class="flex items-baseline justify-between"><span>Desconto</span><span class="tabular-nums">-{{ review.discount_display }}</span></div>
            <div v-if="review.delivery_fee_q" class="flex items-baseline justify-between"><span>Entrega</span><span class="tabular-nums">{{ review.delivery_fee_display }}</span></div>
          </div>
          <p v-else class="mt-1 text-xs text-muted-foreground">Revise a venda para confirmar o total final.</p>
          <p v-for="warning in review?.warnings || []" :key="warning.code" class="mt-1 text-xs text-amber-700">{{ warning.message }}</p>
        </div>

        <div class="min-h-0 flex-1 overflow-auto">
          <p class="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Pagamentos</p>
          <p v-if="!paymentTenders.length" class="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
            Nenhum pagamento ainda. Toque uma forma ou uma nota ao lado.
          </p>
          <ul v-else class="grid gap-1">
            <li v-for="(tender, idx) in paymentTenders" :key="idx" class="flex items-center justify-between rounded-lg border px-3 py-2">
              <span class="flex items-center gap-2 text-sm font-medium">
                <Icon :name="paymentIcon(tender.method)" class="size-4" />
                {{ methodLabel(tender.method) }}
              </span>
              <span class="flex items-center gap-2">
                <strong class="tabular-nums">{{ formatBRL(tender.amount_q) }}</strong>
                <UiButton variant="ghost" size="icon-xs" aria-label="Remover pagamento" @click="$emit('removeTender', idx)">
                  <Icon name="lucide:x" class="size-3.5 text-destructive" />
                </UiButton>
              </span>
            </li>
          </ul>
        </div>

        <div class="flex shrink-0 items-baseline justify-between rounded-lg px-3 py-3" :class="remainingQ > 0 ? 'bg-muted/50' : 'bg-primary/10'">
          <span class="text-base font-medium">
            <template v-if="remainingQ > 0">Resta a pagar</template>
            <template v-else-if="changeQ > 0">Troco</template>
            <template v-else>Pago</template>
          </span>
          <strong class="text-3xl tabular-nums" :class="remainingQ > 0 ? '' : 'text-primary'">
            <template v-if="remainingQ > 0">{{ formatBRL(remainingQ) }}</template>
            <template v-else-if="changeQ > 0">{{ formatBRL(changeQ) }}</template>
            <template v-else>✓</template>
          </strong>
        </div>
      </div>

      <!-- RIGHT — payment controls: methods, cash bills, numpad -->
      <div class="flex min-h-0 flex-col gap-3 rounded-lg border bg-card p-4">
        <div class="grid shrink-0 grid-cols-3 gap-2">
          <UiButton
            v-for="method in injectableMethods"
            :key="method.ref"
            variant="outline"
            class="h-auto flex-col gap-1.5 py-4"
            @click="$emit('addTender', method.ref)"
          >
            <Icon :name="paymentIcon(method.ref)" class="size-6" />
            <span class="text-xs font-medium">{{ method.label }}</span>
          </UiButton>
        </div>

        <div class="grid shrink-0 grid-cols-4 gap-2">
          <button
            v-for="preset in cashPresets"
            :key="preset"
            type="button"
            class="rounded-lg border bg-card py-2 text-sm font-semibold tabular-nums transition hover:bg-accent active:translate-y-px"
            @click="$emit('addCashTender', preset)"
          >
            R$ {{ preset / 100 }}
          </button>
          <button
            type="button"
            class="rounded-lg border bg-card py-2 text-sm font-semibold transition hover:bg-accent active:translate-y-px"
            @click="$emit('addCashTender', Math.max(0, remainingQ))"
          >
            Exato
          </button>
        </div>

        <div class="flex shrink-0 items-baseline justify-between rounded-lg border bg-muted/40 px-3 py-2">
          <span class="text-sm font-medium text-muted-foreground">Valor a registrar</span>
          <strong class="text-2xl tabular-nums">{{ nextAmountDisplay }}</strong>
        </div>

        <PosNumpad @digit="pushCashDigit" @backspace="cashBackspace" @clear="cashClear" />

        <p class="shrink-0 text-xs text-muted-foreground">
          Toque a forma (usa o restante) ou uma nota (dinheiro). Para um valor específico, digite e toque a forma.
        </p>

        <div v-if="deliveryCollections.length > 1" class="grid shrink-0 grid-cols-2 gap-2">
          <UiButton
            v-for="collection in deliveryCollections"
            :key="collection.ref"
            variant="outline"
            size="sm"
            class="h-auto justify-start whitespace-normal px-3 py-1.5 text-left"
            :class="paymentCollection === collection.ref ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground' : ''"
            @click="$emit('update:paymentCollection', collection.ref)"
          >
            <span class="text-xs font-medium">{{ collection.label }}</span>
          </UiButton>
        </div>
      </div>
    </div>

    <!-- Footer: manager approval (when required) + final action -->
    <div class="grid shrink-0 gap-2">
      <div
        v-if="review?.requires_manager_approval"
        class="grid gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 sm:grid-cols-[1fr_auto] sm:items-center"
      >
        <div>
          <p class="text-sm font-semibold text-amber-800">Aprovação gerencial necessária</p>
          <p class="text-xs text-amber-700">O desconto excede o limite. Gerente deve aprovar com usuário e PIN.</p>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <UiInput
            :model-value="managerUsername"
            placeholder="Gerente (usuário)"
            autocomplete="off"
            @update:model-value="$emit('update:managerUsername', String($event || ''))"
          />
          <UiInput
            :model-value="managerPin"
            type="password"
            inputmode="numeric"
            placeholder="PIN do gerente"
            autocomplete="off"
            @update:model-value="$emit('update:managerPin', String($event || ''))"
          />
        </div>
      </div>

      <UiButton
        v-if="needsReview"
        size="lg"
        class="w-full"
        :disabled="!items.length || loading"
        :loading="loading"
        @click="$emit('review')"
      >
        Revisar venda
      </UiButton>
      <UiButton
        v-else
        size="lg"
        class="w-full"
        :disabled="!items.length || loading || approvalBlocking || !paymentCovered"
        :loading="loading"
        @click="$emit('submit')"
      >
        <template v-if="!paymentCovered">Falta {{ formatBRL(remainingQ) }}</template>
        <template v-else>Finalizar venda · {{ review?.total_display }}</template>
      </UiButton>
    </div>
  </section>

  <!-- SHEET: Entrega / Retirada -->
  <UiSheet v-model:open="fulfillmentSheetOpen">
    <UiSheetContent side="right" title="Entrega" description="Como o cliente recebe o pedido.">
      <template #content>
        <div class="grid gap-4 overflow-y-auto px-4 pb-6">
          <div class="grid grid-cols-2 gap-2">
            <UiButton
              v-for="option in fulfillmentOptions"
              :key="option.ref"
              variant="outline"
              class="h-auto justify-start whitespace-normal px-3 py-2 text-left"
              :class="fulfillmentType === option.ref ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground' : ''"
              @click="$emit('update:fulfillmentType', option.ref)"
            >
              <span>
                <span class="block text-sm font-semibold">{{ option.label }}</span>
                <span class="block text-xs opacity-80">{{ option.description }}</span>
              </span>
            </UiButton>
          </div>

          <div v-if="fulfillmentType === 'delivery'" class="grid gap-3">
            <div v-if="savedAddresses.length" class="flex flex-wrap gap-2">
              <UiButton
                v-for="address in savedAddresses"
                :key="address.id"
                type="button"
                variant="outline"
                size="sm"
                class="h-auto justify-start whitespace-normal px-2 py-1 text-left"
                @click="$emit('pickSavedAddress', address)"
              >
                <span class="max-w-48 truncate">{{ address.label || address.formatted_address }}</span>
              </UiButton>
            </div>
            <label class="grid gap-1 text-sm">
              <span class="font-medium text-muted-foreground">Endereço</span>
              <PosAddressAutocomplete
                :model-value="deliveryAddress"
                :capability="addressAutocomplete"
                @update:model-value="$emit('update:deliveryAddress', String($event || ''))"
                @selected="onAddressSelected"
              />
            </label>
            <div class="grid gap-2 sm:grid-cols-2">
              <label class="grid gap-1 text-sm">
                <span class="font-medium text-muted-foreground">Número</span>
                <UiInput :model-value="deliveryStreetNumber" placeholder="123" @update:model-value="$emit('update:deliveryStreetNumber', String($event || ''))" />
              </label>
              <label class="grid gap-1 text-sm">
                <span class="font-medium text-muted-foreground">Bairro</span>
                <UiInput :model-value="deliveryNeighborhood" placeholder="Centro" @update:model-value="$emit('update:deliveryNeighborhood', String($event || ''))" />
              </label>
            </div>
            <div class="grid gap-2 sm:grid-cols-2">
              <label class="grid gap-1 text-sm">
                <span class="font-medium text-muted-foreground">Complemento</span>
                <UiInput :model-value="deliveryComplement" placeholder="Apto, bloco" @update:model-value="$emit('update:deliveryComplement', String($event || ''))" />
              </label>
              <label class="grid gap-1 text-sm">
                <span class="font-medium text-muted-foreground">Instruções</span>
                <UiInput :model-value="deliveryInstructions" placeholder="Portaria, referência" @update:model-value="$emit('update:deliveryInstructions', String($event || ''))" />
              </label>
            </div>
            <div class="grid gap-2 sm:grid-cols-2">
              <label class="grid gap-1 text-sm">
                <span class="font-medium text-muted-foreground">Data</span>
                <UiInput :model-value="deliveryDate" type="date" @update:model-value="$emit('update:deliveryDate', String($event || ''))" />
              </label>
              <label class="grid gap-1 text-sm">
                <span class="font-medium text-muted-foreground">Taxa</span>
                <UiInput :model-value="deliveryFeeInput" inputmode="decimal" placeholder="0,00" @update:model-value="$emit('update:deliveryFeeInput', String($event || ''))" />
              </label>
            </div>
            <label class="grid gap-1 text-sm">
              <span class="font-medium text-muted-foreground">Horário combinado</span>
              <UiInput :model-value="deliveryTimeSlot" placeholder="Ex: 14:00-14:30" @update:model-value="$emit('update:deliveryTimeSlot', String($event || ''))" />
            </label>
            <label class="grid gap-1 text-sm">
              <span class="font-medium text-muted-foreground">Observações</span>
              <UiTextarea :model-value="orderNotes" :rows="2" placeholder="Complemento, referência, instruções" @update:model-value="$emit('update:orderNotes', String($event || ''))" />
            </label>
          </div>

          <UiButton class="mt-2" @click="fulfillmentSheetOpen = false">Concluir</UiButton>
        </div>
      </template>
    </UiSheetContent>
  </UiSheet>

  <!-- SHEET: Cliente & fiscal -->
  <UiSheet v-model:open="customerSheetOpen">
    <UiSheetContent side="right" title="Cliente & fiscal" description="Identificação e comprovante. Tudo opcional.">
      <template #content>
        <div class="grid gap-4 overflow-y-auto px-4 pb-6">
          <div class="grid gap-2 sm:grid-cols-2">
            <label class="grid gap-1 text-sm">
              <span class="font-medium text-muted-foreground">Cliente</span>
              <UiInput :model-value="customerName" placeholder="Nome no balcão" @update:model-value="$emit('update:customerName', String($event || ''))" />
            </label>
            <label class="grid gap-1 text-sm">
              <span class="font-medium text-muted-foreground">WhatsApp</span>
              <div class="flex gap-2">
                <UiInput
                  :model-value="customerPhone"
                  inputmode="tel"
                  placeholder="(43) 99999-0000"
                  @update:model-value="$emit('update:customerPhone', String($event || ''))"
                  @keydown.enter.prevent="$emit('lookupCustomer')"
                />
                <UiButton
                  type="button"
                  variant="outline"
                  size="icon"
                  aria-label="Buscar cliente"
                  :disabled="lookupBusy || !customerPhone.trim()"
                  @click="$emit('lookupCustomer')"
                >
                  <Icon name="lucide:user-search" class="size-4" :class="lookupBusy ? 'animate-pulse' : ''" />
                </UiButton>
              </div>
            </label>
            <label class="grid gap-1 text-sm">
              <span class="font-medium text-muted-foreground">CPF/CNPJ</span>
              <UiInput :model-value="customerTaxId" inputmode="numeric" placeholder="Para fiscal" @update:model-value="$emit('update:customerTaxId', String($event || ''))" />
            </label>
            <label class="grid gap-1 text-sm">
              <span class="font-medium text-muted-foreground">E-mail</span>
              <UiInput :model-value="customerEmail" type="email" placeholder="cliente@email.com" @update:model-value="$emit('update:customerEmail', String($event || ''))" />
            </label>
          </div>

          <div
            v-if="customerLookup && (customerMemory?.favorite_item?.sku || customerMemory?.last_order_items?.length)"
            class="grid gap-2 rounded-lg border bg-muted/30 p-3"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="text-sm font-semibold">{{ customerLookup.name }}</span>
              <span v-if="customerMemory?.total_orders" class="text-xs text-muted-foreground">{{ customerMemory.total_orders }} pedidos</span>
            </div>
            <div class="flex flex-wrap gap-2">
              <UiButton v-if="customerMemory?.favorite_item?.sku" type="button" variant="outline" size="sm" @click="$emit('applyCustomerFavorite')">
                <Icon name="lucide:heart" class="size-4" /> Favorito
              </UiButton>
              <UiButton v-if="customerMemory?.last_order_items?.length" type="button" variant="outline" size="sm" @click="$emit('repeatCustomerLastOrder')">
                <Icon name="lucide:rotate-ccw" class="size-4" /> Último pedido
              </UiButton>
            </div>
          </div>

          <div class="grid gap-2">
            <p class="text-sm font-medium text-muted-foreground">Fiscal e comprovante</p>
            <UiButton
              type="button"
              variant="outline"
              class="justify-between"
              :class="issueFiscalDocument ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground' : ''"
              @click="$emit('update:issueFiscalDocument', !issueFiscalDocument)"
            >
              <span>Emitir fiscal</span>
              <Icon :name="issueFiscalDocument ? 'lucide:check' : 'lucide:minus'" class="size-4" />
            </UiButton>
            <div class="grid grid-cols-3 gap-2">
              <UiButton
                v-for="mode in receiptModes"
                :key="mode.ref"
                type="button"
                variant="outline"
                class="h-auto justify-center whitespace-normal px-2 py-2 text-xs"
                :class="receiptMode === mode.ref ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground' : ''"
                @click="$emit('update:receiptMode', mode.ref)"
              >
                {{ mode.label }}
              </UiButton>
            </div>
            <label v-if="receiptMode === 'email'" class="grid gap-1 text-sm">
              <span class="font-medium text-muted-foreground">E-mail do comprovante</span>
              <UiInput :model-value="receiptEmail" type="email" placeholder="cliente@email.com" @update:model-value="$emit('update:receiptEmail', String($event || ''))" />
            </label>
          </div>

          <UiButton class="mt-2" @click="customerSheetOpen = false">Concluir</UiButton>
        </div>
      </template>
    </UiSheetContent>
  </UiSheet>

  <!-- SHEET: Desconto -->
  <UiSheet v-model:open="discountSheetOpen">
    <UiSheetContent side="right" title="Desconto" description="Tipo, valor e motivo. O backend revisa e aplica.">
      <template #content>
        <div class="grid gap-4 overflow-y-auto px-4 pb-6">
          <div class="grid grid-cols-2 gap-2">
            <UiButton
              v-for="option in discountTypes"
              :key="option.ref"
              variant="outline"
              :class="discountType === option.ref ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground' : ''"
              @click="$emit('update:discountType', option.ref === 'fixed' ? 'fixed' : 'percent')"
            >
              {{ option.label }}
            </UiButton>
          </div>
          <label class="grid gap-1 text-sm">
            <span class="font-medium text-muted-foreground">{{ discountType === "fixed" ? "Valor (R$)" : "Percentual (%)" }}</span>
            <UiInput :model-value="discountValue" inputmode="decimal" placeholder="0" @update:model-value="$emit('update:discountValue', String($event || ''))" />
          </label>
          <div v-if="discountReasons.length" class="flex flex-wrap gap-2">
            <UiButton
              v-for="reason in discountReasons"
              :key="reason.ref"
              variant="outline"
              size="sm"
              :class="discountReason === reason.ref ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground' : ''"
              @click="$emit('update:discountReason', reason.ref)"
            >
              {{ reason.label }}
            </UiButton>
          </div>
          <UiButton class="mt-2" @click="discountSheetOpen = false">Concluir</UiButton>
        </div>
      </template>
    </UiSheetContent>
  </UiSheet>
</template>
