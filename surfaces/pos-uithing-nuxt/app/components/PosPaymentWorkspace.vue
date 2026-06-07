<script setup lang="ts">
// Payment screen (spec §2.4, Odoo-fidelity). A dedicated screen, not a drawer:
// LEFT  — payment methods (tap = inject a tender), the tender list, manager
//         approval (only when the review demands it), and the Validate button.
// CENTER — remaining / change / total + the value numpad (edits the selected
//         tender). RIGHT — sale-data as on-demand actions (fulfillment / customer
//         / discount sheets), collection, and the kitchen-handoff status.
//
// Zero arithmetic of policy: the total/remaining/change/coverage all come from
// the composable (which derives them from the authoritative review via the
// `presentation/payment` module). This screen renders; it does not compute.
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
import {
  cashDeltaPresets,
  collectionsForFulfillment,
  injectableMethods as toInjectableMethods,
  paymentIcon,
  tenderLineView,
} from "~/presentation/payment";

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
  paymentCollection: "terminal" | "on_delivery";
  paymentTenders: POSPaymentTenderDraft[];
  selectedTenderIndex: number;
  paymentRemainingQ: number;
  paymentChangeQ: number;
  paymentCovered: boolean;
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
  "update:paymentCollection": ["terminal" | "on_delivery"];
  addTender: [string];
  removeTender: [number];
  selectTender: [number];
  tenderDigit: [string];
  tenderBackspace: [];
  tenderClear: [];
  tenderAdd: [number];
  tenderExact: [];
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
const managerThresholdQ = computed(() => props.review?.manager_approval_threshold_q || 0);

// On-demand sale-data drawers (Odoo-style: customer/fulfillment/discount are
// actions that open a sheet, not a wall of fields next to the payment).
const fulfillmentSheetOpen = ref(false);
const customerSheetOpen = ref(false);
const discountSheetOpen = ref(false);

// Minimalist flow (calm by subtraction): the total is the hero; the cash
// entry (quick bills) appears only when a cash tender exists, and the full
// numpad stays hidden behind "Outro valor" — most counter sales finish in a
// tap (PIX/card cover exactly; cash via "Exato" or a bill).
const showNumpad = ref(false);
const hasCashTender = computed(() => props.paymentTenders.some((tender) => tender.method === "cash"));
const cashDeltas = computed(() => cashPresets.value.filter((preset) => preset > 0));
const cashHasExact = computed(() => cashPresets.value.includes(0));
watch(hasCashTender, (has) => { if (!has) showNumpad.value = false; });

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
const injectableMethods = computed(() => toInjectableMethods(props.paymentMethods));
const tenderLines = computed(() => props.paymentTenders.map((tender) => tenderLineView(tender, props.paymentMethods)));
const deliveryCollections = computed(() => collectionsForFulfillment(props.paymentCollections, props.fulfillmentType));
const cashPresets = computed(() => cashDeltaPresets(props.checkoutContract));

function onAddressSelected(address: StructuredAddressProjection) {
  emit("update:deliveryAddressStructured", address);
  if (address.route) emit("update:deliveryAddress", address.route);
  if (address.street_number) emit("update:deliveryStreetNumber", address.street_number);
  if (address.neighborhood) emit("update:deliveryNeighborhood", address.neighborhood);
}
</script>

