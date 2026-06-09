<script setup lang="ts">
// Payment screen (spec §2.4) — "Conta + Instrumento". Two stable zones, no modes
// that pop in and out:
//   LEFT  (a Conta)       — the charge: the sale total as a stable hero (never
//                           collapses to zero) + one adaptive live readout
//                           (Faltam → Troco → Pronto) + the tender lines, which
//                           accumulate and are editable. Split lives here.
//   RIGHT (o Instrumento) — always present: the method tiles (tap = lança o que
//                           falta na forma) + a persistent numpad that edits the
//                           SELECTED tender + cash cédulas as the cash nuance.
//
// The numpad is universal (every tender, not just cash) — which is exactly what
// split payment needs. Zero arithmetic of policy: total/remaining/change/coverage
// come from the composable (authoritative review via `presentation/payment`).
// This screen renders intent; it does not compute.
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
  selectedTenderMethod: string;
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
  /** Numpad edits the SELECTED tender; decimal entry (reais first, comma → centavos). */
  tenderDigit: [string];
  tenderComma: [];
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

// The instrument (right zone): the numpad edits the SELECTED tender, so it lights
// up once a tender exists; cédulas are the cash nuance, offered only when the
// selected tender is cash. BR notes (2/5/10/20/50/100) — the first tap after
// selecting a tender SETS (the customer handed R$50), then accumulates.
const digitKeys = ["1", "2", "3", "4", "5", "6", "7", "8", "9"];
// Quick-add column (Odoo's +10/+20/+50): each ADDS to the selected tender. Fixed
// 4×4 numpad like Odoo — last row is C · 0 · comma · backspace.
const quickAddsQ = [1000, 2000, 5000];
const numpadActive = computed(() => props.selectedTenderIndex >= 0 && props.selectedTenderIndex < props.paymentTenders.length);

// The adaptive live readout under the hero — one line that carries the state the
// operator needs right now, so the big number stays the (stable) sale total.
const payState = computed<"idle" | "short" | "change" | "ready">(() => {
  if (props.paymentChangeQ > 0) return "change";
  if (props.paymentCovered) return "ready";
  if (props.paymentTenders.length) return "short";
  return "idle";
});

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

// Contextual CTA (Odoo-style, refined): with nothing tendered the footer is a
// one-tap "receive it all in the default method"; once covered it becomes
// Finalizar; while short it shows what's missing (disabled).
const defaultMethod = computed(() => injectableMethods.value[0] || null);
const ctaLabel = computed(() => {
  if (needsReview.value) return "Atualizando…";
  if (payState.value === "idle") return defaultMethod.value ? `Receber tudo · ${defaultMethod.value.label}` : "Receber pagamento";
  if (payState.value === "short") return `Falta ${formatBRL(props.paymentRemainingQ)}`;
  return "Validar";
});
const ctaDisabled = computed(() => {
  if (!props.items.length || props.loading || needsReview.value) return true;
  if (payState.value === "short") return true;
  if ((payState.value === "ready" || payState.value === "change") && approvalBlocking.value) return true;
  return false;
});
function onCta() {
  if (payState.value === "idle") {
    if (defaultMethod.value) emit("addTender", defaultMethod.value.ref);
  } else {
    emit("submit");
  }
}

function onAddressSelected(address: StructuredAddressProjection) {
  emit("update:deliveryAddressStructured", address);
  if (address.route) emit("update:deliveryAddress", address.route);
  if (address.street_number) emit("update:deliveryStreetNumber", address.street_number);
  if (address.neighborhood) emit("update:deliveryNeighborhood", address.neighborhood);
}
</script>

