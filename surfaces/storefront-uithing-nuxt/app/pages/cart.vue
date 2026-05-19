<script setup lang="ts">
import type { CartItemProjection, CartResponse, ProductMutationMeta } from '~/types/shopman'

const apiPath = useShopmanApiPath()
const {
  cart,
  cartIssue,
  rateLimitRecovery,
  setFromServer,
  setSkuQty,
  applyCoupon,
  removeCoupon,
  acceptAvailableQty,
  retryLastMutation
} = useCartState()
const { data, pending, error, refresh } = await useFetch<CartResponse>(apiPath('/api/v1/storefront/cart/'), {
  credentials: 'include'
})

watch(() => data.value?.cart, cart => {
  setFromServer(cart)
}, { immediate: true })

const coupon = ref('')
const couponPending = ref(false)
const checkoutAction = computed(() => cart.value.actions.find(action => action.ref === 'checkout') || null)
const continueAction = computed(() => cart.value.actions.find(action => action.ref === 'continue_shopping') || null)
const checkoutTarget = computed(() => localRouteFromBackend(checkoutAction.value?.href || '/checkout'))
const checkoutDisabled = computed(() => !checkoutAction.value?.enabled)
const checkoutReason = computed(() => checkoutAction.value?.reason || '')
const cartIssueQtyAction = computed(() => cartIssue.value?.actions.find(action => action.ref === 'set_available_qty' && action.enabled) || null)
const cartIssueQtyLabel = computed(() => {
  if (cartIssueQtyAction.value?.label) return cartIssueQtyAction.value.label
  const qty = cartIssue.value?.available_qty
  return qty != null ? `Usar ${formatCount(qty, 'unidade disponível', 'unidades disponíveis')}` : ''
})

function metaForLine (line: CartItemProjection): ProductMutationMeta {
  return {
    sku: line.sku,
    name: line.name,
    price_q: line.unit_price_q,
    price_display: line.price_display,
    image_url: line.image_url
  }
}

async function removeLine (line: CartItemProjection) {
  await setSkuQty(metaForLine(line), 0)
}

async function submitCoupon () {
  if (!coupon.value.trim()) return
  couponPending.value = true
  try {
    await applyCoupon(coupon.value.trim())
    coupon.value = ''
  } finally {
    couponPending.value = false
  }
}

useSeoMeta({
  title: 'Carrinho'
})
</script>

