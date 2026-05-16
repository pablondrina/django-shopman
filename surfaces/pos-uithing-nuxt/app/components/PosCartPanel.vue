<script setup lang="ts">
import type {
  POSCartItem,
  POSCheckoutContractProjection,
  POSFulfillmentOptionProjection,
  POSPaymentCollectionProjection,
  POSPaymentMethodProjection,
  POSSaleReviewProjection,
} from "~/types/pos";
import { cartTotalQ, formatBRL } from "~/utils/posIntent";

const props = defineProps<{
  tabDisplay: string;
  items: POSCartItem[];
  fulfillmentOptions: POSFulfillmentOptionProjection[];
  paymentMethods: POSPaymentMethodProjection[];
  paymentCollections: POSPaymentCollectionProjection[];
  checkoutContract: POSCheckoutContractProjection | null;
  checkoutMode: boolean;
  review: POSSaleReviewProjection | null;
  fulfillmentType: "pickup" | "delivery";
  paymentMethod: string;
  paymentCollection: "terminal" | "on_delivery";
  customerName: string;
  customerPhone: string;
  customerTaxId: string;
  customerEmail: string;
  deliveryAddress: string;
  deliveryStreetNumber: string;
  deliveryNeighborhood: string;
  deliveryDate: string;
  deliveryTimeSlot: string;
  deliveryFeeInput: string;
  orderNotes: string;
  tenderedAmountInput: string;
  issueFiscalDocument: boolean;
  receiptMode: string;
  receiptEmail: string;
  loading: boolean;
  saving: boolean;
}>();

const emit = defineEmits<{
  "update:fulfillmentType": ["pickup" | "delivery"];
  "update:paymentMethod": [string];
  "update:paymentCollection": ["terminal" | "on_delivery"];
  "update:customerName": [string];
  "update:customerPhone": [string];
  "update:customerTaxId": [string];
  "update:customerEmail": [string];
  "update:deliveryAddress": [string];
  "update:deliveryStreetNumber": [string];
  "update:deliveryNeighborhood": [string];
  "update:deliveryDate": [string];
  "update:deliveryTimeSlot": [string];
  "update:deliveryFeeInput": [string];
  "update:orderNotes": [string];
  "update:tenderedAmountInput": [string];
  "update:issueFiscalDocument": [boolean];
  "update:receiptMode": [string];
  "update:receiptEmail": [string];
  increment: [string];
  decrement: [string];
  remove: [string];
  save: [];
  prepare: [];
  back: [];
  submit: [];
  clear: [];
}>();

const totalDisplay = computed(() => formatBRL(cartTotalQ(props.items)));
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

function setTenderedByDelta(deltaQ: number) {
  const amountQ = Math.max(0, totalForCashQ.value + deltaQ);
  const formatted = (amountQ / 100).toFixed(2).replace(".", ",");
  emit("update:tenderedAmountInput", formatted);
}
</script>

<template>
  <UiCard class="gap-4 rounded-lg p-4 shadow-none lg:sticky lg:top-4">
    <div class="flex items-center justify-between gap-3">
      <div>
        <p class="text-xs font-medium uppercase text-muted-foreground">Comanda</p>
        <p class="text-2xl font-semibold tabular-nums">#{{ tabDisplay || "..." }}</p>
      </div>
      <UiBadge :variant="checkoutMode ? 'default' : 'outline'">
        {{ checkoutMode ? "Checkout" : "Venda" }}
      </UiBadge>
      <UiButton
        variant="ghost"
        size="icon-sm"
        aria-label="Liberar comanda"
        title="Liberar comanda"
        @click="$emit('clear')"
      >
        <Icon name="lucide:x" class="size-4" />
      </UiButton>
    </div>

    <UiSeparator />

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
        <UiInput
          :model-value="customerPhone"
          inputmode="tel"
          placeholder="(43) 99999-0000"
          @update:model-value="$emit('update:customerPhone', String($event || ''))"
        />
      </label>
      <label v-if="checkoutMode" class="grid gap-1 text-sm">
        <span class="font-medium text-muted-foreground">CPF/CNPJ</span>
        <UiInput
          :model-value="customerTaxId"
          inputmode="numeric"
          placeholder="Para fiscal"
          @update:model-value="$emit('update:customerTaxId', String($event || ''))"
        />
      </label>
      <label v-if="checkoutMode" class="grid gap-1 text-sm">
        <span class="font-medium text-muted-foreground">E-mail</span>
        <UiInput
          :model-value="customerEmail"
          type="email"
          placeholder="cliente@email.com"
          @update:model-value="$emit('update:customerEmail', String($event || ''))"
        />
      </label>
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
        <span class="font-medium text-muted-foreground">Rua</span>
        <UiTextarea
          :model-value="deliveryAddress"
          rows="2"
          placeholder="Rua ou avenida"
          @update:model-value="$emit('update:deliveryAddress', String($event || ''))"
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
      <div v-if="checkoutMode" class="grid gap-2 sm:grid-cols-2">
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
      <label v-if="checkoutMode" class="grid gap-1 text-sm">
        <span class="font-medium text-muted-foreground">Observações</span>
        <UiTextarea
          :model-value="orderNotes"
          rows="2"
          placeholder="Complemento, referência, instruções"
          @update:model-value="$emit('update:orderNotes', String($event || ''))"
        />
      </label>
    </div>

    <div class="grid gap-2">
      <p class="text-sm font-medium text-muted-foreground">Pagamento</p>
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
      <div v-if="checkoutMode && paymentMethod === 'cash' && paymentCollection === 'terminal'" class="grid gap-2">
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

    <div v-if="checkoutMode" class="grid gap-2">
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

    <UiSeparator />

    <div class="min-h-36">
      <p v-if="!items.length" class="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
        Carrinho vazio
      </p>
      <ul v-else class="grid max-h-[34vh] gap-2 overflow-auto pr-1">
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
          <div class="flex items-center gap-1">
            <UiButton variant="ghost" size="icon-xs" aria-label="Diminuir" @click="$emit('decrement', item.sku)">
              <Icon name="lucide:minus" class="size-3.5" />
            </UiButton>
            <span class="w-6 text-center text-sm font-semibold tabular-nums">{{ item.qty }}</span>
            <UiButton variant="ghost" size="icon-xs" aria-label="Aumentar" @click="$emit('increment', item.sku)">
              <Icon name="lucide:plus" class="size-3.5" />
            </UiButton>
            <UiButton variant="ghost" size="icon-xs" aria-label="Remover" @click="$emit('remove', item.sku)">
              <Icon name="lucide:trash-2" class="size-3.5 text-destructive" />
            </UiButton>
          </div>
        </li>
      </ul>
    </div>

    <div class="grid gap-3">
      <div class="flex items-baseline justify-between">
        <span class="text-sm font-medium text-muted-foreground">Total enviado ao contrato</span>
        <strong class="text-2xl tabular-nums">{{ totalDisplay }}</strong>
      </div>
      <div class="grid grid-cols-2 gap-2">
        <UiButton
          variant="outline"
          :disabled="!items.length || saving"
          :loading="saving"
          @click="checkoutMode ? $emit('back') : $emit('save')"
        >
          {{ checkoutMode ? "Voltar" : "Salvar" }}
        </UiButton>
        <UiButton :disabled="!items.length || loading" :loading="loading" @click="checkoutMode ? $emit('submit') : $emit('prepare')">
          {{ checkoutMode ? "Finalizar" : "Checkout" }}
        </UiButton>
      </div>
    </div>
  </UiCard>
</template>