<template>
  <section class="flex h-full min-h-0 flex-col gap-3">
    <!-- Payment screen — clone fiel do Odoo POS (desktop-first). INSTRUMENTO à
         ESQUERDA (lista de métodos + botões de função empilhados acima do numpad +
         numpad 4×4 com coluna de +N + Voltar/Validar no rodapé da coluna); VALOR
         gigante à DIREITA (total estável, centrado) + linhas de pagamento +
         troco/restante. Os botões de função (Cliente/Retirada/Desconto/Nota) ficam
         logo acima do numpad, como o Odoo empilha conforme as opções ativas. -->

    <!-- MAIN — clone Odoo: INSTRUMENTO esquerda, VALOR direita -->
    <div class="mx-auto flex min-h-0 w-full max-w-5xl flex-1 gap-5 overflow-hidden">

      <!-- LEFT · INSTRUMENTO -->
      <div class="flex w-full max-w-[22rem] shrink-0 flex-col gap-2">
        <!-- payment methods (tap = lança o que falta na forma) -->
        <div class="flex flex-col gap-1.5">
          <button
            v-for="method in injectableMethods"
            :key="method.ref"
            type="button"
            class="flex items-center gap-3 rounded-lg border bg-card px-3.5 py-3 text-left text-sm font-medium transition hover:border-primary/50 hover:bg-accent active:translate-y-px"
            :class="method.ref === selectedTenderMethod ? 'border-primary bg-primary/5' : ''"
            @click="$emit('addTender', method.ref)"
          >
            <Icon :name="paymentIcon(method.ref)" class="size-5 shrink-0 text-muted-foreground" />
            <span class="flex-1">{{ method.label }}</span>
          </button>
        </div>

        <!-- função: empilhados acima do numpad (Odoo reflui conforme as opções).
             Cliente + Retirada/Entrega + Desconto + Nota fiscal. -->
        <div class="grid grid-cols-2 gap-1.5">
          <button
            type="button"
            class="flex items-center justify-center gap-2 rounded-lg border bg-card px-3 py-2.5 text-sm font-medium transition hover:bg-accent active:translate-y-px"
            :class="customerSet ? 'border-primary/40' : ''"
            @click="customerSheetOpen = true"
          >
            <Icon name="lucide:user-round" class="size-4 text-muted-foreground" />
            <span class="min-w-0 truncate">{{ customerName || "Cliente" }}</span>
          </button>
          <button
            type="button"
            class="flex items-center justify-center gap-2 rounded-lg border bg-card px-3 py-2.5 text-sm font-medium transition hover:bg-accent active:translate-y-px"
            @click="fulfillmentSheetOpen = true"
          >
            <Icon :name="fulfillmentType === 'delivery' ? 'lucide:bike' : 'lucide:store'" class="size-4 text-muted-foreground" />
            <span class="min-w-0 truncate">{{ fulfillmentLabel }}</span>
          </button>
          <button
            v-if="discountTypes.length"
            type="button"
            class="flex items-center justify-center gap-2 rounded-lg border bg-card px-3 py-2.5 text-sm font-medium transition hover:bg-accent active:translate-y-px"
            :class="hasDiscount ? 'border-primary/40 bg-primary/5 text-primary' : ''"
            @click="discountSheetOpen = true"
          >
            <Icon name="lucide:tag" class="size-4" :class="hasDiscount ? '' : 'text-muted-foreground'" />
            <span class="min-w-0 truncate">{{ hasDiscount ? `Desconto ${discountSummary}` : "Desconto" }}</span>
          </button>
          <button
            type="button"
            class="flex items-center justify-center gap-2 rounded-lg border bg-card px-3 py-2.5 text-sm font-medium transition hover:bg-accent active:translate-y-px"
            :class="issueFiscalDocument ? 'border-primary bg-primary/5 text-primary' : ''"
            @click="$emit('update:issueFiscalDocument', !issueFiscalDocument)"
          >
            <Icon :name="issueFiscalDocument ? 'lucide:check-square' : 'lucide:file-text'" class="size-4" :class="issueFiscalDocument ? '' : 'text-muted-foreground'" />
            <span>Nota fiscal</span>
          </button>
          <button
            v-for="collection in (deliveryCollections.length > 1 ? deliveryCollections : [])"
            :key="collection.ref"
            type="button"
            class="flex items-center justify-center gap-2 rounded-lg border bg-card px-3 py-2.5 text-sm font-medium transition hover:bg-accent active:translate-y-px"
            :class="paymentCollection === collection.ref ? 'border-primary bg-primary/5 text-primary' : ''"
            @click="$emit('update:paymentCollection', collection.ref)"
          >
            <span class="min-w-0 truncate">{{ collection.label }}</span>
          </button>
        </div>

        <!-- numpad 4×4 (Odoo): dígitos em 3 colunas + coluna de +N à direita; a
             última linha é C · 0 · vírgula · apagar. Entrada decimal: inteiro
             primeiro, vírgula entra nos centavos (digitar 25 → R$ 25,00). -->
        <div class="grid grid-cols-4 gap-1.5" role="group" aria-label="Teclado de valor">
          <template v-for="(digit, i) in digitKeys" :key="digit">
            <button
              type="button"
              class="grid place-items-center rounded-lg border bg-card py-3.5 text-xl font-semibold tabular-nums transition hover:bg-accent active:translate-y-px disabled:opacity-40"
              :disabled="!numpadActive"
              :aria-label="`Dígito ${digit}`"
              @click="$emit('tenderDigit', digit)"
            >
              {{ digit }}
            </button>
            <!-- after every 3rd digit, the +N key for that row (Odoo +10/+20/+50) -->
            <button
              v-if="(i + 1) % 3 === 0"
              type="button"
              class="grid place-items-center rounded-lg border border-primary/30 bg-primary/5 py-3.5 text-base font-semibold tabular-nums text-primary transition hover:bg-primary/10 active:translate-y-px disabled:opacity-40"
              :disabled="!numpadActive"
              :aria-label="`Adicionar ${formatBRL(quickAddsQ[(i + 1) / 3 - 1] || 0)}`"
              @click="$emit('tenderAdd', quickAddsQ[(i + 1) / 3 - 1] || 0)"
            >
              +{{ (quickAddsQ[(i + 1) / 3 - 1] || 0) / 100 }}
            </button>
          </template>
          <!-- last row: C · 0 · vírgula · apagar -->
          <button type="button" class="grid place-items-center rounded-lg border bg-card py-3.5 text-base font-semibold transition hover:bg-accent active:translate-y-px disabled:opacity-40" :disabled="!numpadActive" aria-label="Limpar" @click="$emit('tenderClear')">C</button>
          <button type="button" class="grid place-items-center rounded-lg border bg-card py-3.5 text-xl font-semibold tabular-nums transition hover:bg-accent active:translate-y-px disabled:opacity-40" :disabled="!numpadActive" aria-label="Dígito 0" @click="$emit('tenderDigit', '0')">0</button>
          <button type="button" class="grid place-items-center rounded-lg border bg-card py-3.5 text-xl font-semibold transition hover:bg-accent active:translate-y-px disabled:opacity-40" :disabled="!numpadActive" aria-label="Vírgula (centavos)" @click="$emit('tenderComma')">,</button>
          <button type="button" class="grid place-items-center rounded-lg border bg-card py-3.5 transition hover:bg-accent active:translate-y-px disabled:opacity-40" :disabled="!numpadActive" aria-label="Apagar" @click="$emit('tenderBackspace')">
            <Icon name="lucide:delete" class="size-5" />
          </button>
        </div>

        <!-- manager approval (quando o review exige) -->
        <PosManagerApproval
          v-if="review?.requires_manager_approval"
          :manager-username="managerUsername"
          :manager-pin="managerPin"
          :threshold-q="managerThresholdQ"
          @update:manager-username="$emit('update:managerUsername', $event)"
          @update:manager-pin="$emit('update:managerPin', $event)"
        />

        <!-- Voltar + Validar (rodapé da coluna, copiando o Back + Validate do Odoo) -->
        <div class="mt-auto grid grid-cols-2 gap-1.5 pt-1">
          <UiButton variant="outline" size="lg" class="h-14 text-base" @click="$emit('back')">
            <Icon name="lucide:arrow-left" class="size-5" />
            Voltar
          </UiButton>
          <UiButton
            size="lg"
            class="h-14 text-base"
            :variant="payState === 'idle' ? 'secondary' : 'default'"
            :disabled="ctaDisabled"
            :loading="loading || needsReview"
            @click="onCta"
          >
            {{ ctaLabel }}
          </UiButton>
        </div>
      </div>

      <!-- RIGHT · VALOR -->
      <div class="flex min-h-0 flex-1 flex-col gap-3 py-1">
        <!-- valor gigante (estável = total a cobrar), centrado -->
        <div class="flex flex-1 flex-col items-center justify-center text-center">
          <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Total a cobrar</p>
          <p class="text-7xl font-bold tabular-nums tracking-tight xl:text-8xl">{{ review ? review.total_display : interimTotalDisplay }}</p>
          <p v-if="items.length" class="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
            <Icon name="lucide:flame" class="size-3.5 shrink-0" :class="firedCount ? 'text-primary' : ''" />
            {{ kitchenNote }}
          </p>
        </div>

        <!-- linhas de pagamento + troco/restante -->
        <div v-if="tenderLines.length" class="shrink-0 border-t pt-3">
          <ul class="flex flex-col gap-1.5">
            <li v-for="(tender, idx) in tenderLines" :key="idx">
              <button
                type="button"
                class="flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2.5 text-left transition"
                :class="idx === selectedTenderIndex ? 'border-primary bg-primary/10 ring-1 ring-primary/30' : 'hover:bg-accent/60'"
                :aria-current="idx === selectedTenderIndex ? 'true' : undefined"
                @click="$emit('selectTender', idx)"
              >
                <span class="flex min-w-0 items-center gap-2 text-sm font-medium">
                  <Icon :name="tender.icon" class="size-4 shrink-0" />
                  <span class="truncate">{{ tender.label }}</span>
                </span>
                <span class="flex shrink-0 items-center gap-2">
                  <strong class="text-lg tabular-nums">{{ tender.amountDisplay }}</strong>
                  <UiButton variant="ghost" size="icon-xs" aria-label="Remover pagamento" @click.stop="$emit('removeTender', idx)">
                    <Icon name="lucide:x" class="size-3.5 text-destructive" />
                  </UiButton>
                </span>
              </button>
            </li>
          </ul>
          <div class="mt-2 flex items-center justify-between gap-2 px-1">
            <span class="text-sm font-medium uppercase tracking-wide" :class="payState === 'change' ? 'text-primary' : 'text-muted-foreground'">
              {{ payState === "change" ? "Troco" : payState === "ready" ? "Pago" : "Restante" }}
            </span>
            <strong
              class="text-3xl font-bold tabular-nums"
              :class="payState === 'change' ? 'text-primary' : payState === 'ready' ? 'text-muted-foreground' : ''"
            >
              {{ payState === "change" ? formatBRL(paymentChangeQ) : payState === "ready" ? formatBRL(0) : formatBRL(paymentRemainingQ) }}
            </strong>
          </div>
        </div>
      </div>
    </div>

  </section>

  <!-- MODAL: Entrega / Retirada -->
  <UiDialog v-model:open="fulfillmentSheetOpen">
    <UiDialogContent class="max-h-[85vh] overflow-y-auto sm:max-w-lg">
      <UiDialogHeader>
        <UiDialogTitle>Entrega</UiDialogTitle>
        <UiDialogDescription>Como o cliente recebe o pedido.</UiDialogDescription>
      </UiDialogHeader>
      <div class="grid gap-4">
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

        </div>
      <UiDialogFooter>
        <UiButton class="w-full" @click="fulfillmentSheetOpen = false">Concluir</UiButton>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>

  <!-- MODAL: Cliente & fiscal -->
  <UiDialog v-model:open="customerSheetOpen">
    <UiDialogContent class="max-h-[85vh] overflow-y-auto sm:max-w-lg">
      <UiDialogHeader>
        <UiDialogTitle>Cliente &amp; fiscal</UiDialogTitle>
        <UiDialogDescription>Digite o WhatsApp — buscamos o cadastro. Identificação e comprovante.</UiDialogDescription>
      </UiDialogHeader>
      <div class="grid gap-4">
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

        </div>
        <UiDialogFooter>
          <UiButton class="w-full" @click="customerSheetOpen = false">Concluir</UiButton>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

  <!-- MODAL: Desconto -->
  <UiDialog v-model:open="discountSheetOpen">
    <UiDialogContent class="max-h-[85vh] overflow-y-auto sm:max-w-md">
      <UiDialogHeader>
        <UiDialogTitle>Desconto</UiDialogTitle>
        <UiDialogDescription>Tipo, valor e motivo. O backend revisa e aplica.</UiDialogDescription>
      </UiDialogHeader>
      <div class="grid gap-4">
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
        </div>
        <UiDialogFooter>
          <UiButton class="w-full" @click="discountSheetOpen = false">Concluir</UiButton>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>
</template>
