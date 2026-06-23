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
    <UiDescriptionListDetails class="tabular-nums sm:text-right">
      {{ cart.has_discount ? (cart.original_subtotal_display || cart.subtotal_display) : cart.subtotal_display }}
    </UiDescriptionListDetails>

    <template v-for="discount in cart.discount_lines" :key="discount.label">
      <UiDescriptionListTerm>{{ discount.label }}</UiDescriptionListTerm>
      <UiDescriptionListDetails class="tabular-nums text-primary sm:text-right">
        {{ discountDisplay(discount.amount_display) }}
      </UiDescriptionListDetails>
    </template>

    <template v-if="cart.delivery_fee_display">
      <UiDescriptionListTerm>
        Entrega<span v-if="cart.delivery_distance_display" class="shop-muted font-normal"> · {{ cart.delivery_distance_display }}</span>
      </UiDescriptionListTerm>
      <UiDescriptionListDetails class="tabular-nums sm:text-right">{{ cart.delivery_fee_display }}</UiDescriptionListDetails>
    </template>

    <UiDescriptionListTerm class="font-semibold text-foreground">Total</UiDescriptionListTerm>
    <UiDescriptionListDetails :class="[compact ? 'text-base' : 'text-xl', 'font-semibold tabular-nums sm:text-right']">
      {{ cart.grand_total_display }}
    </UiDescriptionListDetails>
  </UiDescriptionList>
</template>
