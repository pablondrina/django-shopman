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
  selectedTenderIndex: number;
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
  selectTender: [number];
  tenderDigit: [string];
  tenderBackspace: [];
  tenderClear: [];
  tenderAdd: [number];
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

// Kitchen clarity: tell the operator, unequivocally, what finalizing will do
// vs what was already fired — so it's never a mystery whether food was sent.
const firedCount = computed(() => props.items.filter((item) => item.fired).length);
const kitchenNote = computed(() => {
  const total = props.items.length;
  if (!total) return "";
  const fired = firedCount.value;
  if (fired === 0) return `Ao finalizar, ${total === 1 ? "o item vai" : "os itens vão"} para a cozinha.`;
  if (fired < total) return `${fired} ${fired === 1 ? "item já está" : "itens já estão"} na cozinha; o restante vai ao finalizar.`;
  return total === 1 ? "O item já está na cozinha." : "Todos os itens já estão na cozinha.";
});

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

// Quick-add amounts for the payment numpad (Odoo's +10/+20/+50, in cents).
const quickAmounts = [1000, 5000, 10000] as const;

function onAddressSelected(address: StructuredAddressProjection) {
  emit("update:deliveryAddressStructured", address);
  if (address.route) emit("update:deliveryAddress", address.route);
  if (address.street_number) emit("update:deliveryStreetNumber", address.street_number);
  if (address.neighborhood) emit("update:deliveryNeighborhood", address.neighborhood);
}
</script>

