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
const filteredCollections = computed(() =>
  props.paymentCollections.filter((collection) =>
    collection.fulfillment_types.includes(props.fulfillmentType)
    && collection.payment_method_refs.includes(props.paymentMethod),
  ),
);
const receiptModes = computed(() => props.checkoutContract?.receipt_modes || [
  { ref: "none", label: "Sem comprovante", description: "" },
  { ref: "print", label: "Imprimir", description: "" },
  { ref: "email", label: "E-mail", description: "" },
]);
const cashPresetDeltas = computed(() => props.checkoutContract?.cash_tender_delta_presets_q || [0, 1000, 2000, 5000, 10000]);
const totalForCashQ = computed(() => props.review?.total_q || cartTotalQ(props.items));
const customerMemory = computed(() => props.customerLookup?.memory || null);
const savedAddresses = computed(() => props.customerLookup?.saved_addresses || []);
const needsReview = computed(() => !props.review);
const approvalBlocking = computed(() =>
  !!props.review?.requires_manager_approval
  && (!props.managerUsername.trim() || !props.managerPin.trim()),
);

function setTenderedByDelta(deltaQ: number) {
  const amountQ = Math.max(0, totalForCashQ.value + deltaQ);
  const formatted = (amountQ / 100).toFixed(2).replace(".", ",");
  emit("update:tenderedAmountInput", formatted);
}

function onAddressSelected(address: StructuredAddressProjection) {
  emit("update:deliveryAddressStructured", address);
  if (address.route) emit("update:deliveryAddress", address.route);
  if (address.street_number) emit("update:deliveryStreetNumber", address.street_number);
  if (address.neighborhood) emit("update:deliveryNeighborhood", address.neighborhood);
}
</script>

