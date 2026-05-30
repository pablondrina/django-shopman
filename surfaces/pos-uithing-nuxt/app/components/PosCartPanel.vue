<script setup lang="ts">
import type {
  POSCartItem,
  POSCustomerLookupProjection,
} from "~/types/pos";
import { cartTotalQ, formatBRL } from "~/utils/posIntent";

const props = defineProps<{
  tabDisplay: string;
  items: POSCartItem[];
  customerLookup: POSCustomerLookupProjection | null;
  requiresTab: boolean;
  hasOpenTab: boolean;
  customerName: string;
  customerPhone: string;
  loading: boolean;
  saving: boolean;
  lookupBusy: boolean;
  canFire: boolean;
  firing: boolean;
}>();

const emit = defineEmits<{
  "update:customerName": [string];
  "update:customerPhone": [string];
  increment: [string];
  decrement: [string];
  remove: [string];
  save: [];
  prepare: [];
  move: [];
  fire: [];
  clear: [];
  requestTab: [];
  lookupCustomer: [];
  applyCustomerFavorite: [];
  repeatCustomerLastOrder: [];
}>();

const unfiredCount = computed(() => props.items.filter((item) => !item.fired).length);

const totalDisplay = computed(() => formatBRL(cartTotalQ(props.items)));
const customerMemory = computed(() => props.customerLookup?.memory || null);
</script>

<template>
  <UiCard v-if="requiresTab && !hasOpenTab" class="gap-4 rounded-lg p-4 shadow-none lg:sticky lg:top-4">
    <div class="grid gap-3 text-center">
      <div class="mx-auto grid size-11 place-items-center rounded-lg border bg-muted">
        <Icon name="lucide:receipt-text" class="size-5 text-muted-foreground" />
      </div>
      <div class="grid gap-1">
        <p class="text-base font-semibold">Abra uma comanda</p>
        <p class="text-sm text-muted-foreground">
          O carrinho do POS fica recuperável somente depois de associado a uma comanda.
        </p>
      </div>
      <UiButton type="button" :disabled="loading" @click="$emit('requestTab')">
        Escolher comanda
      </UiButton>
    </div>
  </UiCard>

  <UiCard v-else class="gap-4 rounded-lg p-4 shadow-none lg:sticky lg:top-4">
    <div class="flex items-center justify-between gap-3">
      <div>
        <p class="text-xs font-medium uppercase text-muted-foreground">Comanda</p>
        <p v-if="hasOpenTab" class="text-2xl font-semibold tabular-nums">#{{ tabDisplay || "..." }}</p>
        <p v-else class="text-xl font-semibold">Venda rápida</p>
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
    </div>

    <div
      v-if="customerLookup && (customerMemory?.favorite_item?.sku || customerMemory?.last_order_items?.length)"
      class="grid gap-2 rounded-lg border bg-muted/30 p-2"
    >
      <div class="flex items-center justify-between gap-2">
        <span class="text-sm font-semibold">{{ customerLookup.name }}</span>
        <span v-if="customerMemory?.total_orders" class="text-xs text-muted-foreground">
          {{ customerMemory.total_orders }} pedidos
        </span>
      </div>
      <div class="flex flex-wrap gap-2">
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
    </div>

    <UiSeparator />

    <div class="min-h-36">
      <p v-if="!items.length" class="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
        Carrinho vazio
      </p>
      <ul v-else class="grid max-h-[42vh] gap-2 overflow-auto pr-1">
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
            <span
              v-if="item.fired"
              class="mt-1 inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground"
            >
              <Icon name="lucide:flame" class="size-3" />
              Na cozinha
            </span>
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

    <UiSeparator />

    <div class="grid gap-3">
      <div class="flex items-baseline justify-between">
        <span class="text-sm font-medium text-muted-foreground">Total parcial</span>
        <strong class="text-2xl tabular-nums">{{ totalDisplay }}</strong>
      </div>
      <UiButton
        v-if="canFire && hasOpenTab && items.length"
        variant="outline"
        size="sm"
        class="justify-center gap-2"
        :disabled="loading || saving || firing || !unfiredCount"
        :loading="firing"
        @click="$emit('fire')"
      >
        <Icon name="lucide:flame" class="size-4" />
        {{ unfiredCount ? `Enviar para cozinha (${unfiredCount})` : "Tudo na cozinha" }}
      </UiButton>
      <UiButton
        v-if="hasOpenTab && items.length"
        variant="ghost"
        size="sm"
        class="justify-start gap-2 text-muted-foreground"
        :disabled="loading || saving"
        @click="$emit('move')"
      >
        <Icon name="lucide:split" class="size-4" />
        Mover itens (dividir / transferir / juntar)
      </UiButton>
      <div class="grid grid-cols-2 gap-2">
        <UiButton
          variant="outline"
          :disabled="!items.length || saving"
          :loading="saving"
          @click="$emit('save')"
        >
          Salvar
        </UiButton>
        <UiButton :disabled="!items.length || loading" :loading="loading" @click="$emit('prepare')">
          Checkout
        </UiButton>
      </div>
    </div>
  </UiCard>
</template>
