<script setup lang="ts">
import type { CartItemProjection, CartProjection, CartResponse, ProductMutationMeta } from '~/types/shopman'

const { cart, setFromServer, setSkuQty } = useCartState()
const apiPath = useShopmanApiPath()
const { data, pending, error, refresh } = await useFetch<CartResponse>(apiPath('/api/v1/storefront/cart/'), {
  credentials: 'include'
})

watchEffect(() => setFromServer(data.value?.cart))

function metaForLine (line: CartItemProjection): ProductMutationMeta {
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
  if (cart.value.summary_pending) return `${itemsLabel.value} · atualizando totais`
  return `${itemsLabel.value} · ${cart.value.subtotal_display}`
})

const minimumPending = computed(() => (cart.value.minimum_order_progress?.remaining_q ?? 0) > 0)
const checkoutDisabled = computed(() =>
  cart.value.is_empty ||
  !!cart.value.summary_pending ||
  cart.value.has_unavailable_items ||
  minimumPending.value
)

const checkoutLabel = computed(() => {
  if (cart.value.is_empty) return 'Carrinho vazio'
  if (cart.value.summary_pending) return 'Atualizando carrinho'
  if (cart.value.has_unavailable_items) return 'Revise os itens'
  if (minimumPending.value) {
    return `Faltam ${cart.value.minimum_order_progress?.remaining_display}`
  }
  if (cart.value.has_ready_for_confirmation_items) return 'Confirmar pedido'
  return 'Finalizar pedido'
})

const checkoutColor = computed(() => cart.value.has_ready_for_confirmation_items ? 'success' as const : 'primary' as const)
const upsellMeta = computed<ProductMutationMeta | null>(() => {
  const upsell = cart.value.upsell
  if (!upsell) return null
  return {
    sku: upsell.sku,
    name: upsell.name,
    price_q: upsell.unit_price_q,
    price_display: upsell.price_display,
    image_url: upsell.image_url
  }
})
const releaseCandidate = ref<CartItemProjection | null>(null)
const releaseModalOpen = computed({
  get: () => !!releaseCandidate.value,
  set: (value) => {
    if (!value) releaseCandidate.value = null
  }
})

async function acceptAvailable (line: CartItemProjection) {
  if (line.available_qty == null) return
  await setSkuQty(metaForLine(line), line.available_qty).catch(() => {})
}

function needsReleaseConfirmation (line: CartItemProjection) {
  return line.is_awaiting_confirmation || line.is_ready_for_confirmation
}

async function removeLine (line: CartItemProjection) {
  if (needsReleaseConfirmation(line)) {
    releaseCandidate.value = line
    return
  }
  await setSkuQty(metaForLine(line), 0).catch(() => {})
}

async function confirmReleaseReservation () {
  const line = releaseCandidate.value
  if (!line) return
  releaseCandidate.value = null
  await setSkuQty(metaForLine(line), 0).catch(() => {})
}

useHead({ title: 'Seu carrinho' })
</script>

