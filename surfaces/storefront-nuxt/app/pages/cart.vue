<script setup lang="ts">
import type { CartItemProjection, CartProjection, CartResponse, ProductCommandMeta } from '~/types/shopman'

const { cart, setFromServer, setSkuQty } = useCartState()
const apiPath = useShopmanApiPath()
const { data, pending, error, refresh } = await useFetch<CartResponse>(apiPath('/api/v1/storefront/cart/'), {
  credentials: 'include'
})

watchEffect(() => setFromServer(data.value?.cart))

function metaForLine (line: CartItemProjection): ProductCommandMeta {
  return {
    sku: line.sku,
    name: line.name,
    price_q: line.unit_price_q,
    price_display: line.price_display,
    image_url: line.image_url
  }
}

function applyCart (next: CartProjection) {
  setFromServer(next)
}

const isAwaitingPolling = computed(() => cart.value.has_awaiting_confirmation_items)

if (import.meta.client) {
  let pollTimer: ReturnType<typeof setInterval> | null = null

  function startPolling () {
    stopPolling()
    pollTimer = setInterval(() => { refresh() }, 30_000)
  }
  function stopPolling () {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  watch(isAwaitingPolling, (active) => {
    if (active) startPolling()
    else stopPolling()
  }, { immediate: true })

  onBeforeUnmount(stopPolling)
}

const itemsLabel = computed(() => cart.value.items_count === 1 ? '1 item' : `${cart.value.items_count} itens`)

const summaryDescription = computed(() => {
  if (cart.value.is_empty) return 'Nenhum item selecionado'
  return `${itemsLabel.value} · ${cart.value.subtotal_display}`
})

const minimumPending = computed(() => (cart.value.minimum_order_progress?.remaining_q ?? 0) > 0)
const checkoutDisabled = computed(() =>
  cart.value.is_empty ||
  cart.value.has_unavailable_items ||
  minimumPending.value
)

const checkoutLabel = computed(() => {
  if (cart.value.is_empty) return 'Carrinho vazio'
  if (cart.value.has_unavailable_items) return 'Revise os itens'
  if (minimumPending.value) {
    return `Faltam ${cart.value.minimum_order_progress?.remaining_display}`
  }
  if (cart.value.has_ready_for_confirmation_items) return 'Confirmar agora · tudo pronto'
  return 'Finalizar pedido'
})

const checkoutColor = computed(() => cart.value.has_ready_for_confirmation_items ? 'success' as const : 'primary' as const)

async function acceptAvailable (line: CartItemProjection) {
  if (line.available_qty == null) return
  await setSkuQty(metaForLine(line), line.available_qty).catch(() => {})
}

async function removeLine (line: CartItemProjection) {
  await setSkuQty(metaForLine(line), 0).catch(() => {})
}

useHead({ title: 'Seu carrinho' })
</script>

<template>
  <UContainer class="py-6 sm:py-10">
    <USkeleton v-if="pending" class="h-40 w-full" />

    <UAlert v-else-if="error" color="error" variant="soft" title="Não foi possível carregar o carrinho" />

    <div v-else>
      <UPageHeader title="Seu carrinho" :description="summaryDescription">
        <template #links>
          <UButton label="Continuar comprando" to="/menu" icon="i-lucide-arrow-left" color="neutral" variant="ghost" />
        </template>
      </UPageHeader>

      <UEmpty
        v-if="cart.is_empty"
        icon="i-lucide-bread"
        title="Carrinho vazio, mas o forno tá quentinho"
        description="Escolha o que apetece e a casa prepara pra você. Tem fornada saindo agora."
        :actions="[{ label: 'Ver cardápio', to: '/menu', icon: 'i-lucide-utensils' }]"
        class="mt-12"
      />

      <div v-else class="mt-6 grid lg:grid-cols-[1fr_380px] gap-6 items-start">
        <div class="grid gap-3">
          <UAlert
            v-if="cart.has_unavailable_items"
            icon="i-lucide-triangle-alert"
            color="warning"
            variant="subtle"
            title="Itens com estoque limitado"
            description="Ajustamos o que dá pra entregar. Revise abaixo antes de finalizar."
          />

          <UCard v-if="cart.minimum_order_progress?.remaining_q && cart.minimum_order_progress.remaining_q > 0" :ui="{ body: 'p-4' }">
            <div class="grid gap-3">
              <div class="flex items-center justify-between text-sm">
                <span class="font-medium flex items-center gap-2">
                  <UIcon name="i-lucide-target" class="size-4 text-primary" />
                  Pedido mínimo
                </span>
                <span class="text-muted tabular-nums">
                  {{ cart.subtotal_display }} / {{ cart.minimum_order_progress.minimum_display }}
                </span>
              </div>
              <UProgress :model-value="cart.minimum_order_progress.percent" />
              <p class="text-sm text-muted">
                Faltam <strong class="text-highlighted">{{ cart.minimum_order_progress.remaining_display }}</strong>
                para o pedido mínimo de <strong class="text-highlighted">{{ cart.minimum_order_progress.minimum_display }}</strong>.
              </p>
            </div>
          </UCard>

          <CartLineItem
            v-for="line in cart.items"
            :key="line.sku"
            :line="line"
            @accept-available="acceptAvailable"
            @remove="removeLine"
          />

          <UCard
            v-if="cart.upsell"
            :ui="{ body: 'p-4 sm:p-5' }"
            class="border-dashed"
          >
            <div class="flex items-center gap-4">
              <NuxtLink
                :to="`/produto/${cart.upsell.sku}`"
                class="size-16 shrink-0 overflow-hidden rounded-md bg-elevated"
              >
                <img v-if="cart.upsell.image_url" :src="cart.upsell.image_url" :alt="cart.upsell.name" class="size-full object-cover">
                <UIcon v-else name="i-lucide-cookie" class="absolute inset-0 m-auto size-6 text-muted" />
              </NuxtLink>
              <div class="flex-1 min-w-0">
                <p class="text-xs uppercase tracking-wide text-primary font-semibold">Que tal adicionar?</p>
                <NuxtLink :to="`/produto/${cart.upsell.sku}`" class="font-semibold text-highlighted hover:text-primary truncate block">
                  {{ cart.upsell.name }}
                </NuxtLink>
                <span class="text-sm text-muted tabular-nums">{{ cart.upsell.price_display }}</span>
              </div>
              <UButton
                :to="`/produto/${cart.upsell.sku}`"
                size="sm"
                color="neutral"
                variant="outline"
                icon="i-lucide-plus"
                label="Ver"
              />
            </div>
          </UCard>
        </div>

        <div class="grid gap-3 lg:sticky lg:top-[calc(var(--ui-header-height)+24px)]">
          <UCard variant="subtle">
            <template #header>
              <div class="flex items-center justify-between">
                <strong>Resumo do pedido</strong>
                <UBadge color="neutral" variant="subtle">
                  {{ itemsLabel }}
                </UBadge>
              </div>
            </template>

            <div class="grid gap-2.5">
              <div class="flex justify-between text-sm">
                <span class="text-muted">Subtotal</span>
                <span class="tabular-nums">
                  <span v-if="cart.has_discount" class="text-muted line-through mr-2">{{ cart.original_subtotal_display }}</span>
                  <span class="text-highlighted">{{ cart.subtotal_display }}</span>
                </span>
              </div>

              <div
                v-for="discount in cart.discount_lines"
                :key="discount.label"
                class="flex justify-between text-sm text-success"
              >
                <span class="flex items-center gap-1.5">
                  <UIcon name="i-lucide-tag" class="size-3.5" />
                  {{ discount.label }}
                </span>
                <span class="tabular-nums">−{{ discount.amount_display }}</span>
              </div>

              <div v-if="cart.delivery_fee_display" class="flex justify-between text-sm">
                <span class="text-muted">Entrega</span>
                <span class="tabular-nums">
                  <span v-if="cart.delivery_is_free" class="text-success">Grátis</span>
                  <template v-else>{{ cart.delivery_fee_display }}</template>
                </span>
              </div>
            </div>

            <USeparator class="my-3" />

            <div class="flex justify-between items-baseline">
              <span class="font-medium">Total</span>
              <strong class="text-2xl tabular-nums text-highlighted">{{ cart.grand_total_display }}</strong>
            </div>

            <template #footer>
              <UButton
                v-if="!minimumPending"
                to="/checkout"
                block
                icon="i-lucide-arrow-right"
                trailing
                :label="checkoutLabel"
                :color="checkoutColor"
                :disabled="checkoutDisabled"
                size="lg"
              />
              <UButton
                v-else
                block
                disabled
                :label="checkoutLabel"
                color="neutral"
                variant="soft"
                icon="i-lucide-lock"
                size="lg"
              />
              <UButton
                to="/menu"
                block
                color="neutral"
                variant="ghost"
                size="sm"
                label="Continuar comprando"
                icon="i-lucide-arrow-left"
                class="mt-2"
              />
            </template>
          </UCard>

          <CartCouponSection :cart="cart" @updated="applyCart" />
        </div>
      </div>
    </div>
  </UContainer>
</template>
