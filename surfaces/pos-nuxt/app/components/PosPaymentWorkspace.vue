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
  POSCustomerSearchResult,
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
  searchResults: POSCustomerSearchResult[];
  searchBusy: boolean;
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
  resolveCustomer: [];
  clearCustomer: [];
  search: [string];
  selectResult: [POSCustomerSearchResult];
  applyCustomerFavorite: [];
  repeatCustomerLastOrder: [];
  pickSavedAddress: [SavedAddressProjection];
}>();

const interimTotalDisplay = computed(() => formatBRL(cartTotalQ(props.items)));
// Nota fiscal é SECUNDÁRIA: mora no modal do Cliente (não é botãozão no grid) e só
// aparece quando a loja ofereceu NFC-e no PDV E o adapter fiscal está configurado.
const supportsFiscalDocument = computed(() => !!props.checkoutContract?.capabilities?.supports_fiscal_document);
const receiptModes = computed(() => props.checkoutContract?.receipt_modes || [
  { ref: "none", label: "Sem comprovante", description: "" },
  { ref: "print", label: "Imprimir", description: "" },
  { ref: "email", label: "E-mail", description: "" },
]);
const savedAddresses = computed(() => props.customerLookup?.saved_addresses || []);
const needsReview = computed(() => !props.review);
const approvalBlocking = computed(() =>
  !!props.review?.requires_manager_approval
  && (!props.managerUsername.trim() || !props.managerPin.trim()),
);
const managerThresholdQ = computed(() => props.review?.manager_approval_threshold_q || 0);
// Avisos não-bloqueantes da review (disponibilidade no balcão, pagamento): o
// operador VÊ a ressalva antes de finalizar; nunca bloqueiam a venda.
const reviewWarnings = computed(() => props.review?.warnings ?? []);

// On-demand sale-data drawers (Odoo-style: customer/fulfillment/discount are
// actions that open a sheet, not a wall of fields next to the payment).
const fulfillmentSheetOpen = ref(false);
const customerSheetOpen = ref(false);
function onSelectResult(result: POSCustomerSearchResult) {
  emit("selectResult", result);
}
// Reset the shared search when the customer modal reopens fresh.
watch(customerSheetOpen, (open) => { if (!open) emit("search", ""); });
const discountSheetOpen = ref(false);

// The instrument (right zone): the numpad edits the SELECTED tender, so it lights
// up once a tender exists; cédulas are the cash nuance, offered only when the
// selected tender is cash. BR notes (2/5/10/20/50/100) — the first tap after
// selecting a tender SETS (the customer handed R$50), then accumulates.
const digitKeys = ["1", "2", "3", "4", "5", "6", "7", "8", "9"];
// Full BR cédulas (2/5/10/20/50/100) — the bills the customer hands over; each tap
// ADDS to the selected cash tender (first tap after a fresh/auto value replaces,
// then accumulates). Shown only when paying in cash.
const cashNotesQ = [200, 500, 1000, 2000, 5000, 10000];
const cashSelected = computed(() => props.selectedTenderMethod === "cash");
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