<template>
  <main class="shop-section">
    <div class="shop-container space-y-5">
      <UiBreadcrumbs
        :items="[
          { label: 'Início', link: '/' },
          { label: 'Carrinho' }
        ]"
      />

      <div>
        <p class="shop-kicker">Carrinho</p>
        <h1 class="mt-1 text-3xl font-semibold">Seu carrinho</h1>
        <p class="mt-2 shop-muted">
          {{ cart.is_empty ? 'Escolha itens no cardápio para montar o pedido.' : `${formatCount(cart.items_count, 'item', 'itens')} · ${cart.grand_total_display}` }}
        </p>
      </div>

      <UiSkeleton v-if="pending" class="h-72 rounded-lg" />

      <UiAlert v-else-if="error" variant="destructive">
        <UiAlertTitle>Não foi possível carregar o carrinho</UiAlertTitle>
        <UiAlertDescription>
          <UiButton size="sm" variant="outline" @click="refresh">Atualizar</UiButton>
        </UiAlertDescription>
      </UiAlert>

      <template v-else>
        <UiAlert v-if="cartIssue" variant="destructive">
          <UiAlertTitle>{{ cartIssue.title }}</UiAlertTitle>
          <UiAlertDescription>
            <p>{{ cartIssue.detail }}</p>
            <div v-if="cartIssue.substitutes.length" class="mt-3 space-y-2">
              <p class="text-xs font-semibold uppercase tracking-normal text-muted-foreground">Alternativas disponíveis</p>
              <UiItemGroup class="gap-2">
                <UiItem v-for="substitute in cartIssue.substitutes.slice(0, 3)" :key="substitute.sku || substitute.name" variant="outline" size="sm">
                  <UiItemContent>
                    <UiItemTitle>{{ substitute.name || substitute.sku }}</UiItemTitle>
                    <UiItemDescription v-if="substitute.reason">{{ substitute.reason }}</UiItemDescription>
                    <UiItemDescription v-else-if="substitute.available_qty != null">
                      {{ formatCount(substitute.available_qty, 'unidade disponível', 'unidades disponíveis') }}
                    </UiItemDescription>
                  </UiItemContent>
                </UiItem>
              </UiItemGroup>
            </div>
            <div class="mt-3 flex flex-wrap gap-2">
              <UiButton v-if="cartIssue.available_qty != null" size="sm" variant="outline" @click="acceptAvailableQty">
                {{ cartIssueQtyLabel }}
              </UiButton>
              <UiButton size="sm" variant="ghost" @click="retryLastMutation">Tentar novamente</UiButton>
            </div>
          </UiAlertDescription>
        </UiAlert>

        <UiAlert v-if="rateLimitRecovery">
          <UiAlertTitle>Aguarde um instante</UiAlertTitle>
          <UiAlertDescription>{{ rateLimitRecovery.detail }}</UiAlertDescription>
        </UiAlert>

        <UiEmpty v-if="cart.is_empty" class="border">
          <UiEmptyMedia variant="icon">
            <Icon name="lucide:shopping-bag" />
          </UiEmptyMedia>
          <UiEmptyHeader>
            <UiEmptyTitle>Carrinho vazio</UiEmptyTitle>
            <UiEmptyDescription>Escolha um item no cardápio e volte para finalizar por aqui.</UiEmptyDescription>
          </UiEmptyHeader>
          <UiEmptyContent class="flex flex-col items-center gap-2">
            <UiButton :to="localRouteFromBackend(continueAction?.href || '/menu')" icon="lucide:utensils">
              {{ continueAction?.label || 'Ver cardápio' }}
            </UiButton>
            <UiButton
              :to="checkoutTarget"
              variant="outline"
              icon="lucide:clipboard-check"
              :disabled="checkoutDisabled"
            >
              {{ checkoutAction?.label || 'Finalizar pedido' }}
            </UiButton>
            <p v-if="checkoutDisabled && checkoutReason" class="max-w-sm text-center text-xs text-muted-foreground">
              {{ checkoutReason }}
            </p>
          </UiEmptyContent>
        </UiEmpty>

        <div v-else class="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
          <section class="space-y-4">
            <UiAlert v-if="checkoutDisabled && checkoutReason" variant="warning">
              <UiAlertTitle>Antes de finalizar</UiAlertTitle>
              <UiAlertDescription>{{ checkoutReason }}</UiAlertDescription>
            </UiAlert>

            <UiCard class="gap-0 overflow-hidden py-0" data-cart-items-card>
              <UiItem
                v-for="line in cart.items"
                :key="line.line_id"
                class="grid grid-cols-[5rem_minmax(0,1fr)] items-stretch gap-3 rounded-none border-0 border-b bg-card p-3 last:border-b-0 sm:grid-cols-[6rem_minmax(0,1fr)] sm:gap-4 sm:p-4"
                data-cart-line-item
              >
                <UiItemMedia v-if="line.image_url" variant="image" class="size-20 rounded-lg sm:size-24">
                  <img
                    :src="line.image_url"
                    :alt="line.name"
                    loading="lazy"
                    decoding="async"
                  >
                </UiItemMedia>
                <UiItemMedia v-else variant="icon" class="size-20 rounded-lg sm:size-24">
                  <Icon name="lucide:image" />
                </UiItemMedia>

                <UiItemContent class="min-w-0 self-stretch">
                  <div class="flex min-w-0 items-start gap-3">
                    <div class="min-w-0 flex-1">
                      <UiItemTitle class="line-clamp-2 leading-tight">{{ line.name }}</UiItemTitle>
                      <UiItemDescription class="mt-1 space-y-0.5">
                        <span v-if="line.original_price_display" class="block text-xs">
                          <span class="line-through">{{ line.original_price_display }}</span>
                          <span class="ml-1 font-medium text-foreground">{{ line.qty }} × {{ line.price_display }} cada</span>
                        </span>
                        <span v-else class="block text-xs">{{ line.qty }} × {{ line.price_display }} cada</span>
                        <span v-if="line.discount_label" class="block text-xs font-medium text-primary">{{ line.discount_label }}</span>
                        <span v-if="line.availability_warning" class="block text-xs text-destructive">{{ line.availability_warning }}</span>
                      </UiItemDescription>
                    </div>

                    <UiButton
                      variant="ghost"
                      size="icon-sm"
                      icon="lucide:trash-2"
                      class="-mr-1 -mt-1 shrink-0 text-muted-foreground hover:text-destructive"
                      :aria-label="`Remover ${line.name}`"
                      :disabled="cart.summary_pending"
                      @click="removeLine(line)"
                    />
                  </div>

                  <div class="mt-auto flex flex-wrap items-center justify-between gap-3 pt-3">
                    <QuantityControl
                      :meta="metaForLine(line)"
                      :qty="line.qty"
                      :disabled="!line.is_available"
                      :max-qty="line.available_qty"
                      :min-qty="1"
                      compact
                    />
                    <p class="ml-auto text-base font-semibold text-foreground tabular-nums">{{ line.total_display }}</p>
                  </div>
                </UiItemContent>
              </UiItem>
            </UiCard>

            <CartUpsellRail v-if="cart.upsell" :upsell="cart.upsell" heading="Mais um item?" />

            <div v-if="cart.minimum_order_progress" class="rounded-lg border p-4">
              <div class="mb-2 flex justify-between gap-3 text-sm">
                <span>Pedido mínimo</span>
                <span>{{ cart.minimum_order_progress.remaining_display }}</span>
              </div>
              <UiProgress :model-value="cart.minimum_order_progress.percent" />
            </div>

            <UiCard>
              <UiCardHeader>
                <UiCardTitle>Cupom</UiCardTitle>
                <UiCardDescription>Adicione um código antes de finalizar.</UiCardDescription>
              </UiCardHeader>
              <UiCardContent class="space-y-3">
                <form class="flex gap-2" @submit.prevent="submitCoupon">
                  <UiInput v-model="coupon" placeholder="Cupom" autocomplete="off" />
                  <UiButton type="submit" variant="outline" :loading="couponPending">Aplicar</UiButton>
                </form>
                <UiItem v-if="cart.coupon_code" variant="outline" size="sm" class="bg-card">
                  <UiItemMedia variant="icon" class="size-8 rounded-md">
                    <Icon name="lucide:ticket-percent" />
                  </UiItemMedia>
                  <UiItemContent>
                    <UiItemTitle>Cupom {{ cart.coupon_code }}</UiItemTitle>
                    <UiItemDescription>Desconto aplicado no resumo.</UiItemDescription>
                  </UiItemContent>
                  <UiItemActions>
                    <UiButton size="sm" variant="ghost" icon="lucide:x" @click="removeCoupon">
                      Remover
                    </UiButton>
                  </UiItemActions>
                </UiItem>
              </UiCardContent>
            </UiCard>
          </section>

          <aside class="space-y-4 lg:sticky lg:top-24 lg:self-start">
            <UiCard>
              <UiCardHeader>
                <UiCardTitle>Resumo</UiCardTitle>
                <UiCardDescription>{{ formatCount(cart.items_count, 'item', 'itens') }}</UiCardDescription>
              </UiCardHeader>
              <UiCardContent>
                <CartSummaryBreakdown :cart="cart" />
              </UiCardContent>
              <UiCardFooter class="hidden flex-col gap-2 md:flex">
                <UiButton
                  :to="checkoutTarget"
                  class="w-full"
                  size="lg"
                  icon="lucide:clipboard-check"
                  :disabled="checkoutDisabled"
                >
                  {{ checkoutAction?.label || 'Finalizar pedido' }}
                </UiButton>
                <p v-if="checkoutDisabled && checkoutReason" class="text-center text-xs text-muted-foreground">
                  {{ checkoutReason }}
                </p>
                <UiButton
                  v-if="continueAction"
                  :to="localRouteFromBackend(continueAction.href)"
                  variant="outline"
                  class="w-full"
                >
                  {{ continueAction.label }}
                </UiButton>
              </UiCardFooter>
            </UiCard>
          </aside>
        </div>
      </template>

      <div
        v-if="!cart.is_empty"
        class="sticky bottom-20 z-30 rounded-lg border bg-background/95 p-3 shadow-lg backdrop-blur md:hidden"
      >
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p class="text-xs font-medium uppercase text-muted-foreground">Total do pedido</p>
            <p class="text-xl font-semibold tabular-nums">{{ cart.grand_total_display }}</p>
          </div>
          <UiButton
            :to="checkoutTarget"
            size="lg"
            icon="lucide:clipboard-check"
            class="w-full sm:w-auto"
            :disabled="checkoutDisabled"
          >
            {{ checkoutAction?.label || 'Finalizar pedido' }}
          </UiButton>
        </div>
        <p v-if="checkoutDisabled && checkoutReason" class="mt-2 text-center text-xs text-muted-foreground">
          {{ checkoutReason }}
        </p>
      </div>
    </div>
  </main>
</template>