<template>
  <section class="flex h-full min-h-0 flex-col gap-3">
    <!-- Top bar: back + title -->
    <div class="flex shrink-0 items-center gap-3">
      <UiButton variant="outline" size="sm" class="gap-2" @click="$emit('back')">
        <Icon name="lucide:arrow-left" class="size-4" />
        Voltar à comanda
      </UiButton>
      <p class="text-base font-semibold">Pagamento</p>
      <span v-if="hasOpenTab && tabDisplay" class="text-sm tabular-nums text-muted-foreground">#{{ tabDisplay }}</span>
    </div>

    <!-- Main (Odoo payment screen): methods + summary + validate (left) ·
         remaining/change + numpad (center) · sale-data actions (right) -->
    <div class="grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.3fr)_minmax(0,0.8fr)]">

      <!-- LEFT — payment methods, summary, manager approval, validate -->
      <div class="flex min-h-0 flex-col gap-2 rounded-lg border bg-card p-3">
        <p class="shrink-0 text-xs font-medium uppercase tracking-wide text-muted-foreground">Forma de pagamento</p>
        <div class="grid shrink-0 gap-1">
          <button
            v-for="method in injectableMethods"
            :key="method.ref"
            type="button"
            class="flex items-center gap-2.5 rounded-lg border px-3 py-2.5 text-left text-sm font-medium transition hover:border-primary/50 hover:bg-accent"
            @click="$emit('addTender', method.ref)"
          >
            <Icon :name="paymentIcon(method.ref)" class="size-5 text-muted-foreground" />
            {{ method.label }}
          </button>
        </div>

        <UiSeparator class="shrink-0" />
        <p class="shrink-0 text-xs font-medium uppercase tracking-wide text-muted-foreground">Pagamentos</p>
        <div class="min-h-0 flex-1 overflow-auto">
          <p v-if="!paymentTenders.length" class="rounded-lg border border-dashed p-3 text-center text-xs text-muted-foreground">
            Toque uma forma de pagamento.
          </p>
          <ul v-else class="grid gap-1">
            <li
              v-for="(tender, idx) in paymentTenders"
              :key="idx"
              class="flex cursor-pointer items-center justify-between gap-2 rounded-lg border px-3 py-2 transition"
              :class="idx === selectedTenderIndex ? 'border-primary bg-primary/10 ring-1 ring-primary/30' : 'hover:bg-accent/60'"
              :aria-current="idx === selectedTenderIndex ? 'true' : undefined"
              @click="$emit('selectTender', idx)"
            >
              <span class="flex min-w-0 items-center gap-2 text-sm font-medium">
                <Icon :name="paymentIcon(tender.method)" class="size-4 shrink-0" />
                <span class="truncate">{{ methodLabel(tender.method) }}</span>
              </span>
              <span class="flex shrink-0 items-center gap-1">
                <strong class="tabular-nums">{{ formatBRL(tender.amount_q) }}</strong>
                <UiButton variant="ghost" size="icon-xs" aria-label="Remover pagamento" @click.stop="$emit('removeTender', idx)">
                  <Icon name="lucide:x" class="size-3.5 text-destructive" />
                </UiButton>
              </span>
            </li>
          </ul>
        </div>

        <div
          v-if="review?.requires_manager_approval"
          class="grid shrink-0 gap-1.5 rounded-lg border border-amber-500/40 bg-amber-500/10 p-2"
        >
          <p class="text-xs font-semibold text-amber-800">Aprovação do gerente</p>
          <UiInput
            :model-value="managerUsername"
            placeholder="Gerente"
            autocomplete="off"
            class="h-8"
            @update:model-value="$emit('update:managerUsername', String($event || ''))"
          />
          <UiInput
            :model-value="managerPin"
            type="password"
            inputmode="numeric"
            placeholder="PIN"
            autocomplete="off"
            class="h-8"
            @update:model-value="$emit('update:managerPin', String($event || ''))"
          />
        </div>

        <UiButton
          size="lg"
          class="w-full shrink-0"
          :disabled="!items.length || loading || needsReview || approvalBlocking || !paymentCovered"
          :loading="loading || needsReview"
          @click="$emit('submit')"
        >
          <template v-if="needsReview">Atualizando…</template>
          <template v-else-if="!paymentCovered">Falta {{ formatBRL(remainingQ) }}</template>
          <template v-else>Validar · {{ review?.total_display }}</template>
        </UiButton>
      </div>

      <!-- CENTER — remaining/change/total + numpad (edits the selected tender) -->
      <div class="flex min-h-0 flex-col gap-3 rounded-lg border bg-card p-3">
        <div class="flex shrink-0 items-start justify-between gap-3 border-b pb-3">
          <div>
            <p class="text-sm text-muted-foreground">Resta a pagar</p>
            <strong class="text-3xl tabular-nums">{{ formatBRL(Math.max(0, remainingQ)) }}</strong>
            <p class="mt-0.5 text-xs tabular-nums text-muted-foreground">Total {{ review ? review.total_display : interimTotalDisplay }}</p>
          </div>
          <div class="text-right">
            <p class="text-sm text-muted-foreground">Troco</p>
            <strong class="text-3xl tabular-nums text-primary">{{ formatBRL(changeQ) }}</strong>
          </div>
        </div>

        <div class="grid min-h-0 flex-1 grid-cols-4 grid-rows-4 gap-2 text-xl">
          <button type="button" class="grid place-items-center rounded-lg border bg-card font-semibold tabular-nums transition hover:bg-accent active:translate-y-px" @click="$emit('tenderDigit', '1')">1</button>
          <button type="button" class="grid place-items-center rounded-lg border bg-card font-semibold tabular-nums transition hover:bg-accent active:translate-y-px" @click="$emit('tenderDigit', '2')">2</button>
          <button type="button" class="grid place-items-center rounded-lg border bg-card font-semibold tabular-nums transition hover:bg-accent active:translate-y-px" @click="$emit('tenderDigit', '3')">3</button>
          <button type="button" class="grid place-items-center rounded-lg border bg-muted/60 text-sm font-semibold tabular-nums transition hover:bg-accent active:translate-y-px" @click="$emit('tenderAdd', quickAmounts[0])">+{{ quickAmounts[0] / 100 }}</button>
          <button type="button" class="grid place-items-center rounded-lg border bg-card font-semibold tabular-nums transition hover:bg-accent active:translate-y-px" @click="$emit('tenderDigit', '4')">4</button>
          <button type="button" class="grid place-items-center rounded-lg border bg-card font-semibold tabular-nums transition hover:bg-accent active:translate-y-px" @click="$emit('tenderDigit', '5')">5</button>
          <button type="button" class="grid place-items-center rounded-lg border bg-card font-semibold tabular-nums transition hover:bg-accent active:translate-y-px" @click="$emit('tenderDigit', '6')">6</button>
          <button type="button" class="grid place-items-center rounded-lg border bg-muted/60 text-sm font-semibold tabular-nums transition hover:bg-accent active:translate-y-px" @click="$emit('tenderAdd', quickAmounts[1])">+{{ quickAmounts[1] / 100 }}</button>
          <button type="button" class="grid place-items-center rounded-lg border bg-card font-semibold tabular-nums transition hover:bg-accent active:translate-y-px" @click="$emit('tenderDigit', '7')">7</button>
          <button type="button" class="grid place-items-center rounded-lg border bg-card font-semibold tabular-nums transition hover:bg-accent active:translate-y-px" @click="$emit('tenderDigit', '8')">8</button>
          <button type="button" class="grid place-items-center rounded-lg border bg-card font-semibold tabular-nums transition hover:bg-accent active:translate-y-px" @click="$emit('tenderDigit', '9')">9</button>
          <button type="button" class="grid place-items-center rounded-lg border bg-muted/60 text-sm font-semibold tabular-nums transition hover:bg-accent active:translate-y-px" @click="$emit('tenderAdd', quickAmounts[2])">+{{ quickAmounts[2] / 100 }}</button>
          <button type="button" class="grid place-items-center rounded-lg border bg-card text-base font-medium transition hover:bg-accent active:translate-y-px" @click="$emit('tenderClear')">C</button>
          <button type="button" class="grid place-items-center rounded-lg border bg-card font-semibold tabular-nums transition hover:bg-accent active:translate-y-px" @click="$emit('tenderDigit', '0')">0</button>
          <button type="button" class="grid place-items-center rounded-lg border bg-card font-semibold tabular-nums transition hover:bg-accent active:translate-y-px" @click="$emit('tenderDigit', '0'); $emit('tenderDigit', '0')">00</button>
          <button type="button" class="grid place-items-center rounded-lg border bg-card transition hover:bg-accent active:translate-y-px" aria-label="Apagar" @click="$emit('tenderBackspace')"><Icon name="lucide:delete" class="size-5" /></button>
        </div>
      </div>

      <!-- RIGHT — sale-data actions (open sheets) + collection + kitchen status -->
      <div class="flex min-h-0 flex-col gap-2 rounded-lg border bg-muted/40 p-3">
        <p class="shrink-0 text-xs font-medium uppercase tracking-wide text-muted-foreground">Dados da venda</p>
        <button
          type="button"
          class="flex items-center gap-2 rounded-lg border bg-card px-3 py-2.5 text-left text-sm transition hover:bg-accent"
          @click="fulfillmentSheetOpen = true"
        >
          <Icon :name="fulfillmentType === 'delivery' ? 'lucide:bike' : 'lucide:store'" class="size-4 shrink-0 text-muted-foreground" />
          <span class="min-w-0 flex-1 truncate font-medium">{{ fulfillmentLabel }}</span>
          <Icon name="lucide:chevron-right" class="size-4 shrink-0 text-muted-foreground" />
        </button>
        <button
          type="button"
          class="flex items-center gap-2 rounded-lg border bg-card px-3 py-2.5 text-left text-sm transition hover:bg-accent"
          @click="customerSheetOpen = true"
        >
          <Icon name="lucide:user-round" class="size-4 shrink-0 text-muted-foreground" />
          <span class="min-w-0 flex-1 truncate" :class="customerSet ? 'font-medium' : 'text-muted-foreground'">{{ customerName || "Cliente & fiscal" }}</span>
          <Icon name="lucide:chevron-right" class="size-4 shrink-0 text-muted-foreground" />
        </button>
        <button
          v-if="discountTypes.length"
          type="button"
          class="flex items-center gap-2 rounded-lg border bg-card px-3 py-2.5 text-left text-sm transition hover:bg-accent"
          @click="discountSheetOpen = true"
        >
          <Icon name="lucide:tag" class="size-4 shrink-0 text-muted-foreground" />
          <span class="min-w-0 flex-1 truncate" :class="hasDiscount ? 'font-medium' : 'text-muted-foreground'">{{ hasDiscount ? `Desconto ${discountSummary}` : "Desconto" }}</span>
          <Icon name="lucide:chevron-right" class="size-4 shrink-0 text-muted-foreground" />
        </button>

        <div v-if="deliveryCollections.length > 1" class="grid gap-1">
          <button
            v-for="collection in deliveryCollections"
            :key="collection.ref"
            type="button"
            class="rounded-lg border px-3 py-2 text-left text-xs font-medium transition hover:bg-accent"
            :class="paymentCollection === collection.ref ? 'border-primary bg-primary/10' : 'bg-card'"
            @click="$emit('update:paymentCollection', collection.ref)"
          >
            {{ collection.label }}
          </button>
        </div>

        <div v-if="items.length" class="mt-auto flex items-start gap-2 rounded-lg bg-background/70 px-3 py-2 text-xs">
          <Icon name="lucide:flame" class="mt-0.5 size-4 shrink-0" :class="firedCount ? 'text-amber-600' : 'text-muted-foreground'" />
          <span :class="firedCount ? 'font-medium' : 'text-muted-foreground'">{{ kitchenNote }}</span>
        </div>
      </div>
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