<template>
  <section class="grid items-start gap-4 lg:grid-cols-3">
    <!-- ZONE 1 — comanda / itens (resumo, somente leitura) -->

    <div class="grid content-start gap-4 rounded-lg border bg-card p-4">
      <div class="flex items-center justify-between gap-3">
        <div>
          <p class="text-xs font-medium uppercase text-muted-foreground">Comanda</p>
          <p v-if="hasOpenTab" class="text-2xl font-semibold tabular-nums">#{{ tabDisplay || "..." }}</p>
          <p v-else class="text-xl font-semibold">Venda rápida</p>
        </div>
        <UiButton variant="outline" size="sm" @click="$emit('back')">
          <Icon name="lucide:arrow-left" class="size-4" />
          Voltar à comanda
        </UiButton>
      </div>

      <UiSeparator />

      <div class="min-h-36">
        <p v-if="!items.length" class="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          Carrinho vazio
        </p>
        <ul v-else class="grid gap-2">
          <li
            v-for="item in items"
            :key="item.sku"
            class="grid grid-cols-[1fr_auto] gap-2 border-b pb-2 last:border-0"
          >
            <div class="min-w-0">
              <p class="line-clamp-2 text-sm font-semibold leading-snug">{{ item.name }}</p>
              <p class="mt-1 text-xs text-muted-foreground tabular-nums">
                {{ item.qty }}x {{ formatBRL(item.price_q) }}
              </p>
            </div>
            <span class="text-sm font-semibold tabular-nums">{{ formatBRL(item.price_q * item.qty) }}</span>
          </li>
        </ul>
      </div>

      <UiSeparator />

      <div class="flex items-baseline justify-between">
        <span class="text-sm font-medium text-muted-foreground">Total parcial</span>
        <strong class="text-2xl tabular-nums">{{ interimTotalDisplay }}</strong>
      </div>
      <p class="text-xs text-muted-foreground">
        Para alterar itens, volte à comanda. O total final é confirmado pelo backend na revisão.
      </p>
    </div>

    <!-- ZONE 2 — dados da venda (alteram o pedido) -->

    <div class="grid content-start gap-4 rounded-lg border bg-card p-4">
      <p class="text-sm font-semibold">Dados da venda</p>

      <div class="grid gap-2 sm:grid-cols-2">
        <label class="grid gap-1 text-sm">
          <span class="font-medium text-muted-foreground">Cliente</span>
          <UiInput
            :model-value="customerName"
            placeholder="Nome no balcão"
            @update:model-value="$emit('update:customerName', String($event || ''))"
          />
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
              size="icon-sm"
              aria-label="Buscar cliente"
              title="Buscar cliente"
              :disabled="lookupBusy || !customerPhone.trim()"
              @click="$emit('lookupCustomer')"
            >
              <Icon name="lucide:user-search" class="size-4" :class="lookupBusy ? 'animate-pulse' : ''" />
            </UiButton>
          </div>
        </label>
        <label class="grid gap-1 text-sm">
          <span class="font-medium text-muted-foreground">CPF/CNPJ</span>
          <UiInput
            :model-value="customerTaxId"
            inputmode="numeric"
            placeholder="Para fiscal"
            @update:model-value="$emit('update:customerTaxId', String($event || ''))"
          />
        </label>
        <label class="grid gap-1 text-sm">
          <span class="font-medium text-muted-foreground">E-mail</span>
          <UiInput
            :model-value="customerEmail"
            type="email"
            placeholder="cliente@email.com"
            @update:model-value="$emit('update:customerEmail', String($event || ''))"
          />
        </label>
      </div>

      <div
        v-if="customerLookup && (customerMemory?.favorite_item?.sku || customerMemory?.last_order_items?.length || savedAddresses.length)"
        class="grid gap-2 rounded-lg border bg-muted/30 p-2"
      >
        <div class="flex items-center justify-between gap-2">
          <span class="text-sm font-semibold">{{ customerLookup.name }}</span>
          <span v-if="customerMemory?.total_orders" class="text-xs text-muted-foreground">
            {{ customerMemory.total_orders }} pedidos
          </span>
        </div>
        <div v-if="customerMemory?.favorite_item?.sku || customerMemory?.last_order_items?.length" class="flex flex-wrap gap-2">
          <UiButton
            v-if="customerMemory?.favorite_item?.sku"
            type="button"
            variant="outline"
            size="sm"
            @click="$emit('applyCustomerFavorite')"
          >
            <Icon name="lucide:heart" class="size-4" />
            Favorito
          </UiButton>
          <UiButton
            v-if="customerMemory?.last_order_items?.length"
            type="button"
            variant="outline"
            size="sm"
            @click="$emit('repeatCustomerLastOrder')"
          >
            <Icon name="lucide:rotate-ccw" class="size-4" />
            Último pedido
          </UiButton>
        </div>
        <div v-if="fulfillmentType === 'delivery' && savedAddresses.length" class="flex gap-2 overflow-x-auto pb-1">
          <UiButton
            v-for="address in savedAddresses"
            :key="address.id"
            type="button"
            variant="outline"
            size="sm"
            class="h-auto shrink-0 justify-start whitespace-normal px-2 py-1 text-left"
            @click="$emit('pickSavedAddress', address)"
          >
            <span class="max-w-48 truncate">{{ address.label || address.formatted_address }}</span>
          </UiButton>
        </div>
      </div>

      <div class="grid gap-2">
        <p class="text-sm font-medium text-muted-foreground">Entrega</p>
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
      </div>

      <div v-if="fulfillmentType === 'delivery'" class="grid gap-2">
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
            <UiInput
              :model-value="deliveryStreetNumber"
              placeholder="123"
              @update:model-value="$emit('update:deliveryStreetNumber', String($event || ''))"
            />
          </label>
          <label class="grid gap-1 text-sm">
            <span class="font-medium text-muted-foreground">Bairro</span>
            <UiInput
              :model-value="deliveryNeighborhood"
              placeholder="Centro"
              @update:model-value="$emit('update:deliveryNeighborhood', String($event || ''))"
            />
          </label>
        </div>
        <div class="grid gap-2 sm:grid-cols-2">
          <label class="grid gap-1 text-sm">
            <span class="font-medium text-muted-foreground">Complemento</span>
            <UiInput
              :model-value="deliveryComplement"
              placeholder="Apto, bloco"
              @update:model-value="$emit('update:deliveryComplement', String($event || ''))"
            />
          </label>
          <label class="grid gap-1 text-sm">
            <span class="font-medium text-muted-foreground">Instruções</span>
            <UiInput
              :model-value="deliveryInstructions"
              placeholder="Portaria, referência"
              @update:model-value="$emit('update:deliveryInstructions', String($event || ''))"
            />
          </label>
        </div>
        <div class="grid gap-2 sm:grid-cols-2">
          <label class="grid gap-1 text-sm">
            <span class="font-medium text-muted-foreground">Data</span>
            <UiInput
              :model-value="deliveryDate"
              type="date"
              @update:model-value="$emit('update:deliveryDate', String($event || ''))"
            />
          </label>
          <label class="grid gap-1 text-sm">
            <span class="font-medium text-muted-foreground">Taxa</span>
            <UiInput
              :model-value="deliveryFeeInput"
              inputmode="decimal"
              placeholder="0,00"
              @update:model-value="$emit('update:deliveryFeeInput', String($event || ''))"
            />
          </label>
        </div>
        <label class="grid gap-1 text-sm">
          <span class="font-medium text-muted-foreground">Horário combinado</span>
          <UiInput
            :model-value="deliveryTimeSlot"
            placeholder="Ex: 14:00-14:30"
            @update:model-value="$emit('update:deliveryTimeSlot', String($event || ''))"
          />
        </label>
        <label class="grid gap-1 text-sm">
          <span class="font-medium text-muted-foreground">Observações</span>
          <UiTextarea
            :model-value="orderNotes"
            :rows="2"
            placeholder="Complemento, referência, instruções"
            @update:model-value="$emit('update:orderNotes', String($event || ''))"
          />
        </label>
      </div>

      <div v-if="discountTypes.length" class="grid gap-2">
        <p class="text-sm font-medium text-muted-foreground">Desconto</p>
        <div class="grid grid-cols-2 gap-2">
          <UiButton
            v-for="option in discountTypes"
            :key="option.ref"
            variant="outline"
            size="sm"
            :class="discountType === option.ref ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground' : ''"
            @click="$emit('update:discountType', option.ref === 'fixed' ? 'fixed' : 'percent')"
          >
            {{ option.label }}
          </UiButton>
        </div>
        <label class="grid gap-1 text-sm">
          <span class="font-medium text-muted-foreground">{{ discountType === "fixed" ? "Valor (R$)" : "Percentual (%)" }}</span>
          <UiInput
            :model-value="discountValue"
            inputmode="decimal"
            placeholder="0"
            @update:model-value="$emit('update:discountValue', String($event || ''))"
          />
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
          <UiInput
            :model-value="receiptEmail"
            type="email"
            placeholder="cliente@email.com"
            @update:model-value="$emit('update:receiptEmail', String($event || ''))"
          />
        </label>
      </div>
    </div>

    <!-- ZONE 3 — pagamento / conferência / ação final -->

    <div class="grid content-start gap-4 rounded-lg border bg-card p-4">
      <p class="text-sm font-semibold">Pagamento e conferência</p>

      <div class="grid gap-2">
        <p class="text-sm font-medium text-muted-foreground">Forma de pagamento</p>
        <div class="grid grid-cols-3 gap-2">
          <UiButton
            v-for="method in paymentMethods"
            :key="method.ref"
            variant="outline"
            class="justify-center"
            :class="paymentMethod === method.ref ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground' : ''"
            @click="$emit('update:paymentMethod', method.ref)"
          >
            {{ method.label }}
          </UiButton>
        </div>
        <div v-if="filteredCollections.length > 1" class="grid grid-cols-2 gap-2">
          <UiButton
            v-for="collection in filteredCollections"
            :key="collection.ref"
            variant="outline"
            class="h-auto justify-start whitespace-normal px-3 py-2 text-left"
            :class="paymentCollection === collection.ref ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground' : ''"
            @click="$emit('update:paymentCollection', collection.ref)"
          >
            <span>
              <span class="block text-sm font-semibold">{{ collection.label }}</span>
              <span class="block text-xs opacity-80">{{ collection.description }}</span>
            </span>
          </UiButton>
        </div>
        <div v-if="paymentMethod === 'cash' && paymentCollection === 'terminal'" class="grid gap-2">
          <label class="grid gap-1 text-sm">
            <span class="font-medium text-muted-foreground">Valor recebido</span>
            <UiInput
              :model-value="tenderedAmountInput"
              inputmode="decimal"
              placeholder="Dinheiro recebido"
              @update:model-value="$emit('update:tenderedAmountInput', String($event || ''))"
            />
          </label>
          <div class="flex gap-2 overflow-x-auto pb-1">
            <UiButton
              v-for="delta in cashPresetDeltas"
              :key="delta"
              type="button"
              variant="outline"
              size="sm"
              class="shrink-0"
              @click="setTenderedByDelta(delta)"
            >
              {{ delta === 0 ? "Exato" : `+${formatBRL(delta)}` }}
            </UiButton>
          </div>
        </div>
      </div>

      <UiSeparator />

      <div v-if="review" class="grid gap-2 rounded-lg border bg-muted/40 p-3">
        <div class="flex items-baseline justify-between">
          <span class="text-sm text-muted-foreground">Subtotal</span>
          <span class="tabular-nums">{{ review.subtotal_display }}</span>
        </div>
        <div v-if="review.delivery_fee_q" class="flex items-baseline justify-between">
          <span class="text-sm text-muted-foreground">Entrega</span>
          <span class="tabular-nums">{{ review.delivery_fee_display }}</span>
        </div>
        <div v-if="review.discount_q" class="flex items-baseline justify-between">
          <span class="text-sm text-muted-foreground">Desconto</span>
          <span class="tabular-nums">-{{ review.discount_display }}</span>
        </div>
        <div class="flex items-baseline justify-between border-t pt-2">
          <span class="text-sm font-semibold">Total revisado</span>
          <strong class="text-xl tabular-nums">{{ review.total_display }}</strong>
        </div>
        <div v-if="review.change_q" class="flex items-baseline justify-between">
          <span class="text-sm text-muted-foreground">Troco</span>
          <span class="font-semibold tabular-nums">{{ review.change_display }}</span>
        </div>
        <p v-for="warning in review.warnings" :key="warning.code" class="text-xs text-amber-700">
          {{ warning.message }}
        </p>
      </div>
      <div v-else class="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
        Revise a venda para conferir o total final, descontos e troco antes de finalizar.
      </div>

      <div v-if="review?.requires_manager_approval" class="grid gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3">
        <p class="text-sm font-semibold text-amber-800">Aprovação gerencial necessária</p>
        <p class="text-xs text-amber-700">
          O desconto excede o limite. Um gerente autorizado deve aprovar com usuário e PIN.
        </p>
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
        :disabled="!items.length || loading"
        :loading="loading"
        @click="$emit('review')"
      >
        Revisar venda
      </UiButton>
      <UiButton
        v-else
        size="lg"
        :disabled="!items.length || loading || approvalBlocking"
        :loading="loading"
        @click="$emit('submit')"
      >
        Finalizar venda · {{ review?.total_display }}
      </UiButton>
    </div>
  </section>
</template>
