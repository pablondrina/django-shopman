<script setup lang="ts">
import type {
  POSCartItem,
  POSFulfillmentOptionProjection,
  POSPaymentCollectionProjection,
  POSPaymentMethodProjection,
} from "~/types/pos";
import { cartTotalQ, formatBRL } from "~/utils/posIntent";

const props = defineProps<{
  tabDisplay: string;
  items: POSCartItem[];
  fulfillmentOptions: POSFulfillmentOptionProjection[];
  paymentMethods: POSPaymentMethodProjection[];
  paymentCollections: POSPaymentCollectionProjection[];
  fulfillmentType: "pickup" | "delivery";
  paymentMethod: string;
  paymentCollection: "terminal" | "on_delivery";
  customerName: string;
  customerPhone: string;
  deliveryAddress: string;
  deliveryTimeSlot: string;
  loading: boolean;
  saving: boolean;
}>();

const emit = defineEmits<{
  "update:fulfillmentType": ["pickup" | "delivery"];
  "update:paymentMethod": [string];
  "update:paymentCollection": ["terminal" | "on_delivery"];
  "update:customerName": [string];
  "update:customerPhone": [string];
  "update:deliveryAddress": [string];
  "update:deliveryTimeSlot": [string];
  increment: [string];
  decrement: [string];
  remove: [string];
  save: [];
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
</script>

<template>
  <UiCard class="gap-4 rounded-lg p-4 shadow-none lg:sticky lg:top-4">
    <div class="flex items-center justify-between gap-3">
      <div>
        <p class="text-xs font-medium uppercase text-muted-foreground">Comanda</p>
        <p class="text-2xl font-semibold tabular-nums">#{{ tabDisplay || "..." }}</p>
      </div>
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
        <UiTextarea
          :model-value="deliveryAddress"
          rows="2"
          placeholder="Rua, número, bairro e referência"
          @update:model-value="$emit('update:deliveryAddress', String($event || ''))"
        />
      </label>
      <label class="grid gap-1 text-sm">
        <span class="font-medium text-muted-foreground">Horário combinado</span>
        <UiInput
          :model-value="deliveryTimeSlot"
          placeholder="Ex: 14:00-14:30"
          @update:model-value="$emit('update:deliveryTimeSlot', String($event || ''))"
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
        <UiButton variant="outline" :disabled="!items.length || saving" :loading="saving" @click="$emit('save')">
          Salvar
        </UiButton>
        <UiButton :disabled="!items.length || loading" :loading="loading" @click="$emit('submit')">
          Finalizar
        </UiButton>
      </div>
    </div>
  </UiCard>
</template>