<template>
  <UContainer class="py-6 sm:py-10">
    <USkeleton v-if="pending" class="h-40 w-full" />

    <UAlert
      v-else-if="error"
      color="error"
      variant="soft"
      :title="operationalCopy.loadFailure.cart.title"
      :description="operationalCopy.loadFailure.cart.description"
    />

    <div v-else>
      <section class="shop-soft-panel rounded-lg p-4 sm:p-6">
        <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p class="shop-section-kicker">
              Carrinho
            </p>
            <h1 class="mt-2 text-3xl font-bold leading-tight text-highlighted sm:text-4xl">Seu pedido</h1>
            <p class="mt-2 text-sm leading-relaxed text-muted sm:text-base">{{ summaryDescription }}</p>
          </div>
          <UButton label="Continuar comprando" to="/menu" color="neutral" variant="outline" size="lg" class="self-start" />
        </div>
      </section>

      <div
        v-if="cart.is_empty"
        class="mt-12 rounded-lg border border-default bg-default p-8 text-center"
      >
        <h2 class="text-lg font-semibold text-highlighted">Carrinho vazio</h2>
        <p class="mx-auto mt-2 max-w-[18rem] text-sm leading-relaxed text-muted">
          Adicione itens para iniciar.
        </p>
        <UButton to="/menu" label="Ver cardápio" class="mt-5" />
      </div>

      <div v-else class="mt-6 grid lg:grid-cols-[1fr_380px] gap-6 items-start">
        <div class="grid gap-3">
          <UAlert
            v-if="cart.summary_pending"
            color="neutral"
            variant="subtle"
            title="Atualizando o carrinho"
            description="Estamos recalculando totais, cupom, entrega e pedido mínimo."
          />

          <UAlert
            v-if="cart.has_unavailable_items"
            color="warning"
            variant="subtle"
            title="Itens com estoque limitado"
            description="Alguns itens mudaram de disponibilidade. Revise antes de finalizar."
          />

          <UCard v-if="cart.minimum_order_progress?.remaining_q && cart.minimum_order_progress.remaining_q > 0" :ui="{ body: 'p-4' }">
            <div class="grid gap-3">
              <div class="flex items-center justify-between text-sm">
                <span class="font-medium">
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
            :ui="{ body: 'p-0 sm:p-0' }"
            class="overflow-hidden border border-primary/30 bg-primary/5 ring-1 ring-primary/10"
          >
            <div class="grid grid-cols-[96px_minmax(0,1fr)] sm:grid-cols-[120px_minmax(0,1fr)]">
              <div
                class="relative m-3 size-[72px] overflow-hidden rounded-md bg-elevated sm:m-4 sm:size-[88px]"
              >
                <img
                  v-if="cart.upsell.image_url"
                  :src="cart.upsell.image_url"
                  :alt="cart.upsell.name"
                  loading="lazy"
                  decoding="async"
                  sizes="80px"
                  class="size-full object-cover"
                >
                <UIcon v-else name="i-lucide-image" class="absolute inset-0 m-auto size-6 text-muted" />
              </div>
              <div class="min-w-0 p-4 sm:p-5">
                <p class="text-xs uppercase text-primary font-semibold">Sugestão</p>
                <p class="font-semibold text-highlighted truncate">
                  {{ cart.upsell.name }}
                </p>
                <span class="text-sm text-muted tabular-nums">{{ cart.upsell.price_display }}</span>
                <div class="mt-3 flex justify-end">
                  <ProductStepper
                    v-if="upsellMeta"
                    :meta="upsellMeta"
                    :can-add="true"
                    size="sm"
                    add-label="Adicionar"
                  />
                </div>
              </div>
            </div>
          </UCard>
        </div>

        <div class="grid gap-3 lg:sticky lg:top-[calc(var(--ui-header-height)+24px)]">
          <UCard variant="subtle" class="shop-soft-panel">
            <template #header>
              <div class="flex items-center justify-between">
                <strong>Resumo do pedido</strong>
                <div class="flex items-center gap-2">
                  <UBadge v-if="cart.summary_pending" color="neutral" variant="soft">
                    Atualizando
                  </UBadge>
                  <UBadge color="neutral" variant="subtle">
                    {{ itemsLabel }}
                  </UBadge>
                </div>
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
                <span>
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

            <UProgress v-if="cart.summary_pending" animation="carousel" class="mt-3" />

            <USeparator class="my-3" />

            <div class="flex justify-between items-baseline">
              <span class="font-medium">Total</span>
              <strong
                class="text-2xl tabular-nums text-highlighted"
                :class="cart.summary_pending && 'opacity-70'"
              >
                {{ cart.grand_total_display }}
              </strong>
            </div>

            <template #footer>
              <UButton
                v-if="!minimumPending"
                to="/checkout"
                block
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
                size="lg"
              />
              <UButton
                to="/menu"
                block
                color="neutral"
                variant="ghost"
                size="lg"
                label="Continuar comprando"
                class="mt-2"
              />
            </template>
          </UCard>

          <CartCouponSection :cart="cart" @updated="applyCart" />

          <div class="rounded-lg border border-default bg-elevated/45 p-4">
            <p class="text-sm font-semibold text-highlighted">Antes de finalizar</p>
            <p class="mt-1 text-sm leading-relaxed text-muted">
              Itens indisponíveis, pedido mínimo e confirmação operacional são revisados antes do envio.
            </p>
          </div>
        </div>
      </div>

      <UModal
        v-model:open="releaseModalOpen"
        title="Liberar reserva?"
        :ui="{ content: 'max-w-md' }"
      >
        <template #body>
          <div class="grid gap-4">
            <p class="text-sm leading-relaxed text-muted">
              Esta ação remove <strong class="text-highlighted">{{ releaseCandidate?.name }}</strong> do carrinho e libera a reserva para outros pedidos.
            </p>
            <UAlert
              v-if="releaseCandidate?.confirmation_deadline_display"
              color="warning"
              variant="subtle"
              :title="`Reserva ativa até ${releaseCandidate.confirmation_deadline_display}`"
              description="Se quiser manter este item, volte e conclua o pedido."
            />
            <div class="grid gap-2 sm:grid-cols-2">
              <UButton
                color="neutral"
                variant="outline"
                block
                label="Manter item"
                @click="releaseCandidate = null"
              />
              <UButton
                color="warning"
                variant="solid"
                block
                label="Liberar reserva"
                @click="confirmReleaseReservation"
              />
            </div>
          </div>
        </template>
      </UModal>
    </div>
  </UContainer>
</template>