<template>
  <section class="flex h-full min-h-0 flex-col gap-4">
    <!-- Payment screen (minimalist, "calm by subtraction" — Loyverse/Toast). The
         total is the hero; sale-data are quiet chips; methods are big; the cash
         entry (quick bills) + numpad appear only when needed. Most counter sales
         finish in one tap (PIX/card cover exactly). Title/back: shell context bar. -->

    <!-- sale-data: quiet chips (secondary, on-demand sheets) -->
    <div class="flex shrink-0 flex-wrap items-center justify-center gap-2">
      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-sm transition hover:bg-accent"
        @click="fulfillmentSheetOpen = true"
      >
        <Icon :name="fulfillmentType === 'delivery' ? 'lucide:bike' : 'lucide:store'" class="size-4 text-muted-foreground" />
        <span class="font-medium">{{ fulfillmentLabel }}</span>
      </button>
      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-sm transition hover:bg-accent"
        @click="customerSheetOpen = true"
      >
        <Icon name="lucide:user-round" class="size-4 text-muted-foreground" />
        <span :class="customerSet ? 'font-medium' : 'text-muted-foreground'">{{ customerName || "Cliente" }}</span>
      </button>
      <button
        v-if="discountTypes.length"
        type="button"
        class="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition hover:bg-accent"
        :class="hasDiscount ? 'border-primary/40 bg-primary/5 font-medium' : 'border-border text-muted-foreground'"
        @click="discountSheetOpen = true"
      >
        <Icon name="lucide:tag" class="size-4" />
        <span>{{ hasDiscount ? `Desconto ${discountSummary}` : "Desconto" }}</span>
      </button>
      <button
        v-for="collection in (deliveryCollections.length > 1 ? deliveryCollections : [])"
        :key="collection.ref"
        type="button"
        class="inline-flex items-center rounded-full border px-3 py-1.5 text-sm transition hover:bg-accent"
        :class="paymentCollection === collection.ref ? 'border-primary bg-primary/10 font-medium' : 'border-border text-muted-foreground'"
        @click="$emit('update:paymentCollection', collection.ref)"
      >
        {{ collection.label }}
      </button>
    </div>

    <!-- HERO: total + methods + (cash) entry, centered and calm -->
    <div class="grid min-h-0 flex-1 place-items-center overflow-auto">
      <div class="flex w-full max-w-md flex-col items-stretch gap-6 py-2">
        <!-- total hero -->
        <div class="text-center">
          <p class="text-sm font-medium uppercase tracking-wide text-muted-foreground">
            {{ paymentCovered ? "Pronto para finalizar" : "Resta a pagar" }}
          </p>
          <p class="mt-1 text-6xl font-bold tabular-nums tracking-tight">{{ formatBRL(Math.max(0, paymentRemainingQ)) }}</p>
          <p class="mt-2 text-sm tabular-nums text-muted-foreground">
            Total {{ review ? review.total_display : interimTotalDisplay }}
            <span v-if="paymentChangeQ > 0" class="font-semibold text-primary"> · Troco {{ formatBRL(paymentChangeQ) }}</span>
          </p>
        </div>

        <!-- method tiles (big) -->
        <div class="grid grid-cols-3 gap-3">
          <button
            v-for="method in injectableMethods"
            :key="method.ref"
            type="button"
            class="flex flex-col items-center justify-center gap-2 rounded-2xl border bg-card px-2 py-5 text-sm font-medium transition hover:border-primary/50 hover:bg-accent active:translate-y-px"
            @click="$emit('addTender', method.ref)"
          >
            <Icon :name="paymentIcon(method.ref)" class="size-8 text-muted-foreground" />
            {{ method.label }}
          </button>
        </div>

        <!-- tenders added (compact, only when present) -->
        <div v-if="tenderLines.length" class="flex flex-col gap-1.5">
          <button
            v-for="(tender, idx) in tenderLines"
            :key="idx"
            type="button"
            class="flex items-center justify-between gap-2 rounded-xl border px-3 py-2.5 text-left transition"
            :class="idx === selectedTenderIndex ? 'border-primary bg-primary/10 ring-1 ring-primary/30' : 'hover:bg-accent/60'"
            :aria-current="idx === selectedTenderIndex ? 'true' : undefined"
            @click="$emit('selectTender', idx)"
          >
            <span class="flex min-w-0 items-center gap-2 text-sm font-medium">
              <Icon :name="tender.icon" class="size-4 shrink-0" />
              <span class="truncate">{{ tender.label }}</span>
            </span>
            <span class="flex shrink-0 items-center gap-1">
              <strong class="tabular-nums">{{ tender.amountDisplay }}</strong>
              <UiButton variant="ghost" size="icon-xs" aria-label="Remover pagamento" @click.stop="$emit('removeTender', idx)">
                <Icon name="lucide:x" class="size-3.5 text-destructive" />
              </UiButton>
            </span>
          </button>
        </div>

        <!-- cash entry: quick bills + "outro valor" reveals the numpad -->
        <div v-if="hasCashTender" class="flex flex-col gap-2">
          <div class="grid grid-flow-col auto-cols-fr gap-2">
            <button
              v-if="cashHasExact"
              type="button"
              class="rounded-lg border bg-muted/60 py-3 text-sm font-semibold transition hover:bg-accent active:translate-y-px"
              @click="$emit('tenderExact')"
            >
              Exato
            </button>
            <button
              v-for="delta in cashDeltas"
              :key="delta"
              type="button"
              class="rounded-lg border bg-muted/60 py-3 text-sm font-semibold tabular-nums transition hover:bg-accent active:translate-y-px"
              :aria-label="`Recebido ${formatBRL(delta)}`"
              @click="$emit('tenderAdd', delta)"
            >
              +{{ delta / 100 }}
            </button>
            <button
              type="button"
              class="rounded-lg border py-3 text-sm font-semibold transition active:translate-y-px"
              :class="showNumpad ? 'border-primary bg-primary/10' : 'bg-muted/60 hover:bg-accent'"
              @click="showNumpad = !showNumpad"
            >
              Outro valor
            </button>
          </div>
          <PosPaymentNumpad
            v-if="showNumpad"
            :presets="[]"
            @digit="$emit('tenderDigit', $event)"
            @backspace="$emit('tenderBackspace')"
            @clear="$emit('tenderClear')"
            @add="$emit('tenderAdd', $event)"
            @exact="$emit('tenderExact')"
          />
        </div>
      </div>
    </div>

    <!-- FOOTER — kitchen note + manager approval (when required) + Finalizar CTA -->
    <div class="grid shrink-0 gap-2">
      <div v-if="items.length" class="flex items-center justify-center gap-2 text-xs">
        <Icon name="lucide:flame" class="size-3.5 shrink-0" :class="firedCount ? 'text-amber-600' : 'text-muted-foreground'" />
        <span :class="firedCount ? 'font-medium' : 'text-muted-foreground'">{{ kitchenNote }}</span>
      </div>
      <PosManagerApproval
        v-if="review?.requires_manager_approval"
        :manager-username="managerUsername"
        :manager-pin="managerPin"
        :threshold-q="managerThresholdQ"
        @update:manager-username="$emit('update:managerUsername', $event)"
        @update:manager-pin="$emit('update:managerPin', $event)"
      />
      <UiButton
        size="lg"
        class="h-14 w-full text-base"
        :disabled="!items.length || loading || needsReview || approvalBlocking || !paymentCovered"
        :loading="loading || needsReview"
        @click="$emit('submit')"
      >
        <template v-if="needsReview">Atualizando…</template>
        <template v-else-if="!paymentCovered">Falta {{ formatBRL(paymentRemainingQ) }}</template>
        <template v-else>Finalizar · {{ review?.total_display }}</template>
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
