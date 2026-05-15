<script setup lang="ts">
import type { CartItemProjection, ProductCommandMeta } from '~/types/shopman'

const props = defineProps<{ line: CartItemProjection }>()
const emit = defineEmits<{
  acceptAvailable: [CartItemProjection]
  remove: [CartItemProjection]
}>()

const { isPending } = useCartState()

const meta = computed<ProductCommandMeta>(() => ({
  sku: props.line.sku,
  name: props.line.name,
  price_q: props.line.unit_price_q,
  price_display: props.line.price_display,
  image_url: props.line.image_url
}))

const showWarning = computed(() => !props.line.is_available && !!props.line.availability_warning)
const pending = computed(() => isPending(props.line.sku))
const removeLabel = computed(() => props.line.is_awaiting_confirmation || props.line.is_ready_for_confirmation
  ? 'Liberar reserva'
  : 'Remover')
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
      <div class="grid grid-cols-[72px_minmax(0,1fr)] gap-3 sm:grid-cols-[88px_minmax(0,1fr)] sm:gap-4">
        <NuxtLink
          :to="`/produto/${line.sku}`"
          class="row-span-2 size-[72px] overflow-hidden rounded-md bg-elevated sm:size-[88px]"
          :aria-label="`Ver ${line.name}`"
        >
          <img v-if="line.image_url" :src="line.image_url" :alt="line.name" loading="lazy" decoding="async" sizes="80px" class="size-full object-cover">
          <span v-else class="grid size-full place-items-center text-xs font-semibold text-muted">
            {{ line.name.slice(0, 2).toUpperCase() }}
          </span>
        </NuxtLink>

        <div class="flex min-w-0 items-start justify-between gap-3">
          <NuxtLink
            :to="`/produto/${line.sku}`"
            class="line-clamp-2 text-sm font-semibold leading-snug text-highlighted hover:text-primary sm:text-base"
          >
            {{ line.name }}
          </NuxtLink>
          <UButton
            color="neutral"
            variant="ghost"
            icon="i-lucide-trash-2"
            size="xs"
            :aria-label="`${removeLabel} ${line.name}`"
            :loading="pending"
            :disabled="pending"
            data-haptic="double"
            @click="emit('remove', line)"
          />
        </div>

        <div class="flex min-w-0 items-end justify-between gap-3">
          <div class="min-w-0 text-xs text-muted sm:text-sm">
            <p class="whitespace-nowrap">
              <span v-if="line.original_price_display" class="mr-2 line-through tabular-nums">
                {{ line.original_price_display }}
              </span>
              <span class="tabular-nums">{{ line.qty }} x {{ line.price_display }} · {{ line.total_display }}</span>
            </p>
            <UBadge v-if="line.discount_label" color="success" variant="subtle" size="xs" class="mt-1 max-w-full">
              <span class="truncate">{{ line.discount_label }}</span>
            </UBadge>
          </div>
          <ProductStepper
            :meta="meta"
            :can-add="line.is_available"
            :max-qty="line.available_qty"
            size="xs"
          />
        </div>
      </div>

      <UAlert
        v-if="showWarning"
        color="warning"
        variant="subtle"
        :title="line.availability_warning || 'Estoque limitado'"
        :description="line.available_qty != null && line.available_qty > 0
          ? `Disponível para este pedido: ${line.available_qty}.`
          : 'Item indisponível para este pedido.'"
        :ui="{ root: 'p-3' }"
      >
        <template #actions>
          <UButton
            v-if="line.available_qty != null && line.available_qty > 0"
            size="xs"
            color="warning"
            variant="solid"
            :label="`Aceitar ${line.available_qty}`"
            data-haptic="light"
            @click="emit('acceptAvailable', line)"
          />
          <UButton
            size="xs"
            color="neutral"
            variant="outline"
            :label="removeLabel"
            :loading="pending"
            :disabled="pending"
            data-haptic="double"
            @click="emit('remove', line)"
          />
        </template>
      </UAlert>

      <PlannedHoldBadge :item="line" />
    </div>
  </UCard>
</template>