// Validar (Odoo's Validate): NO "pay it all" shortcut — the button stays disabled
// until a payment form is consciously chosen and covers the total. This prevents
// the impulse to finalize a sale without paying attention to the method.
// Validar: enabled once a form covers the total. When the review demands manager
// approval and it isn't given yet, the click opens the authorization dialog
// (instead of disabling the button with a cramped inline field).
const needsAuth = computed(() => approvalBlocking.value);
const managerAuthOpen = ref(false);
const ctaLabel = computed(() => {
  if (needsReview.value) return "Atualizando…";
  return needsAuth.value ? "Autorizar e validar" : "Validar";
});
const ctaDisabled = computed(() => {
  if (!props.items.length || props.loading || needsReview.value) return true;
  if (!props.paymentCovered) return true; // só habilita quando uma forma cobre o total
  return false;
});
function onCta() {
  if (needsAuth.value) { managerAuthOpen.value = true; return; }
  emit("submit");
}
function onManagerAuthorize(username: string, pin: string) {
  emit("update:managerUsername", username);
  emit("update:managerPin", pin);
  managerAuthOpen.value = false;
  emit("submit");
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

    <!-- MAIN — clone Odoo: INSTRUMENTO esquerda, VALOR direita. Colunas
         RESPONSIVAS (B.1): teto 1+2 (instrumento:valor) → 1+1 → empilha (valor no
         topo). Grid com nº de colunas por breakpoint; instrumento ocupa sempre 1,
         valor ocupa o restante. (Sem 1+3 no xl — esparramava o valor.) -->
    <div class="grid min-h-0 w-full flex-1 grid-cols-1 gap-6 overflow-hidden md:grid-cols-2 lg:grid-cols-3">

      <!-- LEFT · INSTRUMENTO (empilhado: vai abaixo do valor) -->
      <div class="order-2 flex min-h-0 flex-col gap-2 md:order-none">
        <!-- payment methods (tap = lança o que falta na forma) -->
        <div class="flex flex-col gap-1.5">
          <button
            v-for="method in injectableMethods"
            :key="method.ref"
            type="button"
            class="flex h-11 items-center gap-3 rounded-md border bg-card px-3 text-left text-sm font-medium transition hover:border-primary/50 hover:bg-accent active:translate-y-px"
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
            class="flex h-11 items-center justify-center gap-2 rounded-md border bg-card px-3 text-sm font-medium transition hover:bg-accent active:translate-y-px"
            :class="customerSet ? 'border-primary bg-primary/5' : ''"
            @click="customerSheetOpen = true"
          >
            <Icon name="lucide:user-round" class="size-4 text-muted-foreground" />
            <span class="min-w-0 truncate">{{ customerName || "Cliente" }}</span>
          </button>
          <button
            type="button"
            class="flex h-11 items-center justify-center gap-2 rounded-md border bg-card px-3 text-sm font-medium transition hover:bg-accent active:translate-y-px"
            @click="fulfillmentSheetOpen = true"
          >
            <Icon :name="fulfillmentType === 'delivery' ? 'lucide:bike' : 'lucide:store'" class="size-4 text-muted-foreground" />
            <span class="min-w-0 truncate">{{ fulfillmentLabel }}</span>
          </button>
          <button
            v-if="discountTypes.length"
            type="button"
            class="flex h-11 items-center justify-center gap-2 rounded-md border bg-card px-3 text-sm font-medium transition hover:bg-accent active:translate-y-px"
            :class="hasDiscount ? 'border-primary bg-primary/5' : ''"
            @click="discountSheetOpen = true"
          >
            <Icon name="lucide:tag" class="size-4" :class="hasDiscount ? 'text-foreground' : 'text-muted-foreground'" />
            <span class="min-w-0 truncate">{{ hasDiscount ? `Desconto ${discountSummary}` : "Desconto" }}</span>
          </button>
          <!-- 'Nota fiscal' NÃO fica aqui como botão principal: é secundária, dentro do
               modal do Cliente (abre pelo botão 'Cliente'), e só quando habilitada. -->
          <button
            v-for="collection in (deliveryCollections.length > 1 ? deliveryCollections : [])"
            :key="collection.ref"
            type="button"
            class="flex h-11 items-center justify-center gap-2 rounded-md border bg-card px-3 text-sm font-medium transition hover:bg-accent active:translate-y-px"
            :class="paymentCollection === collection.ref ? 'border-primary bg-primary/5' : ''"
            @click="$emit('update:paymentCollection', collection.ref)"
          >
            <span class="min-w-0 truncate">{{ collection.label }}</span>
          </button>
        </div>

        <!-- numpad (dígitos: entrada decimal, vírgula nos centavos) + trilho de
             cédulas à direita (só dinheiro: as 6 notas BR que o cliente entrega) -->
        <div class="flex gap-1.5">
          <div class="grid grid-cols-3 gap-1.5" :class="cashSelected ? 'flex-[3] basis-0' : 'flex-1'" role="group" aria-label="Teclado de valor">
            <button
              v-for="digit in digitKeys"
              :key="digit"
              type="button"
              class="grid place-items-center rounded-md border bg-card h-14 text-xl font-semibold tabular-nums transition hover:bg-accent active:translate-y-px disabled:opacity-40"
              :disabled="!numpadActive"
              :aria-label="`Dígito ${digit}`"
              @click="$emit('tenderDigit', digit)"
            >
              {{ digit }}
            </button>
            <button type="button" class="grid place-items-center rounded-md border bg-card h-14 text-xl font-semibold transition hover:bg-accent active:translate-y-px disabled:opacity-40" :disabled="!numpadActive" aria-label="Vírgula (centavos)" @click="$emit('tenderComma')">,</button>
            <button type="button" class="grid place-items-center rounded-md border bg-card h-14 text-xl font-semibold tabular-nums transition hover:bg-accent active:translate-y-px disabled:opacity-40" :disabled="!numpadActive" aria-label="Dígito 0" @click="$emit('tenderDigit', '0')">0</button>
            <button type="button" class="grid place-items-center rounded-md border border-destructive/25 bg-destructive/5 h-14 text-destructive transition hover:bg-destructive/10 active:translate-y-px disabled:opacity-40" :disabled="!numpadActive" aria-label="Apagar" @click="$emit('tenderBackspace')">
              <Icon name="lucide:delete" class="size-5" />
            </button>
          </div>
          <!-- cédula rail — 4ª coluna (mesma largura das colunas do teclado);
               verde dinheiro + ícone de nota -->
          <div v-if="cashSelected" class="grid flex-1 basis-0 grid-rows-6 gap-1.5" role="group" aria-label="Cédulas recebidas">
            <button
              v-for="note in cashNotesQ"
              :key="note"
              type="button"
              class="flex items-center justify-center gap-1 rounded-md border border-green-500/30 bg-green-500/10 text-sm font-semibold tabular-nums text-green-800 transition hover:bg-green-500/20 active:translate-y-px disabled:opacity-40"
              :disabled="!numpadActive"
              :aria-label="`Recebi nota de ${formatBRL(note)}`"
              @click="$emit('tenderAdd', note)"
            >
              <Icon name="lucide:banknote" class="size-3.5 shrink-0 opacity-70" />
              {{ note / 100 }}
            </button>
          </div>
        </div>

        <!-- manager approval: when the review demands it, "Autorizar e validar"
             opens a dedicated PIN authorization screen (PosManagerAuthDialog) -->
        <p v-if="needsAuth" class="flex items-center gap-1.5 px-1 text-xs text-muted-foreground">
          <Icon name="lucide:shield-check" class="size-3.5 shrink-0 text-amber-600" />
          Requer autorização do gerente para finalizar.
        </p>

        <!-- Voltar + Validar (rodapé da coluna, copiando o Back + Validate do Odoo) -->
        <div class="mt-auto grid grid-cols-2 gap-1.5 pt-1">
          <UiButton variant="outline" size="lg" class="h-14 text-base" @click="$emit('back')">
            <Icon name="lucide:arrow-left" class="size-5" />
            Voltar
          </UiButton>
          <UiButton
            size="lg"
            class="h-14 text-base"
            :disabled="ctaDisabled"
            :loading="loading || needsReview"
            @click="onCta"
          >
            {{ ctaLabel }}
          </UiButton>
        </div>
      </div>

      <!-- RIGHT · VALOR (empilhado: no topo; cresce 1→2 conforme o breakpoint, teto 1+2) -->
      <div class="order-1 flex min-h-0 flex-col gap-3 py-1 md:order-none lg:col-span-2">
        <!-- valor gigante (estável = total a cobrar), centrado -->
        <div class="flex flex-1 flex-col items-center justify-center text-center">
          <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Total a cobrar</p>
          <p class="text-7xl font-bold tabular-nums tracking-tight xl:text-8xl">{{ review ? review.total_display : interimTotalDisplay }}</p>
          <p v-if="items.length" class="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
            <Icon name="lucide:flame" class="size-3.5 shrink-0" :class="firedCount ? 'text-primary' : ''" />
            {{ kitchenNote }}
          </p>
        </div>

        <!-- avisos não-bloqueantes da review (nunca impedem finalizar) -->
        <ul v-if="reviewWarnings.length" class="shrink-0 flex flex-col gap-1.5">
          <li
            v-for="(w, idx) in reviewWarnings"
            :key="idx"
            class="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-300"
            role="status"
          >
            <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0" />
            <span>{{ w.message }}</span>
          </li>
        </ul>

        <!-- linhas de pagamento + troco/restante -->
        <div v-if="tenderLines.length" class="shrink-0 border-t pt-3">
          <ul class="flex flex-col gap-1.5">
            <li v-for="(tender, idx) in tenderLines" :key="idx">
              <button
                type="button"
                class="flex h-11 w-full items-center justify-between gap-2 rounded-md border px-3 text-left transition"
                :class="idx === selectedTenderIndex ? 'border-primary bg-primary/5' : 'hover:bg-accent/60'"
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
              :class="fulfillmentType === option.ref ? 'border-primary bg-primary/5' : ''"
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

  <!-- Cliente & fiscal — shared full-screen picker (showFiscal rides the receipt) -->
  <PosCustomerModal
    v-model:open="customerSheetOpen"
    :show-fiscal="supportsFiscalDocument"
    :customer-name="customerName"
    :customer-phone="customerPhone"
    :customer-tax-id="customerTaxId"
    :customer-email="customerEmail"
    :customer-lookup="customerLookup"
    :search-results="searchResults"
    :search-busy="searchBusy"
    :lookup-busy="lookupBusy"
    :issue-fiscal-document="issueFiscalDocument"
    :receipt-mode="receiptMode"
    :receipt-modes="receiptModes"
    :receipt-email="receiptEmail"
    @update:customer-name="$emit('update:customerName', $event)"
    @update:customer-phone="$emit('update:customerPhone', $event)"
    @update:customer-tax-id="$emit('update:customerTaxId', $event)"
    @update:customer-email="$emit('update:customerEmail', $event)"
    @update:issue-fiscal-document="$emit('update:issueFiscalDocument', $event)"
    @update:receipt-mode="$emit('update:receiptMode', $event)"
    @update:receipt-email="$emit('update:receiptEmail', $event)"
    @search="$emit('search', $event)"
    @select-result="onSelectResult"
    @clear="$emit('clearCustomer')"
    @resolve-customer="$emit('resolveCustomer')"
    @apply-customer-favorite="$emit('applyCustomerFavorite')"
    @repeat-customer-last-order="$emit('repeatCustomerLastOrder')"
  />

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
              :class="discountType === option.ref ? 'border-primary bg-primary/5' : ''"
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
              :class="discountReason === reason.ref ? 'border-primary bg-primary/5' : ''"
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

  <!-- AUTORIZAÇÃO DO GERENTE -->
  <PosManagerAuthDialog
    v-model:open="managerAuthOpen"
    :threshold-q="managerThresholdQ"
    :busy="loading"
    @authorize="onManagerAuthorize"
  />
</template>
