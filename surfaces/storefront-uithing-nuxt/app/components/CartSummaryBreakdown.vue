<script setup lang="ts">
import type { CartProjection } from '~/types/shopman'

defineProps<{
  cart: CartProjection
  compact?: boolean
  flat?: boolean
}>()

function discountDisplay (amount: string) {
  const value = amount.trim()
  if (!value) return ''
  return value.startsWith('-') ? value : `- ${value}`
}
</script>

<template>
  <UiDescriptionList :class="[flat ? '' : 'rounded-lg border bg-card px-3', compact ? 'text-sm' : '']">
    <UiDescriptionListTerm>Subtotal</UiDescriptionListTerm>
    <UiDescriptionListDetails class="sm:text-right">
      <span v-if="cart.has_discount" class="inline-flex flex-col items-start sm:items-end">
        <span class="shop-meta line-through">{{ cart.original_subtotal_display }}</span>
        <span class="tabular-nums">{{ cart.subtotal_display }}</span>
      </span>
      <span v-else class="tabular-nums">{{ cart.subtotal_display }}</span>
    </UiDescriptionListDetails>

    <template v-for="discount in cart.discount_lines" :key="discount.label">
      <UiDescriptionListTerm>{{ discount.label }}</UiDescriptionListTerm>
      <UiDescriptionListDetails class="tabular-nums text-primary sm:text-right">
        {{ discountDisplay(discount.amount_display) }}
      </UiDescriptionListDetails>
    </template>

    <template v-if="cart.delivery_fee_display">
      <UiDescriptionListTerm>Entrega</UiDescriptionListTerm>
      <UiDescriptionListDetails class="tabular-nums sm:text-right">{{ cart.delivery_fee_display }}</UiDescriptionListDetails>
    </template>

    <UiDescriptionListTerm class="font-semibold text-foreground">Total</UiDescriptionListTerm>
    <UiDescriptionListDetails :class="[compact ? 'text-base' : 'text-xl', 'font-semibold tabular-nums sm:text-right']">
      {{ cart.grand_total_display }}
    </UiDescriptionListDetails>
  </UiDescriptionList>
</template>
