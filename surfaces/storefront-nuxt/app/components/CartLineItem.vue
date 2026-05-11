<script setup lang="ts">
import type { CartItemProjection, ProductCommandMeta } from '~/types/shopman'

const props = defineProps<{ line: CartItemProjection }>()
const emit = defineEmits<{
  acceptAvailable: [CartItemProjection]
  remove: [CartItemProjection]
}>()

const meta = computed<ProductCommandMeta>(() => ({
  sku: props.line.sku,
  name: props.line.name,
  price_q: props.line.unit_price_q,
  price_display: props.line.price_display,
  image_url: props.line.image_url
}))

const showWarning = computed(() => !props.line.is_available && !!props.line.availability_warning)
</script>

<template>
  <UCard
    as="article"
    :ui="{ body: 'p-3 sm:p-4' }"
    :class="[
      showWarning && 'ring-1 ring-warning',
      line.is_ready_for_confirmation && 'ring-1 ring-success'
    ]"
  >
    <div class="grid gap-3">
      <div class="flex gap-3 sm:gap-4">
        <NuxtLink
          :to="`/produto/${line.sku}`"
          class="size-16 sm:size-20 shrink-0 overflow-hidden rounded-md bg-elevated"
          :aria-label="`Ver ${line.name}`"
        >
          <img v-if="line.image_url" :src="line.image_url" :alt="line.name" loading="lazy" class="size-full object-cover">
          <UIcon v-else name="i-lucide-cookie" class="absolute inset-0 m-auto size-6 text-muted" />
        </NuxtLink>

        <div class="flex-1 min-w-0 grid gap-1">
          <div class="flex items-start justify-between gap-3">
            <NuxtLink
              :to="`/produto/${line.sku}`"
              class="text-base font-semibold text-highlighted hover:text-primary leading-snug line-clamp-2"
            >
              {{ line.name }}
            </NuxtLink>
            <strong class="text-base sm:text-lg text-highlighted tabular-nums whitespace-nowrap">
              {{ line.total_display }}
            </strong>
          </div>

          <div class="flex items-baseline gap-2 text-sm text-muted">
            <span v-if="line.original_price_display" class="line-through tabular-nums">
              {{ line.original_price_display }}
            </span>
            <span class="tabular-nums">{{ line.price_display }} cada</span>
          </div>

          <div v-if="line.discount_label" class="mt-1">
            <UBadge color="success" variant="subtle" size="xs">
              <UIcon name="i-lucide-tag" class="size-3" />
              {{ line.discount_label }}
            </UBadge>
          </div>
        </div>
      </div>

      <div class="flex items-center justify-between gap-2 pt-1 border-t border-default">
        <UButton
          color="neutral"
          variant="ghost"
          icon="i-lucide-trash-2"
          size="xs"
          label="Remover"
          @click="emit('remove', line)"
        />
        <ProductStepper
          :meta="meta"
          :can-add="line.is_available"
          :max-qty="line.available_qty"
          size="sm"
        />
      </div>

      <UAlert
        v-if="showWarning"
        icon="i-lucide-triangle-alert"
        color="warning"
        variant="subtle"
        :title="line.availability_warning || 'Estoque limitado'"
        :description="line.available_qty != null && line.available_qty > 0
          ? `Você pediu ${line.qty} e a casa consegue preparar ${line.available_qty}.`
          : 'No momento não conseguimos atender este item.'"
        :ui="{ root: 'p-3' }"
      >
        <template #actions>
          <UButton
            v-if="line.available_qty != null && line.available_qty > 0"
            size="xs"
            color="warning"
            variant="solid"
            :label="`Aceitar ${line.available_qty}`"
            icon="i-lucide-circle-check"
            @click="emit('acceptAvailable', line)"
          />
          <UButton
            size="xs"
            color="neutral"
            variant="outline"
            label="Remover"
            icon="i-lucide-x"
            @click="emit('remove', line)"
          />
        </template>
      </UAlert>

      <PlannedHoldBadge :item="line" />
    </div>
  </UCard>
</template>
